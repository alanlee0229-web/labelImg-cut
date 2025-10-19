with open('deepseek_html_20251019_fc9be4 (1).html', 'r', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()
    
# 检查第710行附近的内容
for i in range(705, 715):
    if i < len(lines):
        print(f"Line {i+1}: {lines[i].rstrip()}")

# 搜索包含特殊字符或模块相关的行
for i, line in enumerate(lines):
    if 'module' in line or '`' in line:
        print(f"Special line {i+1}: {line.rstrip()}")

# 检查文件结尾是否正确
print("\nFile ending:")
for line in lines[-10:]:
    print(line.rstrip())