# PilotCode Feature Audit

This document catalogs all features in the original TypeScript Claude Code implementation and tracks their parity status in the Python rewrite (`pilotcode_py`).

**Last updated:** 2026-04-04

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Fully implemented |
| ⚠️ | Partially implemented / basic version |
| ❌ | Not implemented |
| 🚫 | Skipped (enterprise-only / experimental / ant-internal) |

---

## 1. Tools (~40 in TS, 51 in Python)

### Core Tools (Public)

| Tool | TS Status | Python Status | Notes |
|------|-----------|---------------|-------|
| BashTool | ✅ | ✅ | Python: full async subprocess, timeout, background tasks |
| FileReadTool | ✅ | ✅ | Python: read files with limits |
| FileEditTool | ✅ | ✅ | Python: search/replace editing |
| FileWriteTool | ✅ | ✅ | Python: write/overwrite with conflict detection |
| GlobTool | ✅ | ✅ | Python: pattern matching |
| GrepTool | ✅ | ✅ | Python: regex search, multiple output modes |
| WebFetchTool | ✅ | ✅ | Python: fetch pages |
| WebSearchTool | ✅ | ✅ | Python: web search |
| AskUserQuestionTool | ✅ | ✅ | Python: user prompt tool |
| TodoWriteTool | ✅ | ✅ | Python: todo management |
| SkillTool | ✅ | ✅ | Python: skill loading |
| AgentTool | ✅ | ✅ | Python: 7 agent types, full lifecycle |
| BriefTool | ✅ | ✅ | Python: text summarization |
| NotebookEditTool | ✅ | ✅ | Python: Jupyter notebook editing |
| MCPTool | ✅ | ⚠️ | Python: basic wrapper, no full server management |
| ListMcpResourcesTool | ✅ | ✅ | Python: basic |
| ReadMcpResourceTool | ✅ | ✅ | Python: basic |
| McpAuthTool | ✅ | ❌ | — |
| LSPTool | ✅ | ⚠️ | Python: basic command forwarding only |
| ToolSearchTool | ✅ | ✅ | Python: tool discovery |
| SyntheticOutputTool | ✅ | ✅ | Python: synthetic output injection |
| EnterPlanModeTool / ExitPlanModeV2Tool | ✅ | ✅ | Python: plan mode tools |
| UpdatePlanStep | ✅ | ✅ | Python: plan step updates |

### Task / Orchestration Tools

| Tool | TS Status | Python Status | Notes |
|------|-----------|---------------|-------|
| TaskOutputTool | ✅ | ✅ | Python: task output retrieval |
| TaskStopTool | ✅ | ✅ | Python: stop background tasks |
| TaskCreateTool | ✅ | ✅ | Python: create tasks |
| TaskGetTool | ✅ | ✅ | Python: get task status |
| TaskUpdateTool | ✅ | ✅ | Python: update tasks |
| TaskListTool | ✅ | ✅ | Python: list tasks |

### Communication / Team Tools

| Tool | TS Status | Python Status | Notes |
|------|-----------|---------------|-------|
| SendMessageTool | ✅ | ✅ | Python: agent messaging |
| TeamCreateTool | ✅ | ✅ | Python: team creation |
| TeamDeleteTool | ✅ | ✅ | Python: team deletion |
| TeamAddMember | ✅ | ✅ | Python: add to team |
| TeamList | ✅ | ✅ | Python: list teams |
| ReceiveMessage | ✅ | ✅ | Python: receive messages |

### Git / Worktree Tools

| Tool | TS Status | Python Status | Notes |
|------|-----------|---------------|-------|
| GitStatus | ✅ | ✅ | Python: git status |
| GitDiff | ✅ | ✅ | Python: git diff |
| GitLog | ✅ | ✅ | Python: git log |
| GitBranch | ✅ | ✅ | Python: git branch |
| EnterWorktreeTool | ✅ | ✅ | Python: enter worktree |
| ExitWorktreeTool | ✅ | ✅ | Python: exit worktree |
| ListWorktrees | ✅ | ✅ | Python: list worktrees |

### Utility / Other Tools

| Tool | TS Status | Python Status | Notes |
|------|-----------|---------------|-------|
| ConfigTool | ✅ | ✅ | Python: config management |
| PowerShellTool | ✅ | ✅ | Python: cross-platform PowerShell |
| REPLTool | 🚫 (ant-only) | ✅ | Python: included |
| SleepTool | 🚫 (gated) | ✅ | Python: included |
| RemoteTriggerTool | 🚫 (gated) | ✅ | Python: included |
| CronCreate/Delete/List/Update | 🚫 (gated) | ✅ | Python: included |

### Missing / Experimental Tools

| Tool | TS Status | Python Status | Priority |
|------|-----------|---------------|----------|
| WebBrowserTool | 🚫 (gated) | ❌ | Medium |
| TerminalCaptureTool | 🚫 (gated) | ❌ | Low |
| CtxInspectTool | 🚫 (gated) | ❌ | Low |
| SnipTool | 🚫 (gated) | ❌ | Low |
| WorkflowTool | 🚫 (gated) | ❌ | Low |
| OverflowTestTool | 🚫 (test) | ❌ | Low |
| TungstenTool | 🚫 (ant) | ❌ | Low |
| MonitorTool | 🚫 (gated) | ❌ | Low |
| ListPeersTool | 🚫 (gated) | ❌ | Low |
| VerifyPlanExecutionTool | 🚫 (env) | ❌ | Low |
| SuggestBackgroundPRTool | 🚫 (ant) | ❌ | Low |
| SendUserFileTool | 🚫 (gated) | ❌ | Low |
| PushNotificationTool | 🚫 (gated) | ❌ | Low |
| SubscribePRTool | 🚫 (gated) | ❌ | Low |

---

## 2. Commands (~80 built-in in TS, 65 in Python)

### Core Commands

| Command | TS | Python | Notes |
|---------|----|--------|-------|
| `/help` | ✅ | ✅ | — |
| `/clear` | ✅ | ✅ | — |
| `/quit` / `/exit` | ✅ | ✅ | `/exit` not present in Python |
| `/config` | ✅ | ✅ | — |
| `/compact` | ✅ | ✅ | — |
| `/cost` | ✅ | ✅ | — |
| `/diff` | ✅ | ✅ | — |
| `/doctor` | ✅ | ✅ | — |
| `/export` | ✅ | ✅ | — |
| `/history` | ✅ | ✅ | — |
| `/model` | ✅ | ✅ | — |
| `/permissions` | ✅ | ❌ | — |
| `/plan` | ✅ | ✅ | — |
| `/session` | ✅ | ✅ | — |
| `/status` | ✅ | ✅ | — |
| `/theme` | ✅ | ✅ | — |
| `/memory` | ✅ | ✅ | — |
| `/resume` | ✅ | ❌ | High priority missing feature |
| `/rename` | ✅ | ❌ | — |
| `/share` | ✅ | ❌ | — |
| `/skills` | ✅ | ✅ | — |
| `/tasks` | ✅ | ✅ | — |
| `/tools` | ✅ | ✅ | CLI only |
| `/version` | ✅ | ✅ | — |
| `/branch` | ✅ | ✅ | — |
| `/commit` | ✅ | ✅ | — |
| `/stash` | ✅ | ✅ | — |
| `/tag` | ✅ | ✅ | — |
| `/remote` | ✅ | ✅ | — |
| `/merge` | ✅ | ✅ | — |
| `/rebase` | ✅ | ✅ | — |
| `/reset` | ✅ | ✅ | — |
| `/clean` | ✅ | ✅ | — |
| `/cherrypick` | ✅ | ✅ | — |
| `/revert` | ✅ | ✅ | — |
| `/blame` | ✅ | ✅ | — |
| `/bisect` | ✅ | ✅ | — |
| `/switch` | ✅ | ✅ | — |
| `/agents` | ✅ | ✅ | Python: enhanced with 7 types |
| `/workflow` | ✅ | ✅ | Python: 4 modes |
| `/review` | ✅ | ✅ | — |
| `/lint` | ✅ | ✅ | — |
| `/format` | ✅ | ✅ | — |
| `/test` | ✅ | ✅ | — |
| `/coverage` | ✅ | ✅ | — |
| `/symbols` | ✅ | ✅ | — |
| `/references` | ✅ | ✅ | — |
| `/mcp` | ✅ | ✅ | — |
| `/lsp` | ✅ | ✅ | — |
| `/debug` | ✅ | ✅ | — |
| `/env` | ✅ | ✅ | — |

### File/Navigation Commands

| Command | TS | Python | Notes |
|---------|----|--------|-------|
| `/cat` | ✅ | ✅ | — |
| `/ls` | ✅ | ✅ | — |
| `/cd` | ✅ | ✅ | — |
| `/pwd` | ✅ | ✅ | — |
| `/edit` | ✅ | ✅ | — |
| `/mkdir` | ✅ | ✅ | — |
| `/rm` | ✅ | ✅ | — |
| `/cp` | ✅ | ✅ | — |
| `/mv` | ✅ | ✅ | — |
| `/touch` | ✅ | ✅ | — |
| `/head` | ✅ | ✅ | — |
| `/tail` | ✅ | ✅ | — |
| `/wc` | ✅ | ✅ | — |
| `/find` | ✅ | ✅ | — |

### Missing Commands

| Command | TS | Python | Priority |
|---------|----|--------|----------|
| `/color` | ✅ | ❌ | Low |
| `/context` | ✅ | ❌ | Medium |
| `/copy` | ✅ | ❌ | Low |
| `/desktop` | ✅ | ❌ | Low |
| `/fast` | ✅ | ❌ | Low |
| `/feedback` | ✅ | ❌ | Low |
| `/files` | ✅ | ❌ | Medium |
| `/ide` | ✅ | ❌ | Low |
| `/init` | ✅ | ❌ | Medium |
| `/install` | ✅ | ❌ | Low |
| `/keybindings` | ✅ | ❌ | Low |
| `/login` / `/logout` | ✅ | ❌ | Medium |
| `/mobile` | ✅ | ❌ | Low |
| `/onboarding` | ✅ | ❌ | Low |
| `/output-style` | ✅ | ❌ | Low |
| `/passes` | ✅ | ❌ | Low |
| `/plugin` | ✅ | ❌ | High |
| `/pr_comments` | ✅ | ❌ | Low |
| `/privacy-settings` | ✅ | ❌ | Low |
| `/rate-limit-options` | ✅ | ❌ | Low |
| `/release-notes` | ✅ | ❌ | Low |
| `/reload-plugins` | ✅ | ❌ | High |
| `/rewind` | ✅ | ❌ | Low |
| `/sandbox-toggle` | ✅ | ❌ | Low |
| `/security-review` | ✅ | ❌ | Low |
| `/stickers` | ✅ | ❌ | Low |
| `/terminalSetup` | ✅ | ❌ | Low |
| `/thinkback` | ✅ | ❌ | Low |
| `/upgrade` | ✅ | ❌ | Low |
| `/usage` | ✅ | ❌ | Low |
| `/vim` | ✅ | ❌ | Low |
| `/voice` | 🚫 | ❌ | Low |
| `/bridge` | 🚫 | ❌ | Low |
| `/teleport` | 🚫 | ❌ | Low |
| `/proactive` | 🚫 | ❌ | Low |
| `/workflows` | 🚫 | ❌ | Low |

---

## 3. Core Runtime Features

| Feature | TS | Python | Notes |
|---------|----|--------|-------|
| QueryEngine / streaming loop | ✅ | ✅ | Python: basic streaming, tool call parsing |
| Message history management | ✅ | ✅ | Python: in-memory only |
| Tool call accumulation | ✅ | ✅ | Python: handles single/multi tool calls |
| Auto-compact | ✅ | ❌ | High priority missing |
| Token counting / budgeting | ✅ | ❌ | High priority missing |
| Context management | ✅ | ⚠️ | Python: basic message list |
| Cost tracking | ✅ | ⚠️ | Python: hook exists, not fully wired |
| StreamingToolExecutor | ✅ | ⚠️ | Python: serial execution in REPL |
| Tool orchestration (concurrent read-only) | ✅ | ❌ | Medium priority |
| Tool result caching | ✅ | ❌ | Low priority |
| Tool hooks (Pre/Post tool use) | ✅ | ✅ | Python: 5 hook types implemented |
| Agent hooks (Pre/Post agent run) | ✅ | ✅ | Python: implemented |
| Error hooks | ✅ | ✅ | Python: implemented |
| Permission denied hooks | ✅ | ✅ | Python: implemented |
| Session persistence | ✅ | ❌ | High priority |
| Session resume | ✅ | ❌ | High priority |
| Conversation export | ✅ | ✅ | Python: basic JSON export |

---

## 4. Permission System

| Feature | TS | Python | Notes |
|---------|----|--------|-------|
| Risk-based prompting | ✅ | ✅ | Python: 4 risk levels |
| Permission levels (Ask/Allow/Always/Deny/Never) | ✅ | ✅ | Python: implemented |
| Session grants / denies | ✅ | ✅ | Python: fingerprint-based |
| Auto-allow mode (`--auto-allow`) | ✅ | ✅ | Python: CLI flag |
| Permission modes (default/dontAsk/acceptEdits/bypass/plan) | ✅ | ❌ | Medium priority |
| Permission rules editor | ✅ | ❌ | Medium priority |
| Bash security classifier | ✅ | ⚠️ | Python: simple pattern matching |
| YOLO classifier | ✅ | ❌ | Low priority |
| Path validation / filesystem checks | ✅ | ❌ | Medium priority |

---

## 5. Agent System

| Feature | TS | Python | Notes |
|---------|----|--------|-------|
| Agent definitions / roles | ✅ | ✅ | Python: 7 built-in types |
| Agent spawning | ✅ | ✅ | Python: via AgentTool |
| Agent persistence | ✅ | ✅ | Python: JSON disk storage |
| Parent/child agent trees | ✅ | ✅ | Python: tree structure |
| Agent messaging | ✅ | ✅ | Python: Send/ReceiveMessage tools |
| Team creation/management | ✅ | ✅ | Python: 4 team tools |
| Coordinator mode | 🚫 | ❌ | Enterprise feature |
| Swarm workers | 🚫 | ❌ | Enterprise feature |
| Agent memory snapshots | ✅ | ⚠️ | Python: basic metadata only |
| Agent forking | 🚫 | ❌ | Enterprise feature |

---

## 6. Services

| Service | TS | Python | Notes |
|---------|----|--------|-------|
| API client (Anthropic / OpenAI-compatible) | ✅ | ✅ | Python: httpx-based |
| OAuth flow | ✅ | ❌ | Medium priority |
| MCP client / connection manager | ✅ | ⚠️ | Python: basic MCP tool wrapper |
| MCP server management UI | ✅ | ❌ | Medium priority |
| Plugin marketplace | ✅ | ❌ | High priority |
| Plugin loader | ✅ | ❌ | High priority |
| Analytics / telemetry | ✅ | ❌ | Skipped |
| Settings sync | ✅ | ❌ | Low priority |
| Policy limits | ✅ | ❌ | Low priority |
| LSP manager | ✅ | ⚠️ | Python: minimal |
| Voice / STT | ✅ | ❌ | Low priority |
| Session memory extraction | ✅ | ❌ | Medium priority |
| Team memory sync | ✅ | ❌ | Low priority |
| Compact service | ✅ | ❌ | High priority |
| Token estimation | ✅ | ❌ | High priority |

---

## 7. CLI / Transport

| Feature | TS | Python | Notes |
|---------|----|--------|-------|
| Interactive REPL | ✅ | ✅ | Python: prompt_toolkit + Rich |
| Headless / structured JSON I/O | ✅ | ❌ | Medium priority |
| Remote I/O adapter | ✅ | ❌ | Low priority |
| SSE transport | ✅ | ❌ | Low priority |
| WebSocket transport | ✅ | ❌ | Low priority |
| Bridge mode | 🚫 | ❌ | Enterprise feature |
| Direct connect server | 🚫 | ❌ | Enterprise feature |
| Self-update | ✅ | ❌ | Low priority |

---

## 8. UI / TUI

| Feature | TS | Python | Notes |
|---------|----|--------|-------|
| Message rendering (markdown, code, diff) | ✅ | ✅ | Python: Rich-based |
| Permission dialogs | ✅ | ✅ | Python: Rich TUI dialog |
| Status bar | ✅ | ✅ | Python: Rich status bar |
| Input with history | ✅ | ✅ | Python: prompt_toolkit |
| Spinner / thinking indicator | ✅ | ✅ | Python: Rich Status |
| Theme system | ✅ | ⚠️ | Python: config exists, not full theme picker |
| Vim mode | ✅ | ❌ | Low priority |
| Message search / history dialog | ✅ | ❌ | Low priority |
| Quick open / fuzzy picker | ✅ | ❌ | Low priority |
| Multi-panel layout | ✅ | ❌ | Textual experiment exists but disabled |
| Animated logo / splash | ✅ | ❌ | Low priority |

---

## Summary Statistics

| Category | TS Count | Python Count | Coverage |
|----------|----------|--------------|----------|
| Tools | ~40 core + ~15 exp | 51 | ~85% of core tools |
| Commands | ~80 built-in | 65 | ~81% of core commands |
| Core runtime | 12 major | 8 major | ~67% |
| Services | 22 areas | 3 areas | ~14% |
| UI/TUI | 15 major | 8 major | ~53% |

**Overall estimated parity: ~60-70% of the publicly relevant surface area.**

The biggest remaining gaps are:
1. **Session persistence & resume** (user experience critical)
2. **Auto-compact & token counting** (reliability critical)
3. **Plugin system** (extensibility critical)
4. **MCP full support** (integration critical)
5. **Headless / structured JSON mode** (automation critical)
