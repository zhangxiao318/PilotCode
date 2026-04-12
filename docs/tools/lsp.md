# LSP 工具

语言服务器协议工具。

## 作用

- 代码智能提示
- 跳转到定义
- 查找引用
- 代码诊断

## 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `action` | string | ✅ | 操作类型 |
| `file_path` | string | ✅ | 文件路径 |
| `line` | integer | ❌ | 行号 |
| `column` | integer | ❌ | 列号 |

## Action 类型

| Action | 说明 |
|--------|------|
| `definition` | 跳转到定义 |
| `references` | 查找引用 |
| `hover` | 悬停信息 |
| `diagnostics` | 代码诊断 |
| `completion` | 代码补全 |

## 使用示例

### 跳转到定义

```python
LSP(
    action="definition",
    file_path="src/main.py",
    line=10,
    column=5
)
```

### 查找引用

```python
LSP(
    action="references",
    file_path="src/main.py",
    line=15,
    column=10
)
```

### 代码诊断

```python
LSP(
    action="diagnostics",
    file_path="src/main.py"
)
```

## 使用场景

### 场景1：理解代码

```python
# 找到函数定义
LSP(action="definition", file_path="main.py", line=20, column=8)
```

### 场景2：重构

```python
# 查找所有引用
LSP(action="references", file_path="utils.py", line=10, column=5)
```

### 场景3：代码质量

```python
# 检查代码问题
LSP(action="diagnostics", file_path="main.py")
```

## 前提条件

需要安装对应语言的 LSP 服务器：

| 语言 | LSP 服务器 |
|------|-----------|
| Python | pylsp, pyright |
| JavaScript/TypeScript | typescript-language-server |
| Rust | rust-analyzer |
| Go | gopls |

## 相关工具

- **CodeSearch** - 代码搜索
- **Grep** - 文本搜索