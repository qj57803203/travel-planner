# 小红书 Cookies 获取指南

## Cookies 格式

小红书 MCP 需要的 cookies.json 格式：

```json
{
  "version": 2,
  "seed": 123456789,
  "saved_at": "2026-09-05T00:00:00Z",
  "cookies": [
    {
      "name": "a1",
      "value": "xxx",
      "domain": ".xiaohongshu.com",
      "path": "/",
      "expires": 1735689600,
      "httpOnly": true,
      "secure": true,
      "sameSite": "None"
    },
    {
      "name": "web_session",
      "value": "xxx",
      "domain": ".xiaohongshu.com",
      "path": "/",
      "expires": 1735689600,
      "httpOnly": true,
      "secure": true,
      "sameSite": "None"
    }
  ]
}
```

## 获取方式

### 方式一：浏览器插件导出（推荐）

1. **Chrome/Edge 安装插件**
   - [EditThisCookie](https://chrome.google.com/webstore/detail/editthiscookie/fngmhnnpilhplaeedifhccceomclgfbg)
   - 或 [Cookie-Editor](https://chrome.google.com/webstore/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm)

2. **登录小红书**
   - 打开 https://www.xiaohongshu.com
   - 扫码登录

3. **导出 Cookies**
   - 点击插件图标
   - 选择"导出"或"Export"
   - 复制 JSON 内容

4. **保存到服务器**
   ```bash
   # 编辑文件
   vim /opt/travel-planner/deploy/xhs/data/cookies.json
   # 粘贴导出的 cookies 内容
   ```

### 方式二：Chrome DevTools 手动导出

1. 登录小红书后，按 F12 打开开发者工具
2. 切换到 Application → Cookies → https://www.xiaohongshu.com
3. 手动复制所有 cookies 的 name 和 value
4. 按照上面的格式组装 JSON

### 方式三：使用 Python 脚本导出

```python
# install: pip install browser-cookie3
import browser_cookie3
import json
from datetime import datetime

# 获取 Chrome 的 cookies（需要先关闭 Chrome）
cj = browser_cookie3.chrome(domain_name='.xiaohongshu.com')

cookies = []
for cookie in cj:
    cookies.append({
        "name": cookie.name,
        "value": cookie.value,
        "domain": cookie.domain,
        "path": cookie.path,
        "expires": int(cookie.expires) if cookie.expires else None,
        "httpOnly": bool(cookie.has_nonstandard_attr('HttpOnly')),
        "secure": cookie.secure,
        "sameSite": "None"
    })

data = {
    "version": 2,
    "seed": 123456789,
    "saved_at": datetime.utcnow().isoformat() + "Z",
    "cookies": cookies
}

with open("cookies.json", "w") as f:
    json.dump(data, f, indent=2)

print(f"导出 {len(cookies)} 个 cookies")
```

## 关键 Cookies

小红书登录必须包含以下 cookies：

| Cookie 名 | 说明 |
|---|---|
| `a1` | 设备标识 |
| `web_session` | 登录会话（最重要） |
| `webId` | 用户标识 |
| `gid` | 用户分组 |

## 验证 Cookies 是否有效

```bash
# 重启 MCP 服务
docker compose restart xiaohongshu-mcp

# 查看日志
docker compose logs xiaohongshu-mcp

# 测试搜索功能
docker compose exec xiaohongshu-mcp curl -X POST http://localhost:18060/mcp \
  -H "Content-Type: application/json" \
  -d '{"method": "tools/call", "params": {"name": "search_feeds", "arguments": {"keyword": "苏州旅游"}}}'
```

## Cookies 过期处理

- **有效期**：通常 7-30 天
- **过期表现**：搜索返回空结果或报错
- **处理方式**：重新登录并更新 cookies.json

## 自动刷新方案（可选）

如果需要自动刷新 cookies，可以：

1. 启动 xhs-browser 容器
2. 通过 Selenium/Playwright 自动化登录
3. 定时导出 cookies 到共享目录

但这种方式复杂度较高，建议手动刷新。
