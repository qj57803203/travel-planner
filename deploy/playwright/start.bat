@echo off
echo 启动 Playwright MCP 服务...
echo.
echo 服务地址: http://127.0.0.1:18070/mcp
echo.
echo 按 Ctrl+C 停止服务
echo.

npx @playwright/mcp --port 18070
