# Reflection Mode（反思模式）

> **状态**: TODO / 设计完成，待实现  
> **优先级**: P2  
> **关联改进项**: P2 Reflection mode（系统性改进计划）

---

## 1. 设计目标

Reflection Mode 是 Agent 四大核心模式之一（ReAct、Plan-and-Execute、Reflection、Multi-Agent）。PilotCode 当前已具备 Plan 模式（启发式）和 Multi-Agent（8 种 Agent 类型），但缺少正式的 Reflection 闭环。

本设计旨在实现**生成→审查→修改**的闭环机制，与现有 `auto_review`（事后审查）形成互补：

| 机制 | 时机 | 作用 | 现有状态 |
|------|------|------|----------|
| **Self-Critique** | 生成前 | 模型自我检查 | ❌ 未实现 |
| **Pre-Edit Reflection** | 编辑前 | 审查编辑计划，阻止错误编辑 | ❌ 未实现 |
| **Post-Edit Review** (`auto_review`) | 编辑后 | 审查修改后的代码质量 | ✅ 已实现 |
| **Post-Turn Reflection** | 轮次后 | 复盘决策链，检测目标偏离 | ❌ 未实现 |

---

## 2. 核心原则

1. **与现有组件互补**：不替代 `PostEditValidator`，而是填补"事前预防 + 过程复盘"的空白
2. **分层可控**：从"零额外开销"到"完整双 Agent"，用户按需选择
3. **不破坏流式架构**：Pre-edit 在工具执行层同步进行；Post-turn 可异步
4. **成本可控**：支持用 `compact_model`（如 qwen2.5-7b）执行 reflection，降低 token 消耗

---

## 3. 三层架构

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: Post-Turn Reflector (轮次级复盘)                   │
│  • 每轮结束后审查决策链                                       │
│  • 检测目标偏离、无效循环、方案优化                            │
│  • 将反馈注入下轮系统提示                                      │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Pre-Edit Reflector (工具级预审查)                  │
│  • FileEdit/FileWrite 执行前审查编辑计划                       │
│  • 检查匹配准确性、语法正确性、完整性                          │
│  • 发现问题则阻止执行，返回修改建议                             │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Self-Critique (提示词级自我批评)                   │
│  • 在系统提示中嵌入反思指令                                     │
│  • 让模型在生成工具调用前自我检查                               │
│  • 零额外 LLM 调用                                            │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. 配置接口

```python
@dataclass
class QueryEngineConfig:
    # ... 现有字段 ...

    # Reflection 模式: off | self_critique | pre_edit | post_turn | full
    reflection_mode: str = "off"

    # 用于 reflection 的轻量模型（None = 使用主模型）
    reflection_model: str | None = None

    # Pre-edit reflection 的触发阈值
    pre_edit_reflection_threshold: str = "medium"  # low | medium | high

    # Post-turn reflection 的最小对话轮数
    post_turn_reflection_min_turns: int = 3
```

---

## 5. Layer 1: Self-Critique（零开销）

### 实现位置
`PromptBuilder._get_default_system_prompt()`

### 机制
在系统提示末尾追加自我批评指令，让强模型（Claude/GPT-4）在生成工具调用前自动检查：

```
在生成任何工具调用前，请先进行自我检查：
1. 这个工具调用是否必要？是否有更简洁的方式？
2. 如果是 FileEdit，搜索字符串是否足够精确且唯一？
3. 修改是否完整？是否遗漏了相关调用点？
4. 如果上一轮出现错误，是否分析了根因而不是表面修复？
```

### 适用场景
所有模型，零成本，适合强模型。

---

## 6. Layer 2: Pre-Edit Reflector（高价值）

### 实现位置
`src/pilotcode/services/reflection/pre_edit_reflector.py`

### 触发时机
`file_edit_call()` 中，在 `edit_file_content()` 之前。

### 快速过滤（减少 80% 不必要的 LLM 调用）

```python
def _should_reflect(file_path: str, old_string: str, new_string: str, content: str) -> bool:
    # 1. 精确匹配 → 跳过（高置信度）
    if old_string in content:
        return False

    # 2. 模糊匹配 → 需要审查
    if _is_fuzzy_match(old_string, content):
        return True

    # 3. 涉及语法敏感区域 → 需要审查
    if _touches_syntax_boundary(old_string, content):
        return True

    # 4. 修改超过 50 行 → 需要审查
    if old_string.count('\n') > 50 or new_string.count('\n') > 50:
        return True

    return False
```

### 审查 Prompt 设计

```
你是一位严格的代码审查员。请审查以下编辑计划：

文件：{file_path}
当前内容（相关片段）：
```python
{content_context}
```

拟议编辑：
<<<<<<< SEARCH
{old_string}
=======
{new_string}
>>>>>>> REPLACE

请检查：
1. 搜索字符串是否能精确匹配文件中的唯一位置？
2. 替换后代码是否语法正确？
3. 是否遗漏了需要同步修改的相关代码（调用点、测试、类型声明）？
4. 是否有更简洁或更安全的修改方式？

如果一切正常，回复 "LGTM"。
如果有问题，请明确说明问题并给出修改建议。
```

### 与现有流程集成

```python
# file_edit_tool.py::file_edit_call()
if reflection_mode in ("pre_edit", "full"):
    reflector = PreEditReflector(model_client, threshold=config.pre_edit_reflection_threshold)
    reflection = await reflector.reflect(file_path, old_string, new_string, cwd)
    if not reflection.approved:
        return ToolResult(
            data=FileEditOutput(error=reflection.feedback, ...),
            error=f"Pre-edit reflection blocked: {reflection.feedback}",
            output_for_assistant=reflection.feedback,  # 让模型看到反馈
        )
# 继续执行 edit_file_content...
```

### 价值
在错误发生前阻止，避免"编辑后测试失败再修复"的往返。

---

## 7. Layer 3: Post-Turn Reflector（用于长对话）

### 实现位置
`src/pilotcode/services/reflection/post_turn_reflector.py`

### 触发时机
`QueryEngine.submit_message()` 末尾，或异步后台任务。

### 触发条件
- 对话轮数 >= `post_turn_reflection_min_turns`
- 本轮有文件修改
- 或检测到潜在的 doom loop（与现有 doom loop 检测结合）

### 对话摘要构建（控制 token）

```python
def _summarize_turn(messages: list[MessageType], changed_files: list[str]) -> str:
    tools_used = []
    for msg in messages:
        if isinstance(msg, ToolUseMessage):
            tools_used.append(f"{msg.name}: {msg.input.get('file_path', '')[:50]}")

    return f"""
本轮操作序列：
{chr(10).join(f"- {t}" for t in tools_used[-10:])}

修改的文件：{', '.join(changed_files)}
"""
```

### 审查 Prompt 设计

```
你是一位策略审查员。请审查以下 AI 助手的决策过程：

用户原始请求：{user_original_query}

本轮操作摘要：
{turn_summary}

请检查：
1. 助手是否偏离了用户的原始目标？
2. 是否有重复执行相似操作的无效循环？
3. 选择的工具是否最合适？是否有过度使用复杂工具？
4. 如果发现更好的解决思路，请提供具体建议。

如果有改进建议，请简明扼要地列出（不超过 3 条）。
如果没有问题，回复 "LGTM"。
```

### 结果注入

```python
# QueryEngine.submit_message()
if reflection_mode in ("post_turn", "full"):
    feedback = await self._post_turn_reflector.reflect(
        self.messages, self._changed_files, self.config.cwd
    )
    if feedback and feedback != "LGTM":
        self.messages.append(SystemMessage(
            content=f"[Reflection feedback]\n{feedback}"
        ))
```

### 异步优化
为了不阻塞用户交互，可以将 reflection 放入后台任务，结果在下轮对话开始时注入。

---

## 8. 与现有组件的关系

| 现有组件 | 与 Reflection 的关系 |
|---|---|
| `PostEditValidator` | **互补**。PostEdit 是"事后"（文件已改），PreEdit 是"事前"（阻止错误） |
| `Reflector` (P-EVR) | **不同层级**。P-EVR Reflector 监控 mission/task 健康；PostTurn Reflector 监控对话决策质量 |
| `ReworkContext` | **数据消费方**。Reflection 发现的教训可以写入 `ReworkContext.lessons_learned` |
| `Doom Loop Detection` | **协同**。PostTurn Reflector 可以读取 doom loop 历史，给出更高层次的策略建议 |
| `auto_review` | **上下游**。PreEdit → FileEdit → auto_review → PostTurn，形成完整闭环 |

---

## 9. 实现路线图

### Phase 1（建议优先实现）
**Layer 1 Self-Critique + Layer 2 Pre-Edit Reflector**

- [ ] 修改 `PromptBuilder`，在系统提示中追加 Self-Critique 指令
- [ ] 新建 `src/pilotcode/services/reflection/__init__.py`
- [ ] 新建 `src/pilotcode/services/reflection/pre_edit_reflector.py`
- [ ] 修改 `file_edit_tool.py::file_edit_call()`，集成 PreEditReflector
- [ ] 修改 `QueryEngineConfig`，添加 reflection 相关配置
- [ ] 编写单元测试

**改动量**：小（~3 个文件修改 + 1 个新模块）  
**价值**：高（Pre-edit 能阻止大量常见编辑错误）  
**成本**：可控（快速过滤机制减少 80% 不必要的 reflection）

### Phase 2（后续）
**Layer 3 Post-Turn Reflector**

- [ ] 新建 `post_turn_reflector.py`
- [ ] 修改 `QueryEngine.submit_message()`，集成 PostTurnReflector
- [ ] 可选：实现异步 reflection（后台任务）
- [ ] 编写单元测试

**适用场景**：长对话（>5 轮）、复杂任务拆解。

---

## 10. 相关参考

- 微信文章《Agent 面试从底层到实战》：Reflection 是四大核心 Agent 模式之一
- Claude Code：通过 `auto_review` 实现事后审查，无 Pre-edit reflection
- OpenCode：无内置 Reflection，依赖模型自身能力
- Self-Refine (2023)：LLM 通过自我反馈迭代改进输出的学术论文
