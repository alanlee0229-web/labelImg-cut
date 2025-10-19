#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
简化版图像文件批量重命名工具
功能：将指定路径下所有文件夹中的图像文件名前面加上文件夹名称
"""

import os
from pathlib import Path


def rename_images_with_folder():
    """主函数：重命名图像文件"""
    
    # 获取用户输入的路径
    print("图像文件批量重命名工具")
    print("=" * 40)
    
    while True:
        root_path = input("请输入要处理的根目录路径（或按回车使用当前目录）: ").strip()
        
        if not root_path:
            root_path = os.getcwd()
            print(f"使用当前目录：{root_path}")
            break
        
        if os.path.exists(root_path):
            break
        else:
            print(f"错误：路径 {root_path} 不存在，请重新输入")
    
    # 确认操作
    print(f"\n即将处理目录：{root_path}")
    print("这将重命名所有子文件夹中的图像文件")
    
    confirm = input("确认继续吗？(y/n): ").lower()
    if confirm not in ['y', 'yes', '是']:
        print("操作已取消")
        return
    
    # 支持的图像格式
    image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif', '.webp'}
    
    # 统计信息
    total_renamed = 0
    total_folders = 0
    
    print("\n开始处理...")
    print("-" * 50)
    
    # 遍历根目录下的所有子文件夹
    for item in Path(root_path).iterdir():
        if item.is_dir():
            folder_name = item.name
            print(f"\n处理文件夹：{folder_name}")
            
            folder_renamed = 0
            
            # 遍历文件夹中的所有文件
            for file_path in item.iterdir():
                if file_path.is_file():
                    # 检查是否为图像文件
                    if file_path.suffix.lower() in image_extensions:
                        old_name = file_path.name
                        new_name = f"{folder_name}_{old_name}"
                        new_path = file_path.parent / new_name
                        
                        # 检查新文件名是否已存在
                        if new_path.exists():
                            print(f"  跳过：{new_name} 已存在")
                            continue
                        
                        try:
                            # 执行重命名
                            file_path.rename(new_path)
                            print(f"  ✓ {old_name} -> {new_name}")
                            folder_renamed += 1
                            total_renamed += 1
                        except Exception as e:
                            print(f"  ✗ 重命名失败：{old_name}，错误：{e}")
            
            if folder_renamed > 0:
                total_folders += 1
                print(f"  完成：重命名了 {folder_renamed} 个文件")
            else:
                print("  未找到需要重命名的图像文件")
    
    # 显示结果
    print("-" * 50)
    print(f"处理完成！")
    print(f"处理文件夹数量：{total_folders}")
    print(f"总重命名文件数：{total_renamed}")
    
    if total_renamed > 0:
        print(f"\n所有图像文件已成功重命名！")
        print(f"新文件名格式：文件夹名_原文件名")
    else:
        print(f"\n没有找到需要重命名的图像文件")


if __name__ == "__main__":
    try:
        rename_images_with_folder()
    except KeyboardInterrupt:
        print("\n\n操作被用户中断")
    except Exception as e:
        print(f"\n发生错误：{e}")
    
    input("\n按回车键退出...")
