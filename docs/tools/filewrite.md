# FileWrite 工具

创建新文件并写入内容。

## 作用

- 创建新文件
- 写入生成的代码
- 创建配置文件
- 保存输出结果

## 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `path` | string | ✅ | 文件路径 |
| `content` | string | ✅ | 文件内容 |

## 使用示例

### 创建新文件

```python
FileWrite(
    path="hello.py",
    content='print("Hello, World!")'
)
```

### 写入生成的代码

```python
FileWrite(
    path="src/utils.py",
    content="""
def calculate_sum(a, b):
    \"\"\"Calculate sum of two numbers.\"\"\"\n    return a + b
"""
)
```

### 创建配置文件

```python
FileWrite(
    path="config.yaml",
    content="""
database:
  host: localhost
  port: 3306
  name: myapp
"""
)
```

## 使用场景

### 场景1：创建新模块

```python
# 创建新的 Python 模块
FileWrite(
    path="src/services/new_service.py",
    content="""
\"\"\"New service module.\"\"\"

class NewService:
    def __init__(self):
        pass
    
    def process(self, data):
        return data
"""
)
```

### 场景2：保存输出结果

```python
# 执行命令并保存结果
Bash(command="ls -la > /tmp/output.txt")
FileRead(path="/tmp/output.txt")

# 或直接写入
FileWrite(path="results.txt", content="Analysis complete")
```

### 场景3：创建测试文件

```python
FileWrite(
    path="test_example.py",
    content="""
import pytest

def test_addition():
    assert 1 + 1 == 2
"""
)
```

## 错误处理

| 错误 | 说明 | 解决 |
|------|------|------|
| File exists | 文件已存在 | 使用 FileEdit 修改 |
| Permission denied | 无权限 | 检查目录权限 |
| Directory not found | 目录不存在 | 先创建目录 |

## 注意事项

1. **文件已存在会失败**：这是保护机制，防止意外覆盖
2. **自动创建目录**：父目录不存在时会自动创建
3. **原子写入**：写入是原子操作，不会写入部分文件
4. **编码**：默认使用 UTF-8

## 与 FileEdit 的区别

| FileWrite | FileEdit |
|-----------|----------|
| 创建新文件 | 修改现有文件 |
| 文件已存在会失败 | 文件必须存在 |
| 写入完整内容 | 替换部分内容 |

## 相关工具

- **FileRead** - 读取文件
- **FileEdit** - 编辑文件
- **Bash** - 使用 shell 命令创建文件