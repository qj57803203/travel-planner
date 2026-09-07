"""Chrome CDP 管理器 — 直接通过 WebSocket 协议连接 Docker 内常驻 Chrome。

设计目标：
- 去掉 MCP 中间层，直接用 CDP WebSocket 协议控制 Chrome
- 供小红书浏览器爬虫和携程酒店爬虫共用
- 进程级串行锁：多个 Page 同时连同一个 Chrome 会搞死 CDP 会话
- 三层自愈：超时 → 重连 → 杀 Chrome 重启

部署方式：后端通过 network_mode 共享 Chrome 容器的网络命名空间，
直连 localhost:9223（Chrome 只绑定 127.0.0.1）。

用法：
    async with get_chrome_page() as page:
        await page.goto("https://example.com")
        content = await page.content()
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import urllib.request
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from app.config import settings

logger = logging.getLogger(__name__)

# 进程级串行锁：同一时刻只允许一个操作控制 Chrome
_CHROME_LOCK = threading.Lock()


# ============================================================
# CDP WebSocket 连接
# ============================================================

class CDPPage:
    """轻量 CDP Page 封装，通过 WebSocket 直接发送 CDP 命令。

    只实现项目需要的方法：goto / evaluate / content / wait_for_selector。
    """

    def __init__(self, ws, target_id: str):
        self._ws = ws
        self._target_id = target_id
        self._msg_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._events: asyncio.Queue = asyncio.Queue()
        self._listen_task: asyncio.Task | None = None

    async def _start_listening(self):
        """后台监听 WebSocket 消息。"""
        try:
            async for raw in self._ws:
                data = json.loads(raw)
                if "id" in data:
                    fut = self._pending.pop(data["id"], None)
                    if fut and not fut.done():
                        fut.set_result(data)
                else:
                    await self._events.put(data)
        except Exception:
            pass

    async def _send(self, method: str, params: dict | None = None) -> dict:
        """发送 CDP 命令并等待响应。"""
        self._msg_id += 1
        msg = {"id": self._msg_id, "method": method, "params": params or {}}
        fut = asyncio.get_event_loop().create_future()
        self._pending[self._msg_id] = fut
        await self._ws.send(json.dumps(msg))
        result = await asyncio.wait_for(fut, timeout=30)
        if "error" in result:
            raise RuntimeError(f"CDP error: {result['error']}")
        return result.get("result", {})

    async def goto(self, url: str, wait_until: str = "load", timeout: float = 30000):
        """导航到 URL。"""
        # Page.enable 可能超时，添加重试逻辑
        for attempt in range(3):
            try:
                await self._send("Page.enable")
                break
            except Exception as e:
                if attempt == 2:
                    raise
                logger.warning("Page.enable 失败（第%d次）：%s: %s", attempt + 1, type(e).__name__, e)
                await asyncio.sleep(1)

        await self._send("Page.navigate", {"url": url})
        # 等待页面加载
        deadline = asyncio.get_event_loop().time() + timeout / 1000
        while asyncio.get_event_loop().time() < deadline:
            try:
                result = await self._send("Runtime.evaluate", {
                    "expression": "document.readyState",
                    "returnByValue": True,
                })
                state = result.get("result", {}).get("value", "")
                if wait_until == "domcontentloaded" and state in ("interactive", "complete"):
                    return
                if wait_until == "load" and state == "complete":
                    return
            except Exception:
                pass
            await asyncio.sleep(0.5)

    async def evaluate(self, expression: str):
        """执行 JavaScript 并返回结果。"""
        # 包装成 IIFE 如果是函数声明
        expr = expression.strip()
        if expr.startswith("async ()") or expr.startswith("()") or expr.startswith("function"):
            expr = f"({expr})()"

        result = await self._send("Runtime.evaluate", {
            "expression": expr,
            "returnByValue": True,
            "awaitPromise": True,
        })
        remote_obj = result.get("result", {})
        if remote_obj.get("subtype") == "error":
            raise RuntimeError(f"JS error: {remote_obj.get('description', 'unknown')}")
        return remote_obj.get("value")

    async def content(self) -> str:
        """获取页面 HTML 内容。"""
        result = await self._send("Runtime.evaluate", {
            "expression": "document.documentElement.outerHTML",
            "returnByValue": True,
        })
        return result.get("result", {}).get("value", "")

    async def inner_text(self, selector: str = "body") -> str:
        """获取元素的文本内容。"""
        result = await self._send("Runtime.evaluate", {
            "expression": f"document.querySelector('{selector}')?.innerText || ''",
            "returnByValue": True,
        })
        return result.get("result", {}).get("value", "")

    async def query_selector_all(self, selector: str) -> list:
        """查询所有匹配元素，返回 CDP Node 列表。"""
        result = await self._send("Runtime.evaluate", {
            "expression": f"document.querySelectorAll('{selector}').length",
            "returnByValue": True,
        })
        count = result.get("result", {}).get("value", 0)
        nodes = []
        for i in range(count):
            nodes.append(CDPElement(self, selector, i))
        return nodes

    async def screenshot(self, path: str = None, quality: int = 60) -> str:
        """截图并返回 base64 编码的图片数据。

        Args:
            path: 保存路径（可选），如 /tmp/xhs_login.jpg
            quality: JPEG 质量（1-100），默认 60

        Returns:
            base64 编码的图片数据
        """
        result = await self._send("Page.captureScreenshot", {
            "format": "jpeg",
            "quality": quality,
        })
        import base64
        data = result.get("data", "")
        if path and data:
            with open(path, "wb") as f:
                f.write(base64.b64decode(data))
        return data

    async def close(self):
        """关闭页面。"""
        if self._listen_task:
            self._listen_task.cancel()
        try:
            await self._send("Page.close")
        except Exception:
            pass


class CDPElement:
    """CDP 元素封装，通过 JS 选择器定位。"""

    def __init__(self, page: CDPPage, selector: str, index: int):
        self._page = page
        self._selector = selector
        self._index = index
        self._expr = f"document.querySelectorAll('{selector}')[{index}]"

    async def get_attribute(self, name: str) -> str | None:
        result = await self._page._send("Runtime.evaluate", {
            "expression": f"{self._expr}?.getAttribute('{name}')",
            "returnByValue": True,
        })
        return result.get("result", {}).get("value")

    async def inner_text(self) -> str:
        result = await self._page._send("Runtime.evaluate", {
            "expression": f"{self._expr}?.innerText || ''",
            "returnByValue": True,
        })
        return result.get("result", {}).get("value", "")

    async def query_selector(self, selector: str) -> "CDPElement | None":
        """在当前元素内查询子元素。"""
        result = await self._page._send("Runtime.evaluate", {
            "expression": f"!!({self._expr}?.querySelector('{selector}'))",
            "returnByValue": True,
        })
        if result.get("result", {}).get("value"):
            return CDPChildElement(self._page, self._expr, selector)
        return None


class CDPChildElement(CDPElement):
    """CDP 子元素封装。"""

    def __init__(self, page: CDPPage, parent_expr: str, selector: str):
        self._page = page
        self._selector = selector
        self._index = 0
        self._expr = f"({parent_expr})?.querySelector('{selector}')"


# ============================================================
# Chrome 连接管理
# ============================================================

_ws_connection = None
_listen_task = None


def _get_ws_url() -> str:
    """从 Chrome CDP /json/version 获取 WebSocket URL。

    后端通过 network_mode 共享 Chrome 容器网络，直连 localhost:9223。
    注意：这是同步函数（urllib 是同步的），不要加 async。
    """
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(f"{settings.chrome_debug_url}/json/version")
    with opener.open(req, timeout=5) as resp:
        data = json.loads(resp.read().decode())
    ws_url = data.get("webSocketDebuggerUrl", "")
    if not ws_url:
        raise RuntimeError("Chrome /json/version 未返回 webSocketDebuggerUrl")
    logger.info("Chrome WebSocket URL: %s", ws_url)
    return ws_url


def _ensure_tab_via_http() -> None:
    """确保调试 Chrome 至少有一个标签页。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"{settings.chrome_debug_url}/json/list", timeout=5) as resp:
            targets = json.loads(resp.read().decode())
        if any(t.get("type") == "page" for t in targets):
            return
        req = urllib.request.Request(
            f"{settings.chrome_debug_url}/json/new?about:blank", method="PUT"
        )
        opener.open(req, timeout=5).read()
    except Exception:
        pass


async def _connect_websocket(ws_url: str):
    """建立 WebSocket 连接。"""
    import websockets
    return await websockets.connect(ws_url, max_size=50 * 1024 * 1024)


def _get_targets() -> list[dict]:
    """获取 Chrome 所有 target。注意：同步函数。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f"{settings.chrome_debug_url}/json/list", timeout=5) as resp:
        return json.loads(resp.read().decode())


async def _restart_chrome() -> None:
    """杀掉僵死的 Chrome，交给 Docker（restart: unless-stopped）拉起全新实例。"""
    import subprocess
    from urllib.parse import urlparse

    port = urlparse(settings.chrome_debug_url).port or 9222
    logger.warning("Chrome 僵死，尝试杀掉进程（端口 %s）", port)
    try:
        await asyncio.to_thread(
            subprocess.run,
            ["pkill", "-f", f"remote-debugging-port={port}"],
            timeout=10,
        )
    except Exception:
        pass
    await asyncio.sleep(6)


@asynccontextmanager
async def get_chrome_page(
    timeout_s: float = 60,
    retries: int = 2,
) -> AsyncGenerator[CDPPage, None]:
    """获取一个可用的 CDP Page（async context manager）。

    用法：
        async with get_chrome_page() as page:
            await page.goto("https://example.com")
            content = await page.evaluate("document.title")
    """
    # 带超时的锁获取，避免无限等待
    import concurrent.futures
    lock_acquired = await asyncio.wait_for(
        asyncio.to_thread(_CHROME_LOCK.acquire),
        timeout=timeout_s
    )
    if not lock_acquired:
        raise TimeoutError(f"获取 Chrome 锁超时（>{timeout_s}s）")
    try:
        page = await _create_page_with_retry(retries)
        yield page
    finally:
        _CHROME_LOCK.release()


async def _create_page_with_retry(retries: int) -> CDPPage:
    """创建 CDP Page，带重试和自愈。"""
    last_err = None
    for attempt in range(retries + 1):
        try:
            # 1. 确保有标签页
            _ensure_tab_via_http()

            # 2. 获取 WebSocket URL
            ws_url = _get_ws_url()

            # 3. 获取现有标签页
            targets = _get_targets()
            page_targets = [t for t in targets if t.get("type") == "page"]
            if not page_targets:
                raise RuntimeError("Chrome 无可用标签页")

            target_id = page_targets[0]["id"]
            target_ws_url = page_targets[0].get("webSocketDebuggerUrl", ws_url)

            # 4. 连接 WebSocket
            ws = await _connect_websocket(target_ws_url)
            page = CDPPage(ws, target_id)
            page._listen_task = asyncio.create_task(page._start_listening())
            logger.info("CDP Page 创建成功（target=%s）", target_id[:12])
            return page

        except Exception as e:
            last_err = e
            logger.warning("创建 CDP Page 失败（第 %d 次）：%s", attempt + 1, e)
            if attempt < retries:
                if attempt >= 1 and settings.remote_browser:
                    await _restart_chrome()
                await asyncio.sleep(2 * (attempt + 1))

    raise RuntimeError(f"无法创建 CDP Page（重试 {retries} 次）: {last_err}")


async def close() -> None:
    """关闭连接（CDP 无持久连接，此方法为空操作）。"""
    pass
