"""chrome-devtools-mcp 客户端封装（参考 tongyou-travel-agent 项目）。

两种运行模式（由 chrome_executable 配置决定）：
- 服务器部署（无 chrome_executable）：连接 Docker 内常驻 headless Chrome（--browser-url）
- 本地开发（有 chrome_executable）：让 MCP 自己拉起 headless 浏览器

设计要点（踩坑经验）：
- 全局串行锁：多个 MCP 客户端同时连同一个 Chrome 会互相搞死 CDP 会话
- 启动前确保标签页：Chrome 无标签页时所有 MCP 工具报 "No page selected"
- 三层自愈：45s 超时 → 重建 MCP 会话 → 杀 Chrome 重启
"""

import asyncio
import json
import logging
import threading
import urllib.request
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import settings

logger = logging.getLogger(__name__)


class MCPConnectionError(Exception):
    pass


# 进程级串行锁：多个 chrome-devtools-mcp 客户端同时连同一个常驻 Chrome 会互相
# 搞死对方的 CDP 会话（navigate 永久无响应）。任一时刻只允许一个 MCP 会话存在。
# 用 threading.Lock 而非 asyncio.Lock：每个后台任务跑在自己线程的独立事件循环里。
_MCP_GLOBAL_LOCK = threading.Lock()


class ChromeMCP:
    """chrome-devtools-mcp 会话封装。用法：

    async with ChromeMCP() as chrome:
        await chrome.call("navigate_page", {"url": "https://example.com"})
        snapshot = await chrome.call("take_snapshot", {})
    """

    def __init__(self, browser_url: str | None = None):
        self.browser_url = browser_url or settings.chrome_debug_url
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._holds_lock = False

    async def __aenter__(self) -> "ChromeMCP":
        # 全局串行：等上一个 MCP 会话彻底结束（在线程池里阻塞等待，不卡事件循环）
        await asyncio.to_thread(_MCP_GLOBAL_LOCK.acquire)
        self._holds_lock = True
        try:
            await self.connect()
        except BaseException:
            self._release_slot()
            raise
        return self

    async def __aexit__(self, *exc):
        try:
            await self.close()
        finally:
            self._release_slot()

    def _release_slot(self) -> None:
        if self._holds_lock:
            self._holds_lock = False
            _MCP_GLOBAL_LOCK.release()

    async def connect(self, retries: int = 2) -> None:
        """连接 chrome-devtools-mcp（stdio 模式）。

        两种模式：
        - chrome_executable 指定时：让 mcp 自己拉起 headless 浏览器（本地开发）
        - 否则：连现成调试 Chrome（服务器部署，Docker 内常驻 Chrome）
        """
        args = ["-y", "chrome-devtools-mcp@0.6.0"]
        if settings.chrome_executable:
            args += [
                "--headless=true",
                "--executablePath",
                settings.chrome_executable,
            ]
        else:
            args += ["--browser-url", self.browser_url]
        params = StdioServerParameters(command="npx", args=args)

        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                if not settings.chrome_executable:
                    # 必须在 MCP 启动前确保浏览器有标签页：连接后再建 MCP 感知不到
                    await asyncio.to_thread(self._ensure_tab_via_http)
                self._stack = AsyncExitStack()
                read, write = await self._stack.enter_async_context(stdio_client(params))
                self._session = await self._stack.enter_async_context(ClientSession(read, write))
                await asyncio.wait_for(self._session.initialize(), timeout=30)
                return
            except Exception as e:  # noqa: BLE001
                last_err = e
                await self.close()
                if attempt < retries:
                    await asyncio.sleep(2 * (attempt + 1))
        raise MCPConnectionError(
            f"无法连接 chrome-devtools-mcp（browser_url={self.browser_url}）。"
            f"请确认已启动带 --remote-debugging-port=9222 的 Chrome。原始错误: {last_err}"
        )

    def _ensure_tab_via_http(self) -> None:
        """确保调试 Chrome 至少有一个标签页（必须在 MCP 启动前调用）。

        浏览器一个标签页都没有时，chrome-devtools-mcp 的所有工具
        （包括 new_page）都报 "No page selected"，且连接后再建标签页也感知不到，
        只能在启动 MCP 前用 Chrome 调试 HTTP 接口补一个。
        """
        # 本机 CDP 接口必须直连：环境里的 HTTP_PROXY 会把 127.0.0.1 也送进代理（502）
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(f"{self.browser_url}/json/list", timeout=5) as resp:
                targets = json.loads(resp.read().decode())
            if any(t.get("type") == "page" for t in targets):
                return
            req = urllib.request.Request(
                f"{self.browser_url}/json/new?about:blank", method="PUT"
            )
            opener.open(req, timeout=5).read()
        except Exception:  # noqa: BLE001 — Chrome 不可达时留给 MCP 连接报错
            pass

    async def _restart_remote_browser(self) -> None:
        """杀掉僵死的常驻 Chrome，交给 Docker（restart: unless-stopped）拉起全新实例。"""
        import subprocess
        from urllib.parse import urlparse

        port = urlparse(self.browser_url).port or 9222
        logger.warning("remote browser wedged, killing chrome on :%s", port)
        try:
            await asyncio.to_thread(
                subprocess.run,
                ["pkill", "-f", f"remote-debugging-port={port}"],
                timeout=10,
            )
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(6)  # 等 Docker 拉起新实例

    async def close(self) -> None:
        if self._stack is not None:
            try:
                await self._stack.aclose()
            except Exception:  # noqa: BLE001
                pass
            self._stack = None
            self._session = None

    # 单次工具调用的兜底超时 + 三层自愈：
    #   1) 45s 超时（navigate 自带 30s 页面超时，足够）
    #   2) 超时 → 重建 mcp 会话重试（mcp 子进程僵死的情况）
    #   3) 仍超时且是远程常驻浏览器 → 杀掉 Chrome（Docker restart 秒级拉起
    #      全新实例）→ 重连重试。
    CALL_TIMEOUT_S = 45

    async def call(self, tool: str, arguments: dict[str, Any] | None = None) -> str:
        """调用一个 MCP 工具，返回文本结果。工具报错时抛异常而不是把错误文本当结果。"""
        result = None
        for attempt in range(3):
            if self._session is None:
                raise MCPConnectionError("MCP 会话未连接")
            try:
                result = await asyncio.wait_for(
                    self._session.call_tool(tool, arguments or {}), timeout=self.CALL_TIMEOUT_S
                )
                break
            except TimeoutError as e:
                if attempt == 0:
                    # 第一层：重建 MCP 会话
                    logger.warning("MCP 工具 %s 超时，重建会话重试", tool)
                    await self.close()
                    await self.connect()
                elif attempt == 1 and settings.remote_browser:
                    # 第二层：杀掉僵死的远程 Chrome，等 Docker 重启
                    logger.warning("MCP 工具 %s 再次超时，重启远程 Chrome", tool)
                    await self._restart_remote_browser()
                    await self.close()
                    await self.connect()
                else:
                    raise MCPConnectionError(
                        f"MCP 工具 {tool} 超过 {self.CALL_TIMEOUT_S}s 未响应（自愈失败）"
                    ) from e

        parts = []
        for item in result.content:
            if getattr(item, "type", "") == "text":
                parts.append(item.text)
        text = "\n".join(parts)

        if getattr(result, "isError", False):
            raise MCPConnectionError(f"MCP 工具 {tool} 执行失败: {text[:300]}")
        return text
