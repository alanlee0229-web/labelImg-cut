# 图像文件批量重命名工具

这个工具可以批量重命名图像文件，在文件名前面添加文件夹名称。

## 功能特点

- 🖼️ 支持多种图像格式：jpg, jpeg, png, bmp, tiff, tif, gif, webp
- 📁 自动遍历所有子文件夹
- 🔒 安全模式：默认预览，确认后执行
- 💾 支持备份功能
- ⚠️ 智能跳过已存在的文件名
- 📊 详细的操作统计信息

## 文件说明

### 1. `rename_images_with_folder.py` - 完整版脚本
功能最全面，支持命令行参数和高级功能。

**使用方法：**
```bash
# 预览模式（推荐先使用）
python rename_images_with_folder.py /path/to/images

# 实际执行重命名
python rename_images_with_folder.py /path/to/images --execute

# 创建备份后重命名
python rename_images_with_folder.py /path/to/images --execute --backup

# 查看帮助
python rename_images_with_folder.py --help
```

**参数说明：**
- `path`: 要处理的根目录路径
- `--execute, -e`: 执行实际重命名（默认是预览模式）
- `--backup, -b`: 在重命名前创建备份

### 2. `simple_rename.py` - 简化版脚本
交互式界面，更容易使用，适合不熟悉命令行的用户。

**使用方法：**
```bash
python simple_rename.py
```

然后按照提示输入路径和确认操作即可。

## 使用示例

### 目录结构示例
```
images/
├── cat/
│   ├── image1.jpg
│   ├── image2.png
│   └── image3.bmp
├── dog/
│   ├── photo1.jpg
│   └── photo2.png
└── bird/
    └── bird1.jpg
```

### 重命名后的结果
```
images/
├── cat/
│   ├── cat_image1.jpg
│   ├── cat_image2.png
│   └── cat_image3.bmp
├── dog/
│   ├── dog_photo1.jpg
│   └── dog_photo2.png
└── bird/
    └── bird_bird1.jpg
```

## 安全特性

1. **预览模式**：默认只显示将要进行的操作，不实际修改文件
2. **备份功能**：可以在重命名前创建完整备份
3. **冲突检测**：自动跳过会导致文件名冲突的情况
4. **用户确认**：执行前需要用户明确确认

## 注意事项

⚠️ **重要提醒：**
- 重命名操作会直接修改文件，建议先使用预览模式
- 建议在重要数据上使用前先备份
- 确保有足够的磁盘空间（特别是使用备份功能时）

## 支持的图像格式

- JPEG (.jpg, .jpeg)
- PNG (.png)
- BMP (.bmp)
- TIFF (.tiff, .tif)
- GIF (.gif)
- WebP (.webp)

## 错误处理

脚本会处理以下情况：
- 路径不存在
- 文件权限不足
- 磁盘空间不足
- 文件名冲突
- 网络驱动器问题

## 系统要求

- Python 3.6+
- 无需额外依赖包
- 支持 Windows、macOS、Linux

## 故障排除

### 常见问题

1. **"权限被拒绝"错误**
   - 确保有文件夹的写入权限
   - 检查文件是否被其他程序占用

2. **"路径不存在"错误**
   - 检查路径是否正确
   - 使用绝对路径或相对路径

3. **重命名失败**
   - 检查文件名是否包含特殊字符
   - 确认目标文件名不包含系统保留字符

### 获取帮助

如果遇到问题，可以：
1. 使用预览模式先检查操作
2. 查看详细的错误信息
3. 检查文件权限和路径

## 许可证

此脚本为开源软件，可自由使用和修改。
