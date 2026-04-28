# E2E 测试说明

PilotCode 的端到端（E2E）测试覆盖 LLM 推理、工具调用、WebSocket 通信、会话管理等完整链路。测试框架分为 **三层诊断架构**，可系统区分失败根因是 LLM 能力不足还是 PilotCode 框架问题。

---

## 目录结构

```
tests/e2e/
├── websocket/                    # Layer 3: 完整端到端（WebSocket）
│   ├── client.py                 # WebSocket 测试客户端
│   ├── conftest.py               # WebSocket 测试 fixture
│   ├── test_websocket_e2e.py     # 37 个 WebSocket E2E 用例
│   └── cases/                    # JSON 格式的测试用例数据
│       ├── simple_tasks.json
│       ├── complex_tasks.json
│       └── tool_behavior.json
└── model_capability/             # Layer 1 & 2: 模型能力诊断
    ├── conftest.py               # bare_llm_client / model_capability_client fixture
    ├── engine_helper.py          # QueryEngine + ToolExecutor 完整执行循环
    ├── diagnostics.py            # 失败归因诊断引擎
    ├── analyze_results.py        # JUnit XML 结果分析脚本
    ├── README.md                 # 能力测试框架说明
    ├── test_bare_llm/            # Layer 1: 裸 LLM 能力（零工具）
    │   ├── helpers.py            # strip_thinking() 等共享工具
    │   ├── test_code_understanding.py
    │   ├── test_code_generation.py
    │   ├── test_instruction_following.py
    │   └── test_script_generation.py   # 完整脚本生成能力
    ├── test_tool_capability/     # Layer 2: LLM + 工具调用
    │   ├── test_tool_selection.py
    │   ├── test_task_planning.py
    │   └── test_code_editing.py
    ├── test_instruction_following.py   # Layer 2: 指令遵循（中文场景）
    ├── test_context_retention.py       # Layer 2: 多轮上下文保持
    └── test_function_calling.py        # Layer 2: 工具参数精度
```

---

## 三层诊断框架

```
Layer 1 (Bare LLM)       -> 直接调用 model_client，无工具，无框架
Layer 2 (LLM + Tools)    -> QueryEngine + ToolExecutor，完整工具循环
Layer 3 (E2E WebSocket)  -> 完整 PilotCode 系统（含 LoopGuard、心跳、权限等）
```

### 归因规则

| Layer 1 | Layer 2 | Layer 3 | 根因归因 |
|---------|---------|---------|----------|
| FAIL    | —       | —       | **LLM 基础能力弱**（代码理解/生成/指令遵循） |
| PASS    | FAIL    | —       | **LLM function calling 弱** 或 **PilotCode 工具实现问题** |
| PASS    | PASS    | FAIL    | **PilotCode 框架问题**（LoopGuard / 超时 / 上下文压缩 / 系统提示词） |

> 详见 `tests/e2e/model_capability/diagnostics.py` 中的 `diagnose_failure()` 函数。

---

## 运行方式

### 前置条件

1. **LLM 后端服务已启动**（默认 `http://172.19.202.70:8080/v1`）
2. **WebSocket 服务端已启动**（如需运行 Layer 3）
   ```bash
   python -m pilotcode --web --web-port 8080
   ```

### 运行命令

> **Layer 1 可完全独立运行** — 不需要启动 WebSocket 服务器，不需要 QueryEngine，只需要模型 API 可访问。

```bash
# 1. 默认跳过（不运行 LLM 测试，快速回归）
pytest tests/e2e/ -v

# 2. 启用 LLM E2E 测试（需要 --run-llm-e2e 开关）
pytest tests/e2e/ --run-llm-e2e -v

# 3. 仅运行 Layer 1（裸模型能力，最快，零框架依赖）
#    无需启动 WebSocket 服务器，直接调用模型 API
pytest tests/e2e/model_capability/test_bare_llm/ --run-llm-e2e -v

# 4. 仅运行 Layer 2（工具调用能力）
#    同样无需启动 WebSocket 服务器，QueryEngine + ToolExecutor 在测试进程内运行
pytest tests/e2e/model_capability/test_tool_capability/ --run-llm-e2e -v

# 5. 仅运行 Layer 3（WebSocket 端到端）
pytest tests/e2e/websocket/ --run-llm-e2e -v

# 6. 自定义超时（默认 120s/180s）
pytest tests/e2e/ --run-llm-e2e --e2e-timeout 300 -v

# 7. 指定 WebSocket 端口（默认 8081）
pytest tests/e2e/websocket/ --run-llm-e2e --ws-port 18081 -v

# 8. 生成 JUnit XML 并自动分析（推荐完整回归）
pytest tests/e2e/ --run-llm-e2e --e2e-timeout=240 \
    --junitxml=/tmp/e2e_results.xml && \
    python tests/e2e/analyze_results.py /tmp/e2e_results.xml

# 9. 通过 /config 命令直接运行（交互式环境）
/config --test layer1   # 运行 Layer 1 裸模型能力测试
/config --test layer2   # 运行 Layer 2 工具调用能力测试
# 测试完成后自动输出分析报告
```

---

## 各层测试内容

### Layer 1 — 裸模型能力 (`test_bare_llm/`)

直接调用 LLM API，不经过 PilotCode 任何框架逻辑。用于诊断 LLM 本身是否具备基础编码能力。

| 测试模块 | 测试内容 |
|----------|----------|
| `test_code_understanding.py` | 解释代码功能、定位 Bug、总结复杂逻辑 |
| `test_code_generation.py` | 5 个 HumanEval/MBPP 风格函数生成任务，本地执行验证 |
| `test_instruction_following.py` | JSON 格式输出、编号列表、否定词处理、长度约束 |
| `test_script_generation.py` | **完整可执行脚本生成**（非函数片段）：文件统计、错误处理、子进程验证 |

`test_script_generation.py` 与 `test_code_generation.py` 的关键区别：

| | `test_code_generation.py` | `test_script_generation.py` |
|--|--------------------------|----------------------------|
| **输出形式** | 孤立函数片段 (`def foo(...)`) | 完整可执行脚本 (`#!/usr/bin/env python3` + `if __name__`) |
| **执行环境** | 测试框架 `exec()` 注入 | 子进程独立运行 (`subprocess.run`) |
| **验证重点** | 算法正确性 | 工程完整性：import、路径处理、错误处理、输出格式 |
| **典型失败** | 逻辑 bug | 忘记 `import os`、硬编码路径、没有错误处理 |

### Layer 2 — 工具调用能力 (`test_tool_capability/`)

使用 `engine_helper.run_with_tools()` 驱动完整的 **submit_message → 工具执行 → 结果回传 → 继续** 循环。

| 测试模块 | 测试内容 |
|----------|----------|
| `test_tool_selection.py` | 搜索任务优先使用 Grep（而非 FileRead 遍历）、批量操作防循环 |
| `test_task_planning.py` | 多步分解：发现 → 读取 → 修改 → 验证、**脚本生成与执行闭环**、多部分请求并行处理 |
| `test_code_editing.py` | 读-改-验证闭环：精确编辑、类方法添加、编辑后语法检查 |

> `test_task_planning.py` 新增的脚本生成测试：
> - `test_generate_count_script_and_execute`：LLM 生成统计脚本 → Bash 执行 → 验证输出
> - `test_generate_recursive_script_with_excludes`：LLM 生成递归扫描脚本，验证目录排除逻辑 |

### Layer 3 — WebSocket 端到端 (`tests/e2e/websocket/`)

通过 WebSocket 与完整 PilotCode 服务端交互，覆盖真实用户体验。

| 测试类别 | 数量 | 说明 |
|----------|------|------|
| 简单任务 | 7 个 | 单轮/多轮文件读取、Glob、Grep、Bash |
| 复杂任务 | 多个 | 多步骤工具链、上下文保持 |
| 会话管理 | 3 个 | 创建/附着/隔离 |
| 上下文保持 | 2 个 | 多轮记忆、压缩后记忆 |
| 工具行为 | 19 个 | 跨平台工具验证 |

---

## 关键设计决策

### 1. `--run-llm-e2e` 显式开关

默认 **跳过** 所有 LLM 相关测试，避免：
- 无 LLM 后端时的连接失败
- CI/CD 环境中不必要的 API 调用开销
- 本地开发时的长时间阻塞

### 2. 宽松断言策略

`contains`（期望响应包含某关键词）不匹配时，从 **FAIL 降级为 UserWarning**，仅做提示不中断测试。严格检查项包括：
- `tool_calls` / `not_tool_calls`
- `not_contains`
- 响应长度边界

### 3. Reasoning Model 输出过滤（Thinking 清理）

部分推理模型（如 Qwen3.6-35B-A3B-FP8 with thinking enabled）会在响应中输出大量 reasoning/thinking 内容，格式如下：

```
The user is asking...
</think>

YesThe user is asking...  <-- thinking 内容在 </think> 后继续输出
</think>

```

这会导致 bare_llm 和 model_capability 测试的断言被污染。**所有 e2e 测试已通过 `strip_thinking()` 自动过滤**。

**过滤策略**（`tests/e2e/model_capability/test_bare_llm/helpers.py`）：

1. **只收集 `AssistantMessage`** — `submit_message` 流中会混入 `UserMessage`，排除
2. **`<think>...</think>` 块删除** — 完整 reasoning 块直接移除
3. **多 `</think>` 处理** — 取最后一个 `</think>` 之后的内容
4. **流式过滤** — 一旦检测到 `</think>`，后续包含 reasoning 关键词的 chunk 直接丢弃

> 如果你的模型也出现 thinking 污染导致 e2e 失败，检查 `_chat()` / `_run_turn()` / `run_with_tools()` 是否已调用 `strip_thinking()`。

### 4. 测试运行分析报告

运行完测试后，使用 `analyze_results.py` 自动分类失败根因：

```bash
# 1. 运行测试并生成 JUnit XML
pytest tests/e2e/model_capability/ --run-llm-e2e --e2e-timeout=240 \
    --junitxml=/tmp/e2e_results.xml

# 2. 运行分析脚本
python tests/e2e/analyze_results.py /tmp/e2e_results.xml
```

**输出示例**：

```
======================================================================
  E2E 测试结果分析报告
======================================================================

  总用例数 : 7
  ✅ 通过  : 3
  ❌ 失败  : 4
  ⏭️  跳过  : 0

----------------------------------------------------------------------
  失败根因分类
----------------------------------------------------------------------

  🔄 上下文保持失败（重复调用工具） — 2 个
      • TestTwoTurnContext::test_file_content_remembered
      • TestTwoTurnContext::test_search_result_remembered

  ⏱ 模型响应超时 — 1 个
      • TestNegation::test_do_not_call_tool

  ❌ 普通断言失败 — 1 个
      • TestFormatConstraints::test_json_format
```

**分类维度**：

| 类别 | 标记 | 说明 |
|------|------|------|
| ⏱ timeout | `TimeoutError` | 模型响应慢或网络问题 |
| 🧠 thinking_pollution | `<think>`、`Thinking Process:` | 模型 reasoning 输出污染（需过滤） |
| 🔄 context_retention | `should NOT FileRead again` | 多轮对话中 LLM 忘记上下文 |
| 🔧 tool_param_mismatch | `Param '` | 工具参数不符合预期 |
| 📝 file_edit_failed | `File was not modified` | FileEdit/FileWrite 未生效 |
| ❌ assertion_mismatch | `AssertionError` | 输出内容不符合预期 |
| ❓ other | 未匹配 | 需人工分析 |

### 5. 客户端自动处理机制

WebSocket 测试客户端自动处理以下场景，防止测试挂起：
- `user_question_request` → 自动回复 `"yes"`
- `permission_request` → 自动批准
- 45 秒 recv 超时保护

### 6. 临时目录隔离

所有文件写入类测试使用 `tmp_path` fixture，在临时目录中执行，不污染项目代码。

---

## 添加新测试

### 添加 Layer 1 测试（裸模型）

```python
import pytest
from pilotcode.utils.model_client import Message

@pytest.mark.llm_e2e
async def test_my_code_task(bare_llm_client, e2e_timeout):
    messages = [Message(role="user", content="你的任务描述")]
    chunks = []
    async for chunk in bare_llm_client.chat_completion(messages, stream=True):
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        if delta.get("content"):
            chunks.append(delta["content"])
    response = "".join(chunks)
    assert "期望关键词" in response.lower()
```

**如果测试目标需要生成完整脚本并执行**：

```python
import pytest
import subprocess
import tempfile
from pathlib import Path

@pytest.mark.llm_e2e
async def test_my_script_task(bare_llm_client, e2e_timeout, tmp_path):
    # 1. 让 LLM 生成脚本
    messages = [Message(role="user", content="生成一个脚本做 XXX")]
    chunks = []
    async for chunk in bare_llm_client.chat_completion(messages, stream=True):
        delta = chunk.get("choices", [{}])[0].get("delta", {})
        if delta.get("content"):
            chunks.append(delta["content"])

    # 2. 提取并清理脚本（自动处理 <think>、markdown fences）
    from test_bare_llm.helpers import strip_thinking
    script = strip_thinking("".join(chunks))

    # 3. 子进程执行验证
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        script_path = f.name
    proc = subprocess.run(["python3", script_path], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, f"Script failed: {proc.stderr}"
    assert "期望输出" in proc.stdout
```

### 添加 Layer 2 测试（带工具执行）

```python
import pytest
from ..engine_helper import run_with_tools

@pytest.mark.llm_e2e
async def test_my_tool_task(model_capability_client, e2e_timeout):
    result = await run_with_tools(
        model_capability_client,
        "你的任务描述",
        timeout=e2e_timeout,
        max_turns=10,
    )
    tool_names = [tc.name for tc in result.tool_calls]
    assert "期望工具" in tool_names
    assert len(result.final_response) > 20
```

### 添加 Layer 3 测试（JSON 用例）

在 `tests/e2e/websocket/cases/` 下创建或编辑 JSON 文件：

```json
{
  "suite": "my_suite",
  "cases": [
    {
      "id": "M001",
      "name": "我的测试",
      "steps": [
        {
          "send": "用户查询",
          "expect": {
            "tool_calls": ["FileRead"],
            "contains": ["期望内容"]
          }
        }
      ]
    }
  ]
}
```

---

## 故障排查

| 现象 | 可能原因 | 解决方式 |
|------|----------|----------|
| 测试全部 Skip | 未加 `--run-llm-e2e` | 添加开关 |
| Connection refused | WebSocket 服务端未启动 | 先启动 `python -m pilotcode --web` |
| Timeout | LLM 推理慢或工具执行慢 | 增加 `--e2e-timeout` |
| Tool 未调用 | LLM function calling 能力弱 | 检查 Layer 1 是否通过 |
| FileEdit 失败 | old_string 不匹配 | 属于 LLM 参数精度问题 |
| 死循环/大量 FileRead | LoopGuard 未触发或 LLM 探索失控 | 查看 `diagnostics.py` 归因报告 |
| 响应包含长篇 thinking | Reasoning 模型输出了思考过程 | 已自动过滤，如仍失败检查 `strip_thinking()` 是否被调用 |
| analyze_results.py 无输出 | XML 文件尚未写入完成 | 等 pytest 完全结束后再运行分析脚本 |
