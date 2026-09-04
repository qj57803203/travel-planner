# Playwright MCP 服务

用于爬取携程酒店数据的浏览器自动化服务。

## 启动方式

### Windows

```bash
cd deploy/playwright
start.bat
```

### 其他系统

```bash
cd deploy/playwright
npx @playwright/mcp --port 18070
```

## 配置

在 `backend/.env` 中添加：

```bash
CTRIPE_MCP_URL=http://127.0.0.1:18070/mcp
```

## 验证

1. 启动服务后，日志显示 `Listening on http://127.0.0.1:18070`
2. 生成行程时，如果住宿建议中有地铁站名，会自动搜索携程酒店
3. 前端会显示"🏨 推荐酒店"卡片，点击可跳转携程查看详情

## 注意事项

- 携程有反爬机制，搜索频率不能太高（建议每次间隔 2 秒以上）
- 如果搜索失败，可能是页面结构变化，需要更新爬虫代码
- 首次运行会下载 Chromium 浏览器（约 150MB）
