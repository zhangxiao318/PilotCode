# Agent 工具

子 Agent 工具，用于并行或独立任务。

## 作用

- 创建子 Agent 执行任务
- 并行处理多个任务
- 独立上下文避免干扰

## 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `description` | string | ✅ | 任务描述 |
| `prompt` | string | ✅ | 具体任务提示 |

## 使用示例

### 并行分析

```python
# 分析多个文件
Agent(
    description="Analyze utils.py",
    prompt="Read src/utils.py and analyze its structure"
)

Agent(
    description="Analyze config.py",
    prompt="Read src/config.py and analyze its structure"
)
```

### 独立任务

```python
Agent(
    description="Write tests",
    prompt="Write unit tests for the UserService class"
)
```

## 使用场景

### 场景1：并行分析多个模块

```python
# 同时分析多个文件
Agent(description="Analyze auth module", prompt="...")
Agent(description="Analyze db module", prompt="...")
Agent(description="Analyze api module", prompt="...")
```

### 场景2：独立开发任务

```python
Agent(
    description="Implement feature",
    prompt="Implement the login feature in auth.py"
)
```

## 与 Task 的区别

| Agent | Task |
|-------|------|
| 智能体执行 | 后台执行 |
| 有上下文 | 简单任务 |
| 可交互 | 一次性 |

## 相关工具

- **TaskCreate** - 创建后台任务