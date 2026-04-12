# Code Indexing & Large-Scale Analysis

PilotCode 提供企业级的代码索引和大规模工程分析能力，类似于 Claude Code。

## 快速开始

```bash
# 1. 索引代码库（首次使用需要）
/index full

# 2. 查看索引统计
/index stats

# 3. 使用语义搜索
/search authentication logic

# 4. 使用符号搜索
/search -s UserModel
```

## 核心概念

### 为什么要索引？

| 对比项 | 无索引 (Grep) | 有索引 (Code Index) |
|--------|--------------|-------------------|
| 搜索速度 | 秒级（全文扫描） | 毫秒级（预建索引） |
| 语义理解 | ❌ 纯文本匹配 | ✅ 自然语言查询 |
| 代码关系 | ❌ 无 | ✅ 类/函数/调用关系 |
| 大项目支持 | 🚫 性能急剧下降 | ✅ 可处理10万+文件 |
| 上下文理解 | ❌ 需手动读取文件 | ✅ 智能代码片段 |

### 索引流程

```
源代码文件
    ↓
符号提取 (类、函数、变量)
    ↓
语义向量化 (用于自然语言搜索)
    ↓
索引存储 (内存 + 可导出)
    ↓
快速查询
```

## 命令详解

### `/index` - 索引管理

#### 基础用法

```bash
# 增量索引（只索引变化的文件，推荐日常使用）
/index

# 完整重新索引（首次使用或强制刷新）
/index full

# 查看索引统计
/index stats

# 清除索引
/index clear

# 导出索引到文件
/index export

# 从文件导入索引
/index import
```

#### 输出示例

```
🗂️  Performing full reindex in: /home/user/myproject
📁 Found 369 source files to index
⏳ Starting full reindex...

✅ Full reindex complete!

📊 Statistics:
  Files indexed: 369
  Symbols: 3574
  Snippets: 1777
```

### `/search` - 代码搜索

支持四种搜索方式：

#### 1. 语义搜索（默认）

使用自然语言描述你想找的代码，系统会理解意图并返回相关代码：

```bash
# 查找用户认证相关代码
/search authentication middleware

# 查找数据库连接池实现
/search database connection pool

# 查找错误处理和重试逻辑
/search error handling and retry mechanism

# 查找配置文件解析
/search config file parser
```

#### 2. 符号搜索（`-s`）

精确查找函数、类、变量定义，速度最快：

```bash
# 查找类定义
/search -s UserModel
/search -s AuthController

# 查找函数
/search -s authenticate_user
/search -s calculate_total_price

# 查找方法（类成员函数）
/search -s validate_input

# 支持模糊匹配
/search -s "*Controller"
```

#### 3. 正则搜索（`-r`）

使用正则表达式进行模式匹配：

```bash
# 查找所有类定义
/search -r "class\s+\w+"

# 查找所有 TODO/FIXME 注释
/search -r "TODO|FIXME|XXX"

# 查找特定模式的函数
/search -r "def.*auth"

# 查找继承关系
/search -r "class.*\(BaseModel\)"
```

#### 4. 文件搜索（`-f`）

按文件名模式搜索：

```bash
# 查找所有测试文件
/search -f "*test*.py"

# 查找配置文件
/search -f "config.*"

# 查找特定目录下的文件
/search -f "src/**/*.py"
```

#### 高级过滤选项

```bash
# 按编程语言过滤
/search authentication -l python
/search database -l cpp
/search router -l javascript

# 限制结果数量
/search -s User -n 10
/search authentication -n 5

# 组合使用
/search -s "get_*" -l python -n 20
```

## 使用场景

### 场景1：理解陌生项目

```bash
# 第一步：建立索引（2-3分钟）
/index full

# 第二步：查看项目概况
/index stats
# 输出：Files: 542, Symbols: 8234, Languages: {python: 350, cpp: 120, ...}

# 第三步：查找入口点
/search main function
/search -s "App|Server|Main"

# 第四步：了解核心模块
/search core module
/search -s "*Service|*Manager|*Controller"
```

### 场景2：查找特定功能的实现

```bash
# 语义搜索更直观
/search password hashing implementation

# 找到后精确定位
/search -s hash_password
/search -s "*Hash*"

# 查看相关类
/search -s PasswordHasher
```

### 场景3：代码重构前分析

```bash
# 查找所有使用旧函数的地方
/search -s old_function_name

# 查找继承关系
/search -r "class.*\(OldBaseClass\)"

# 查找相关配置
/search -r "old_config_key"
```

### 场景4：C/C++ 项目开发

```bash
# 索引 C/C++ 项目
/index full

# 查找头文件中的宏定义
/search -r "#define MAX_"

# 查找结构体定义
/search -s "struct Point"

# 查找类定义（支持 .cpp/.cc/.cxx/.hpp/.hh/.hxx）
/search -s MyClass

# 查找函数实现
/search -s process_data

# 查找命名空间
/search -r "namespace\s+\w+"
```

### 场景5：Bug 修复

```bash
# 搜索错误信息相关的代码
/search "error message"

# 查找异常处理
/search exception handling

# 定位具体函数
/search -s handle_error
```

### 场景6：学习代码库

```bash
# 了解项目架构
/search project architecture

# 查找设计模式使用
/search singleton pattern
/search factory pattern

# 查找示例用法
/search example usage
```

## 支持的编程语言

### 完整支持（符号提取 + 语义搜索）

| 语言 | 扩展名 | 提取的符号 |
|------|--------|-----------|
| **Python** | `.py`, `.pyw`, `.pyi` | 类、函数、方法、变量 |
| **C** | `.c`, `.h` | 函数、结构体、宏、typedef |
| **C++** | `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hh`, `.hxx`, `.c++`, `.h++` | 类、函数、方法、命名空间、模板、结构体 |
| **JavaScript** | `.js`, `.jsx`, `.mjs`, `.cjs` | 类、函数、方法 |
| **TypeScript** | `.ts`, `.tsx` | 类、接口、函数 |
| **Go** | `.go` | 函数、结构体 |
| **Rust** | `.rs` | 函数、结构体、trait |
| **Java** | `.java` | 类、方法、接口 |

### 基础支持

| 语言 | 扩展名 |
|------|--------|
| Ruby | `.rb` |
| PHP | `.php` |
| Swift | `.swift` |
| Kotlin | `.kt`, `.kts` |
| Scala | `.scala` |
| R | `.r` |
| Objective-C | `.m`, `.mm` |
| C# | `.cs` |
| F# | `.fs`, `.fsx` |
| Elm | `.elm` |

## 架构

```
┌─────────────────────────────────────────────┐
│         CodebaseIndexer                     │
├─────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌────────┐    │
│  │  Symbol  │  │ Semantic │  │  AST   │    │
│  │  Index   │  │  Search  │  │ Analysis│   │
│  └──────────┘  └──────────┘  └────────┘    │
│  ┌──────────┐  ┌──────────┐                 │
│  │ File     │  │Dependency│                 │
│  │ Metadata │  │  Graph   │                 │
│  └──────────┘  └──────────┘                 │
└─────────────────────────────────────────────┘
```

### 关键组件

- **Symbol Indexer**: 基于正则表达式提取代码符号
- **AST Analyzer**: Python AST 深度分析（依赖关系、复杂度）
- **Embedding Service**: 向量嵌入用于语义搜索
- **File Metadata Cache**: 文件变更追踪，支持增量索引

## 性能优化

### 索引策略

```bash
# 小项目 (<100文件)：完整索引很快
/index full

# 大项目 (1000+文件)：日常使用增量索引
/index              # 只索引变化的文件

# 定期重建（每周/每月）
/index clear && /index full
```

### 搜索优化

```bash
# 最快：符号搜索（精确匹配）
/search -s ExactSymbolName

# 较快：文件搜索
/search -f "*.py"

# 较慢但灵活：语义搜索
/search natural language query

# 最慢：正则搜索（全文扫描）
/search -r "complex.*pattern"
```

## 故障排除

### 问题：搜索返回空结果

```bash
# 检查是否已索引
/index stats

# 如果没有索引或索引为空
/index full

# 如果索引过期
/index clear
/index full
```

### 问题：索引很慢

```bash
# 检查文件数量
find . -name "*.py" | wc -l

# 排除不需要的目录（自动忽略，但可确认）
# 已忽略：node_modules, __pycache__, .git, build, dist

# 大项目首次索引需要几分钟是正常的
# 后续使用增量索引会快很多
```

### 问题：某些文件未被索引

```bash
# 检查文件扩展名是否在支持列表中
/search -f "*.xyz"

# 检查文件是否在忽略目录中
# 默认忽略：.git, node_modules, __pycache__, etc.

# 手动索引特定文件（通过工具）
CodeIndex(action="index", file_path="/path/to/file.py")
```

## 最佳实践

1. **首次使用项目时**
   ```bash
   /index full
   /index stats  # 确认索引成功
   ```

2. **日常开发**
   ```bash
   # 代码变化后
   /index  # 增量更新
   
   # 查找具体符号
   /search -s SymbolName
   ```

3. **探索性开发**
   ```bash
   # 先用语义搜索定位大致范围
   /search authentication flow
   
   # 再用符号搜索精确定位
   /search -s AuthManager
   ```

4. **团队协作**
   ```bash
   # 导出索引领给团队成员
   /index export
   
   # 团队成员导入
   /index import
   ```

## 与 Claude Code 对比

| 功能 | PilotCode | Claude Code |
|------|-----------|-------------|
| 符号索引 | ✅ | ✅ |
| 语义搜索 | ✅ | ✅ |
| AST 分析 | ✅ (Python/C/C++) | ✅ (多语言) |
| 增量索引 | ✅ | ✅ |
| 文件监控 | 🚧 计划中 | ✅ |
| 代码图分析 | 🚧 计划中 | ✅ |
| 多语言 AST | 部分支持 | 完整支持 |

## 相关文档

- [QUICKSTART.md](QUICKSTART.md) - 快速开始指南（包含代码索引章节）
- [README.md](README.md) - 项目概述
- `src/pilotcode/services/codebase_indexer.py` - 核心实现
- `src/pilotcode/services/code_index.py` - 符号提取
- `src/pilotcode/services/embedding_service.py` - 语义搜索

## 未来计划

- [ ] 文件监控自动索引
- [ ] 跨语言调用图分析
- [ ] 代码变更影响分析
- [ ] FAISS 集成支持超大代码库
- [ ] 代码相似度检测
- [ ] 智能代码补全基于索引