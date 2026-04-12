# 代码索引与搜索

PilotCode 的代码索引系统提供高效的代码库理解和搜索能力，支持语义搜索、符号搜索和正则搜索。

---

## 概述

代码索引系统通过分析源代码，构建可快速查询的索引，使 AI 能够：
- **理解项目结构** - 快速了解大型代码库
- **精准定位代码** - 通过语义或符号查找相关代码
- **分析依赖关系** - 理解代码间的调用关系
- **跨语言支持** - 支持多种编程语言

---

## 功能特性

### 支持的编程语言

| 语言 | 符号提取 | 语义索引 | 扩展名 |
|------|----------|----------|--------|
| Python | ✅ | ✅ | .py, .pyi |
| JavaScript/TypeScript | ✅ | ✅ | .js, .jsx, .ts, .tsx |
| Go | ✅ | ✅ | .go |
| Rust | ✅ | ✅ | .rs |
| Java | ✅ | ✅ | .java |
| C/C++ | ✅ | ✅ | .c, .h, .cpp, .hpp, .cc, .hh, .cxx, .hxx |
| Ruby | ✅ | ✅ | .rb |
| PHP | ✅ | ✅ | .php |
| Swift | ✅ | ✅ | .swift |
| Kotlin | ✅ | ✅ | .kt |

### 索引内容

```
📁 代码索引包含：
├── 文件元数据（路径、语言、行数）
├── 符号定义（类、函数、变量）
├── 代码片段（可搜索的代码块）
├── 嵌入向量（语义搜索用）
└── 关系图谱（调用关系）
```

### 三种搜索方式

#### 1. 语义搜索（默认）

理解自然语言描述，返回语义相关的代码：

```
/search "用户认证逻辑"
```

返回：
- `src/auth/middleware.py` - `authenticate_user()` 函数
- `src/api/login.py` - 登录路由处理
- `src/models/user.py` - User 模型验证方法

**技术实现**：使用代码嵌入向量 + 余弦相似度

#### 2. 符号搜索

精确查找类、函数、变量定义：

```
/search -s UserModel              # 查找 UserModel 类
/search -s authenticate_user      # 查找函数
/search -s API_BASE_URL          # 查找常量
```

**技术实现**：基于 AST 分析的符号表查询

#### 3. 正则搜索

使用正则表达式匹配代码：

```
/search -r "class.*View"          # 查找所有 View 类
/search -r "def test_"            # 查找测试函数
/search -r "TODO|FIXME"           # 查找待办事项
```

---

## 相关代码

### 核心模块

```
src/pilotcode/
├── services/
│   ├── codebase_indexer.py       # CodebaseIndexer - 索引管理
│   ├── code_index.py             # CodeIndex - 符号提取
│   ├── embedding_service.py      # 嵌入向量服务
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
    
    async def index_codebase(self, incremental=True) -> IndexStats
    async def search(self, query: SearchQuery) -> List[CodeSnippet]
    def get_stats(self) -> IndexStats
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

# 构建索引
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
| **符号搜索** | ✅ | ✅ | ✅ | ❌ |
| **正则搜索** | ✅ | ✅ | ✅ | ✅ |
| **多语言** | 15+ | 40+ | 10+ | 文本 |
| **本地索引** | ✅ | ❌ (云端) | ❌ | N/A |
| **增量更新** | ✅ | ✅ | N/A | N/A |
| **嵌入向量** | ✅ | ✅ | ❌ | ❌ |
| **IDE 集成** | CLI | 网页/IDE | 网页 | CLI |

### 优势

1. **本地优先** - 代码索引存储在本地，保护隐私
2. **AI 集成** - 与 AI 代理深度集成，自动使用索引
3. **增量更新** - 只索引变更文件，高效快速
4. **多搜索方式** - 语义 + 符号 + 正则，覆盖不同场景

### 劣势

1. **语言覆盖** - 相比 Sourcegraph 语言支持较少
2. **Web 界面** - 只有 CLI，没有网页界面
3. **团队协作** - 索引共享需要手动导出导入

---

## 技术实现

### 索引构建流程

```
1. 扫描项目目录
   └── 识别支持的源文件

2. 解析文件
   ├── Python: AST 解析
   ├── C/C++: 正则 + 简单解析
   └── 其他: 正则模式匹配

3. 提取符号
   ├── 类定义
   ├── 函数定义
   ├── 变量定义
   └── 导入关系

4. 生成嵌入
   └── 使用 Embedding Service

5. 存储索引
   └── JSON 文件或内存
```

### 搜索流程

```
语义搜索:
Query → Embedding → 向量相似度计算 → 返回最相似的代码片段

符号搜索:
Query → 符号表查询 → 精确匹配 → 返回定义位置

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
# 代码变更后增量更新
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
```

### 4. 大型项目优化

```bash
# 排除不需要的目录
# 在项目根目录创建 .pilotcode.json
{
  "index_exclude": ["node_modules", "dist", ".git", "vendor"]
}
```

---

## 相关文档

- [代码索引工具](../tools/code_index_tool.md)
- [代码搜索工具](../tools/code_search_tool.md)
- [大型项目分析指南](../guides/analyze-large-project.md)
