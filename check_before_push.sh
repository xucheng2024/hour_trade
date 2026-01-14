#!/bin/bash
# 推送前安全检查脚本

echo "========================================="
echo "🔍 GitHub 推送前安全检查"
echo "========================================="
echo ""

# 检查1: .env 文件
echo "✓ 检查 .env 文件..."
if git ls-files | grep -q "^\.env$"; then
    echo "❌ 错误: .env 文件在 git 中！"
    echo "   运行: git rm --cached .env"
    exit 1
else
    echo "✅ .env 文件未被跟踪"
fi

# 检查2: API密钥
echo ""
echo "✓ 检查硬编码的 API 密钥..."
if grep -r "520fe3fe" --exclude-dir=.git . | grep -v ".example" | grep -v "check_before_push.sh" > /dev/null; then
    echo "❌ 错误: 发现硬编码的 API 密钥！"
    echo "   请检查以下文件:"
    grep -r "520fe3fe" --exclude-dir=.git . | grep -v ".example" | grep -v "check_before_push.sh"
    exit 1
else
    echo "✅ 未发现硬编码的 API 密钥"
fi

# 检查3: .gitignore 存在
echo ""
echo "✓ 检查 .gitignore..."
if [ ! -f ".gitignore" ]; then
    echo "❌ 错误: .gitignore 文件不存在！"
    exit 1
else
    echo "✅ .gitignore 文件存在"
fi

# 检查4: 大文件
echo ""
echo "✓ 检查大文件..."
large_files=$(find . -type f -size +10M -not -path "./.git/*" -not -path "./src/crypto_remote/node_modules/*" 2>/dev/null)
if [ ! -z "$large_files" ]; then
    echo "⚠️  警告: 发现大文件 (>10MB):"
    echo "$large_files"
    echo "   考虑添加到 .gitignore"
else
    echo "✅ 未发现超大文件"
fi

# 检查5: Git状态
echo ""
echo "✓ Git 状态:"
git status --short | head -20

# 检查6: 文件数量
echo ""
echo "✓ 项目统计:"
file_count=$(git ls-files | wc -l)
echo "   - 被追踪的文件数: $file_count"
du -sh . 2>/dev/null | awk '{print "   - 项目大小: " $1}'

echo ""
echo "========================================="
echo "✅ 安全检查通过！"
echo "========================================="
echo ""
echo "下一步: 推送到 GitHub"
echo "命令: ./push_to_github.sh"
echo ""
