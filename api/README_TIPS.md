# Vercel部署注意事项

## ⚠️ 常见错误及预防

### 1. HTML模板大括号问题
**问题**: Python `.format()` 会把单个 `{}` 当作占位符
```python
# ❌ 错误
HTML = "<style> body { color: red; } </style>".format()

# ✅ 正确  
HTML = "<style> body {{ color: red; }} </style>".format()
```

**解决方案**:
- 方案A: CSS中所有 `{` 改成 `{{`，所有 `}` 改成 `}}`
- 方案B: 使用外部HTML文件（推荐）
- 方案C: 使用Jinja2模板引擎

### 2. 部署前必做检查
```bash
# 1. 语法检查
python3 -m py_compile api/index.py

# 2. AST解析检查
python3 -c "import ast; ast.parse(open('api/index.py').read())"

# 3. 本地测试导入
python3 -c "import sys; sys.path.insert(0, 'api'); import index"

# 4. 检查requirements
pip install -r requirements.txt --dry-run
```

### 3. 常见错误清单
- [ ] 忘记转义HTML模板中的大括号
- [ ] 缺少import语句（time, collections等）
- [ ] try/except结构不完整
- [ ] 使用了global语句（在Vercel可能有问题）
- [ ] 字符串拼接使用 `+=` 而不是 `list.join()`
- [ ] 忘记关闭数据库连接

### 4. 调试技巧
```python
# 添加更多日志
print(f"[DEBUG] Step 1: {variable}")

# 捕获所有异常
try:
    # your code
except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
    raise

# 测试数据库连接
try:
    conn = get_db_connection()
    print("[DB] Connection OK")
    conn.close()
except Exception as e:
    print(f"[DB ERROR] {e}")
```

### 5. Vercel特定问题
- 环境变量必须在Vercel Dashboard配置
- Serverless函数有10秒超时限制（免费版）
- 内存限制1GB
- 不支持持久化文件系统
- 每次请求都是冷启动（缓存在内存）

### 6. 最佳实践
1. **分离关注点**: HTML/CSS/JS放单独文件
2. **使用模板引擎**: Jinja2而不是字符串.format()
3. **充分测试**: 本地完整测试再部署
4. **错误处理**: 所有函数都要try/except
5. **日志输出**: 多打印日志便于调试
6. **代码审查**: 部署前git diff检查改动

### 7. 快速修复模板
当遇到FUNCTION_INVOCATION_FAILED时：
```bash
# 1. 检查语法
python3 -m py_compile api/index.py

# 2. 查看详细错误（如果有）
python3 api/index.py

# 3. 验证导入
python3 -c "exec(open('api/index.py').read())"

# 4. 修复后立即部署测试
vercel --prod
```
