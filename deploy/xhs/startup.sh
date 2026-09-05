#!/bin/bash
# 小红书登录浏览器启动脚本
# 用户通过 noVNC 访问此浏览器，扫码登录小红书

echo "正在启动小红书登录浏览器..."

# 等待桌面环境就绪
sleep 5

# 启动 Chromium 并打开小红书登录页面
chromium-browser \
    --no-sandbox \
    --disable-gpu \
    --start-maximized \
    --window-size=1280,800 \
    "https://www.xiaohongshu.com" &

echo "小红书登录浏览器已启动"
echo "请访问 http://your-server-ip:6080 进行扫码登录"
echo "VNC 密码: xhs123（请在 docker-compose.yml 中修改）"
