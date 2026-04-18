# AI辅助编程工具的架构框架：以 Claude Code 与 PilotCode 为例

## 1. 引言

AI辅助编程工具（AI Coding Assistants）是一类以大语言模型（LLM）为核心推理引擎，通过工具调用（Tool Use / Function Calling）与开发者环境交互的软件系统。它们不只是"代码补全"，而是能够理解代码库结构、执行多步骤任务、读写文件、运行命令的**自主编程代理（Autonomous Coding Agents）**。

本文以 **Claude Code**（Anthropic 官方 CLI 工具）和 **PilotCode**（开源 SWE-bench 评估框架）的源代码为实例，剖析这类工具的通用架构、核心组件及其与大模型的协作关系。

---

## 2. 通用架构框架

所有现代 AI 辅助编程工具都遵循一个统一的**感知-推理-行动循环（Perception-Reasoning-Action Loop）**：

```
┌─────────────────────────────────────────────────────────────┐
│                      大语言模型 (LLM)                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐  │
│  │  System     │    │  User       │    │  Tool Results   │  │
│  │  Prompt     │───→│  Prompt     │───→│  (Observation)  │  │
│  └─────────────┘    └─────────────┘    └─────────────────┘  │
│           ↑                                    ↓              │
│           └──────── 生成 Tool Calls ───────────┘              │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      工具执行层 (Tool Executor)                │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────────┐ │
│  │ FileRead│  │FileWrite│  │  Bash   │  │  CodeSearch     │ │
│  └─────────┘  └─────────┘  └─────────┘  └─────────────────┘ │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────────┐ │
│  │ FileEdit│  │  Grep   │  │  Glob   │  │  Git Diff       │ │
│  └─────────┘  └─────────┘  └─────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      状态管理层 (State Manager)                │
│         消息历史、文件系统状态、权限上下文、会话状态            │
└─────────────────────────────────────────────────────────────┘
```

### 2.1 核心设计原则

1. **LLM 不直接操作环境**：LLM 只输出文本和工具调用指令，实际的环境操作（文件读写、命令执行）由工具层完成。这是安全隔离的基础。
2. **消息历史是状态核心**：整个会话的状态由 `messages: List[Message]` 表示，包含 system prompt、user input、assistant responses、tool results。LLM 通过读取消息历史来"记忆"上下文。
3. **工具是能力的延伸**：工具的丰富程度决定了代理的能力边界。没有 Bash 工具就不能运行测试，没有 FileEdit 工具就不能修改代码。
4. **权限控制是安全闸门**：每个工具调用都需要权限管理器的批准（尤其在交互模式下），防止意外破坏。

---

## 3. 核心组件详解

### 3.1 查询引擎（Query Engine）

Query Engine 是连接 LLM 与工具层的**中央调度器**。它负责：
- 将消息历史发送给 LLM API
- 解析 LLM 返回的文本和工具调用（Tool Calls）
- 分发工具调用给 Tool Executor
- 将工具执行结果重新注入消息历史

**Claude Code 的实现**（`src/query.ts` / `QueryEngine.ts`）：
```typescript
// 简化的核心循环
async submit_message(prompt: string, options?: QueryOptions) {
  this.messages.push(user_message(prompt))
  const response = await this.llm.chat(this.messages, options)
  
  for (const tool_call of response.tool_calls) {
    const result = await this.tool_executor.execute(tool_call)
    this.messages.push(tool_message(result))
  }
  
  return response
}
```

**PilotCode 的实现**（`src/pilotcode/query_engine.py`）：
```python
class QueryEngine:
    def __init__(self, config: QueryEngineConfig):
        self.messages: list[Message] = []
        self.tools = config.tools
        self.model_client = get_model_client()
    
    async def submit_message(self, prompt: str, options=None):
        self.messages.append(UserMessage(content=prompt))
        response = await self.model_client.chat_completion(
            messages=self.messages,
            tools=self.tools,
        )
        # 解析 tool_calls，执行，将结果注入 messages
```

### 3.2 工具层（Tool Layer）

工具层定义了代理能够执行的原子操作。按功能可分为：

| 类别 | 工具示例 | 作用 |
|------|---------|------|
| **文件读写** | `FileRead`, `FileWrite`, `FileEdit`, `ApplyPatch` | 与代码文件交互 |
| **代码搜索** | `Glob`, `Grep`, `CodeSearch`, `CodeContext` | 在代码库中定位信息 |
| **命令执行** | `Bash`, `PowerShell` | 运行测试、编译、git 命令 |
| **版本控制** | `GitDiff`, `GitStatus`, `GitLog` | 查看代码变更 |
| **项目索引** | `CodeIndex` | 构建代码库的符号索引 |
| **协作代理** | `Agent` | 启动子代理并行处理任务 |

**Claude Code** 的工具注册系统（`src/tools/registry.ts`）：
```typescript
// 每个工具都是一个类，包含 name, description, parameters, execute 方法
class FileReadTool extends Tool<FileReadInput, FileReadOutput> {
  name = "FileRead"
  description = "Read the contents of a file"
  
  async execute(input: FileReadInput): Promise<FileReadOutput> {
    const content = await fs.readFile(input.file_path, "utf-8")
    return { content }
  }
}

// 全局注册
register_tool(FileReadTool)
```

**PilotCode** 的工具注册系统（`src/pilotcode/tools/registry.py`）：
```python
class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}
    
    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
    
    def get_all(self) -> list[Tool]:
        return list(self._tools.values())

# 各工具模块在导入时自动注册
register_tool(FileReadTool())
register_tool(FileEditTool())
```

### 3.3 权限管理（Permission Manager）

权限管理器控制哪些工具可以在什么条件下执行。这是防止意外破坏的关键防线。

**Claude Code** 采用多级权限：
- `ALWAYS_ALLOW`：只读工具（FileRead, Grep）自动通过
- `NEEDS_APPROVAL`：写操作需要用户确认
- `NEVER_ALLOW`：危险操作（`rm -rf /`）直接拒绝

**PilotCode** 的 headless 模式使用 `auto_allow=True`，所有工具自动通过，适用于自动化评估场景。

### 3.4 状态与消息管理（State & Messages）

消息历史是代理的"记忆"。每次 LLM 调用都需要完整的 messages 作为输入。

**关键问题：上下文窗口限制**
- Claude Code 使用**消息压缩（Compaction）**：当消息过长时，将旧消息压缩为摘要，保留关键信息
- PilotCode 使用**消息截断（Compression）**：`_compress_messages_for_retry` 在 retry 时只保留 system message 和失败摘要

**Claude Code 的附件系统（Attachments）**：
```typescript
// 在特定时机向消息流中注入额外上下文
attachments = [
  { type: "plan_mode", planFilePath: "/tmp/plan.md" },
  { type: "skills", skills: ["python", "django"] },
  { type: "codebase_index", index: {...} },
]
```

---

## 4. 与大模型的关系

### 4.1 LLM 是推理引擎，不是执行引擎

LLM 的核心作用是：
1. **理解用户意图**：将自然语言描述转化为可执行的计划
2. **选择工具**：根据当前状态决定调用哪个工具、传入什么参数
3. **综合结果**：将工具执行结果解读为下一步行动或最终答案

LLM **不直接**：
- 读取文件（它调用 FileRead 工具）
- 执行命令（它调用 Bash 工具）
- 修改代码（它调用 FileEdit 工具）

这种分离使得：
- **可审计**：所有操作都有日志记录
- **可撤销**：工具层可以实现回滚
- **可限制**：通过禁用某些工具来限制 LLM 的能力范围

### 4.2 模型客户端（Model Client）

模型客户端负责与 LLM API 通信，处理：
- 消息格式化（OpenAI、Anthropic、本地 GGUF 等格式）
- 流式响应（Streaming）
- 工具调用解析（从 assistant message 中提取 `tool_calls`）

**PilotCode 的 ModelClient**（`src/pilotcode/utils/model_client.py`）：
```python
class ModelClient:
    def __init__(self, api_key=None, base_url=None, model=None):
        config = get_global_config()
        self.base_url = base_url or config.base_url  # http://172.19.201.40:3530/
        self.model = model or config.default_model
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=300.0)
    
    async def chat_completion(self, messages, tools=None, stream=True):
        # 转换为 OpenAI API 格式
        # 处理流式/非流式响应
        # 解析 choices[0].delta / choices[0].message
```

### 4.3 工具描述作为 LLM 的"能力说明书"

LLM 通过工具的 JSON Schema 描述来了解自己能做什么。这些描述被注入到 system prompt 中：

```json
{
  "type": "function",
  "function": {
    "name": "FileEdit",
    "description": "Edit a file by replacing a specific string with another",
    "parameters": {
      "type": "object",
      "properties": {
        "file_path": {"type": "string"},
        "old_string": {"type": "string"},
        "new_string": {"type": "string"}
      }
    }
  }
}
```

工具的 `description` 质量直接影响 LLM 的使用效果。描述越精确，LLM 调用越准确。

---

## 5. Claude Code 架构深度分析

### 5.1 多代理架构（Multi-Agent Architecture）

Claude Code 的一个核心创新是**内置代理（Built-in Agents）**：

```typescript
// src/tools/AgentTool/built-in/
EXPLORE_AGENT    // 只读代码库探索
PLAN_AGENT       // 只读架构设计
VERIFICATION_AGENT // 只读验证测试
```

每个代理有独立的：
- **System Prompt**：定义代理的角色和行为约束
- **工具白名单/黑名单**：Explore Agent 禁用 FileEdit/FileWrite
- **模型配置**：Explore Agent 可用轻量级模型（Haiku）加速

**Explore Agent 的 Prompt 核心约束**：
```
=== CRITICAL: READ-ONLY MODE - NO FILE MODIFICATIONS ===
You are STRICTLY PROHIBITED from:
- Creating new files
- Modifying existing files
- Deleting files
- Moving or copying files
```

### 5.2 Plan Mode（规划模式）

Plan Mode 是 Claude Code 的核心工作流，分为 5 个阶段：

```
Phase 1: Explore    → 并行启动 1-3 个 Explore Agent 搜索代码库
Phase 2: Design     → 启动 Plan Agent 设计实现方案
Phase 3: Review     → 审查 plan，向用户澄清问题
Phase 4: Final Plan → 将 plan 写入 plan file（唯一可编辑的文件）
Phase 5: Exit       → 调用 ExitPlanMode 请求用户批准
```

**关键设计**：Plan Mode 中 LLM **只能编辑 plan file**，不能修改任何项目文件。这强制模型在动手写代码前先完成思考，避免边想边改导致的混乱。

### 5.3 Verification Agent（验证代理）

Verification Agent 是一个专门用于**对抗性测试**的子代理：

```
System Prompt: "Your job is not to confirm the implementation works — 
                it's to try to break it."
```

它按变更类型采取不同的验证策略：
- **Frontend**：启动 dev server → 浏览器自动化 → curl 子资源
- **Backend**：curl 端点 → 验证响应 shape → 测试错误处理
- **Bug Fix**：复现原始 bug → 验证修复 → 回归测试

**强制输出格式**：每个检查必须包含 `Command run` 和 `Output observed`，不能只读代码下结论。

---

## 6. PilotCode 架构深度分析

### 6.1 Headless 自动反馈循环

PilotCode 面向 **SWE-bench 自动化评估**，核心模式是无人值守的 headless 执行：

```python
# run_headless_with_feedback 的核心逻辑
async def run_headless_with_feedback(prompt, max_rounds=3, max_iterations=25):
    for round in range(max_rounds):
        result = await run_headless(prompt, max_iterations=max_iterations)
        
        patch = get_git_diff()
        
        if patch is empty:
            # 空 patch → 压缩消息，retry
            messages = compress_messages(messages)
            prompt = EMPTY_PATCH_PROMPT
            continue
            
        if has_syntax_errors(patch):
            # 语法错误 → 压缩消息，retry
            messages = compress_messages(messages)
            prompt = SYNTAX_ERROR_PROMPT.format(errors=errors)
            continue
            
        # patch 有效，但还有剩余 round → review
        if round < max_rounds - 1:
            messages = compress_messages(messages)
            prompt = REVIEW_PROMPT
            continue
            
    return result
```

### 6.2 Planning Mode with Auto-Fallback

PilotCode 的 planning mode 是 Claude Code 的简化自动化版本：

```python
async def run_headless_with_planning(prompt, max_iterations=25):
    # Step 1: Planning（只读模式）
    plan = await run_headless(planning_prompt, read_only=True)
    
    # Step 2: Plan Validation
    is_valid, issues = validate_plan(plan, cwd)
    if not is_valid:
        # Plan 引用不存在的文件 → fallback 到 direct execution
        return await run_headless(fallback_prompt)
    
    # Step 3: Execution
    for attempt in range(max_plan_attempts):
        result = await run_headless(execution_prompt)
        
        # Step 4: Verification
        verification = await run_headless(verification_prompt)
        if verification.complete:
            break
        else:
            # 有遗漏 → 下一轮修复
            execution_prompt += missing_items
```

**与 Claude Code 的关键差异**：
| 特性 | Claude Code | PilotCode |
|------|------------|-----------|
| 用户交互 | 交互式，需用户批准 | Headless，全自动 |
| Plan Mode | 用户触发，严格只读 | 自动分类触发，只读规划 |
| 验证 | Verification Agent（对抗性） | 自动 verification（15 turn）|
| 权限 | 多级权限，需确认 | auto_allow，全部通过 |
| 消息压缩 | 智能 compaction + attachment | 简单压缩 + 发现摘要 |

### 6.3 代码索引与向量存储

PilotCode 包含一个**代码库索引器（CodebaseIndexer）**，用于加速大规模代码库的搜索：

```python
class CodebaseIndexer:
    def __init__(self, root_path):
        self.root_path = root_path
        self._indexed_files: set[str] = set()
        self._file_hashes: dict[str, str] = {}
        self._symbol_indexer = CodeIndexer()
        # 缓存路径：~/.cache/pilotcode/index_cache/<hash>.json
        self._cache_path = cache_dir / f"{hash(root_path)}.json"
    
    async def index_codebase(self, incremental=True):
        # 遍历文件，提取符号，计算 hash
        # 增量更新：只索引变更的文件
        
    def export_index(self, output_path):
        # 保存索引到外部缓存（避免污染 git diff）
```

**关键优化**：索引缓存放在 `~/.cache/pilotcode/` 而不是项目根目录，防止被 `git diff` 捕获。

---

## 7. 关键设计差异对比

| 维度 | Claude Code | PilotCode |
|------|------------|-----------|
| **目标场景** | 日常开发，人机协作 | SWE-bench 自动化评估 |
| **交互模式** | 交互式 TUI | Headless，无人工干预 |
| **Plan Mode 触发** | 用户主动 `/plan` 或模型建议 | 自动复杂度分类（文件数 > 150 → PLAN）|
| **Planning 权限** | 严格只读，禁用所有写工具 | 只读模式，plan validation 校验 |
| **Agents** | Explore/Plan/Verification 代理 | 单一 REPL + 自动 feedback loop |
| **消息压缩** | 智能 compaction + plan_mode attachment | Round summary + 发现摘要 |
| **验证机制** | Verification Agent（对抗性测试）| 自动 diff + syntax check + test run |
| **权限控制** | 多级权限（Always/Ask/Never）| auto_allow（评估场景全开）|
| **索引缓存** | 无内置索引（依赖工具搜索）| CodebaseIndexer + VectorStore |
| **与大模型关系** | 云端 API（Claude）| 本地 GGUF（Qwen3-Coder-30B）|

---

## 8. 总结

AI辅助编程工具的架构可以概括为**"LLM 作为大脑，工具作为四肢"**的代理系统：

1. **大模型是推理核心**，负责理解意图、选择工具、综合结果，但不直接接触环境。
2. **工具层定义能力边界**，工具的丰富程度和描述质量直接决定代理的上限。
3. **消息历史是状态载体**，所有上下文都通过消息传递，上下文窗口管理是核心工程挑战。
4. **权限控制是安全底线**，尤其在交互式场景中，必须防止意外破坏。

Claude Code 代表了**生产级交互式工具**的成熟设计：多代理分工、Plan Mode 工作流、严格的权限控制。PilotCode 代表了**自动化评估框架**的工程实践：headless 反馈循环、plan validation、代码索引优化。两者共享同一套底层架构，但在交互模式、验证深度和部署场景上有显著差异。

理解这些架构，对于构建自己的 AI 编程代理、评估现有工具的能力边界、或优化特定场景下的性能，都有重要参考价值。
