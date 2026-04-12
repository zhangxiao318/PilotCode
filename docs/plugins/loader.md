# Loader - 插件加载器

加载器模块负责加载插件中的 Skills 和 Commands，支持 Markdown 格式的定义文件。

---

## 模块结构

```
src/pilotcode/plugins/loader/
├── __init__.py              # 模块导出
├── skills.py                # Skill 加载器
└── commands.py              # Command 加载器
```

---

## Skill 加载器

Skills 是可复用的提示模板，定义在 Markdown 文件中。

### Skill 文件格式

```markdown
---
name: code-review
description: Review code for issues
aliases: [review, cr]
whenToUse: When user asks for code review
argumentHint: <file_path>
allowedTools: [Read, Grep, CodeSearch]
model: claude-3-5-sonnet
---

Please review the following code for:
1. Potential bugs
2. Security issues
3. Performance problems
4. Code style violations

File: {{file_path}}

```
{{code}}
```

Provide your review in a structured format...
```

### Frontmatter 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | **必需** Skill 名称 |
| `description` | string | Skill 描述 |
| `aliases` | list | 别名列表 |
| `whenToUse` | string | 使用时机说明 |
| `argumentHint` | string | 参数提示 |
| `allowedTools` | list | 允许使用的 Tools |
| `model` | string | 指定模型 |

### SkillLoader

```python
from pilotcode.plugins.loader.skills import SkillLoader

# 创建加载器
loader = SkillLoader(Path("/path/to/skills"))

# 加载所有 Skills
skills = loader.load_all()

# 获取特定 Skill
skill = loader.get_skill("code-review")

# 列出所有 Skills
names = loader.list_skills()
```

### 从文件加载

```python
from pilotcode.plugins.loader.skills import load_skill_from_file

skill = load_skill_from_file(Path("skills/code-review.md"))

print(skill.name)           # "code-review"
print(skill.description)    # "Review code for issues"
print(skill.content)        # Markdown 内容（不含 frontmatter）
```

### 解析 Frontmatter

```python
from pilotcode.plugins.loader.skills import parse_frontmatter

content = """---
name: my-skill
description: A skill
---

Skill content here...
"""

frontmatter, markdown = parse_frontmatter(content)
# frontmatter: {"name": "my-skill", "description": "A skill"}
# markdown: "Skill content here..."
```

### 目录结构

```
skills/
├── code-review.md           # 单个 skill 文件
├── refactor.md
└── complex-skill/           # 子目录 skill
    └── SKILL.md             # 必须命名为 SKILL.md
```

### 错误处理

```python
from pilotcode.plugins.loader.skills import SkillLoadError

try:
    skill = load_skill_from_file(Path("invalid.md"))
except SkillLoadError as e:
    print(f"Failed to load skill: {e}")
```

常见错误：

| 错误 | 说明 |
|------|------|
| `File not found` | Skill 文件不存在 |
| `Invalid YAML frontmatter` | Frontmatter YAML 格式错误 |
| `Missing required 'name' field` | 缺少必需的 name 字段 |

---

## Command 加载器

Commands 类似于 Skills，但用于定义斜杠命令。

### Command 文件格式

```markdown
---
name: git-status
description: Show git status
aliases: [gs, status]
---

Show the current git status for the repository.

Usage: /git-status
```

### CommandLoader

```python
from pilotcode.plugins.loader.commands import CommandLoader

# 创建加载器
loader = CommandLoader(Path("/path/to/commands"))

# 加载所有 Commands
commands = loader.load_all()

# 获取特定 Command
cmd = loader.get_command("git-status")

# 列出所有 Commands
names = loader.list_commands()
```

### 与 Skill 的区别

| 特性 | Skill | Command |
|------|-------|---------|
| 用途 | 复用提示模板 | 定义斜杠命令 |
| 文件名 | 任意 `.md` | 任意 `.md` |
| 执行方式 | 由 LLM 选择 | 用户输入 `/command` |
| 参数 | 通过变量传递 | 通过 args 传递 |

---

## SkillDefinition

Skill 定义的数据结构：

```python
from pilotcode.plugins.core.types import SkillDefinition

skill = SkillDefinition(
    name="code-review",                    # Skill 名称
    description="Review code for issues",  # 描述
    aliases=["review", "cr"],              # 别名
    when_to_use="When user asks for review",  # 使用时机
    argument_hint="<file_path>",           # 参数提示
    allowed_tools=["Read", "Grep"],        # 允许的工具
    model="claude-3-5-sonnet",             # 指定模型
    content="Please review..."             # 提示内容
)
```

---

## 完整示例

### 创建自定义 Skill

```python
from pathlib import Path
from pilotcode.plugins.loader.skills import SkillLoader, load_skill_from_file

# 加载插件中的 skills
loader = SkillLoader(Path("my-plugin/skills"))
skills = loader.load_all()

# 使用 skill
skill = loader.get_skill("code-review")
if skill:
    print(f"Name: {skill.name}")
    print(f"Description: {skill.description}")
    print(f"Allowed tools: {skill.allowed_tools}")
    print(f"Content preview: {skill.content[:100]}...")
```

### 动态创建 Skill

```python
from pilotcode.plugins.core.types import SkillDefinition

skill = SkillDefinition(
    name="analyze-imports",
    description="Analyze Python imports",
    aliases=["imports"],
    when_to_use="When analyzing Python code structure",
    allowed_tools=["Read", "Grep"],
    content="""
Analyze the imports in this Python file:

File: {{file_path}}

Identify:
1. Standard library imports
2. Third-party imports
3. Local imports
4. Unused imports
5. Circular import risks
"""
)
```

### 模板变量

Skill 内容支持模板变量：

```markdown
---
name: generate-tests
description: Generate unit tests
---

Generate unit tests for the following code:

**Function:** {{function_name}}
**File:** {{file_path}}

```python
{{code}}
```

Requirements:
- Test framework: {{test_framework|default("pytest")}}
- Coverage: {{coverage|default("basic")}}
```

变量通过上下文传递：

```python
context = {
    "function_name": "calculate_sum",
    "file_path": "src/math.py",
    "code": "def calculate_sum(a, b):\n    return a + b",
    "test_framework": "pytest",
    "coverage": "comprehensive"
}

# 使用 Jinja2 渲染
from jinja2 import Template
rendered = Template(skill.content).render(**context)
```

---

## 最佳实践

### Skill 设计原则

1. **单一职责**：每个 Skill 专注于一个任务
2. **清晰描述**：描述应该明确说明使用场景
3. **合理别名**：提供常用的缩写和变体
4. **工具限制**：通过 `allowed_tools` 限制可用工具
5. **参数文档**：使用 `argument_hint` 说明参数格式

### 示例 Skills

**代码审查 Skill：**

```markdown
---
name: security-review
description: Security-focused code review
aliases: [sec-review, security]
whenToUse: When reviewing code for security issues
allowedTools: [Read, Grep, CodeSearch]
---

Perform a security review of the following code:

**File:** {{file_path}}

```python
{{code}}
```

Check for:
- SQL injection vulnerabilities
- XSS vulnerabilities
- CSRF vulnerabilities
- Hardcoded secrets
- Insecure deserialization
- Path traversal
- Command injection

For each issue found:
1. Severity (Critical/High/Medium/Low)
2. Location (line number)
3. Description
4. Remediation suggestion
```

**重构 Skill：**

```markdown
---
name: refactor-suggestion
description: Suggest code refactoring
aliases: [refactor, improve]
whenToUse: When suggesting code improvements
allowedTools: [Read, Grep]
---

Analyze the following code and suggest refactorings:

**File:** {{file_path}}
**Focus areas:** {{focus|default("all")}}

```python
{{code}}
```

Consider:
1. Code smells (duplication, long methods, etc.)
2. Design patterns application
3. Performance optimizations
4. Readability improvements
5. Python idioms

Provide specific before/after examples for each suggestion.
```

---

## 相关文档

- [插件核心管理](./core.md)
- [钩子系统](./hooks.md)
