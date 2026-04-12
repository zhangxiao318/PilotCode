# FileEdit 工具

编辑现有文件，支持搜索替换。

## 作用

- 修改现有文件
- 搜索并替换文本
- 添加新代码到文件
- 删除代码

## 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `path` | string | ✅ | 文件路径 |
| `old_string` | string | ✅ | 要替换的文本 |
| `new_string` | string | ✅ | 新文本 |

## 使用示例

### 修改函数实现

```python
FileEdit(
    path="src/main.py",
    old_string="def add(a, b):\n    return a + b",
    new_string="def add(a, b):\n    \"\"\"Add two numbers.\"\"\"\n    return a + b"
)
```

### 添加新导入

```python
FileEdit(
    path="src/main.py",
    old_string="import os",
    new_string="import os\nimport sys"
)
```

### 删除代码

```python
FileEdit(
    path="src/main.py",
    old_string="# TODO: Remove this\nprint('debug')",
    new_string=""
)
```

## 使用场景

### 场景1：重构代码

```python
# 1. 先读取文件查看内容
FileRead(path="src/utils.py", limit=50)

# 2. 修改特定函数
FileEdit(
    path="src/utils.py",
    old_string="def old_func(x):\n    return x * 2",
    new_string="def new_func(x):\n    \"\"\"Double the input.\"\"\"\n    return x * 2"
)
```

### 场景2：添加新功能

```python
# 在类中添加新方法
FileEdit(
    path="src/services/user.py",
    old_string="class UserService:\n    def get_user(self, id):\n        pass",
    new_string="class UserService:\n    def get_user(self, id):\n        pass\n    \n    def delete_user(self, id):\n        pass"
)
```

### 场景3：修复 Bug

```python
FileEdit(
    path="src/calc.py",
    old_string="result = a / b",
    new_string="result = a / b if b != 0 else 0"
)
```

## 匹配规则

1. **精确匹配**：`old_string` 必须完全匹配（包括空格和换行）
2. **唯一匹配**：文件中只能有一处匹配，否则会失败
3. **多行支持**：可以匹配跨越多行的文本

## 错误处理

| 错误 | 说明 | 解决 |
|------|------|------|
| File not found | 文件不存在 | 使用 FileWrite 创建 |
| No match found | 未找到匹配文本 | 检查 `old_string` |
| Multiple matches | 多处匹配 | 使用更具体的匹配文本 |

## 最佳实践

### 1. 先读取再编辑

```python
# 先读取了解文件结构
FileRead(path="src/main.py")

# 再进行编辑
FileEdit(path="src/main.py", old_string="...", new_string="...")
```

### 2. 使用唯一标识

```python
# 好的做法：使用函数签名作为标识
FileEdit(
    path="main.py",
    old_string="def process_data(data):",
    new_string="def process_data(data: dict):"
)
```

### 3. 复杂编辑分步进行

```python
# 步骤1：添加导入
FileEdit(path="main.py", old_string="import os", new_string="import os\nimport json")

# 步骤2：修改函数
FileEdit(path="main.py", old_string="def load():", new_string="def load() -> dict:")
```

## 相关工具

- **FileRead** - 读取文件
- **FileWrite** - 创建新文件
- **Grep** - 查找文本位置