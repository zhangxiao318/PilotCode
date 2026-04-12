# 大型项目代码分析指南

本指南介绍如何使用 PilotCode 的代码索引和搜索功能高效分析大型代码库。

---

## 概述

对于大型项目（数万到数十万行代码），直接让 AI 读取所有文件效率低下。PilotCode 提供代码索引系统，支持：

- **语义搜索** - 理解代码含义，不仅匹配文本
- **符号搜索** - 快速查找类、函数、变量定义
- **代码统计** - 了解项目结构和复杂度
- **智能上下文** - 自动提取相关代码片段

---

## 工作流程

```
1. 构建索引 → 2. 搜索代码 → 3. 分析理解 → 4. 生成报告
```

---

## 第一步：构建代码索引

### 首次索引

进入项目目录后执行：

```bash
cd /path/to/your/project
./pilotcode

# 在交互界面中执行
/index
```

输出示例：
```
🗂️  Indexing codebase in: /home/user/myproject
📁 Found 1,247 source files to index
⏳ Starting index...
✅ Indexing complete!

📊 Statistics:
  Files indexed: 1,247
  Symbols: 8,932
  Snippets: 3,456

📝 Top Languages:
  python: 542 files
  typescript: 312 files
  javascript: 198 files
  json: 103 files
  markdown: 92 files
```

### 增量更新

代码变更后更新索引：

```
/index              # 增量更新，只处理变更文件
/index full         # 完全重建，适用于重大重构
```

### 查看索引状态

```
/index stats
```

输出示例：
```
📊 Index Statistics

Files: 1,247
Symbols: 8,932
Snippets: 3,456
Last Indexed: 2024-01-15 14:32:10

Languages:
  python: 542 files
  typescript: 312 files
  javascript: 198 files
```

---

## 第二步：搜索代码

### 语义搜索（默认）

描述你想找什么，AI 会理解语义：

```
/search authentication logic
/search database connection handling
/search error handling pattern
```

输出示例：
```
Found 5 results for 'authentication logic':

1. src/auth/middleware.py:45 (function authenticate_user)
   Relevance: 0.94
   ```python
   def authenticate_user(token: str) -> User:
       """Validate JWT token and return user."""
       payload = jwt.decode(token, SECRET_KEY)
       return User.get_by_id(payload['user_id'])
   ```

2. src/api/routes/login.py:23
   Relevance: 0.89
   ```python
   @router.post('/login')
   async def login(credentials: LoginRequest):
       user = await authenticate(credentials.email, credentials.password)
       return {'token': create_jwt(user)}
   ```
```

### 符号搜索

查找特定类或函数：

```
/search -s UserModel          # 查找 UserModel 类
/search -s authenticate       # 查找 authenticate 函数
/search -s API_BASE_URL       # 查找常量
```

### 正则搜索

使用正则表达式搜索：

```
/search -r "class.*View"      # 查找所有 View 类
/search -r "def test_"        # 查找所有测试函数
/search -r "TODO|FIXME"       # 查找待办事项
```

### 文件搜索

按文件名模式搜索：

```
/search -f "*test*.py"        # 查找测试文件
/search -f "*.config.ts"      # 查找配置文件
/search -f "router*"          # 查找路由相关文件
```

### 语言过滤

限定搜索范围：

```
/search -l python "database"  # 只在 Python 文件中搜索
/search -l typescript "interface"  # 只在 TypeScript 文件中搜索
```

### 组合搜索

多种条件组合：

```
/search -r "def.*auth" -l python -n 20   # Python 中的 auth 函数，显示 20 条
/search -s User -f "*models*"            # 在 models 文件中查找 User
```

---

## 第三步：代码分析技巧

### 1. 理解项目结构

```
项目包含哪些主要模块？
各模块之间如何交互？
数据流是怎样的？
```

### 2. 查找入口点

```
/search main function
/search -f "main.py"
/search "application entry point"
```

### 3. 分析依赖关系

```
哪些模块依赖 UserModel？
数据库操作集中在哪些地方？
API 路由是如何组织的？
```

### 4. 查找关键算法

```
/search "sorting algorithm"
/search "cache implementation"
/search "rate limiting"
```

### 5. 代码质量检查

```
/search -r "TODO|FIXME|XXX"
/search "error handling"
/search -r "print\(" -l python   # 查找调试代码
```

---

## 第四步：高级分析

### 生成代码地图

```
请分析这个项目，生成一份代码结构图：
1. 主要模块和它们的职责
2. 关键类和函数
3. 模块间的依赖关系
```

### 查找代码重复

```
/search "similar authentication logic"
/search "duplicate validation code"
```

### 安全审计

```
/search "SQL injection vulnerability"
/search "XSS prevention"
/search "password hashing"
```

### 性能分析

```
/search "database query optimization"
/search "caching strategy"
/search "async await"
```

---

## 实用命令速查

### 索引管理

```
/index              # 增量索引
/index full         # 完全重建
/index stats        # 查看统计
/index clear        # 清除索引
/index export       # 导出索引
/index import       # 导入索引
```

### 搜索命令

```
/search <query>              # 语义搜索
/search -s <symbol>          # 符号搜索
/search -r <pattern>         # 正则搜索
/search -f <file_pattern>    # 文件搜索
/search -l <language>        # 语言过滤
/search -n <number>          # 限制结果数
```

### 导航命令

```
/pwd                # 显示当前目录
/ls                 # 列出文件
/find <pattern>     # 查找文件
/grep <pattern>     # 文本搜索
```

---

## 大型项目最佳实践

### 1. 分步索引

对于超大项目，先索引核心模块：

```bash
# 在项目子目录中分别索引
cd project/src/core && /index
cd project/src/api && /index
```

### 2. 定期维护

```bash
# 添加到 git hooks，提交前自动更新索引
echo './pilotcode -c "/index"' >> .git/hooks/post-commit
chmod +x .git/hooks/post-commit
```

### 3. 团队协作

```bash
# 导出索引分享给团队
/index export team_index.json

# 团队成员导入
/index import team_index.json
```

### 4. 结合 Git 分析

```
最近一周修改了哪些文件？
这个函数最近被谁修改过？
这段代码的历史变更是怎样的？
```

---

## 示例分析会话

### 场景：接手新项目

```
# 1. 了解项目概况
请分析这个项目，告诉我它是做什么的，主要技术栈是什么？

# 2. 查看索引状态
/index stats

# 3. 查找核心业务逻辑
/search business logic
/search -s main

# 4. 了解数据模型
/search -s "class.*Model" -l python
/search database schema

# 5. 查找 API 接口
/search API endpoint
/search -f "*router*"

# 6. 了解测试覆盖
/search -f "*test*"
/search test coverage

# 7. 生成分析报告
请生成一份代码分析报告，包括：
- 项目架构概述
- 核心模块说明
- 技术债务识别
- 改进建议
```

### 场景：Bug 定位

```
# 1. 搜索相关代码
/search error handling
/search -r "function.*login"

# 2. 查看调用链
哪些函数调用了 authenticate？
User.login 的调用者有哪些？

# 3. 查看最近修改
/git log --oneline -10 -- src/auth/

# 4. 分析根本原因
根据错误堆栈，分析可能的原因
```

---

## 故障排除

### 索引失败

```bash
# 检查文件权限
ls -la .

# 检查磁盘空间
df -h

# 尝试完全重建
/index full
```

### 搜索结果不准确

```bash
# 更新索引
/index

# 使用更具体的搜索词
/search "user authentication middleware"

# 结合正则
/search -r "def.*auth.*user"
```

### 内存不足

对于超大项目：

```bash
# 分批索引
# 编辑 .pilotcode.json 排除不需要的目录
{
  "exclude_patterns": ["node_modules", "dist", ".git"]
}
```

---

## 相关文档

- [代码索引工具文档](../tools/code_index_tool.md)
- [代码搜索工具文档](../tools/code_search_tool.md)
- [开发工作流指南](./development-workflow.md)
