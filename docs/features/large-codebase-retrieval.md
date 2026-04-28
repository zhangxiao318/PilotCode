# PilotCode 大型代码库检索与理解能力说明

## 概述

PilotCode 针对本地大型代码库（数万至数十万文件规模）设计了一套完整的索引、检索与理解系统。核心目标是在**不依赖外部服务**的前提下，实现毫秒级的代码检索、自然语言语义搜索、以及适合大语言模型（LLM）上下文窗口的智能代码片段组装。

---

## 一、统一索引架构：五层协作模型

```
┌─────────────────────────────────────────┐
│         CodebaseIndexer (统一入口)       │
├─────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌────────┐ │
│  │  Symbol  │  │ Semantic │  │  AST   │ │
│  │  Index   │  │  Search  │  │ Analysis│ │
│  └──────────┘  └──────────┘  └────────┘ │
│  ┌──────────┐  ┌──────────┐             │
│  │ File     │  │Dependency│  │ Project │ │
│  │ Metadata │  │  Graph   │  │ Memory  │ │
│  └──────────┘  └──────────┘  └────────┘ │
└─────────────────────────────────────────┘
```

**`CodebaseIndexer`** 作为统一门面，协调五个专业服务：

| 服务 | 职责 |
|------|------|
| `CodeIndexer` | 符号提取（类、函数、变量）与 O(1) 快速查找 |
| `ASTCodeAnalyzer` | 深度代码分析（导入关系、调用图） |
| `EmbeddingService` | 语义向量化与自然语言搜索 |
| `FileMetadataCache` | 文件追踪与变更检测 |
| `HierarchicalIndexBuilder` | 大型代码库结构化分层索引 |
| `ProjectMemoryKB` | 项目知识持久化与自动注入 |

---

## 二、增量索引：避免重复劳动

### 2.1 双层变更检测

大型代码库的全量索引可能耗时数分钟到数十分钟。PilotCode 采用**双层检测**确保只处理变化的文件：

1. **第一层（mtime 快速过滤）**：比较文件修改时间，未变更的文件直接跳过
2. **第二层（SHA256 指纹校验）**：对于 mtime 可能未变化的情况（如 `git checkout`），计算文件内容哈希确认是否真的未变

### 2.2 增量更新流程

```
发现文件列表
    ↓
过滤未变更文件（双层检测）
    ↓
批量异步索引（10文件/批次）
    ↓
每500文件自动 checkpoint
    ↓
重建分层索引（指纹匹配则跳过）
    ↓
持久化到 ~/.cache/pilotcode/index_cache/
```

### 2.3 Git 优先文件发现

在 Git 仓库内使用 `git ls-files` 发现文件，比递归扫描（`rglob`）快 **10-100 倍**。非 Git 项目自动回退到文件系统扫描。

---

## 三、混合符号提取：速度优先，精准兜底

### 3.1 按语言选择最优策略

| 语言 | 提取方式 | 原因 |
|------|---------|------|
| **Python** | 自定义 Regex | ~0.5ms/文件，比 AST 快 10-20 倍，且 Python 缩进语法使 Regex 足够准确 |
| **C/C++** | Tree-sitter AST（默认安装） | 复杂语法（宏、模板）需要 AST 才能正确解析 |
| **JS/TS/Go/Rust/Java** | Tree-sitter AST（可选安装） | 结构复杂，AST 提取更可靠 |
| **所有语言** | Regex Fallback | Tree-sitter 未安装时自动降级，不中断工作 |

### 3.2 三级符号索引结构

```python
class CodeIndex:
    symbols: list[Symbol]           # 扁平列表，全量扫描
    symbols_by_name: dict[str, list[Symbol]]   # O(1) 精确名称查找
    symbols_by_file: dict[str, list[Symbol]]   # O(1) 按文件查找
```

搜索时走三级路由：**精确名称桶 → 文件路径桶 → 子字符串线性扫描**，确保小规模项目毫秒响应、大规模项目也不过度耗时。

### 3.3 父级追踪

Python Regex 提取器会跟踪当前所在的类上下文，将方法（method）与函数（function）区分，并记录 `parent` 字段。这使得导航时可以回答："`authenticate` 是 `UserService` 类的方法，还是独立的工具函数？"

---

## 四、分层索引：解决 LLM 上下文窗口瓶颈

### 4.1 问题背景

一个 10,000 文件的项目，全量符号 dump 可能达到数十万 token，远超 LLM 上下文窗口（通常 128K）。传统 RAG 直接检索代码片段，在首次查询时往往"只见树木不见森林"。

### 4.2 三层目录聚类

`HierarchicalIndexBuilder` 将代码库组织为**子图（Subgraph）**结构：

```
Master Index（总览）
├── subgraph: auth/          "Authentication layer"
│   ├── symbols: login(), logout(), verify_token()
│   └── imports_from: db/, crypto/
├── subgraph: db/            "Database layer"
│   ├── symbols: ConnectionPool, query()
│   └── exports_to: auth/, api/
├── subgraph: api/           "API handlers"
│   └── ...
└── orphan_files: ...
```

**聚类算法**：
1. 按目录树自底向上处理
2. 目录含 **2-50 个文件** → 独立子图
3. 目录过大 → 按子目录拆分；无子目录时按**文件名前缀**拆分（如 `user_*.py`, `order_*.py`）
4. 目录过小 → 向上合并；剩余碎片归入 `misc` 子图

### 4.3 子图自动摘要

不需要调用 LLM 生成摘要（避免 API 成本）。系统内置 **2000+ 条目**的目录名启发式映射表：

| 目录名片段 | 自动摘要 |
|-----------|---------|
| `auth` | Authentication layer |
| `db` / `database` | Database layer |
| `middleware` | Middleware components |
| `model` / `models` | Data models |

### 4.4 分层 RAG 上下文组装

`build_context()` 根据代码库规模智能选择检索策略：

```
if 代码库 > 100文件 或 > 500符号:
    Tier 1: Master Index（~2000 token 总览）
    Tier 2: 语义搜索 top-5 代码片段
    Tier 3: 指定子图的详细符号（如果用户聚焦某模块）
else:
    传统模式: 语义搜索 + 符号搜索 + 相关符号
```

**效果**：首次提问时，LLM 先获得"目录结构地图"，再获得具体代码，避免"盲人摸象"。

---

## 五、语义搜索：从自然语言到代码

### 5.1 双模式嵌入

| 模式 | 场景 | 特点 |
|------|------|------|
| `OpenAIEmbeddingProvider` | 有 API Key | 调用 `text-embedding-3-small`，1536 维 |
| `SimpleEmbeddingProvider` | 离线/无 Key | 基于字符 n-gram + bigram 频率的 128 维向量，零延迟 |

### 5.2 Numpy 批量相似度计算

向量存储在内存中。当向量数量 > 100 时，维护一个 `numpy` 矩阵，搜索时使用矩阵乘法：

```python
scores = matrix @ query_vector  # 批量点积，比 Python 循环快 5-10 倍
```

### 5.3 代码分块策略

- **Python**：按 AST 函数/类边界分块，保持语义完整性
- **其他语言**：滑动窗口（100 行，10 行重叠）

### 5.4 幽灵向量清理

重新索引文件前，系统先调用 `delete_by_file_path()` 删除该文件的旧嵌入向量，避免"代码已改但搜索仍返回旧结果"。

---

## 六、项目知识库：跨会话的记忆积累

### 6.1 四类知识条目

```python
ProjectMemoryKB.add_fact()      # 项目事实（如 "使用 SQLAlchemy 2.0"）
ProjectMemoryKB.add_bug()       # 已知缺陷与解决方案
ProjectMemoryKB.add_decision()  # 架构决策记录
ProjectMemoryKB.add_qa()        # 问答对
```

### 6.2 自动上下文注入

每次调用 `build_context()` 时，系统自动查询 `ProjectMemoryKB`，将相关度 ≥ 0.95 的知识条目**前置**到上下文窗口中。这意味着：

- 用户昨天发现的坑，今天提问时 LLM 已经知道
- 架构决策不需要反复解释
- 项目约定（编码风格、技术栈选择）自动生效

### 6.3 存储格式

采用 **JSONL**（每行一个 JSON 对象），优势：
- 追加写入，无需锁
- `git diff` 友好
- 可用标准 Unix 工具（`grep`, `jq`）直接查看

---

## 七、性能指标

| 指标 | 数值 |
|------|------|
| Python 符号提取 | ~0.5 ms/文件 |
| Tree-sitter 符号提取 | ~8 ms/文件 |
| 全量索引（Linux 内核规模，6万文件） | 10-20 分钟，~1GB RAM |
| 增量扫描（无变化） | ~2.5 秒（受限于文件系统遍历） |
| 符号精确查找 | O(1) |
| 语义搜索（>100 向量） | 毫秒级（Numpy 加速） |
| Master Index 文本大小 | ~2000 token |

---

## 八、与同类工具的对比

| 特性 | Grep/Ripgrep | Sourcegraph | GitHub Code Search | **PilotCode** |
|------|-------------|-------------|-------------------|---------------|
| 部署方式 | 本地 CLI | 服务端 | 云端 | **本地优先，零外部依赖** |
| 语义搜索 | ❌ | ✅ | ✅ | **✅（含离线模式）** |
| 符号导航 | ❌ | ✅ | ⚠️ 有限 | **✅（多级索引）** |
| 大项目支持 | 🚫 无上下文 | 需服务端资源 | 需网络 | **✅ 分层索引降维** |
| 项目记忆 | ❌ | ❌ | ❌ | **✅ 自动注入** |
| 增量索引 | ❌ | ✅ | ✅ | **✅ 双层检测** |
| LLM 上下文友好 | ❌ | ❌ | ❌ | **✅ 分层 RAG** |

---

## 九、使用方式

```bash
# 首次索引（全量）
/index full

# 日常增量索引
/index

# 查看统计
/index stats

# 语义搜索
/search authentication middleware

# 符号精确查找
/search -s UserModel

# 正则搜索
/search -r "class.*Controller"

# 查看分层索引总览
/index hierarchy

# 查看某个子图详情
/index subgraph auth
```
