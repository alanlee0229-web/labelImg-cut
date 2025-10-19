#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试修复后的功能
"""

import os
import sys

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_empty_file_handling():
    """测试空文件处理"""
    print("测试空文件处理...")
    
    # 创建测试目录
    test_dir = "test_labels"
    if not os.path.exists(test_dir):
        os.makedirs(test_dir)
    
    # 创建不同类型的测试文件
    test_files = [
        ("normal.txt", "0 0.5 0.5 0.1 0.1"),  # 正常文件
        ("empty.txt", ""),                      # 空文件
        ("whitespace.txt", "   "),              # 只有空格的文件
        ("no_class.txt", "0.5 0.5 0.1 0.1"),  # 没有类别ID的文件
    ]
    
    for filename, content in test_files:
        filepath = os.path.join(test_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"创建测试文件: {filename}")
    
    # 测试读取逻辑
    print("\n测试读取逻辑:")
    for filename in os.listdir(test_dir):
        filepath = os.path.join(test_dir, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()
            print(f"{filename}: '{first_line}'")
            
            # 使用修复后的逻辑
            if first_line and first_line.split():
                first_value = first_line.split()[0]
                if first_value == '0':
                    print(f"  ✓ 类别ID为0")
                else:
                    print(f"  ✗ 类别ID为{first_value}")
            else:
                print(f"  ✗ 空文件或格式错误")
    
    # 清理测试文件
    import shutil
    shutil.rmtree(test_dir)
    print(f"\n清理测试目录: {test_dir}")

def test_main_window_initialization():
    """测试主窗口初始化"""
    print("\n测试主窗口初始化...")
    
    try:
        # 尝试导入主窗口类
        from labelImg import MainWindow
        print("✓ 成功导入MainWindow类")
        
        # 测试参数处理
        print("测试参数处理...")
        # 这里可以添加更多测试
        
    except Exception as e:
        print(f"✗ 导入失败: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("开始测试修复...")
    
    # 测试1：空文件处理
    test_empty_file_handling()
    
    # 测试2：主窗口初始化
    test_main_window_initialization()
    
    print("\n测试完成！")
