# 为模型添加 KnowHow 规则

> **核心原则**：弱模型不是一个模型。Qwen 的双转义问题，Claude 可能没有；Llama 的 import 遗漏，DeepSeek 可能不犯。每个模型的缺陷模式必须**单独跟踪**。

---

## 快速开始

### 1. 确认当前模型是否有 KnowHow 文件

```bash
# 查看 knowhow 目录
ls ~/.pilotcode/knowhow/
```

如果看到 `{模型名}.json`，说明已有规则；如果没有，说明该模型尚未被分析。

### 2. 初始化模型 KnowHow 文件

```python
from pilotcode.services.knowhow import init_knowhow_for_model, QWEN3_CODER_30B_STARTER_ENTRIES

# 为 Qwen3-Coder-30B 生成初始 knowhow 文件
path = init_knowhow_for_model(
    model_name="qwen3-coder-30b",
    entries=QWEN3_CODER_30B_STARTER_ENTRIES,
    notes="Observed with Qwen3-Coder-30B on local deployment (73K context, vLLM)",
)
print(f"Created: {path}")
```

或者手动创建 JSON 文件 `~/.pilotcode/knowhow/qwen3-coder-30b.json`：

```json
{
  "model_name": "qwen3-coder-30b",
  "version": 1,
  "created_at": "2026-04-24T00:00:00Z",
  "notes": "Known issues for Qwen3-Coder-30B",
  "entries": []
}
```

> **关键**：只有创建了该模型的 JSON 文件后，框架才会对这个模型运行 KnowHow 检测。没有文件 = 完全跳过，避免对新模型的误报。

---

## KnowHow 规则格式

### 完整 Entry 示例

```json
{
  "id": "qwen3-double-escaped-n",
  "name": "Double-escaped newline",
  "description": "In Python source code, '\\n' inside a string literal produces literal backslash+n, not a newline. Use single backslash for real escape sequences.",
  "pattern": "\"[^\"]*\\\\n[^\"]*\"|'[^']*\\\\n[^']*'",
  "pattern_type": "regex",
  "applies_to_globs": ["*.py"],
  "fix_type": "replace",
  "fix_replacement": null,
  "severity": "error",
  "tags": ["python", "string", "escape"]
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `string` | ✅ | 唯一标识，建议前缀用模型名，如 `qwen3-xxx` |
| `name` | `string` | ✅ | 人类可读名称 |
| `description` | `string` | ✅ | 错误说明 + 修复建议（会显示给模型） |
| `pattern` | `string` | ✅ | 检测模式 |
| `pattern_type` | `string` | 默认 `"regex"` | `"regex"` 正则 \| `"literal"` 字面量 \| `"ast"` AST（预留） |
| `applies_to_globs` | `list<string>` | 默认 `["*.py"]` | 文件匹配，如 `["*.py", "*.pyi"]` |
| `fix_type` | `string` | 默认 `"warn"` | `"replace"` 替换 \| `"remove"` 删除 \| `"warn"` 仅警告 |
| `fix_replacement` | `string \| null` | 可选 | replace 时的替换模板 |
| `severity` | `string` | 默认 `"warning"` | `"error"` \| `"warning"` \| `"info"` |
| `tags` | `list<string>` | `[]` | 标签，如 `["python", "string"]` |

### 三种检测模式

```json
// ── regex ── 逐行正则匹配（最常用）
{
  "pattern": "asyncio\\.run\\(",
  "pattern_type": "regex"
}

// ── literal ── 逐行字面量查找（适合固定字符串）
{
  "pattern": "TODO: fix this",
  "pattern_type": "literal"
}

// ── ast ── AST 遍历（预留，暂不支持具体 walker）
{
  "pattern": "",
  "pattern_type": "ast"
}
```

### 关于 JSON 中的反斜杠转义

这是最容易出错的地方。

**目标**：检测 Python 源码中的 `"hello\\nworld"`（字面量 `\n`，即反斜杠+n 两个字符）。

| 层级 | 内容 |
|------|------|
| Python 原始字符串 | `r'"[^"]*\\n[^"]*"'` |
| Python 普通字符串 | `'"[^"]*\\\\n[^"]*"'` |
| JSON 字符串 | `"\"[^\"]*\\\\\\\\n[^\"]*\""` |

**建议**：用自然语言描述给强模型生成，不要手写正则（见下一节）。

---

## 推荐工作流：自然语言 → 强模型生成 Entry

### 步骤 1：观察模型错误

在实际使用中发现模型犯了某个错误。记录下来：

> **模型**：qwen3-coder-30b
> **场景**：让它把 `print("hello")` 改成 `print("hello\nworld")`
> **错误输出**：`print("hello\\nworld")` —— 多了个反斜杠
> **根因**：模型在生成 Python 源码时，把字符串内部的 `\n` 又转义了一次

### 步骤 2：用下面的 Prompt 让强模型生成 Entry

将以下 Prompt 发送给 **Claude / GPT-4 / DeepSeek-V4** 等强模型：

````markdown
You are a regex expert. I need a JSON Entry for a code-quality rule that detects a specific mistake made by a weak LLM.

## The mistake

Model: Qwen3-Coder-30B
Context: The model is editing Python source code.
Problem: When asked to insert a newline character inside a string, the model writes `"hello\\nworld"` instead of `"hello\nworld"`. In Python source code, `\\n` inside a string literal produces the two characters backslash+n, not an actual newline. The correct form is a single backslash: `\n`.

## Output format

Return a single JSON object matching this schema:

```json
{
  "id": "{model_prefix}-{short_desc}",
  "name": "Human-readable name",
  "description": "Clear explanation of the mistake and how to fix it.",
  "pattern": "regex pattern",
  "pattern_type": "regex",
  "applies_to_globs": ["*.py"],
  "fix_type": "replace | warn | remove",
  "fix_replacement": "replacement template or null",
  "severity": "error | warning | info",
  "tags": ["python", "..."]
}
```

Requirements:
1. `id` must be unique. Use prefix "qwen3-" for this model.
2. `pattern` must use Python `re` syntax. The pattern is matched LINE-BY-LINE against the source file.
3. `fix_type`: Use "replace" ONLY if the fix is 100% safe and unambiguous. Use "warn" if there's any risk of false positives.
4. The pattern must NOT match the CORRECT form. For example, `"hello\nworld"` (single backslash) must NOT trigger this rule.
5. Return ONLY the JSON object, no markdown fences, no explanation.

## Important note on backslash escaping

The final output will be placed inside a JSON file. In JSON strings, each backslash must be doubled. For example, a regex that matches a literal backslash followed by 'n' in Python source would be written in the JSON file as:

```json
"pattern": "\"[^\"]*\\\\n[^\"]*\""
```

But since you are outputting JSON directly, you only need to write it once-escaped for JSON. Just make sure the regex, when parsed by Python's `re` module, matches the intended pattern.
````

### 步骤 3：验证生成的 Entry

将生成的 JSON 复制到测试文件中验证：

```python
from pilotcode.services.knowhow import KnowhowEntry, KnowhowLibrary
import json

# 加载你生成的 Entry
entry = KnowhowEntry.from_dict({
    "id": "qwen3-double-escaped-n",
    "name": "Double-escaped newline",
    ...  # paste the generated JSON here
})

# 测试：应该匹配错误的代码
bad_code = 'x = "hello\\nworld"\n'
lib = KnowhowLibrary()
lib.add(entry)
matches = lib.check(bad_code, "test.py")
assert len(matches) == 1, f"Expected 1 match, got {len(matches)}"
print(f"✅ Detected: {matches[0].name} at line {matches[0].line_number}")

# 测试：不应该匹配正确的代码
good_code = 'x = "hello\nworld"\n'
matches = lib.check(good_code, "test.py")
assert len(matches) == 0, f"Expected 0 matches, got {len(matches)}"
print("✅ No false positive on correct code")

# 测试：自动修复
fixed = lib.apply_auto_fixes(bad_code, lib.check(bad_code, "test.py"))
assert "hello\\nworld" not in fixed
assert "hello\nworld" in fixed
print("✅ Auto-fix works")
```

### 步骤 4：手工添加到模型 KnowHow 文件

打开 `~/.pilotcode/knowhow/qwen3-coder-30b.json`，在 `entries` 数组末尾追加验证通过的 Entry：

```bash
# 用你喜欢的编辑器打开
vim ~/.pilotcode/knowhow/qwen3-coder-30b.json
```

```json
{
  "model_name": "qwen3-coder-30b",
  ...
  "entries": [
    // ... existing entries ...
    {
      "id": "qwen3-double-escaped-n",
      "name": "Double-escaped newline",
      "description": "...",
      "pattern": "...",
      ...
    }
  ]
}
```

保存后，框架会在下一次编辑时自动加载新规则。

---

## 添加规则时的检查清单

在将新规则加入生产环境前，确认：

- [ ] **不误杀**：测试了 5 个以上正确代码样例，确认没有误报
- [ ] **能捕获**：测试了实际模型输出的错误代码，确认能捕获
- [ ] **修复安全**：如果 `fix_type="replace"`，确认自动修复不会引入新 bug
- [ ] **ID 唯一**：在同一个模型文件中没有重复的 `id`
- [ ] **文档更新**：在 `notes` 字段中简要说明这条规则是在什么场景下发现的

---

## 共享与复用 KnowHow

### 从其他模型复制规则

如果两个模型犯了同样的错误，可以直接复制 Entry：

```bash
# 把 Qwen 的规则复制给新的本地模型
cp ~/.pilotcode/knowhow/qwen3-coder-30b.json ~/.pilotcode/knowhow/my-new-model.json
# 然后修改 model_name 和 notes，删除不适用的条目
```

### 提交到项目仓库

如果你发现了一条有价值的通用规则（不仅限于你的本地模型），可以提交到 PilotCode 仓库：

1. 修改 `src/pilotcode/services/knowhow.py` 中的 `QWEN3_CODER_30B_STARTER_ENTRIES` 或其他 starter 模板
2. 在 PR 描述中说明：模型名称、触发场景、测试样例

---

## 常见问题

### Q: 为什么新模型没有 KnowHow 文件就不检测？

**A**: 避免 false positive。不同模型的缺陷模式差异很大。如果全局统一检测，强模型输出的 `"hello\nworld"` 可能被弱模型的规则误报。

### Q: 混用缩进（mixed tabs/spaces）这种通用问题怎么办？

**A**: 放在 `~/.pilotcode/knowhow/global.json` 中。global 规则会在所有有模型文件的模型中生效。如果某个模型没有自己的 knowhow 文件，global 也不生效（因为整个 knowhow 被跳过）。这是设计如此——没有 profile 过的模型，我们不做任何假设。

### Q: 可以用 AST 模式检测复杂逻辑吗？

**A**: 目前 AST walker 是预留接口，尚未实现具体的遍历逻辑。对于复杂场景，建议先用 `regex` 模式做简单 heuristics，等 AST walker 完善后再迁移。

### Q: 如何删除一条规则？

**A**: 直接从 JSON 文件的 `entries` 数组中删除对应对象，保存即可。框架会在下次编辑时重新加载。
