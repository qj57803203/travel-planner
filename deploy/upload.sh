#!/bin/bash
# 上传代码到服务器
# 使用方法：在 deploy 目录下运行 ./upload.sh

set -e

SERVER="root@118.89.71.196"
REMOTE_DIR="/opt/travel-planner"

echo "=== 上传代码到服务器 ==="

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 确认在正确目录
if [ ! -f "docker-compose.yml" ]; then
    echo "错误：请在 deploy 目录下运行此脚本"
    exit 1
fi

# 1. 构建前端
echo -e "${YELLOW}1. 构建前端...${NC}"
cd ../frontend
if [ ! -d "node_modules" ]; then
    npm install
fi
npm run build
cd ../deploy
echo -e "${GREEN}✓ 前端构建完成${NC}"

# 2. 打包代码
echo -e "${YELLOW}2. 打包代码...${NC}"
cd ..
tar --exclude='node_modules' \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='*.db' \
    --exclude='.env' \
    --exclude='dist' \
    --exclude='.git' \
    -czf /tmp/travel-planner.tar.gz .
cd deploy
echo -e "${GREEN}✓ 代码打包完成${NC}"

# 3. 上传到服务器
echo -e "${YELLOW}3. 上传到服务器...${NC}"
scp /tmp/travel-planner.tar.gz $SERVER:/tmp/

# 4. 在服务器上解压
echo -e "${YELLOW}4. 在服务器上解压...${NC}"
ssh $SERVER << 'EOF'
cd /opt/travel-planner
tar -xzf /tmp/travel-planner.tar.gz
rm /tmp/travel-planner.tar.gz
EOF

echo -e "${GREEN}✓ 代码上传完成${NC}"

echo ""
echo "下一步："
echo "1. SSH 登录服务器: ssh root@118.89.71.196"
echo "2. 配置环境变量: cd /opt/travel-planner/deploy && vim backend.env"
echo "3. 启动服务: ./start.sh"
