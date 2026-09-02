"""小红书 MCP 扫码登录辅助脚本。

用法：
    cd backend
    python scripts/xhs_login.py [MCP_URL]

默认连 http://127.0.0.1:18060/mcp，拉取登录二维码存成 xhs_qr.png，
提示用小红书 App 扫码，然后轮询登录状态直到成功。
"""

import asyncio
import base64
import json
import sys

# Windows 控制台默认 GBK，强制 UTF-8 避免 emoji / 中文打印崩溃
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18060/mcp"


async def _tool_text(session: ClientSession, tool: str, args: dict) -> str:
    res = await session.call_tool(tool, args)
    return "\n".join(c.text for c in res.content if getattr(c, "type", "") == "text")


def _extract_base64(raw: str) -> str:
    """从 get_login_qrcode 返回里提取 base64 图片。字段名不固定，做容错。"""
    try:
        data = json.loads(raw)
    except ValueError:
        return ""
    if isinstance(data, str):
        return data
    if not isinstance(data, dict):
        return ""
    for key in ("qr_image", "image", "img", "base64", "qrcode", "qr_code", "qr_code_base64"):
        v = data.get(key)
        if isinstance(v, str) and v:
            return v
    for val in data.values():  # 嵌套结构兜底
        if isinstance(val, dict):
            for k2 in ("qr_image", "image", "base64", "qrcode"):
                v2 = val.get(k2)
                if isinstance(v2, str) and v2:
                    return v2
    return ""


async def main() -> None:
    async with streamablehttp_client(URL) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()

            # 1. 拉取登录二维码
            raw = await _tool_text(s, "get_login_qrcode", {})
            print("get_login_qrcode 原始返回：", raw[:500])
            img = _extract_base64(raw)
            if img:
                path = "xhs_qr.png"
                with open(path, "wb") as f:
                    f.write(base64.b64decode(img))
                print(f"\n✅ 二维码已保存到 {path}，请打开小红书 App 扫码登录")
            else:
                print("\n⚠️ 未能从返回中解析出二维码图片，请改用 MCP Inspector 手动登录")

            # 2. 轮询登录状态
            for i in range(60):
                await asyncio.sleep(3)
                status = await _tool_text(s, "check_login_status", {})
                low = status.lower()
                print(f"[{i + 1}] 登录状态：{status}")
                if "已登录" in status or "logged" in low or "true" in low:
                    print("✅ 登录成功！cookie 已持久化，可配置后端并启动")
                    return
            print("⏱ 登录超时，请重新运行本脚本")


if __name__ == "__main__":
    asyncio.run(main())
