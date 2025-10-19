import re

def validate_html_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        # 检查基本的HTML标签配对
        open_tags = []
        tag_pattern = re.compile(r'<(/?)(\w+)\s*[^>]*>')
        
        for match in tag_pattern.finditer(content):
            is_closing = match.group(1) == '/'
            tag_name = match.group(2).lower()
            
            # 跳过自闭合标签
            if tag_name in ['br', 'hr', 'img', 'input', 'meta', 'link']:
                continue
            
            if is_closing:
                if not open_tags or open_tags[-1] != tag_name:
                    print(f"错误: 标签 </{tag_name}> 没有匹配的开始标签")
                else:
                    open_tags.pop()
            else:
                open_tags.append(tag_name)
        
        if open_tags:
            print(f"错误: 以下标签没有关闭: {', '.join(open_tags)}")
        else:
            print("HTML标签配对检查通过")
        
        # 检查JavaScript语法（简单检查）
        js_pattern = re.compile(r'<script[^>]*>(.*?)</script>', re.DOTALL)
        for js_match in js_pattern.finditer(content):
            js_code = js_match.group(1)
            # 检查大括号配对
            open_braces = js_code.count('{')
            close_braces = js_code.count('}')
            if open_braces != close_braces:
                print(f"错误: JavaScript中大括号不匹配: {open_braces}个开括号，{close_braces}个闭括号")
        
    except Exception as e:
        print(f"验证过程中出错: {e}")

if __name__ == "__main__":
    validate_html_file('deepseek_html_20251019_fc9be4 (1).html')