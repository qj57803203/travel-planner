#!/usr/bin/env python3
"""小红书 Cookie 导出脚本 — 在 VNC 容器内运行。

使用方法：
1. 启动 xhs-browser 容器：docker compose --profile login up -d xhs-browser
2. 访问 http://服务器IP:6080（密码: xhs123）
3. 在虚拟桌面中打开 Firefox，登录小红书
4. 打开终端，运行：python3 /app/xhs_login.py

脚本会从 Firefox 的 cookie 数据库中提取小红书的 cookie，
保存到 /app/xhs_data/cookies.json 供后端使用。
"""

import json
import os
import sqlite3
import sys
import shutil
import tempfile
from pathlib import Path

# 小红书 cookie 保存路径（与 docker-compose 挂载对应）
OUTPUT_PATH = Path("/app/xhs_data/cookies.json")

# Firefox cookie 数据库路径
FIREFOX_PROFILES = Path.home() / ".mozilla" / "firefox"


def find_firefox_cookie_db() -> Path | None:
    """查找 Firefox 的 cookies.sqlite 文件。"""
    if not FIREFOX_PROFILES.exists():
        return None

    for profile in FIREFOX_PROFILES.iterdir():
        if profile.is_dir() and (profile / "cookies.sqlite").exists():
            return profile / "cookies.sqlite"
    return None


def extract_cookies_from_firefox(db_path: Path) -> list[dict]:
    """从 Firefox SQLite 数据库提取小红书 cookies。"""
    # 复制数据库（Firefox 可能锁定了文件）
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    try:
        shutil.copy2(db_path, tmp.name)
        tmp.close()

        conn = sqlite3.connect(tmp.name)
        cursor = conn.cursor()

        # Firefox cookies 表结构：name, value, host, path, expiry, isSecure, isHttpOnly
        cursor.execute("""
            SELECT name, value, host, path, expiry, isSecure, isHttpOnly
            FROM moz_cookies
            WHERE host LIKE '%xiaohongshu.com%'
        """)

        cookies = []
        for row in cursor.fetchall():
            cookies.append({
                "name": row[0],
                "value": row[1],
                "domain": row[2],
                "path": row[3],
                "expires": row[4],
                "secure": bool(row[5]),
                "httpOnly": bool(row[6]),
            })

        conn.close()
        return cookies
    finally:
        os.unlink(tmp.name)


def extract_cookies_manual() -> list[dict]:
    """手动输入模式：提示用户在浏览器控制台获取 cookie。"""
    print("\n" + "=" * 60)
    print("未能自动提取 Cookie，请手动操作：")
    print("=" * 60)
    print("\n1. 在 Firefox 中打开 https://www.xiaohongshu.com 并登录")
    print("2. 按 F12 打开开发者工具")
    print("3. 切换到「网络(Network)」标签")
    print("4. 刷新页面，点击任意请求")
    print("5. 在「请求头(Request Headers)」中找到 Cookie 行")
    print("6. 复制完整的 Cookie 值")
    print("\n然后粘贴到下方（按 Enter 确认）：\n")

    cookie_str = input("> ").strip()
    if not cookie_str:
        return []

    cookies = []
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if "=" in pair:
            name, value = pair.split("=", 1)
            cookies.append({
                "name": name.strip(),
                "value": value.strip(),
                "domain": ".xiaohongshu.com",
                "path": "/",
            })
    return cookies


def save_cookies(cookies: list[dict]) -> None:
    """保存 cookies 到共享目录。"""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    print("🔍 小红书 Cookie 导出工具")
    print("-" * 40)

    # 尝试从 Firefox 自动提取
    db_path = find_firefox_cookie_db()

    if db_path:
        print(f"✅ 找到 Firefox cookie 数据库: {db_path}")
        cookies = extract_cookies_from_firefox(db_path)

        if cookies:
            print(f"✅ 提取到 {len(cookies)} 个小红书 Cookie")
            save_cookies(cookies)
            print(f"✅ 已保存到 {OUTPUT_PATH}")
            print("\n关键 Cookie:")
            for c in cookies:
                if c["name"] in ("web_session", "a1", "webId", "web_session_same_"):
                    print(f"  - {c['name']} = {c['value'][:20]}...")
            return

        print("⚠️ Firefox 中未找到小红书 Cookie，请先在 Firefox 中登录小红书")

    else:
        print("⚠️ 未找到 Firefox cookie 数据库")
        print("   请确认已在虚拟桌面的 Firefox 中登录小红书")

    # 手动输入模式
    cookies = extract_cookies_manual()
    if cookies:
        save_cookies(cookies)
        print(f"\n✅ 已保存 {len(cookies)} 个 Cookie 到 {OUTPUT_PATH}")
    else:
        print("\n❌ 未获取到 Cookie")
        sys.exit(1)


if __name__ == "__main__":
    main()
