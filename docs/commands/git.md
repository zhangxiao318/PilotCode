# /git 命令

Git 操作命令，用于执行常见的 Git 操作。

## 作用

- 执行 Git 命令
- 查看 Git 状态
- 管理版本控制操作

## 基本用法

```bash
/git [subcommand] [options]
```

## 常用子命令

| 子命令 | 说明 | 示例 |
|--------|------|------|
| `status` | 查看状态 | `/git status` |
| `log` | 查看提交历史 | `/git log -5` |
| `diff` | 查看修改 | `/git diff` |
| `branch` | 分支操作 | `/git branch` |
| `add` | 添加文件 | `/git add .` |
| `commit` | 提交更改 | `/git commit -m "message"` |
| `push` | 推送到远程 | `/git push` |
| `pull` | 拉取更新 | `/git pull` |

## 使用示例

### 查看 Git 状态

```bash
/git status
```

输出示例：
```
On branch main
Your branch is up to date with 'origin/main'.

Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   src/main.py

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	new_file.py
```

### 查看提交历史

```bash
# 最近5次提交
/git log -5

# 简化格式
/git log --oneline -10
```

### 查看修改

```bash
# 查看未暂存的修改
/git diff

# 查看已暂存的修改
/git diff --staged

# 查看特定文件的修改
/git diff src/main.py
```

### 分支操作

```bash
# 列出所有分支
/git branch

# 创建新分支
/git branch feature/new-feature

# 切换分支
/git checkout feature/new-feature

# 创建并切换
/git checkout -b feature/new-feature
```

### 提交更改

```bash
# 添加所有修改
/git add .

# 提交
/git commit -m "Add new feature"

# 添加并提交（如果支持）
/git commit -am "Fix bug"
```

### 推送到远程

```bash
# 推送到当前分支
/git push

# 推送到特定分支
/git push origin main

# 首次推送新分支
/git push -u origin feature/new-feature
```

### 拉取更新

```bash
# 拉取当前分支更新
/git pull

# 拉取特定分支
/git pull origin main
```

## 使用场景

### 场景1：提交代码

```bash
# 查看修改
/git status

# 添加文件
/git add src/main.py

# 提交
/git commit -m "Fix authentication bug"

# 推送
/git push
```

### 场景2：查看历史

```bash
# 查看最近提交
/git log --oneline -10

# 查看某个文件的修改历史
/git log -p src/main.py
```

### 场景3：分支管理

```bash
# 查看当前分支
/git branch

# 创建功能分支
/git checkout -b feature/login

# 开发完成后合并回主分支
/git checkout main
/git merge feature/login
```

## 与 Bash 执行 Git 的区别

两种方式都可以执行 Git 命令：

```bash
# 方式1：使用 /git 命令
/git status

# 方式2：使用 /bash 命令
/bash command="git status"
```

`/git` 命令的优势：
- 更简洁的语法
- 可能提供更友好的输出格式
- 集成到 PilotCode 的输出系统

## 注意事项

1. **权限**：确保有执行 Git 操作的权限
2. **配置**：确保 Git 已正确配置用户名和邮箱
3. **网络**：推送/拉取需要网络连接

## 相关命令

- `/bash` - 执行任意 shell 命令
- `/diff` - 查看文件差异（简化版）
- `/branch` - 分支管理（简化版）