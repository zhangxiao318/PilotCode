# Bash 工具

执行 Bash/Shell 命令。

## 作用

- 执行 shell 命令
- 运行脚本
- 调用系统工具
- 文件操作（ls, cat, cp, mv 等）

## 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `command` | string | ✅ | 要执行的命令 |
| `timeout` | integer | ❌ | 超时时间（秒），默认 300 |

## 使用示例

### 基本命令

```python
Bash(command="ls -la")
Bash(command="pwd")
Bash(command="date")
```

### 运行脚本

```python
Bash(command="python3 script.py")
Bash(command="bash run_tests.sh")
```

### 文件操作

```python
# 列出目录
Bash(command="ls -la src/")

# 查看文件信息
Bash(command="wc -l src/main.py")

# 查找文件
Bash(command="find . -name '*.py' | head -10")
```

### 带超时

```python
Bash(command="sleep 10", timeout=5)
```

## 使用场景

### 场景1：运行测试

```python
Bash(command="python3 -m pytest tests/")
Bash(command="python3 -m pytest tests/test_main.py -v")
```

### 场景2：Git 操作

```python
Bash(command="git status")
Bash(command="git log --oneline -5")
Bash(command="git diff")
```

### 场景3：构建项目

```python
Bash(command="make build")
Bash(command="pip3 install -r requirements.txt")
```

### 场景4：系统信息

```python
Bash(command="df -h")      # 磁盘空间
Bash(command="free -m")    # 内存使用
Bash(command="ps aux")     # 进程列表
```

## 输出格式

```
$ ls -la
总用量 128
drwxrwxr-x  8 user user  4096  4月 12 10:00 .
drwxrwxr-x  5 user user  4096  4月 10 09:00 ..
-rw-rw-r--  1 user user  2456  4月 12 09:30 README.md
```

## 安全提示

1. **危险命令会提示**：删除、格式化等危险操作需要确认
2. **只读命令自动允许**：ls, cat, pwd 等自动执行
3. **超时保护**：防止命令卡住

## 错误处理

| 错误 | 说明 |
|------|------|
| Command not found | 命令不存在 |
| Exit code non-zero | 命令执行失败 |
| Timeout | 超时 |
| Permission denied | 权限不足 |

## 平台差异

| Linux/macOS | Windows |
|-------------|---------|
| `ls` | `dir` |
| `cat` | `type` |
| `rm` | `del` |
| `cp` | `copy` |
| `pwd` | `cd` |

**建议使用**：使用跨平台命令或检查系统类型。

## 与 /git 命令的区别

| Bash | /git |
|------|------|
| `Bash(command="git status")` | `/git status` |
| 通用性强 | Git 专用 |
| 输出原始文本 | 格式化输出 |

## 相关工具

- **PowerShell** - Windows PowerShell 执行
- **/git** - Git 专用命令
- **FileRead** - 读取命令输出文件