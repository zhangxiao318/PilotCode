# PowerShell 工具

执行 PowerShell 命令（跨平台）。

## 作用

- 执行 PowerShell 命令
- Windows 系统管理
- 跨平台脚本执行
- 访问 PowerShell 特定功能

## 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `command` | string | ✅ | PowerShell 命令 |
| `timeout` | integer | ❌ | 超时时间（秒） |

## 使用示例

### Windows 系统

```python
# 查看系统信息
PowerShell(command="Get-ComputerInfo")

# 查看进程
PowerShell(command="Get-Process | Select-Object -First 10")

# 查看服务
PowerShell(command="Get-Service | Where-Object {$_.Status -eq 'Running'}")
```

### 跨平台

```python
# PowerShell 也支持 Linux/macOS
PowerShell(command="Get-Date")
PowerShell(command="Get-Location")
```

## 使用场景

### 场景1：Windows 系统管理

```python
# 查看系统信息
PowerShell(command="Get-ComputerInfo | Select-Object WindowsVersion, TotalPhysicalMemory")

# 查看磁盘空间
PowerShell(command="Get-Volume | Select-Object DriveLetter, SizeRemaining, Size")
```

### 场景2：文件操作

```python
# 递归列出文件
PowerShell(command="Get-ChildItem -Recurse -File | Select-Object -First 20")

# 查看文件内容（大文件）
PowerShell(command="Get-Content log.txt -TotalCount 100")
```

### 场景3：网络操作

```python
# 测试连接
PowerShell(command="Test-NetConnection -ComputerName google.com -Port 80")

# 查看网络配置
PowerShell(command="Get-NetIPAddress | Select-Object IPAddress")
```

## 与 Bash 的区别

| Bash | PowerShell |
|------|------------|
| Unix 风格 | Windows 风格 |
| `ls` | `Get-ChildItem` |
| `cat` | `Get-Content` |
| `grep` | `Select-String` |
| `ps` | `Get-Process` |

## 优势

1. **对象管道**：PowerShell 传递对象而非文本
2. **Windows 集成**：深度集成 Windows 管理功能
3. **跨平台**：PowerShell Core 支持 Linux/macOS

## 相关工具

- **Bash** - Unix Shell 执行