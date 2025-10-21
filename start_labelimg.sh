#!/bin/bash
cd "$(dirname "$0")"

# 检查Python是否安装
if ! command -v python3 &> /dev/null; then
    echo "错误：未找到Python3。请先安装Python 3.6或更高版本。"
    echo "请访问 https://www.python.org/downloads/"
    exit 1
fi

# 检查依赖
if ! python3 -c "import PyQt5; import lxml" &> /dev/null; then
    echo "正在安装所需依赖..."
    pip3 install PyQt5 lxml --user
    if [ $? -ne 0 ]; then
        echo "依赖安装失败！请手动运行：pip3 install PyQt5 lxml"
        exit 1
    fi
fi

# 编译资源文件
echo "正在准备资源文件..."
pyrcc5 -o libs/resources.py resources.qrc
if [ $? -ne 0 ]; then
    echo "资源文件编译失败！"
    echo "尝试使用Python模块方式..."
    python3 -m PyQt5.pyrcc_main -o libs/resources.py resources.qrc
    if [ $? -ne 0 ]; then
        echo "请确保PyQt5已正确安装"
        exit 1
    fi
fi

# 运行程序
echo "启动LabelImg增强版..."
python3 labelImg.py

# 检查程序退出状态
if [ $? -ne 0 ]; then
    echo "程序异常退出！"
    exit 1
fi