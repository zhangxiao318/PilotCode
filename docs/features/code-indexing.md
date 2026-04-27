# 代码索引与搜索

PilotCode 的代码索引系统提供高效的代码库理解和搜索能力，支持语义搜索、符号搜索、正则搜索，以及针对大型代码库的分层索引和项目记忆知识库。

---

## 概述

代码索引系统通过分析源代码，构建可快速查询的索引，使 AI 能够：
- **理解项目结构** - 快速了解大型代码库，通过分层索引把握全局
- **精准定位代码** - 通过语义或符号查找相关代码
- **分析依赖关系** - 理解代码间的调用关系
- **跨语言支持** - 支持多种编程语言，Python 使用高速正则，其他语言使用 Tree-sitter AST
- **项目记忆** - 自动注入项目知识（已知 Bug、架构决策、Q&A）到查询上下文

---

## 功能特性

### 支持的编程语言

| 语言 | 符号提取 | 语义索引 | 扩展名 | 提取方式 |
|------|----------|----------|--------|----------|
| Python | ✅ | ✅ | .py, .pyi | 高速正则 (~0.5ms/文件) |
| JavaScript/TypeScript | ✅ | ✅ | .js, .jsx, .ts, .tsx | Tree-sitter AST (~8ms/文件) |
| Go | ✅ | ✅ | .go | Tree-sitter AST |
| Rust | ✅ | ✅ | .rs | Tree-sitter AST |
| Java | ✅ | ✅ | .java | Tree-sitter AST |
| C/C++ | ✅ | ✅ | .c, .h, .cpp, .hpp, .cc, .hh, .cxx, .hxx | Tree-sitter AST |
| Ruby | ✅ | ✅ | .rb | 正则回退 |
| PHP | ✅ | ✅ | .php | 正则回退 |
| Swift | ✅ | ✅ | .swift | 正则回退 |
| Kotlin | ✅ | ✅ | .kt | 正则回退 |

> **混合提取策略**：Python 保持正则提取（速度优先，10-20 倍于 AST），其余语言使用 Tree-sitter 实现精确的符号边界识别。Tree-sitter 不可用时自动回退到正则。

### 索引内容

```
📁 代码索引包含：
├── 文件元数据（路径、语言、行数、mtime、SHA256）
├── 符号定义（类、函数、变量）— 支持桶索引加速精确查找
├── 代码片段（可搜索的代码块）
├── 嵌入向量（语义搜索用）— numpy batch 加速 (>100 向量)
├── 关系图谱（调用关系、导入/导出）
├── 分层索引（大型项目的目录聚类子图）
└── 项目记忆（.pilotcode/memory/ 中的事实、Bug、决策、Q&A）
```

### 四种搜索方式

#### 1. 语义搜索（默认）

理解自然语言描述，返回语义相关的代码：

```
/search "用户认证逻辑"
```

返回：
- `src/auth/middleware.py` - `authenticate_user()` 函数
- `src/api/login.py` - 登录路由处理
- `src/models/user.py` - User 模型验证方法

**技术实现**：使用代码嵌入向量 + 余弦相似度。当向量数 >100 时自动启用 numpy 批量矩阵乘法，搜索速度提升 5-10 倍。

#### 2. 符号搜索

精确查找类、函数、变量定义，利用 `symbols_by_name` 和 `symbols_by_file` 桶索引实现毫秒级 O(1) 精确匹配：

```
/search -s UserModel              # 查找 UserModel 类
/search -s authenticate_user      # 查找函数
/search -s API_BASE_URL          # 查找常量
```

**技术实现**：3-tier 策略 — 精确名称桶 → 文件路径桶 → 子字符串线性扫描。

#### 3. 正则搜索

使用正则表达式匹配代码：

```
/search -r "class.*View"          # 查找所有 View 类
/search -r "def test_"            # 查找测试函数
/search -r "TODO|FIXME"           # 查找待办事项
```

#### 4. 文件搜索

按文件名模式查找：

```
/search -f "*.py"                 # 查找 Python 文件
/search -f "src/**/*.go"          # 查找 src 下的 Go 文件
```

---

## 分层索引（大型项目）

对于超过 10 个文件的项目，PilotCode 自动构建**分层索引**，将代码库组织为可管理的子图（subgraph），避免大仓库首次查询时超出上下文窗口。

### 三层架构

| 层级 | 名称 | 内容 | 用途 |
|------|------|------|------|
| Tier 1 | Master Index | 项目概览 + 子图摘要（~2000 tokens） | LLM 首次了解项目结构 |
| Tier 2 | Subgraph Detail | 特定子图的详细符号列表 | 聚焦某个模块深入分析 |
| Tier 3 | Symbol Detail | 完整代码（通过 CodeSearch/CodeContext） | 查看具体实现 |

### 自动目录聚类

系统按目录结构将文件分组为子图：
- **最小 2 个文件/子图**，**最大 50 个文件/子图**
- 大目录按文件前缀自动拆分（如 `alpha_*.py` / `beta_*.py`）
- 小目录自动合并到父级或同级 misc 组

### 子图关系分析

自动识别：
- **核心子图**（被最多其他子图依赖）
- **共享模块**（高复用率的文件）
- **入口点**（主程序、CLI 入口）
- **导入/导出关系**（跨子图依赖）

### 使用分层索引

```bash
# 构建索引后，自动生成分层索引（>10 文件时）
/index full

# 查看项目总览（Tier 1）
# AI 自动在首次查询大型项目时获取 Master Index

# 聚焦特定子图深入分析（Tier 2）
# 在 CodeContext 中使用 subgraph 参数
CodeContext(query="路由逻辑", subgraph="src/router")
```

---

## 项目记忆知识库

PilotCode 在项目根目录的 `.pilotcode/memory/` 中维护一个本地知识库，自动将相关知识注入查询上下文（relevance_score=0.95）。

### 记忆类型

| 类别 | 用途 | 示例 |
|------|------|------|
| `fact` | 项目事实 | "使用 asyncio 处理所有 IO" |
| `bug` | 已知 Bug | "Race condition in cache, fixed by #123" |
| `decision` | 架构决策 | "选择 PostgreSQL 而非 MySQL" |
| `qa` | 常见问题 | "Q: 如何运行测试？A: pytest tests/" |

### 使用方式

记忆条目会在调用 `CodeContext` 或 `CodeSearch` 时**自动注入**，无需手动操作。也可以通过代码直接管理：

```python
from pilotcode.services.memory_kb import get_memory_kb

kb = get_memory_kb("/path/to/project")
kb.add_fact("所有 API 返回统一包装格式", tags=["api", "convention"])
kb.add_bug(symptom="偶发 502", root_cause="连接池耗尽", fix="增加 pool_size", files_involved=["db.py"])
kb.add_decision("使用 Redis 缓存", context="性能优化", options_considered=["Memcached", "Redis"], consequences="支持 pub/sub")
kb.add_qa("如何添加新命令？", answer="继承 BaseCommand 并注册到 COMMAND_MAP")
```

---

## 增量索引

### 双层变更检测

增量索引使用两层过滤确保高效且准确：

1. **mtime 快速层** — 对比文件修改时间，无变化则跳过读取（零 I/O）
2. **SHA256 准确层** — mtime 变化或首次索引时，计算内容哈希确认真实变更

### 自动清理

增量模式自动处理：
- **删除文件检测**：对比当前磁盘文件与已索引文件集合，自动移除被删除的文件及其符号、嵌入向量
- **旧向量清理**：重新索引文件前，自动调用 `delete_by_file_path` 清除该文件的旧嵌入，防止幽灵向量
- **max_files 修正**：增量模式始终扫描全部文件（`max_files` 仅在全量重建时生效），确保任何位置的修改都被发现

### 进度报告

对于预计超过 30 秒的索引任务，自动显示进度和 ETA：

```
[CodeIndex] Estimated indexing time: 45s for 485 files. Progress will be shown.
[CodeIndex] 100/485 (21%) ~35s remaining
```

也支持通过 `on_progress` 回调集成到 WebSocket/TUI 界面。

---

## 相关代码

### 核心模块

```
src/pilotcode/
├── services/
│   ├── codebase_indexer.py       # CodebaseIndexer - 统一索引管理
│   ├── code_index.py             # CodeIndex / CodeIndexer - 符号提取 + 桶索引
│   ├── embedding_service.py      # EmbeddingService / VectorStore - 语义向量 + numpy 批量搜索
│   ├── hierarchical_index.py     # HierarchicalIndexBuilder - 分层索引
│   ├── memory_kb.py              # ProjectMemoryKB - 项目记忆知识库
│   └── advanced_code_analyzer.py # 高级代码分析
├── tools/
│   ├── code_index_tool.py        # CodeIndexTool
│   ├── code_search_tool.py       # CodeSearchTool
│   └── code_context_tool.py      # CodeContextTool
├── commands/
│   ├── code_index_cmd.py         # /index 命令
│   └── code_search_cmd.py        # /search 命令
└── query_engine.py               # 查询引擎
```

### 关键类

```python
# 代码索引器
class CodebaseIndexer:
    SUPPORTED_EXTENSIONS = {
        ".py", ".js", ".jsx", ".ts", ".tsx",
        ".go", ".rs", ".java",
        ".cpp", ".c", ".h", ".hpp", ".cc", ".hh", ".cxx", ".hxx",
        # ... 更多扩展名
    }
    IGNORE_DIRS = {".git", "node_modules", "__pycache__", "build", "dist",
                   "extracted", "temp", "tmp", "*.o", "*.ko", "*.cmd", ...}

    async def index_codebase(self, incremental=True, max_files=None) -> CodebaseStats
    async def search(self, query: SearchQuery) -> List[CodeSnippet]
    def build_context(self, query, max_tokens, include_related, subgraph_filter, use_hierarchy)
    def get_master_index_text(self, max_subgraphs=None) -> str
    def get_subgraph_text(self, subgraph_id, max_symbols=100) -> str
    def list_subgraphs(self) -> List[dict]
    def get_stats(self) -> CodebaseStats
    def clear_index(self)
    def export_index(self, path: str)
    def import_index(self, path: str)

# 搜索查询
class SearchQuery:
    text: str                       # 搜索文本
    query_type: str                 # semantic | symbol | regex | file
    file_pattern: Optional[str]     # 文件过滤
    language: Optional[str]         # 语言过滤
    max_results: int = 10

# 代码片段
class CodeSnippet:
    file_path: str
    start_line: int
    end_line: int
    content: str
    language: str
    symbol_name: Optional[str]
    symbol_type: Optional[str]      # function | class | variable
    relevance_score: float
```

---

## 使用示例

### 构建索引

```bash
# 进入项目目录
cd /path/to/project

# 启动 PilotCode
./pilotcode

# 构建索引（自动选择增量或全量）
/index

# 查看索引状态
/index stats
```

### 搜索代码

```bash
# 语义搜索 - 找认证逻辑
/search "user authentication"

# 符号搜索 - 找 User 类
/search -s User

# 正则搜索 - 找所有 API 路由
/search -r "@router\.(get|post|put|delete)"

# 组合搜索 - Python 中的测试函数
/search -r "def test_" -l python

# 限制结果数
/search "database" -n 20
```

### 大型项目：聚焦子图分析

```bash
# 索引后，通过子图过滤深入特定模块
CodeContext(query="路由分发逻辑", subgraph="src/router")

# 或使用代码搜索聚焦子图
/search -f "src/router/*.py"
```

### 导出/导入索引

```bash
# 导出索引分享给团队
/index export team_index.json

# 团队成员导入
/index import team_index.json
```

---

## 与其他工具对比

| 特性 | PilotCode | Sourcegraph | GitHub Code Search | ripgrep |
|------|-----------|-------------|-------------------|---------|
| **语义搜索** | ✅ | ✅ | ❌ | ❌ |
| **符号搜索** | ✅ (O(1) 桶索引) | ✅ | ✅ | ❌ |
| **正则搜索** | ✅ | ✅ | ✅ | ✅ |
| **多语言** | 15+ (Tree-sitter + 正则) | 40+ | 10+ | 文本 |
| **本地索引** | ✅ | ❌ (云端) | ❌ | N/A |
| **增量更新** | ✅ (mtime + SHA256) | ✅ | N/A | N/A |
| **嵌入向量** | ✅ (numpy 批量加速) | ✅ | ❌ | ❌ |
| **分层索引** | ✅ | ❌ | ❌ | ❌ |
| **项目记忆** | ✅ | ❌ | ❌ | ❌ |
| **IDE 集成** | CLI / WebSocket | 网页/IDE | 网页 | CLI |

### 优势

1. **本地优先** - 代码索引存储在本地，保护隐私
2. **AI 集成** - 与 AI 代理深度集成，自动使用索引和项目记忆
3. **增量更新** - mtime + SHA256 双层过滤，高效准确；自动检测删除文件
4. **多搜索方式** - 语义 + 符号 + 正则，符号搜索通过桶索引实现毫秒级响应
5. **大型项目友好** - 分层索引避免大仓库首次查询溢出上下文窗口
6. **混合提取** - Python 正则高速提取，其他语言 Tree-sitter 精确提取

### 劣势

1. **语言覆盖** - 相比 Sourcegraph 语言支持较少（但核心语言覆盖完整）
2. **Web 界面** - 只有 CLI，没有网页界面
3. **团队协作** - 索引共享需要手动导出导入

---

## 技术实现

### 索引构建流程

```
1. 扫描项目目录
   ├── 优先使用 git ls-files（10-100x 快于 rglob）
   └── 非 git 项目使用 rglob 回退

2. 解析文件
   ├── Python: 高速正则提取 (~0.5ms/文件)
   ├── Go/Rust/Java/C/C++/JS/TS: Tree-sitter AST (~8ms/文件)
   └── 其他: 正则模式匹配 + 自动回退

3. 提取符号并构建桶索引
   ├── symbols_by_name: 名称 → 符号列表（O(1) 精确查找）
   └── symbols_by_file: 文件路径 → 符号列表

4. 生成嵌入
   └── 使用 Embedding Service（旧向量自动清理）

5. 存储索引
   └── 内存 + JSON 缓存（~/.cache/pilotcode/index_cache/）

6. 构建分层索引（>10 文件时）
   └── 目录聚类 → 子图摘要 → 导入/导出关系
```

### 搜索流程

```
语义搜索:
Query → Embedding → numpy 批量余弦相似度 (>100 向量) → 返回最相似的代码片段

符号搜索:
Query → 精确名称桶 (symbols_by_name) → 文件路径桶 (symbols_by_file) → 子字符串扫描 → 返回定义位置

正则搜索:
Query → 正则编译 → 全文扫描 → 返回匹配片段
```

---

## 最佳实践

### 1. 首次索引

```bash
# 进入项目根目录
cd /path/to/project

# 完整索引
/index full

# 查看统计确认成功
/index stats
```

### 2. 日常更新

```bash
# 代码变更后增量更新（自动检测变更、新增、删除）
/index

# 或设置 git hook 自动更新
echo './pilotcode -c "/index"' >> .git/hooks/post-commit
```

### 3. 搜索技巧

```bash
# 描述要找什么，而非具体代码
/search "handle user login"     # ✅ 好
/search "def login"             # ❌ 不够好

# 结合多种搜索
/search -s User                 # 找定义
/search "User authentication"   # 找用法

# 限定语言减少噪音
/search "routing" -l python

# 大型项目聚焦子图
CodeContext(query="支付逻辑", subgraph="src/payment")
```

### 4. 大型项目优化

```bash
# 排除不需要的目录
# 在项目根目录创建 .pilotcode.json
{
  "index_exclude": ["node_modules", "dist", ".git", "vendor"]
}
```

对于 Linux 内核级别的超大型项目（60k+ 文件）：
- 首次索引预计 10-20 分钟，内存约 1GB
- 分层索引自动启用，确保 LLM 首次查询不溢出
- 增量 "无变更" 扫描约 2.5 秒（受限于文件系统遍历）

---

## 相关文档

- [代码索引工具](../tools/code_index_tool.md)
- [代码搜索工具](../tools/code_search_tool.md)
- [代码上下文工具](../tools/code_context_tool.md)
- [大型项目分析指南](../guides/analyze-large-project.md)
