# Agent 系统

PilotCode 的 Agent 系统支持多代理协作，通过不同的编排模式解决复杂任务。

---

## 概述

Agent 系统允许创建多个专门的 AI 代理，它们可以：
- **独立工作** - 每个代理有自己的上下文和工具
- **协作配合** - 通过消息传递共享信息
- **层级管理** - 父子代理关系形成树形结构
- **状态持久化** - 代理状态可保存和恢复

---

## 功能特性

### 7 种预定义代理类型

| 类型 | 用途 | 特点 |
|------|------|------|
| **coder** | 代码编写 | 擅长编程、重构、调试 |
| **debugger** | 调试分析 | 专注于问题诊断和修复 |
| **explainer** | 代码解释 | 解释复杂代码和架构 |
| **tester** | 测试编写 | 生成测试用例和测试代码 |
| **reviewer** | 代码审查 | 审查代码质量和风格 |
| **planner** | 任务规划 | 分解复杂任务为子任务 |
| **explorer** | 代码探索 | 快速探索代码库结构 |

### 4 种工作流编排模式

#### 1. 顺序模式 (Sequential)

```
Task → Agent 1 → Agent 2 → Agent 3 → Result
```

代理按顺序执行，每个代理的输出作为下一个代理的输入。

**适用场景**：
- 代码审查流程（编写 → 审查 → 修复）
- 文档生成（分析 → 撰写 → 润色）

```python
# 使用命令
/workflow sequential "实现用户认证" --agents "planner,coder,reviewer"
```

#### 2. 并行模式 (Parallel)

```
         ┌→ Agent 1 →┐
Task → ┼→ Agent 2 →┼→ Merge → Result
         └→ Agent 3 →┘
```

多个代理同时工作，结果合并后返回。

**适用场景**：
- 多文件同时修改
- 多种方案并行探索

```python
# 使用命令
/workflow parallel "优化性能" --agents "coder-1,coder-2,coder-3"
```

#### 3. 监督者模式 (Supervisor)

```
          ┌→ Agent 1 →┐
Task → Supervisor ←→ Agent 2 → Result
          └→ Agent 3 →┘
```

监督者代理协调多个工作代理，分配任务并整合结果。

**适用场景**：
- 复杂项目开发
- 需要协调的团队合作

```python
# 使用命令
/workflow supervisor "开发新功能" --supervisor "planner" --workers "coder,tester,reviewer"
```

#### 4. 辩论模式 (Debate)

```
Task → Agent 1 (观点A) →
       Agent 2 (观点B) → Judge → Result
       Agent 3 (观点C) →
```

多个代理从不同角度分析问题，由裁判代理综合结论。

**适用场景**：
- 架构决策
- 技术选型
- 复杂问题分析

```python
# 使用命令
/workflow debate "选择数据库" --agents "advocate-sql,advocate-nosql,judge"
```

---

## 相关代码

### 核心模块

```
src/pilotcode/
├── agent/
│   ├── agent_manager.py          # AgentManager - 代理生命周期管理
│   ├── agent_orchestrator.py     # AgentOrchestrator - 工作流编排
│   ├── agent_types.py            # 代理类型定义
│   ├── workflow_engine.py        # 工作流引擎
│   └── persistence.py            # 代理状态持久化
├── tools/
│   └── agent_tools.py            # AgentTool, TeamCreate, SendMessage 等
└── commands/
    └── agent_commands.py         # /agents, /workflow 命令
```

### 关键类

```python
# Agent 定义
class Agent:
    id: str                         # 唯一标识
    name: str                       # 代理名称
    agent_type: AgentType           # 代理类型
    status: AgentStatus             # 状态 (PENDING, RUNNING, COMPLETED, FAILED)
    parent_id: Optional[str]        # 父代理ID
    children: List[str]             # 子代理列表
    context: Dict[str, Any]         # 代理上下文
    messages: List[Message]         # 消息历史

# AgentManager - 管理代理生命周期
class AgentManager:
    def create_agent(self, agent_type: str, name: str, ...) -> Agent
    def delete_agent(self, agent_id: str) -> bool
    def get_agent(self, agent_id: str) -> Optional[Agent]
    def list_agents(self) -> List[Agent]
    def get_agent_tree(self, root_id: str) -> AgentTree

# AgentOrchestrator - 工作流编排
class AgentOrchestrator:
    async def execute_sequential(self, agents: List[Agent], task: str) -> Result
    async def execute_parallel(self, agents: List[Agent], task: str) -> Result
    async def execute_supervisor(self, supervisor: Agent, workers: List[Agent], task: str) -> Result
    async def execute_debate(self, agents: List[Agent], judge: Agent, topic: str) -> Result
```

---

## 使用示例

### 创建代理

```bash
# 创建单个代理
/agents create --type coder --name "backend-dev" --prompt "You are a backend developer..."

# 查看代理列表
/agents list

# 查看代理详情
/agents show <agent-id>

# 查看代理树
/agents tree <agent-id>
```

### 执行工作流

```bash
# 顺序工作流
/workflow sequential "实现登录功能" --agents "planner,coder,tester"

# 并行工作流
/workflow parallel "重构代码" --agents "coder-1,coder-2"

# 监督者工作流
/workflow supervisor "开发API" --supervisor "architect" --workers "coder,tester,reviewer"

# 辩论工作流
/workflow debate "选择框架" --agents "advocate-react,advocate-vue,judge"
```

### 代理间通信

```python
# Agent A 发送消息给 Agent B
SendMessage(to_agent="agent-b", message="分析完成，结果如下...")

# Agent B 接收消息
ReceiveMessage(from_agent="agent-a")
```

---

## 与其他工具对比

| 特性 | PilotCode | AutoGPT | LangChain | CrewAI |
|------|-----------|---------|-----------|--------|
| **预定义类型** | 7种 | 无 | 无 | 多种角色 |
| **编排模式** | 4种 | 单代理循环 | 链式/图 | 顺序/层级 |
| **父子关系** | ✅ | ❌ | ❌ | ✅ |
| **状态持久化** | ✅ | ✅ | ❌ | ❌ |
| **消息传递** | ✅ | ❌ | ✅ | ✅ |
| **工作流可视化** | 基础 | 基础 | 完整 | 基础 |

### 优势

1. **专门化代理** - 预定义的代理类型针对编码场景优化
2. **灵活编排** - 4种模式覆盖常见协作场景
3. **层级管理** - 父子关系支持复杂任务分解
4. **集成度** - 与代码索引、Git 等深度集成

### 劣势

1. **通用性** - 相比 LangChain 更专注于编码场景
2. **可视化** - 工作流可视化不如专业工具完善

---

## 最佳实践

### 1. 选择合适的代理类型

```
编写代码 → coder
调试问题 → debugger
审查代码 → reviewer
理解代码 → explainer
规划任务 → planner
探索项目 → explorer
编写测试 → tester
```

### 2. 合理分解任务

```
# 好的分解
"设计架构" → planner
"实现模块A" → coder
"实现模块B" → coder
"编写测试" → tester
"代码审查" → reviewer

# 不好的分解（太细）
"编写第1行代码" → coder
"编写第2行代码" → coder
```

### 3. 使用监督者模式处理复杂任务

```
Supervisor (architect)
  ├─ Worker 1: 设计数据库
  ├─ Worker 2: 设计API
  ├─ Worker 3: 设计前端
  └─ Worker 4: 编写测试
```

---

## 相关文档

- [Agent 命令参考](../commands/agents.md)
- [工作流命令参考](../commands/workflow.md)
- [Hook 系统](./hook-system.md)
