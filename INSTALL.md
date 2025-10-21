# LabelImg 增强版 - 安装指南

本指南提供了在不同操作系统上安装和配置LabelImg增强版的详细步骤。

## 📋 系统要求

- **Python**: 3.6 或更高版本
- **依赖库**: PyQt5, lxml
- **操作系统**: Windows, Linux, macOS

## 💻 Windows 安装步骤

### 方法一：使用 pip 安装依赖

1. **安装 Python**（如已安装请跳过）：
   - 访问 [Python官网](https://www.python.org/downloads/windows/)
   - 下载并安装最新版本
   - **重要**: 安装时勾选「Add Python to PATH」

2. **安装依赖库**：
   ```bash
   pip install PyQt5 lxml
   ```

3. **编译资源文件**：
   ```bash
   cd f:\work_area\___Labellmg\label_app_to_change\labelImg-cut
   pyrcc5 -o libs/resources.py resources.qrc
   ```

4. **运行程序**：
   ```bash
   python labelImg.py
   ```

### 方法二：使用虚拟环境（推荐开发者）

1. **创建虚拟环境**：
   ```bash
   python -m venv venv
   ```

2. **激活虚拟环境**：
   ```bash
   venv\Scripts\activate
   ```

3. **安装依赖**：
   ```bash
   pip install PyQt5 lxml
   ```

4. **编译资源并运行**：
   ```bash
   pyrcc5 -o libs/resources.py resources.qrc
   python labelImg.py
   ```

## 🐧 Linux 安装步骤

### Ubuntu/Debian 系统

1. **更新系统包**：
   ```bash
   sudo apt-get update
   ```

2. **安装系统依赖**：
   ```bash
   sudo apt-get install python3-pyqt5 pyqt5-dev-tools
   sudo apt-get install python3-lxml
   ```

3. **安装 pip 依赖**（如果需要）：
   ```bash
   pip3 install PyQt5 lxml
   ```

4. **编译资源文件**：
   ```bash
   cd /path/to/labelImg-cut
   pyrcc5 -o libs/resources.py resources.qrc
   ```

5. **运行程序**：
   ```bash
   python3 labelImg.py
   ```

### CentOS/Fedora 系统

1. **安装依赖**：
   ```bash
   sudo dnf install python3-qt5 python3-lxml
   ```

2. **编译资源并运行**（同上）

## 🍎 macOS 安装步骤

### 使用 Homebrew

1. **安装 Homebrew**（如已安装请跳过）：
   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

2. **安装 Python 和依赖**：
   ```bash
   brew install python pyqt
   pip3 install lxml
   ```

3. **编译资源文件**：
   ```bash
   cd /path/to/labelImg-cut
   pyrcc5 -o libs/resources.py resources.qrc
   ```

4. **运行程序**：
   ```bash
   python3 labelImg.py
   ```

## ⚙️ 常见安装问题解决

### 1. `pyrcc5` 命令未找到

**解决方法**：
- **Windows**: 确保 PyQt5 已正确安装，尝试 `python -m PyQt5.pyrcc_main` 替代
- **Linux**: 安装 `pyqt5-dev-tools` 包
- **macOS**: 可能需要添加 brew 安装路径到环境变量

### 2. ImportError: No module named 'PyQt5'

**解决方法**：
```bash
pip uninstall PyQt5
pip install PyQt5 --no-cache-dir
```

### 3. 资源文件编译失败

**解决方法**：
- 检查 `resources.qrc` 文件是否存在
- 确保路径中没有中文或特殊字符
- 尝试使用绝对路径：
  ```bash
  pyrcc5 -o $(pwd)/libs/resources.py $(pwd)/resources.qrc
  ```

### 4. 在高分辨率屏幕上显示异常

**解决方法**（Windows）：
- 右键点击 `python.exe`
- 选择「属性」→「兼容性」→「更改高 DPI 设置」
- 勾选「替代高 DPI 缩放行为」，选择「系统」

## 📁 目录结构确认

安装前请确认您的项目目录包含以下核心文件：

```
labelImg-cut/
├── labelImg.py        # 主程序
├── libs/              # 核心库
├── data/              # 数据文件
├── resources/         # 资源文件
└── resources.qrc      # 资源配置
```

## 🚀 快速启动脚本

为方便使用，您可以创建以下启动脚本：

### Windows (start_labelimg.bat)
```batch
@echo off
cd /d "%~dp0"
python labelImg.py
pause
```

### Linux/macOS (start_labelimg.sh)
```bash
#!/bin/bash
cd "$(dirname "$0")"
python3 labelImg.py
```

创建后记得给脚本添加执行权限（Linux/macOS）：
```bash
chmod +x start_labelimg.sh
```

---

安装完成后，请查看 [README.md](./README.md) 和 [DEMO_GUIDE.md](./DEMO_GUIDE.md) 了解更多使用信息！