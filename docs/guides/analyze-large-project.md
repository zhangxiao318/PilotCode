# 大型项目代码分析指南

本指南介绍如何使用 PilotCode 的代码索引和搜索功能高效分析大型代码库。

---

## 概述

对于大型项目（数百到数万文件），直接让 AI 读取所有文件效率低下且容易超出上下文窗口。PilotCode 提供：

- **分层索引** — 将代码库组织为子图，LLM 先读概览再 drill-down
- **语义搜索** — 理解代码含义，不仅匹配文本
- **符号搜索** — 基于桶索引的毫秒级精确查找
- **项目记忆** — 自动注入已知 Bug、架构决策、Q&A
- **智能上下文** — 自动提取相关代码片段，支持子图聚焦

---

## 工作流程

```
1. 构建索引 → 2. 概览理解 → 3. 子图聚焦 → 4. 深入分析 → 5. 生成报告
```

---

## 第一步：构建代码索引

### 首次索引

进入项目目录后执行：

```bash
cd /path/to/your/project
./pilotcode

# 在交互界面中执行
/index full
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
  go: 95 files

🏗️ Hierarchical Index: 12 subgraphs built
  Core: src/core (45 files)
  API: src/api (32 files)
  Utils: src/utils (28 files)
  ...
```

> **分层索引自动构建**：超过 10 个文件时，系统自动按目录聚类生成子图（最小 2 文件/子图，最大 50 文件/子图）。

### 增量更新

代码变更后更新索引：

```
/index              # 增量更新，双层过滤（mtime + SHA256）只处理变更文件
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
Last Indexed: 2026-04-27 14:32:10

Languages:
  python: 542 files
  typescript: 312 files
  javascript: 198 files

Hierarchical Index: 12 subgraphs
  Core: src/core (45 files, 312 symbols)
  API: src/api (32 files, 198 symbols)
  ...
```

---

## 第二步：概览理解（Tier 1）

对于大型项目，首次查询时 AI 会自动获取 **Master Index**（项目概览），包括：

- 总文件数、符号数、行数
- 语言分布
- 子图列表（按目录聚类）
- 核心子图（被最多模块依赖的）
- 共享模块（高复用率）
- 入口点（主程序、CLI）

示例对话：

```
User: 请介绍一下这个项目

AI: [自动获取 Master Index]
这是一个电商后端项目，共 1,247 个文件：
- 核心模块：src/core（订单、支付、库存）
- API 层：src/api（REST 接口）
- 基础设施：src/infra（数据库、缓存、消息队列）
...
```

---

## 第三步：聚焦子图（Tier 2）

了解概览后，使用 `subgraph` 参数深入特定模块：

```python
# 深入支付模块
CodeContext(query="退款流程", subgraph="src/payment")

# 深入路由层
CodeContext(query="权限校验中间件", subgraph="src/middleware")

# 深入数据库层
CodeContext(query="连接池配置", subgraph="src/db")
```

也可以直接询问 AI：

```
User: 请详细分析 src/payment 模块的设计

AI: [自动聚焦 payment 子图]
该模块包含 32 个文件，198 个符号...
```

---

## 第四步：搜索代码

### 语义搜索（默认）

描述你想找什么，AI 会理解语义：

```
/search authentication logic
/search database connection handling
/search error handling pattern
```

### 符号搜索

查找特定类或函数（桶索引实现毫秒级响应）：

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

## 第五步：代码分析技巧

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

## 第六步：高级分析

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

## 项目记忆知识库

PilotCode 会在 `.pilotcode/memory/` 中自动维护项目知识，并在分析时注入上下文。

### 查看现有记忆

```
请列出这个项目的已知问题和架构决策
```

### 添加新记忆

```python
from pilotcode.services.memory_kb import get_memory_kb

kb = get_memory_kb("/path/to/project")
kb.add_fact("订单服务使用 Saga 模式处理分布式事务", tags=["architecture", "order"])
kb.add_bug(symptom="高并发下库存扣减不一致", root_cause="竞态条件", fix="添加乐观锁", files_involved=["inventory.py"])
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

### 上下文工具

```python
CodeContext(query="...", max_tokens=4000)                    # 基本用法
CodeContext(query="...", subgraph="src/payment")             # 聚焦子图
CodeContext(query="...", include_related=True)               # 包含相关符号
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

对于超大项目，PilotCode 会自动处理，但你可以通过子目录分别理解：

```bash
# 先索引整个项目
/index full

# 然后逐个子图深入分析
CodeContext(query="核心业务逻辑", subgraph="src/core")
CodeContext(query="API 设计", subgraph="src/api")
```

### 2. 定期维护

```bash
# 日常增量更新
/index

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

# 共享项目记忆
# .pilotcode/memory/ 目录可加入版本控制
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
# AI 自动获取 Master Index

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

# 7. 深入关键模块
CodeContext(query="订单状态机", subgraph="src/order")

# 8. 生成分析报告
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

# 4. 聚焦相关模块
CodeContext(query="认证异常处理", subgraph="src/auth")

# 5. 分析根本原因
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

# 聚焦子图减少噪音
CodeContext(query="auth", subgraph="src/auth")
```

### 内存不足

对于超大项目：

```bash
# PilotCode 会自动启用分层索引，避免单次加载过多内容
# 也可编辑 .pilotcode.json 排除不需要的目录
{
  "exclude_patterns": ["node_modules", "dist", ".git"]
}
```

### 上下文窗口溢出

```
# 使用 subgraph 参数聚焦小范围
CodeContext(query="...", subgraph="src/small_module", max_tokens=2000)

# 避免请求整个项目概览时附加过多代码
请只分析 src/core 模块
```

---

## 相关文档

- [代码索引与搜索功能](../features/codebase-intelligence.md)
- [代码索引工具文档](../tools/code_index_tool.md)
- [代码搜索工具文档](../tools/code_search_tool.md)
- [代码上下文工具文档](../tools/code_context_tool.md)
- [开发工作流指南](./development-workflow.md)
