#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
图像文件批量重命名工具
功能：将指定路径下所有文件夹中的图像文件名前面加上文件夹名称
"""

import os
import shutil
from pathlib import Path


def get_image_extensions():
    """获取支持的图像文件扩展名"""
    return {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif', '.txt'}


def rename_images_in_folder(folder_path):
    """
    重命名指定文件夹中的图像文件
    
    Args:
        folder_path (str): 文件夹路径
    
    Returns:
        list: 重命名操作列表 [(原文件名, 新文件名), ...]
    """
    folder_path = Path(folder_path)
    if not folder_path.is_dir():
        print(f"错误：{folder_path} 不是一个有效的文件夹")
        return []
    
    folder_name = folder_path.name
    image_extensions = get_image_extensions()
    rename_operations = []
    
    # 遍历文件夹中的所有文件
    for file_path in folder_path.iterdir():
        if file_path.is_file():
            # 检查是否为图像文件
            if file_path.suffix.lower() in image_extensions:
                old_name = file_path.name
                new_name = f"{folder_name}_{old_name}"
                new_path = file_path.parent / new_name
                
                # 检查新文件名是否已存在
                if new_path.exists():
                    print(f"警告：{new_name} 已存在，跳过重命名")
                    continue
                
                try:
                    file_path.rename(new_path)
                    print(f"✓ 重命名：{old_name} -> {new_name}")
                    rename_operations.append((old_name, new_name))
                except Exception as e:
                    print(f"✗ 重命名失败：{old_name} -> {new_name}，错误：{e}")
    
    return rename_operations


def process_all_folders(root_path):
    """
    处理根路径下的所有文件夹
    
    Args:
        root_path (str): 根路径
    """
    root_path = Path(root_path)
    if not root_path.is_dir():
        print(f"错误：{root_path} 不是一个有效的目录")
        return
    
    print(f"开始处理目录：{root_path}")
    print("-" * 50)
    
    total_operations = 0
    processed_folders = 0
    
    # 遍历根目录下的所有子文件夹
    for item in root_path.iterdir():
        if item.is_dir():
            print(f"\n处理文件夹：{item.name}")
            operations = rename_images_in_folder(item)
            
            if operations:
                total_operations += len(operations)
                processed_folders += 1
                print(f"  找到 {len(operations)} 个图像文件")
            else:
                print("  未找到图像文件")
    
    print("-" * 50)
    print(f"处理完成！")
    print(f"处理文件夹数量：{processed_folders}")
    print(f"总重命名操作：{total_operations}")


def main():
    """主函数"""
    # 直接在这里设置要处理的路径
    root_path = r"E:\label"  # 修改为你的实际路径
    
    # 检查路径是否存在
    if not os.path.exists(root_path):
        print(f"错误：路径 {root_path} 不存在")
        print("请修改脚本中的 root_path 变量为正确的路径")
        return
    
    print(f"即将处理目录：{root_path}")
    print("这将重命名所有子文件夹中的图像文件")
    
    # 询问是否创建备份
    backup_choice = input("是否在重命名前创建备份？(y/n): ").lower()
    create_backup = backup_choice in ['y', 'yes', '是']
    
    # 询问确认
    confirm = input("确认继续吗？(输入 'yes' 确认): ")
    if confirm.lower() != 'yes':
        print("操作已取消")
        return
    
    # 创建备份
    if create_backup:
        backup_path = f"{root_path}_backup"
        try:
            print(f"正在创建备份...")
            shutil.copytree(root_path, backup_path)
            print(f"备份创建成功：{backup_path}")
        except Exception as e:
            print(f"备份创建失败：{e}")
            return
    
    # 执行重命名操作
    process_all_folders(root_path)


if __name__ == "__main__":
    main()
