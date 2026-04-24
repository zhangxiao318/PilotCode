# PilotCode 三层诊断评估框架

## 设计目标

PilotCode 是 AI 编码智能体，其核心能力依赖后端大模型。但任务失败时，难以判断是：
- **大模型能力不足**（不会写代码、不会选工具）
- **PilotCode 框架问题**（工具描述不清、LoopGuard 误杀、超时配置不合理）

本框架通过**三层对照实验**系统性地定位根因。

## 三层架构

```
Layer 1 (Bare LLM)       -> 直接调用 model_client，零工具，零框架
Layer 2 (LLM + Tools)    -> QueryEngine + ToolExecutor，完整工具循环
Layer 3 (E2E)            -> WebSocket 完整系统（已有测试）
```

## 归因规则

| Layer 1 | Layer 2 | Layer 3 | 根因归因 |
|---------|---------|---------|----------|
| FAIL    | —       | —       | **LLM基础能力弱**（代码理解/生成/指令遵循） |
| PASS    | FAIL    | —       | **LLM function calling弱** 或 **PilotCode工具实现问题** |
| PASS    | PASS    | FAIL    | **PilotCode框架问题**（LoopGuard/超时/上下文压缩/系统提示词） |

Layer 2 子诊断：
- LLM 选错工具 / 填错参数 → `llm_function_calling`
- LLM 选对工具且参数正确，但工具执行返回 error → `pilotcode_tool`
- 工具执行成功，但 LLM 陷入循环或遗忘结果 → `llm_function_calling` 或 `llm_capability`

## 运行方式

```bash
# 全部 E2E 测试（三层）
pytest tests/e2e/ --run-llm-e2e -v

# 仅 Layer 1（裸模型能力，最快）
pytest tests/e2e/model_capability/test_bare_llm/ --run-llm-e2e -v

# 仅 Layer 2（工具调用能力）
pytest tests/e2e/model_capability/test_tool_capability/ --run-llm-e2e -v

# 仅 Layer 3（端到端）
pytest tests/e2e/websocket/ --run-llm-e2e -v
```

## 测试目录结构

```
tests/e2e/model_capability/
├── conftest.py                          # Fixture：bare_llm_client, model_capability_client
├── engine_helper.py                     # run_with_tools()：完整工具执行循环
├── diagnostics.py                       # 诊断引擎：失败归因
├── test_bare_llm/
│   ├── test_code_understanding.py       # 代码解释、Bug定位
│   ├── test_code_generation.py          # HumanEval风格函数生成+本地执行验证
│   └── test_instruction_following.py    # 格式约束、否定词、长度限制
├── test_tool_capability/
│   ├── test_tool_selection.py           # 工具选择策略（搜索vs读取）
│   ├── test_task_planning.py            # 多步任务分解（发现->读取->修改->验证）
│   └── test_code_editing.py             # 读-改-验证闭环
└── README.md                            # 本文件
```

## 如何添加新测试

### Layer 1 测试

```python
import pytest
from pilotcode.utils.model_client import Message

@pytest.mark.llm_e2e
async def test_my_bare_llm_test(bare_llm_client, e2e_timeout):
    messages = [Message(role="user", content="...")]
    # collect streaming response...
    # assert on response content
```

### Layer 2 测试

```python
import pytest
from ..engine_helper import run_with_tools

@pytest.mark.llm_e2e
async def test_my_tool_test(model_capability_client, e2e_timeout):
    result = await run_with_tools(
        model_capability_client,
        "Your task description here",
        timeout=e2e_timeout,
        max_turns=10,
    )
    # assert on result.tool_calls, result.final_response
```

## 参考基准

本框架的测试设计参考了业界主流编码基准：

| 基准 | 类型 | 难度 | 我们借鉴的维度 |
|------|------|------|----------------|
| HumanEval | 函数生成 | 初级 | Layer 1 代码生成测试 |
| MBPP | 函数生成 | 初级-中级 | Layer 1 代码生成测试 |
| SWE-bench | Bug修复 | 专家 | Layer 2 代码编辑测试 |
| LiveCodeBench | 竞赛编程 | 中级-高级 | 未来可扩展 |

## 已知限制

1. **本地 LLM 能力弱**：Layer 1 的代码生成测试可能因本地模型质量而大面积失败，这恰好反映了真实能力边界
2. **工具执行环境差异**：Layer 2 的文件写入/编辑在临时目录中执行，与真实工作空间行为一致但路径不同
3. **非确定性**：LLM 输出具有随机性，同一测试多次运行可能产生不同结果。建议设置 `temperature=0` 或多次运行取平均
