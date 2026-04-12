# /index 命令

代码库索引管理命令，用于建立和维护代码索引，支持智能代码搜索。

## 作用

建立代码库的索引，包括：
- 提取代码符号（类、函数、变量等）
- 生成语义向量（用于自然语言搜索）
- 分析代码结构和依赖关系

建立索引后，可以使用 `/search` 命令进行快速、智能的代码搜索。

## 基本用法

```bash
/index [subcommand]
```

## 子命令

| 子命令 | 说明 |
|--------|------|
| (无) | 增量索引，只索引变化的文件 |
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
/index
```

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

# 增量更新索引
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
| Python | `.py`, `.pyw`, `.pyi` | ✅ 完整支持 |
| C | `.c`, `.h` | ✅ 完整支持 |
| C++ | `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hh`, `.hxx` | ✅ 完整支持 |
| JavaScript | `.js`, `.jsx`, `.mjs` | ✅ 完整支持 |
| TypeScript | `.ts`, `.tsx` | ✅ 完整支持 |
| Go | `.go` | ✅ 完整支持 |
| Rust | `.rs` | ✅ 完整支持 |
| Java | `.java` | ✅ 完整支持 |
| 其他 | `.rb`, `.php`, `.swift`, `.kt` | ⚠️ 基础支持 |

## 性能说明

| 项目规模 | 首次索引时间 | 增量索引时间 |
|----------|-------------|-------------|
| 小项目 (<100文件) | 10-30秒 | 1-3秒 |
| 中项目 (100-1000文件) | 1-3分钟 | 5-15秒 |
| 大项目 (1000+文件) | 3-10分钟 | 10-30秒 |

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

# 如果异常缓慢，尝试清除后重建
/index clear
/index full
```

### 某些文件未被索引

```bash
# 检查文件是否在忽略列表中
# 默认忽略：.git, node_modules, __pycache__, build, dist 等

# 检查文件扩展名是否支持
/index stats
```

## 相关命令

- `/search` - 使用索引进行代码搜索
- `/pwd` - 显示当前工作目录
- `/ls` - 列出目录内容

## 注意事项

1. **首次使用必须先索引**：没有索引时，`/search` 会提示先运行 `/index`
2. **索引占用内存**：大项目的索引会占用一定内存（约10-50MB每千文件）
3. **索引不自动更新**：代码变化后需要手动运行 `/index` 更新
4. **每个项目独立索引**：不同目录的索引相互独立

## 技术细节

索引存储在内存中，包含：
- **符号索引**：类、函数、变量等的名称和位置
- **语义向量**：用于自然语言搜索的代码嵌入
- **文件元数据**：语言类型、行数、修改时间等

可以通过 `/index export` 导出为 JSON 文件，用于备份或在团队间共享。