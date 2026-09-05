#!/bin/bash
# 服务器初始化脚本
# 使用方法：ssh root@118.89.71.196 'bash -s' < server-init.sh

set -e

echo "=== 服务器初始化 ==="

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 1. 更新系统
echo -e "${YELLOW}1. 更新系统包...${NC}"
apt update
apt upgrade -y

# 2. 检查 Docker
echo -e "${YELLOW}2. 检查 Docker...${NC}"
if command -v docker &> /dev/null; then
    echo -e "${GREEN}✓ Docker 已安装: $(docker --version)${NC}"
else
    echo "安装 Docker..."
    curl -fsSL https://get.docker.com | sh
fi

# 3. 检查 Docker Compose
echo -e "${YELLOW}3. 检查 Docker Compose...${NC}"
if docker compose version &> /dev/null; then
    echo -e "${GREEN}✓ Docker Compose 已安装: $(docker compose version)${NC}"
else
    echo "安装 Docker Compose..."
    apt install -y docker-compose-plugin
fi

# 4. 配置 Docker 镜像加速（国内服务器必备）
echo -e "${YELLOW}4. 配置 Docker 镜像加速...${NC}"
mkdir -p /etc/docker
cat > /etc/docker/daemon.json << 'EOF'
{
  "registry-mirrors": [
    "https://mirror.ccs.tencentyun.com",
    "https://hub-mirror.c.163.com"
  ],
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF
systemctl restart docker

# 5. 配置防火墙
echo -e "${YELLOW}5. 配置防火墙...${NC}"
if command -v ufw &> /dev/null; then
    ufw allow 22/tcp    # SSH
    ufw allow 80/tcp    # HTTP
    ufw allow 443/tcp   # HTTPS
    ufw allow 6080/tcp  # VNC（小红书登录用）
    ufw --force enable
    echo -e "${GREEN}✓ 防火墙已配置${NC}"
else
    echo "未安装 ufw，跳过防火墙配置"
fi

# 6. 创建项目目录
echo -e "${YELLOW}6. 创建项目目录...${NC}"
mkdir -p /opt/travel-planner
mkdir -p /opt/travel-planner/deploy/data
mkdir -p /opt/travel-planner/deploy/xhs/data
mkdir -p /opt/travel-planner/deploy/xhs/browser-data

# 7. 创建空的 cookies 文件
if [ ! -f /opt/travel-planner/deploy/xhs/data/cookies.json ]; then
    echo '{"version":2,"seed":0,"saved_at":"","cookies":[]}' > /opt/travel-planner/deploy/xhs/data/cookies.json
fi

# 8. 设置 Swap（内存不足时的保险）
echo -e "${YELLOW}7. 配置 Swap...${NC}"
if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    echo -e "${GREEN}✓ 2G Swap 已配置${NC}"
else
    echo -e "${GREEN}✓ Swap 已存在${NC}"
fi

echo ""
echo -e "${GREEN}=== 服务器初始化完成 ===${NC}"
echo ""
echo "下一步："
echo "1. 在本地打包代码上传"
echo "2. 配置环境变量"
echo "3. 启动服务"
