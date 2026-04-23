# 开发工作流指南

本指南介绍如何使用 PilotCode 进行功能开发、代码测试和 Git 集成，实现高效的 AI 辅助开发流程。

---

## 概述

PilotCode 不仅是代码助手，更是完整的开发环境，支持：

- **功能开发** - 从需求到实现的 AI 辅助编程
- **代码测试** - 自动化测试生成和执行
- **Git 集成** - 版本控制、分支管理、PR 流程
- **代码审查** - AI 辅助代码审查

---

## 工作流概览

```
1. 需求理解 → 2. 设计讨论 → 3. 编码实现 → 4. 自动审查与测试 → 5. 代码提交
```

> **自动审查**：启用 `auto_review=true` 后，编码完成后系统会自动 Review 变更、运行相关测试，并在测试失败时自动生成修复指令。详见 [模型配置](../features/model-configuration.md)。

---

## 第一步：功能开发

### 1.1 理解需求

描述功能需求，让 AI 帮助分析：

```
我需要实现一个用户认证系统，包括：
- 用户注册和登录
- JWT Token 认证
- 密码加密存储
- 登录失败限制

请帮我设计这个系统的架构。
```

### 1.2 代码探索

使用搜索功能了解现有代码：

```
# 查找相关代码
/search authentication
/search -s User
/search -f "*auth*"

# 查看项目结构
/ls
/find *.py | head -20
```

### 1.3 设计方案

与 AI 讨论设计方案：

```
基于现有的代码结构，我认为：
1. 在 src/auth/ 目录实现认证模块
2. 使用现有的数据库模型
3. 集成到现有的中间件系统

你觉得这个方案如何？有什么建议？
```

### 1.4 生成代码

让 AI 生成初始代码：

```
请帮我实现 auth 模块的核心功能：
1. 创建 src/auth/models.py - 用户模型
2. 创建 src/auth/service.py - 认证逻辑
3. 创建 src/auth/middleware.py - JWT 验证中间件
4. 创建 src/auth/routes.py - API 路由

要求：
- 使用现有的数据库连接
- 遵循项目的代码风格
- 添加适当的错误处理
```

### 1.5 代码迭代

基于反馈迭代改进：

```
这段代码需要改进：
1. 添加输入验证
2. 优化错误消息
3. 添加日志记录

请修改 src/auth/service.py
```

---

## 第二步：代码测试

### 2.1 生成测试用例

```
请为 src/auth/service.py 生成单元测试：
1. 测试正常登录流程
2. 测试错误密码处理
3. 测试 Token 生成和验证
4. 测试边界条件

使用 pytest 框架，放在 tests/test_auth.py
```

### 2.2 运行测试

```
# 运行所有测试
/bash command="pytest"

# 运行特定测试
/bash command="pytest tests/test_auth.py -v"

# 运行并显示覆盖率
/bash command="pytest --cov=src/auth --cov-report=html"
```

### 2.3 分析测试结果

```
测试失败了，请分析原因：
```
<粘贴错误输出>
```

请修复代码或测试。
```

### 2.4 补充测试

```
覆盖率报告显示这些行未被测试：
- src/auth/service.py:45-50
- src/auth/middleware.py:23

请为这些内容补充测试用例。
```

---

## 第三步：Git 集成

### 3.1 查看状态

```
# 查看工作区状态
/git status

# 查看修改的文件
/git diff --name-only

# 查看具体修改
/git diff src/auth/service.py
```

### 3.2 创建分支

```
# 创建功能分支
/git checkout -b feature/user-auth

# 查看分支列表
/git branch -a

# 切换到主分支
/git checkout main
```

### 3.3 提交代码

```
# 查看修改
请帮我总结这次修改的内容，生成提交信息。

# 添加文件到暂存区
/git add src/auth/
/git add tests/test_auth.py

# 提交
/git commit -m "feat: implement user authentication system

- Add user registration and login
- Implement JWT token authentication
- Add password hashing with bcrypt
- Include rate limiting for login attempts
- Add comprehensive unit tests"
```

### 3.4 同步远程

```
# 拉取最新代码
/git pull origin main

# 推送分支
/git push origin feature/user-auth

# 查看远程分支
/git remote -v
```

### 3.5 分支合并

```
# 方式1：使用 merge
/git checkout main
/git pull origin main
/git merge feature/user-auth

# 方式2：使用 rebase
/git checkout feature/user-auth
/git rebase main
/git checkout main
/git merge feature/user-auth
```

### 3.6 处理冲突

遇到冲突时：

```
冲突文件：src/models/user.py

请帮我解决这个合并冲突，保留两边的修改。
```

---

## 第四步：Pull Request 流程

### 4.1 创建 PR

```
请帮我创建 Pull Request：

标题：Implement User Authentication System

描述：
- 实现了用户注册和登录功能
- 使用 JWT 进行身份验证
- 添加了密码加密和登录限制
- 包含完整的单元测试

请检查代码并提交到 GitHub。
```

或使用命令：

```
/github pr create --title "feat: user auth" --body "Implementation details..."
```

### 4.2 代码审查

**自动审查（推荐）**：

启用自动审查后，每次编码完成系统会自动：
1. 审查变更的代码质量
2. 从 `git diff` 提取相关测试文件并运行
3. 测试失败时自动生成修复指令

```bash
# 启用自动审查
/config set auto_review true
/config set max_review_iterations 3
```

自动审查流程：
```
编码完成 → 自动 Review → 运行相关测试 → 测试通过 → 继续
                                    ↓
                              测试失败 → 提取错误 → 生成 Redesign 指令 → LLM 修复
```

**手动审查**：

```
请审查 src/auth/ 目录的代码：
1. 代码风格是否符合项目规范
2. 是否有潜在的安全问题
3. 错误处理是否完善
4. 是否有性能问题
```

### 4.3 处理 Review 意见

**自动修复**：

如果自动审查发现了问题，系统会以 SystemMessage 形式插入修复指令：
```
🚨 TESTS FAILED — Your changes must be revised.

=== Test Errors ===
FAIL: test_auth ...
AssertionError: expected 200 but got 401

=== Redesign Instructions ===
1. Re-read the failing test and ALL code it exercises.
2. Use Grep to find every call site of the function you changed.
3. Produce a COMPLETELY REVISED fix.
```

LLM 会自动根据指令修复问题，最多循环 `max_review_iterations` 轮。

**手动处理**：

```
Reviewer 提出了这些意见：
1. 建议添加 docstring
2. 密码复杂度检查需要加强
3. 测试覆盖率需要提高

请修改代码。
```

### 4.4 合并 PR

```
# PR 审查通过后合并
/github pr merge 123

# 或手动合并
/git checkout main
/git merge feature/user-auth
/git push origin main
```

---

## 第五步：高级工作流

### 5.1 提交信息规范

使用约定式提交：

```
<type>(<scope>): <subject>

<body>

<footer>
```

示例：
```
feat(auth): implement JWT token refresh

- Add token refresh endpoint
- Implement refresh token rotation
- Add token blacklist for logout

Closes #123
```

类型说明：
- `feat` - 新功能
- `fix` - 修复
- `docs` - 文档
- `style` - 代码格式
- `refactor` - 重构
- `test` - 测试
- `chore` - 构建/工具

### 5.2 分支策略

Git Flow 工作流：

```
main        - 生产分支
  ↑
develop     - 开发分支
  ↑
feature/*   - 功能分支
  ↑
hotfix/*    - 紧急修复
  ↑
release/*   - 发布分支
```

常用命令：

```
# 开始新功能
/git checkout -b feature/new-feature develop

# 完成功能
/git checkout develop
/git merge --no-ff feature/new-feature
/git branch -d feature/new-feature

# 创建发布
/git checkout -b release/1.0.0 develop

# 发布完成
/git checkout main
/git merge --no-ff release/1.0.0
/git tag -a v1.0.0
```

### 5.3 代码审查清单

提交前检查：

```
请检查以下清单：
□ 代码可以正常运行
□ 测试全部通过
□ 没有 debug 代码（print/console.log）
□ 错误处理完善
□ 文档已更新
□ 提交信息规范
```

### 5.4 自动化脚本

创建快捷命令：

```python
# .pilotcode_scripts.py
SCRIPTS = {
    "test": "pytest -xvs",
    "lint": "flake8 src/ && black --check src/",
    "format": "black src/ && isort src/",
    "coverage": "pytest --cov=src --cov-report=html",
}
```

使用：

```
/run test      # 运行测试
/run lint      # 代码检查
/run format    # 格式化代码
```

---

## 第六步：实战示例

### 场景：开发新 API 端点

```
# 1. 创建分支
/git checkout -b feature/add-user-api

# 2. 查看现有代码
/search API endpoint
/read src/api/routes/user.py

# 3. 实现功能
请帮我添加用户列表 API：
- GET /api/users - 获取用户列表
- 支持分页和搜索
- 需要管理员权限

# 4. 生成测试
请为新的 API 端点生成测试。

# 5. 运行测试
/bash command="pytest tests/api/test_users.py -v"

# 6. 代码审查
请审查刚才添加的代码。

# 7. 提交代码
/git add .
/git commit -m "feat(api): add user list endpoint with pagination

- Add GET /api/users endpoint
- Support pagination and search
- Add admin permission check
- Include comprehensive tests"

# 8. 推送并创建 PR
/git push origin feature/add-user-api

# 9. 合并
/git checkout main
/git merge feature/add-user-api
/git push origin main
```

---

## 常用命令速查

### Git 命令

```
/git status              # 查看状态
/git log --oneline -10   # 查看提交历史
/git diff                # 查看修改
/git add <file>          # 添加文件
/git commit -m "msg"     # 提交
/git push                # 推送
/git pull                # 拉取
/git checkout -b <name>  # 创建分支
/git merge <branch>      # 合并分支
/git stash               # 暂存修改
/git stash pop           # 恢复暂存
```

### GitHub 命令

```
/github pr list          # 列出 PR
/github pr create        # 创建 PR
/github pr view 123      # 查看 PR
/github pr merge 123     # 合并 PR
/github issue list       # 列出 Issues
```

### 测试命令

```
/pytest                  # 运行测试
/pytest -xvs             # 详细输出
/pytest --cov            # 覆盖率
/pytest -k test_name     # 指定测试
```

---

## 最佳实践

### 1. 小步提交

- 每次提交只做一件事
- 提交信息清晰描述变更
- 频繁提交，及时推送

### 2. 分支管理

- 主分支保持可发布状态
- 功能开发在独立分支
- 及时删除已合并分支

### 3. 测试驱动

- 先写测试，再写实现
- 保持高测试覆盖率
- 自动化测试检查

### 4. 代码审查

- 提交前自我审查
- 关注代码质量和安全
- 及时处理 Review 意见

---

## 相关文档

- [大型项目代码分析](./analyze-large-project.md)
- [LLM 接口设置](./llm-setup.md)
- [Git 命令参考](../commands/git.md)
