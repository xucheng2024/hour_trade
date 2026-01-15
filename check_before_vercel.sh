#!/bin/bash
# Vercel部署前自动检查脚本

echo "🔍 开始检查 api/index.py..."
echo ""

# 1. 检查文件是否存在
if [ ! -f "api/index.py" ]; then
    echo "❌ api/index.py 不存在"
    exit 1
fi

# 2. Python语法检查
echo "📝 检查Python语法..."
if python3 -m py_compile api/index.py 2>/dev/null; then
    echo "✅ Python语法正确"
else
    echo "❌ Python语法错误："
    python3 -m py_compile api/index.py
    exit 1
fi

# 3. AST解析检查
echo ""
echo "🔧 检查AST解析..."
if python3 -c "import ast; ast.parse(open('api/index.py').read())" 2>/dev/null; then
    echo "✅ AST解析成功"
else
    echo "❌ AST解析失败："
    python3 -c "import ast; ast.parse(open('api/index.py').read())"
    exit 1
fi

# 4. 检查单个大括号（可能忘记转义）
echo ""
echo "🎨 检查HTML模板大括号..."
single_braces=$(grep -n "style>" api/index.py | head -1)
if [ ! -z "$single_braces" ]; then
    # 检查<style>标签后是否有单个大括号
    suspect=$(sed -n '/style>/,/\/style>/p' api/index.py | grep -E "[^{]{[^{]|[^}]}[^}]" | wc -l)
    if [ $suspect -gt 0 ]; then
        echo "⚠️  发现可能的单个大括号（需要转义为双大括号）"
        echo "   请检查CSS中的 { 和 } 是否都转义为 {{ 和 }}"
    else
        echo "✅ HTML模板格式正确"
    fi
else
    echo "✅ 未使用内联样式或已正确处理"
fi

# 5. 检查必需的import
echo ""
echo "📦 检查必需的导入..."
required_imports=("import time" "from collections import defaultdict" "import psycopg2")
missing=0
for imp in "${required_imports[@]}"; do
    if ! grep -q "$imp" api/index.py; then
        echo "⚠️  缺少: $imp"
        missing=1
    fi
done
if [ $missing -eq 0 ]; then
    echo "✅ 所有必需的导入都存在"
fi

# 6. 检查try/except配对
echo ""
echo "🔄 检查try/except结构..."
try_count=$(grep -c "^\s*try:" api/index.py)
except_count=$(grep -c "^\s*except" api/index.py)
if [ $try_count -eq $except_count ]; then
    echo "✅ try/except配对正确 (${try_count}个)"
else
    echo "⚠️  try(${try_count}个) 和 except(${except_count}个) 数量不匹配"
fi

# 7. 检查requirements.txt
echo ""
echo "📋 检查依赖..."
if [ -f "requirements.txt" ]; then
    if grep -q "psycopg2-binary" requirements.txt; then
        echo "✅ requirements.txt包含必需依赖"
    else
        echo "⚠️  requirements.txt可能缺少psycopg2-binary"
    fi
else
    echo "⚠️  requirements.txt不存在"
fi

# 8. 检查环境变量
echo ""
echo "🔑 检查环境变量配置..."
if grep -q "DATABASE_URL" api/index.py; then
    echo "✅ 代码中使用了DATABASE_URL"
    echo "   请确保在Vercel Dashboard中已配置此变量"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✨ 检查完成！"
echo ""
echo "如果没有❌错误，可以安全部署："
echo "  vercel --prod"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
