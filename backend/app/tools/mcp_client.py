"""chrome-devtools-mcp 客户端封装（简化版，供携程爬虫使用）。

通过 stdio 启动 chrome-devtools-mcp，连接本地调试 Chrome（--remote-debugging-port=9222）。
参考 tongyou-travel-agent 项目的 ChromeMCP，去掉连接池/全局锁等复杂逻辑。
"""

import asyncio
import logging
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import settings

logger = logging.getLogger(__name__)


class MCPConnectionError(Exception):
    pass


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

    async def __aenter__(self) -> "ChromeMCP":
        await self.connect()
        return self

    async def __aexit__(self, *exc):
        await self.close()

    async def connect(self, retries: int = 2) -> None:
        """连接 chrome-devtools-mcp（stdio 模式）。"""
        # npx chrome-devtools-mcp --browser-url 连接本地调试 Chrome
        args = ["-y", "chrome-devtools-mcp@0.6.0", "--browser-url", self.browser_url]
        params = StdioServerParameters(command="npx", args=args)

        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                self._stack = AsyncExitStack()
                read, write = await self._stack.enter_async_context(stdio_client(params))
                self._session = await self._stack.enter_async_context(ClientSession(read, write))
                await asyncio.wait_for(self._session.initialize(), timeout=30)
                return
            except Exception as e:
                last_err = e
                await self.close()
                if attempt < retries:
                    await asyncio.sleep(2 * (attempt + 1))
        raise MCPConnectionError(
            f"无法连接 chrome-devtools-mcp（browser_url={self.browser_url}）。"
            f"请确认已启动带 --remote-debugging-port=9222 的 Chrome。原始错误: {last_err}"
        )

    async def close(self) -> None:
        if self._stack is not None:
            try:
                await self._stack.aclose()
            except Exception:
                pass
            self._stack = None
            self._session = None

    async def call(self, tool: str, arguments: dict[str, Any] | None = None) -> str:
        """调用一个 MCP 工具，返回文本结果。工具报错时抛异常。"""
        if self._session is None:
            raise MCPConnectionError("MCP 会话未连接")

        timeout_s = 45  # navigate 自带 30s 超时，45s 足够
        try:
            result = await asyncio.wait_for(
                self._session.call_tool(tool, arguments or {}), timeout=timeout_s
            )
        except TimeoutError as e:
            raise MCPConnectionError(f"MCP 工具 {tool} 超过 {timeout_s}s 未响应") from e

        parts = []
        for item in result.content:
            if getattr(item, "type", "") == "text":
                parts.append(item.text)
        text = "\n".join(parts)

        if getattr(result, "isError", False):
            raise MCPConnectionError(f"MCP 工具 {tool} 执行失败: {text[:300]}")
        return text
