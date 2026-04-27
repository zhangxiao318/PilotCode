# /index 命令

代码库索引管理命令，用于建立和维护代码索引，支持智能代码搜索。

## 作用

建立代码库的索引，包括：
- 提取代码符号（类、函数、变量等）
- 生成语义向量（用于自然语言搜索）
- 分析代码结构和依赖关系
- **自动构建分层索引**（>10 文件时生成项目概览和子图）
- **自动维护项目记忆知识库**（`.pilotcode/memory/`）

建立索引后，可以使用 `/search` 命令进行快速、智能的代码搜索。

## 基本用法

```bash
/index [subcommand]
```

## 子命令

| 子命令 | 说明 |
|--------|------|
| (无) | 增量索引，只索引变化的文件（推荐日常使用） |
| `full` | 完整重新索引所有文件 |
| `stats` | 显示索引统计信息 |
| `clear` | 清除所有索引数据 |
| `export` | 导出索引到文件 |
| `import` | 从文件导入索引 |

## 使用示例

### 首次索引项目

```bash
# 完整索引整个项目
/index full
```

输出示例：
```
🗂️  Performing full reindex in: /home/user/myproject
📁 Found 369 source files to index
⏳ Starting full reindex...

✅ Full reindex complete!

📊 Statistics:
  Files indexed: 369
  Symbols: 3574
  Snippets: 1777

📝 Top Languages:
  python: 350 files
  cpp: 15 files
  c: 4 files
```

### 日常增量索引

```bash
# 只索引变化的文件（推荐日常使用）
# 自动检测新增、修改、删除的文件
/index
```

增量索引特点：
- 使用 **mtime + SHA256 双层过滤** 快速跳过未变更文件
- 自动清理被删除文件的符号和嵌入向量
- 重新索引前自动清除旧嵌入，防止幽灵向量
- 扫描所有文件以发现任何位置的变更（不受 max_files 限制）

### 查看索引状态

```bash
/index stats
```

输出示例：
```
📊 Index Statistics

Files: 369
Symbols: 3574
Snippets: 1777
Last Indexed: 2026-04-12 09:29:03

Languages:
  python: 369 files

Hierarchical Index: 8 subgraphs
  Core: src/core (45 files)
  API: src/api (32 files)
  Utils: src/utils (28 files)
  ...
```

### 清除索引

```bash
/index clear
```

### 导出和导入索引

```bash
# 导出索引（用于备份或共享）
/index export

# 导出到指定路径
/index export /path/to/index.json

# 导入索引
/index import

# 从指定路径导入
/index import /path/to/index.json
```

## 使用场景

### 场景1：新项目首次使用

```bash
# 1. 进入项目目录
/cd /path/to/project

# 2. 建立完整索引
/index full

# 3. 确认索引成功
/index stats

# 4. 开始使用搜索
/search authentication
```

### 场景2：代码变化后更新索引

```bash
# 拉取新代码后
git pull

# 增量更新索引（自动检测变更、新增、删除）
/index

# 确认更新
/index stats
```

### 场景3：定期重建索引

```bash
# 每周或每月重建一次，清理过期数据
/index clear
/index full
```

## 支持的编程语言

| 语言 | 扩展名 | 符号提取 |
|------|--------|----------|
| Python | `.py`, `.pyw`, `.pyi` | ✅ 高速正则 (~0.5ms/文件) |
| C | `.c`, `.h` | ✅ Tree-sitter AST |
| C++ | `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hh`, `.hxx` | ✅ Tree-sitter AST |
| JavaScript | `.js`, `.jsx`, `.mjs` | ✅ Tree-sitter AST |
| TypeScript | `.ts`, `.tsx` | ✅ Tree-sitter AST |
| Go | `.go` | ✅ Tree-sitter AST |
| Rust | `.rs` | ✅ Tree-sitter AST |
| Java | `.java` | ✅ Tree-sitter AST |
| 其他 | `.rb`, `.php`, `.swift`, `.kt` | ⚠️ 正则基础支持 |

## 性能说明

| 项目规模 | 首次索引时间 | 增量索引时间 |
|----------|-------------|-------------|
| 小项目 (<100文件) | 5-20秒 | <1秒 |
| 中项目 (100-1000文件) | 30秒-2分钟 | 2-10秒 |
| 大项目 (1000-5000文件) | 2-8分钟 | 5-20秒 |
| 超大项目 (5000+文件) | 10-20分钟 | 10-30秒 |

> 性能基于混合提取策略：Python 正则 ~3ms/文件，Tree-sitter ~12ms/文件。对于 Linux 内核级项目（60k 文件），首次索引约 10-20 分钟，内存约 1GB。

### 进度报告

对于预计超过 30 秒的索引任务，自动显示进度和剩余时间：

```
[CodeIndex] Estimated indexing time: 45s for 485 files. Progress will be shown.
[CodeIndex] 100/485 (21%) ~35s remaining
[CodeIndex] 200/485 (41%) ~18s remaining
```

## 故障排除

### 索引为0个文件

```bash
# 检查当前目录
/pwd

# 检查是否有源代码文件
/ls

# 检查支持的文件类型
/bash command="find . -name '*.py' -o -name '*.cpp' -o -name '*.js' | head -10"

# 重新索引
/index full
```

### 索引很慢

```bash
# 大项目首次索引慢是正常的
# 后续使用增量索引会快很多

# 检查是否在忽略目录中创建了文件
# 默认忽略：.git, node_modules, __pycache__, build, dist, temp, tmp, *.o, *.ko 等

# 如果异常缓慢，尝试清除后重建
/index clear
/index full
```

### 某些文件未被索引

```bash
# 检查文件是否在忽略列表中
# 默认忽略：.git, node_modules, __pycache__, build, dist 等
# 以及 C/C++ 构建产物：*.o, *.ko, *.cmd, *.mod, *.mod.c

# 检查文件扩展名是否支持
/index stats
```

### 删除的文件仍出现在搜索结果中

```bash
# 运行增量索引，自动检测并清理已删除文件
/index

# 或完全重建
/index clear
/index full
```

## 相关命令

- `/search` - 使用索引进行代码搜索
- `/pwd` - 显示当前工作目录
- `/ls` - 列出目录内容

## 注意事项

1. **首次使用必须先索引**：没有索引时，`/search` 会提示先运行 `/index`
2. **索引占用内存**：大项目的索引会占用一定内存（约10-50MB每千文件）
3. **索引不自动更新**：代码变化后需要手动运行 `/index` 更新（可配合 git hook）
4. **每个项目独立索引**：不同目录的索引相互独立
5. **分层索引自动构建**：超过 10 个文件时自动生成分层索引，便于大型项目分析
