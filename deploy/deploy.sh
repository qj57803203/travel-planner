#!/bin/bash
# 旅行规划 Agent 部署脚本

set -e

echo "=== 旅行规划 Agent 部署脚本 ==="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查 Docker
check_docker() {
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}错误: Docker 未安装${NC}"
        echo "请先安装 Docker: curl -fsSL https://get.docker.com | sh"
        exit 1
    fi

    if ! command -v docker compose &> /dev/null; then
        echo -e "${RED}错误: Docker Compose 未安装${NC}"
        echo "请先安装: sudo apt install docker-compose-plugin"
        exit 1
    fi

    echo -e "${GREEN}✓ Docker 已安装${NC}"
}

# 检查环境变量
check_env() {
    if [ ! -f "backend.env" ]; then
        echo -e "${YELLOW}警告: backend.env 不存在，正在从模板创建...${NC}"
        cp backend.env.example backend.env
        echo -e "${YELLOW}请编辑 backend.env 填入 DEEPSEEK_API_KEY${NC}"
        echo "vim backend.env"
        exit 1
    fi

    if ! grep -q "DEEPSEEK_API_KEY=sk-" backend.env; then
        echo -e "${YELLOW}警告: DEEPSEEK_API_KEY 可能未配置${NC}"
        echo "请编辑 backend.env 填入正确的 API Key"
    fi

    echo -e "${GREEN}✓ 环境变量已配置${NC}"
}

# 创建数据目录
create_dirs() {
    echo "创建数据目录..."
    mkdir -p data xhs/data xhs/browser-data
    echo -e "${GREEN}✓ 数据目录已创建${NC}"
}

# 检查前端构建
check_frontend() {
    if [ ! -d "../frontend/dist" ]; then
        echo -e "${YELLOW}警告: 前端未构建${NC}"
        echo "请先构建前端:"
        echo "  cd ../frontend"
        echo "  npm install"
        echo "  npm run build"
        echo ""
        read -p "是否现在构建前端? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            cd ../frontend
            npm install
            npm run build
            cd ../deploy
        else
            echo -e "${RED}前端未构建，部署后无法访问${NC}"
            exit 1
        fi
    fi
    echo -e "${GREEN}✓ 前端已构建${NC}"
}

# 检查小红书 cookies
check_xhs_cookies() {
    if [ ! -f "xhs/data/cookies.json" ]; then
        echo -e "${YELLOW}警告: 小红书 cookies 不存在${NC}"
        echo "小红书功能将不可用，需要登录后才能使用"
        echo ""
        echo "获取 cookies 方式:"
        echo "  1. 启动浏览器服务: docker compose --profile login up -d xhs-browser"
        echo "  2. 访问 http://your-ip:6080 登录"
        echo "  3. 参考 xhs/COOKIES_GUIDE.md"
        echo ""
        # 创建空的 cookies 文件
        echo '{"version":2,"seed":0,"saved_at":"","cookies":[]}' > xhs/data/cookies.json
    else
        # 检查 cookies 是否为空
        if grep -q '"cookies":\[\]' xhs/data/cookies.json; then
            echo -e "${YELLOW}警告: 小红书 cookies 为空，需要登录${NC}"
        else
            echo -e "${GREEN}✓ 小红书 cookies 已配置${NC}"
        fi
    fi
}

# 构建并启动
build_and_start() {
    echo ""
    echo "构建 Docker 镜像..."
    docker compose build

    echo ""
    echo "启动服务..."
    docker compose up -d

    echo ""
    echo -e "${GREEN}=== 部署完成 ===${NC}"
    echo ""
    echo "服务访问地址:"
    echo "  - 前端: http://localhost"
    echo "  - 后端 API: http://localhost:8000"
    echo "  - API 文档: http://localhost:8000/docs"
    echo ""
    echo "如需登录小红书:"
    echo "  docker compose --profile login up -d xhs-browser"
    echo "  访问 http://localhost:6080"
    echo ""
    echo "查看日志:"
    echo "  docker compose logs -f"
    echo ""
}

# 主流程
main() {
    check_docker
    check_env
    create_dirs
    check_frontend
    check_xhs_cookies
    build_and_start
}

# 运行
main
