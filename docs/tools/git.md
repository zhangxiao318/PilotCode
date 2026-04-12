# Git 工具

Git 版本控制工具。

## 工具列表

| 工具 | 说明 |
|------|------|
| **GitStatus** | 查看状态 |
| **GitDiff** | 查看修改 |
| **GitLog** | 提交历史 |
| **GitBranch** | 分支操作 |

## GitStatus

查看工作区状态。

```python
GitStatus()
```

输出：
```
On branch main
Changes not staged for commit:
  modified: src/main.py
Untracked files:
  new_file.py
```

## GitDiff

查看修改内容。

```python
# 查看未暂存的修改
GitDiff()

# 查看已暂存的修改
GitDiff(staged=True)
```

## GitLog

查看提交历史。

```python
# 最近5次提交
GitLog(limit=5)

# 简化格式
GitLog(oneline=True)
```

## GitBranch

分支操作。

```python
# 列出分支
GitBranch()

# 创建分支
GitBranch(name="feature/new", create=True)

# 切换分支
GitBranch(name="feature/new", switch=True)
```

## 使用场景

### 场景1：提交代码

```python
# 1. 查看状态
GitStatus()

# 2. 查看修改
GitDiff()

# 3. 使用 Bash 提交
Bash(command="git add . && git commit -m 'Update'")
```

### 场景2：查看历史

```python
GitLog(limit=10)
```

### 场景3：分支管理

```python
# 查看分支
GitBranch()

# 创建功能分支
GitBranch(name="feature/login", create=True)
```

## 与 /git 命令的区别

| Git 工具 | /git 命令 |
|----------|-----------|
| 程序化调用 | 交互式使用 |
| 返回结构化数据 | 格式化输出 |
| 适合脚本 | 适合手动操作 |

## 对应的命令

- `/git` - 更方便的 Git 命令

## 相关工具

- **Bash** - 执行任意 git 命令