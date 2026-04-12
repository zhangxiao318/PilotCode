# Todo 工具

待办事项管理工具。

## 作用

- 创建任务列表
- 跟踪工作进度
- 管理多步骤任务

## 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `todos` | list | ✅ | 待办事项列表 |

## Todo 项格式

```python
{
    "id": "1",
    "content": "任务内容",
    "status": "pending",  # pending, in_progress, done
    "priority": "high"    # high, medium, low
}
```

## 使用示例

### 创建待办列表

```python
TodoWrite(todos=[
    {"id": "1", "content": "分析需求", "status": "done"},
    {"id": "2", "content": "设计架构", "status": "in_progress"},
    {"id": "3", "content": "编写代码", "status": "pending"}
])
```

### 更新状态

```python
TodoWrite(todos=[
    {"id": "1", "content": "分析需求", "status": "done"},
    {"id": "2", "content": "设计架构", "status": "done"},
    {"id": "3", "content": "编写代码", "status": "in_progress"}
])
```

## 使用场景

### 场景1：复杂任务规划

```python
# 分析任务后创建计划
TodoWrite(todos=[
    {"id": "1", "content": "读取现有代码", "status": "done"},
    {"id": "2", "content": "设计新功能", "status": "in_progress"},
    {"id": "3", "content": "实现核心逻辑", "status": "pending"},
    {"id": "4", "content": "编写测试", "status": "pending"}
])
```

### 场景2：跟踪进度

```python
# 更新完成的任务
TodoWrite(todos=[
    {"id": "1", "content": "步骤1", "status": "done"},
    {"id": "2", "content": "步骤2", "status": "done"}
])
```

## 输出格式

```
Todo List (2/4 done):
✅ [1] 分析需求
✅ [2] 设计架构
⏳ [3] 编写代码 (in_progress)
⬜ [4] 编写测试 (pending)
```

## 最佳实践

1. **开始复杂任务前**创建待办列表
2. **定期更新**状态
3. **完成后清理**已完成的待办