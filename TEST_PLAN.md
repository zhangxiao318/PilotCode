# PilotCode 测试改进计划

## 当前状态 (Current Status)

### 测试统计
- **总工具数**: 48个
- **已测试工具**: 19个 (39.6%)
- **未测试工具**: 29个 (60.4%)
- **测试文件数**: 18个
- **测试覆盖率**: 约40%

### 测试文件分布
```
tests/
├── conftest.py                      # 全局fixtures
├── base.py                          # 测试基类 (新增)
├── unit/
│   ├── tools/
│   │   ├── test_bash.py            # Bash工具 (8测试)
│   │   ├── test_file_tools.py      # 文件工具 (9测试)
│   │   ├── test_git.py             # Git工具 (7测试)
│   │   └── test_git_complete.py    # Git完整测试 (新增, 12测试)
│   ├── core/
│   │   └── test_query_engine.py    # QueryEngine (11测试)
│   └── services/
│       └── test_permissions.py     # 权限系统 (10测试)
├── integration/
│   └── (待补充)
├── e2e/
│   └── (待补充)
└── parity_comprehensive/            # 现有兼容性测试
```

---

## 第一阶段: 基础设施完善 (Week 1)

### 目标
建立标准化的测试基础设施，统一测试规范。

### 任务清单

- [x] **1.1 创建测试基类** (`tests/base.py`)
  - [x] `ToolTestBase` - 工具测试基类
  - [x] `IntegrationTestBase` - 集成测试基类
  - [x] `MockLLMHelper` - LLM模拟助手
  - [x] `CategoryMarkers` - 测试分类标记

- [ ] **1.2 完善fixtures** (`tests/conftest.py`)
  - [ ] 添加 `temp_worktree` - 临时工作树
  - [ ] 添加 `mock_llm_client` - 模拟LLM客户端
  - [ ] 添加 `clean_app_state` - 干净应用状态
  - [ ] 添加 `sample_conversation` - 示例对话

- [ ] **1.3 创建测试数据**
  - [ ] `tests/fixtures/files/` - 示例文件
    - sample.py, sample.js, sample.json
    - large_file.txt, binary_file.bin
    - special_chars.txt, unicode.txt
  - [ ] `tests/fixtures/responses/` - API响应示例
    - llm_responses.json
    - tool_results.json

- [ ] **1.4 测试配置**
  - [ ] 更新 `pyproject.toml` pytest配置
  - [ ] 添加 `.coveragerc` 覆盖率配置
  - [ ] 添加 `pytest.ini` 本地配置

### 验收标准
- [ ] 所有新测试可以使用基类
- [ ] fixtures覆盖主要使用场景
- [ ] 测试可以在隔离环境运行

---

## 第二阶段: 核心工具测试 (Week 2-3)

### 目标
完成所有核心工具的测试，达到80%工具覆盖率。

### 优先级P0 - 核心工具 (必须完成)

| 工具 | 测试文件 | 测试数 | 状态 |
|------|----------|--------|------|
| GitDiff | test_git_complete.py | 4 | 🔄 |
| GitLog | test_git_complete.py | 4 | 🔄 |
| TaskCreate | test_task_tools.py | 5 | ⬜ |
| TaskGet | test_task_tools.py | 4 | ⬜ |
| TaskList | test_task_tools.py | 3 | ⬜ |
| Bash | test_bash.py | 8 | ✅ |
| FileRead | test_file_tools.py | 4 | ✅ |
| FileWrite | test_file_tools.py | 3 | ✅ |
| FileEdit | test_file_tools.py | 3 | ✅ |

### 优先级P1 - 重要工具

| 工具 | 测试文件 | 测试数 | 状态 |
|------|----------|--------|------|
| Agent | test_agent_tools.py | 6 | ⬜ |
| Glob | test_search_tools.py | 3 | ⬜ |
| Grep | test_search_tools.py | 4 | ⬜ |
| WebSearch | test_web_tools.py | 4 | ⬜ |
| WebFetch | test_web_tools.py | 3 | ⬜ |
| EnterWorktree | test_worktree_tools.py | 3 | ⬜ |
| ExitWorktree | test_worktree_tools.py | 3 | ⬜ |

### 测试模板

每个工具测试应包含:

```python
class Test<ToolName>Tool(ToolTestBase):
    """Test <ToolName> tool.
    
    Coverage:
    - 正常输入
    - 边界条件
    - 错误处理
    - 安全边界
    """
    
    tool_name = "<ToolName>"
    
    # === 正常功能测试 ===
    @pytest.mark.asyncio
    async def test_normal_operation(self, temp_dir):
        """Test normal operation."""
        pass
    
    # === 边界条件测试 ===
    @pytest.mark.asyncio
    async def test_empty_input(self, temp_dir):
        """Test with empty input."""
        pass
    
    @pytest.mark.asyncio
    async def test_large_input(self, temp_dir):
        """Test with large input."""
        pass
    
    # === 错误处理测试 ===
    @pytest.mark.asyncio
    async def test_invalid_input(self, temp_dir):
        """Test with invalid input."""
        pass
    
    @pytest.mark.asyncio
    async def test_missing_resource(self, temp_dir):
        """Test when resource doesn't exist."""
        pass
    
    # === 安全测试 ===
    @pytest.mark.asyncio
    @pytest.mark.security
    async def test_path_traversal(self, temp_dir):
        """Test path traversal protection."""
        pass
```

### 验收标准
- [ ] P0工具测试覆盖率100%
- [ ] P1工具测试覆盖率80%
- [ ] 所有测试通过
- [ ] 代码覆盖率>70%

---

## 第三阶段: 核心功能测试 (Week 4)

### 目标
测试核心功能模块，确保业务逻辑正确。

### 3.1 QueryEngine测试

文件: `tests/unit/core/test_query_engine_complete.py`

```
TestQueryEngineInitialization
├── test_init_with_defaults
├── test_init_with_custom_config
└── test_init_invalid_config

TestQueryEngineMessages
├── test_add_user_message
├── test_add_assistant_message
├── test_add_system_message
├── test_add_tool_use
├── test_add_tool_result
├── test_message_order
└── test_clear_history

TestQueryEngineTokenManagement
├── test_count_tokens_empty
├── test_count_tokens_with_messages
├── test_token_limit_warning
├── test_auto_compact_trigger
└── test_compact_history

TestQueryEngineToolExecution
├── test_single_tool_call
├── test_multiple_tool_calls
├── test_tool_call_chain
├── test_tool_error_handling
└── test_tool_timeout

TestQueryEngineSessionManagement
├── test_save_session
├── test_load_session
├── test_session_persistence
└── test_session_migration
```

### 3.2 权限系统测试

文件: `tests/unit/services/test_permissions_complete.py`

```
TestPermissionManager
├── test_default_deny
├── test_session_allow
├── test_session_deny
├── test_always_allow
├── test_never_allow
├── test_permission_inheritance
└── test_permission_reset

TestPermissionRequest
├── test_request_creation
├── test_request_fingerprint
├── test_request_serialization
└── test_request_deserialization

TestToolExecutorPermissions
├── test_execute_with_permission
├── test_execute_without_permission
├── test_execute_with_timeout
└── test_execute_with_retry
```

### 3.3 Session管理测试

文件: `tests/unit/core/test_session.py`

```
TestSessionCreation
├── test_create_new_session
├── test_load_existing_session
└── test_session_properties

TestSessionPersistence
├── test_save_to_disk
├── test_load_from_disk
├── test_auto_save
└── test_corruption_recovery

TestSessionForking
├── test_fork_session
├── test_merge_sessions
└── test_session_diff
```

---

## 第四阶段: 集成测试 (Week 5)

### 目标
测试组件间的交互，确保系统集成正确。

### 4.1 工具链测试

文件: `tests/integration/test_tool_chains.py`

```python
class TestFileWorkflow:
    """Test file-related tool workflows."""
    
    async def test_read_write_edit_cycle(self):
        """Test: Read -> Write -> Edit -> Read cycle."""
        pass
    
    async def test_glob_then_read(self):
        """Test: Glob files -> Read each."""
        pass
    
    async def test_grep_then_edit(self):
        """Test: Grep pattern -> Edit matches."""
        pass

class TestGitWorkflow:
    """Test git-related tool workflows."""
    
    async def test_feature_branch_workflow(self):
        """Test: Branch -> Commit -> Merge workflow."""
        pass
    
    async def test_code_review_workflow(self):
        """Test: Diff -> Status -> Log workflow."""
        pass

class TestSearchWorkflow:
    """Test search-related workflows."""
    
    async def test_find_and_replace(self):
        """Test: Grep -> Glob -> Edit workflow."""
        pass
```

### 4.2 LLM集成测试

文件: `tests/integration/test_llm_integration.py`

```python
class TestLLMConversation:
    """Test LLM conversation flow."""
    
    async def test_simple_conversation(self):
        """Test simple Q&A without tools."""
        pass
    
    async def test_tool_use_conversation(self):
        """Test conversation with tool use."""
        pass
    
    async def test_multi_turn_conversation(self):
        """Test multi-turn conversation."""
        pass
    
    async def test_error_recovery(self):
        """Test conversation recovery from errors."""
        pass
```

### 4.3 错误处理测试

文件: `tests/integration/test_error_handling.py`

```python
class TestErrorRecovery:
    """Test system error recovery."""
    
    async def test_tool_failure_recovery(self):
        """Test recovery from tool failure."""
        pass
    
    async def test_network_failure_recovery(self):
        """Test recovery from network failure."""
        pass
    
    async def test_llm_failure_recovery(self):
        """Test recovery from LLM failure."""
        pass
```

---

## 第五阶段: E2E测试 (Week 6)

### 目标
端到端测试，验证完整用户场景。

### 5.1 CLI测试

文件: `tests/e2e/test_cli.py`

```python
class TestCLICommands:
    """Test CLI commands."""
    
    def test_help_command(self):
        """Test --help output."""
        pass
    
    def test_version_command(self):
        """Test --version output."""
        pass
    
    def test_configure_command(self):
        """Test configure wizard."""
        pass

class TestCLIWorkflows:
    """Test CLI workflows."""
    
    def test_init_project(self):
        """Test: init -> add files -> commit."""
        pass
    
    def test_code_review(self):
        """Test: review -> suggest -> apply."""
        pass
```

### 5.2 性能测试

文件: `tests/e2e/test_performance.py`

```python
class TestPerformance:
    """Performance benchmarks."""
    
    @pytest.mark.benchmark
    def test_large_file_read(self):
        """Benchmark reading large files."""
        pass
    
    @pytest.mark.benchmark
    def test_many_tools_execution(self):
        """Benchmark executing many tools."""
        pass
    
    @pytest.mark.benchmark
    def test_long_conversation(self):
        """Benchmark long conversation handling."""
        pass
```

---

## CI/CD集成

### GitHub Actions工作流

```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python: ["3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v3
      - name: Run unit tests
        run: pytest tests/unit -v --cov=pilotcode
      - name: Upload coverage
        uses: codecov/codecov-action@v3

  integration-tests:
    needs: unit-tests
    runs-on: ubuntu-latest
    steps:
      - name: Run integration tests
        run: pytest tests/integration -v -m "not network"

  e2e-tests:
    needs: integration-tests
    runs-on: ubuntu-latest
    steps:
      - name: Run E2E tests
        run: pytest tests/e2e -v
```

---

## 验收标准

### 覆盖率目标
- [ ] 行覆盖率: > 80%
- [ ] 分支覆盖率: > 70%
- [ ] 函数覆盖率: > 90%

### 测试质量
- [ ] 所有P0测试通过
- [ ] 无flaky测试
- [ ] 测试运行时间 < 5分钟
- [ ] 文档覆盖率100%

### 可维护性
- [ ] 测试代码符合规范
- [ ] 有清晰的测试文档
- [ ] CI/CD流程自动化
- [ ] 有测试报告生成

---

## 附录: 快速命令

```bash
# 运行特定测试
pytest tests/unit/tools/test_bash.py -v

# 运行带覆盖率
pytest tests/unit --cov=pilotcode --cov-report=html

# 运行特定标记
pytest -m "not network and not slow"

# 生成测试报告
pytest --html=report.html --self-contained-html
```
