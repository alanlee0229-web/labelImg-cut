@echo off
cd /d "%~dp0"

REM 检查Python是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误：未找到Python。请先安装Python 3.6或更高版本。
    echo 请访问 https://www.python.org/downloads/
    pause
    exit /b 1
)

REM 检查依赖
python -c "import PyQt5; import lxml" >nul 2>&1
if %errorlevel% neq 0 (
    echo 正在安装所需依赖...
    pip install PyQt5 lxml --user
    if %errorlevel% neq 0 (
        echo 依赖安装失败！请手动运行：pip install PyQt5 lxml
        pause
        exit /b 1
    )
)

REM 编译资源文件
echo 正在准备资源文件...
pyrcc5 -o libs/resources.py resources.qrc
if %errorlevel% neq 0 (
    echo 资源文件编译失败！
    echo 尝试使用Python模块方式...
    python -m PyQt5.pyrcc_main -o libs/resources.py resources.qrc
    if %errorlevel% neq 0 (
        echo 请确保PyQt5已正确安装
        pause
        exit /b 1
    )
)

REM 运行程序
echo 启动LabelImg增强版...
python labelImg.py

REM 检查程序退出状态
if %errorlevel% neq 0 (
    echo 程序异常退出！
    pause
    exit /b 1
)