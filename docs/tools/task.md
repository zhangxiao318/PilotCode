# Task 工具

后台任务管理工具。

## 工具列表

| 工具 | 说明 |
|------|------|
| **TaskCreate** | 创建任务 |
| **TaskList** | 列出任务 |
| **TaskGet** | 获取任务详情 |
| **TaskStop** | 停止任务 |
| **TaskUpdate** | 更新任务 |

## TaskCreate

创建后台任务。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `description` | string | 任务描述 |
| `command` | string | 要执行的命令 |

### 示例

```python
TaskCreate(
    description="Run tests",
    command="python -m pytest tests/"
)
```

## TaskList

列出所有任务。

```python
TaskList()
```

## TaskGet

获取任务详情。

```python
TaskGet(task_id="task_123")
```

## TaskStop

停止任务。

```python
TaskStop(task_id="task_123")
```

## 使用场景

### 场景1：长时间运行的测试

```python
# 创建测试任务
TaskCreate(description="Run all tests", command="pytest -xvs tests/")

# 继续做其他事情...

# 查看任务状态
TaskList()
```

### 场景2：并行处理

```python
# 启动多个任务
TaskCreate(description="Task 1", command="...")
TaskCreate(description="Task 2", command="...")

# 监控进度
TaskList()
```

## 对应的命令

- `/tasks` - 更方便的任务管理命令