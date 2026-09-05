#!/bin/bash
# 在服务器上启动服务
# 使用方法：ssh root@118.89.71.196，然后 cd /opt/travel-planner/deploy && ./start.sh

set -e

echo "=== 启动旅行规划服务 ==="

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# 1. 检查环境变量
echo -e "${YELLOW}1. 检查环境变量...${NC}"
if [ ! -f "backend.env" ]; then
    echo -e "${RED}错误：backend.env 不存在${NC}"
    echo "请先创建：cp backend.env.example backend.env && vim backend.env"
    exit 1
fi

if ! grep -q "DEEPSEEK_API_KEY=sk-" backend.env; then
    echo -e "${YELLOW}警告：DEEPSEEK_API_KEY 可能未配置${NC}"
    echo "请编辑 backend.env 填入正确的 API Key"
    read -p "是否继续？(y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 2. 创建数据目录
echo -e "${YELLOW}2. 创建数据目录...${NC}"
mkdir -p data xhs/data xhs/browser-data

# 3. 检查前端
echo -e "${YELLOW}3. 检查前端文件...${NC}"
if [ ! -d "../frontend/dist" ]; then
    echo -e "${RED}错误：前端未构建（frontend/dist 目录不存在）${NC}"
    echo "请先在本地构建前端并上传"
    exit 1
fi
echo -e "${GREEN}✓ 前端文件存在${NC}"

# 4. 构建并启动
echo -e "${YELLOW}4. 构建 Docker 镜像...${NC}"
docker compose build

echo -e "${YELLOW}5. 启动服务...${NC}"
docker compose up -d

# 5. 等待服务启动
echo -e "${YELLOW}6. 等待服务启动...${NC}"
sleep 5

# 6. 检查服务状态
echo ""
echo -e "${GREEN}=== 服务状态 ===${NC}"
docker compose ps

echo ""
echo -e "${GREEN}=== 服务访问地址 ===${NC}"
echo "前端: http://118.89.71.196"
echo "API 文档: http://118.89.71.196:8000/docs"
echo ""
echo "如需登录小红书："
echo "  docker compose --profile login up -d xhs-browser"
echo "  访问: http://118.89.71.196:6080"
echo ""
echo "查看日志："
echo "  docker compose logs -f"
