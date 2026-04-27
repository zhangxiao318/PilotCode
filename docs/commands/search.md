# /search 命令

智能代码搜索命令，支持语义搜索、符号搜索、正则搜索和文件搜索。

## 作用

在已索引的代码库中搜索代码，支持四种搜索方式：

1. **语义搜索** - 使用自然语言描述，AI理解意图返回相关代码
2. **符号搜索** - 精确查找类、函数、变量定义（利用桶索引实现毫秒级响应）
3. **正则搜索** - 使用正则表达式匹配代码
4. **文件搜索** - 按文件名模式查找

搜索结果会自动结合**项目记忆知识库**（`.pilotcode/memory/` 中的事实、Bug、决策、Q&A），将相关知识以高相关度（0.95）注入上下文。

## 前提条件

使用 `/search` 前必须先建立代码索引：

```bash
/index full
```

> 如果索引为空，`/search` 会自动触发增量索引，不再限制 `max_files=500`，确保所有文件都可被发现。

## 基本用法

```bash
/search [options] <query>
```

## 选项

| 选项 | 简写 | 说明 | 示例 |
|------|------|------|------|
| `--symbol` | `-s` | 符号搜索 | `/search -s UserModel` |
| `--regex` | `-r` | 正则搜索 | `/search -r "class.*"` |
| `--file` | `-f` | 文件搜索 | `/search -f "*.py"` |
| `--lang` | `-l` | 按语言过滤 | `/search -l python` |
| `--max` | `-n` | 限制结果数量 | `/search -n 10` |

## 搜索类型详解

### 1. 语义搜索（默认）

使用自然语言描述你想找的代码，系统会理解意图并返回相关代码片段。

```bash
# 查找用户认证相关的代码
/search authentication middleware

# 查找数据库连接池实现
/search database connection pool

# 查找错误处理和重试逻辑
/search error handling and retry

# 查找配置文件解析
/search config file parser

# 查找排序算法实现
/search sorting algorithm

# 查找API路由定义
/search API route definitions
```

特点：
- 无需知道精确的函数名
- 理解代码的语义和用途
- 返回相关性排序的结果
- 当索引向量 >100 时自动启用 numpy 批量加速

### 2. 符号搜索（`-s`）

精确查找类、函数、变量等符号定义。基于 `symbols_by_name` 桶索引实现 O(1) 精确匹配，3-tier 回退策略确保高召回率。

```bash
# 查找类定义
/search -s UserModel
/search -s AuthController
/search -s DatabaseConnection

# 查找函数
/search -s authenticate_user
/search -s calculate_total_price
/search -s process_data

# 查找方法（类成员函数）
/search -s validate_input
/search -s to_json

# 查找变量/常量
/search -s MAX_RETRY_COUNT
/search -s DEFAULT_TIMEOUT
```

特点：
- **速度最快**（毫秒级，桶索引 O(1) 查找）
- 精确匹配符号名
- 支持子字符串匹配（回退扫描）

### 3. 正则搜索（`-r`）

使用正则表达式进行模式匹配搜索。

```bash
# 查找所有类定义
/search -r "class\s+\w+"

# 查找所有 TODO/FIXME 注释
/search -r "TODO|FIXME|XXX"

# 查找特定模式的函数
/search -r "def.*auth"

# 查找继承关系
/search -r "class.*\(BaseModel\)"

# 查找特定格式的变量
/search -r "^[A-Z_]+ = "

# 查找所有测试函数
/search -r "def test_\w+"
```

特点：
- 灵活强大的模式匹配
- 适合复杂搜索条件
- 速度较慢（需要扫描）

### 4. 文件搜索（`-f`）

按文件名模式搜索文件。

```bash
# 查找所有测试文件
/search -f "*test*.py"

# 查找配置文件
/search -f "config.*"
/search -f "settings.*"

# 查找特定目录下的文件
/search -f "src/**/*.py"

# 查找所有模型文件
/search -f "*model*.py"

# 查找接口定义文件
/search -f "*.d.ts"
```

特点：
- 按文件名模式匹配
- 快速定位文件
- 支持通配符 `*` 和 `?`

## 高级过滤

### 按编程语言过滤

```bash
# 只在 Python 文件中搜索
/search authentication -l python

# 只在 C++ 文件中搜索
/search -s MyClass -l cpp

# 只在 JavaScript 文件中搜索
/search router -l javascript
```

### 限制结果数量

```bash
# 只返回前5个结果
/search -s User -n 5

# 返回前20个结果
/search database -n 20
```

### 组合使用

```bash
# 符号搜索 + 语言过滤 + 数量限制
/search -s "get_*" -l python -n 20

# 正则搜索 + 语言过滤
/search -r "class.*" -l cpp

# 文件搜索 + 数量限制
/search -f "*.py" -n 50
```

## 大型项目：聚焦子图

对于已构建分层索引的大型项目，可以在 `CodeContext` 中使用 `subgraph` 参数聚焦特定模块：

```bash
# 先索引项目
/index full

# 查看有哪些子图
# （AI 会自动获取分层索引的 Master Index）

# 聚焦特定子图深入分析
CodeContext(query="路由分发逻辑", subgraph="src/router")
```

## 使用场景

### 场景1：理解陌生项目

```bash
# 第一步：建立索引
/index full

# 第二步：查找项目入口
/search main function
/search -s "Main|App|Server"

# 第三步：了解核心模块
/search core module
/search -s "*Service|*Manager|*Controller"

# 第四步：查看架构设计
/search architecture
/search -r "class.*\(object\)"
```

### 场景2：查找特定功能的实现

```bash
# 语义搜索更直观
/search password hashing

# 找到后精确定位
/search -s hash_password
/search -s PasswordHasher

# 查看相关工具函数
/search -s "*hash*"
```

### 场景3：代码重构前分析

```bash
# 查找所有使用旧函数的地方
/search -s old_function_name

# 查找继承关系
/search -r "class.*\(OldBaseClass\)"

# 查找相关配置
/search -r "old_config_key"

# 查找所有导入语句
/search -r "from module import OldClass"
```

### 场景4：Bug 修复

```bash
# 搜索错误信息相关的代码
/search "error message"

# 查找异常处理
/search exception handling
/search -r "except.*Error"

# 定位具体函数
/search -s handle_error
/search -s retry_logic
```

### 场景5：C/C++ 项目开发

```bash
# 索引项目
/index full

# 查找头文件中的宏定义
/search -r "#define MAX_"

# 查找结构体定义
/search -s "struct Point"
/search -s "typedef struct"

# 查找类定义
/search -s MyClass

# 查找函数实现
/search -s process_data
/search -s main

# 查找命名空间
/search -r "namespace\s+\w+"
```

### 场景6：编写文档

```bash
# 查找所有公共API
/search -r "def [a-z].*\(" -n 20

# 查找类方法
/search -r "def [a-z].*\(self" -n 30

# 查找示例用法
/search example usage
```

## 输出格式

搜索结果通常包含：

```
Found 10 results for 'authentication':

1. src/auth/middleware.py:15 (class AuthMiddleware)
   Relevance: 0.95
   ```python
   class AuthMiddleware:
       def process_request(self, request):
           # Authentication logic
   ```

2. src/auth/utils.py:42 (function authenticate)
   Relevance: 0.88
   ```python
   def authenticate_user(username, password):
       # Validate credentials
   ```
```

每个结果包含：
- 文件路径和行号
- 符号类型和名称
- 相关度分数
- 代码片段预览

## 性能说明

| 搜索类型 | 速度 | 适用场景 |
|----------|------|----------|
| 符号搜索 (`-s`) | ⚡ 最快 (<10ms, O(1) 桶索引) | 知道确切名称时 |
| 文件搜索 (`-f`) | ⚡ 很快 (<50ms) | 按文件名查找 |
| 语义搜索 | 🚀 快 (<100ms, numpy 批量加速) | 探索性搜索 |
| 正则搜索 (`-r`) | 🐢 较慢 (1-5s) | 复杂模式匹配 |

## 故障排除

### 搜索返回空结果

```bash
# 检查是否已索引
/index stats

# 如果没有索引或索引为空
/index full

# 如果索引过期
/index clear
/index full
```

### 搜索结果不准确

```bash
# 尝试不同的搜索方式
/search authentication        # 语义搜索
/search -s Auth              # 符号搜索
/search -r "auth.*"          # 正则搜索

# 添加语言过滤
/search authentication -l python

# 更新索引
/index
```

### 搜索太慢

```bash
# 使用更快的搜索方式
/search -s SymbolName        # 代替语义搜索
/search -f "*.py"            # 代替正则搜索

# 限制结果数量
/search query -n 5
```

## 相关命令

- `/index` - 建立代码索引
- `/grep` - 纯文本搜索（无需索引，但较慢）
- `/glob` - 文件模式匹配

## 技巧与最佳实践

1. **优先使用符号搜索**：知道类/函数名时，`-s` 最快最准（桶索引 O(1)）
2. **探索用语义搜索**：不确定具体名称时，语义搜索更直观
3. **组合使用**：先用语义搜索定位，再用符号搜索精确查找
4. **利用语言过滤**：多语言项目中使用 `-l` 缩小范围
5. **限制结果数**：大项目中使用 `-n` 避免信息过载
6. **大型项目聚焦子图**：通过 `CodeContext(subgraph=...)` 深入特定模块

## 对比：/search vs /grep

| 特性 | /search | /grep |
|------|---------|-------|
| 需要索引 | ✅ 是（自动触发增量索引） | ❌ 否 |
| 语义理解 | ✅ 是 | ❌ 否 |
| 速度 | ⚡ 快 | 🐢 慢 |
| 符号定位 | ✅ 精确（桶索引） | ❌ 文本匹配 |
| 项目记忆 | ✅ 自动注入 | ❌ 否 |
| 适用项目 | 中大型 | 小型/临时 |

建议：日常使用 `/search`，仅在索引未建立时使用 `/grep`。
