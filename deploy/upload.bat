@echo off
REM Windows 上传脚本
REM 使用方法：双击运行或在命令行执行

echo === 上传代码到服务器 ===

REM 检查是否在 deploy 目录
if not exist "docker-compose.yml" (
    echo 错误：请在 deploy 目录下运行此脚本
    pause
    exit /b 1
)

REM 1. 构建前端
echo 1. 构建前端...
cd ..\frontend
if not exist "node_modules" (
    call npm install
)
call npm run build
cd ..\deploy
echo 前端构建完成

REM 2. 打包代码（使用 tar 或 7zip）
echo 2. 打包代码...
cd ..
tar --exclude='node_modules' --exclude='.venv' --exclude='__pycache__' --exclude='*.db' --exclude='.env' --exclude='dist' --exclude='.git' -czf %TEMP%\travel-planner.tar.gz .
cd deploy
echo 代码打包完成

REM 3. 上传到服务器
echo 3. 上传到服务器...
scp %TEMP%\travel-planner.tar.gz root@118.89.71.196:/tmp/

REM 4. 在服务器上解压
echo 4. 在服务器上解压...
ssh root@118.89.71.196 "cd /opt/travel-planner && tar -xzf /tmp/travel-planner.tar.gz && rm /tmp/travel-planner.tar.gz"

echo.
echo === 代码上传完成 ===
echo.
echo 下一步：
echo 1. SSH 登录服务器: ssh root@118.89.71.196
echo 2. 配置环境变量: cd /opt/travel-planner/deploy ^&^& vim backend.env
echo 3. 启动服务: ./start.sh
echo.
pause
