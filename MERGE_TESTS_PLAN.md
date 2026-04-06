# 测试目录合并计划

## 当前状况

### tests/ (根目录) - 27个文件
**新测试架构**，结构清晰：
- ✅ 遵循 pytest 最佳实践
- ✅ 有 `conftest.py` fixtures
- ✅ 有 `base.py` 测试基类
- ✅ 有 `unit/` `integration/` `e2e/` 分层
- ✅ `pyproject.toml` 配置的测试路径

### src/tests/ (包内) - 34个文件
**历史遗留测试**，较混乱：
- 所有测试文件平铺在目录下
- 没有 fixtures
- 部分测试可能已过时
- 总大小约 400KB

## 合并策略

### 原则
1. **保留 tests/ 作为唯一测试目录** (已配置在 pyproject.toml)
2. **按功能分类** 合并 src/tests/ 中的测试
3. **删除重复** 测试
4. **保留有价值** 的测试

### 合并映射

| src/tests/ 文件 | 目标位置 | 处理方式 |
|----------------|----------|----------|
| test_tools.py | tests/unit/tools/test_tools_legacy.py | 保留 |
| test_git_commands.py | tests/unit/tools/test_git_legacy.py | 保留 |
| test_file_selector_tool.py | tests/unit/tools/test_file_selector.py | 保留 |
| test_ripgrep_tool.py | tests/unit/tools/test_ripgrep.py | 保留 |
| test_web_browser_tool.py | tests/unit/tools/test_web_browser.py | 保留 |
| test_tui_enhanced.py | tests/unit/tui/ | 保留 |
| test_unicode_input.py | tests/unit/tui/ | 保留 |
| test_query_engine.py | 删除 (已有新版) | 删除 |
| test_permissions.py | 删除 (已有新版) | 删除 |
| test_integration.py | 删除 (需重写) | 删除 |
| test_agent_system.py | tests/integration/ | 移动 |
| test_services_advanced.py | tests/integration/ | 移动 |
| parity_comprehensive/* | tests/parity/ | 移动 |
| 其他 services 测试 | tests/unit/services/ | 分类移动 |

## 操作步骤

### Step 1: 创建目标目录结构
```bash
mkdir -p tests/unit/tools/legacy
mkdir -p tests/unit/services/legacy
mkdir -p tests/unit/tui/legacy
mkdir -p tests/integration/legacy
mkdir -p tests/parity
```

### Step 2: 移动并分类文件

#### 工具测试 (Tools)
```bash
mv src/tests/test_tools.py tests/unit/tools/legacy/
mv src/tests/test_git_commands.py tests/unit/tools/legacy/
mv src/tests/test_file_selector_tool.py tests/unit/tools/legacy/
mv src/tests/test_ripgrep_tool.py tests/unit/tools/legacy/
mv src/tests/test_web_browser_tool.py tests/unit/tools/legacy/
```

#### TUI测试
```bash
mv src/tests/test_tui_enhanced.py tests/unit/tui/legacy/
mv src/tests/test_unicode_input.py tests/unit/tui/legacy/
```

#### 服务测试 (Services)
```bash
mv src/tests/test_ai_security.py tests/unit/services/legacy/
mv src/tests/test_analytics_service.py tests/unit/services/legacy/
mv src/tests/test_binary_feedback.py tests/unit/services/legacy/
mv src/tests/test_context_manager.py tests/unit/services/legacy/
mv src/tests/test_embedding_service.py tests/unit/services/legacy/
mv src/tests/test_error_recovery.py tests/unit/services/legacy/
mv src/tests/test_event_bus.py tests/unit/services/legacy/
mv src/tests/test_file_metadata_cache.py tests/unit/services/legacy/
mv src/tests/test_file_watcher.py tests/unit/services/legacy/
mv src/tests/test_github_service.py tests/unit/services/legacy/
mv src/tests/test_lsp_manager.py tests/unit/services/legacy/
mv src/tests/test_mcp_config_manager.py tests/unit/services/legacy/
mv src/tests/test_model_router.py tests/unit/services/legacy/
mv src/tests/test_prompt_cache.py tests/unit/services/legacy/
mv src/tests/test_result_truncation.py tests/unit/services/legacy/
mv src/tests/test_session_persistence.py tests/unit/services/legacy/
mv src/tests/test_task_queue.py tests/unit/services/legacy/
mv src/tests/test_team_manager.py tests/unit/services/legacy/
mv src/tests/test_tool_sandbox.py tests/unit/services/legacy/
mv src/tests/test_update_checker.py tests/unit/services/legacy/
```

#### 集成测试
```bash
mv src/tests/test_agent_system.py tests/integration/legacy/
mv src/tests/test_services_advanced.py tests/integration/legacy/
mv src/tests/test_code_index.py tests/integration/legacy/
mv src/tests/test_code_intelligence_commands.py tests/integration/legacy/
mv src/tests/test_conversation_fork.py tests/integration/legacy/
mv src/tests/test_package_commands.py tests/integration/legacy/
mv src/tests/test_snapshot.py tests/integration/legacy/
mv src/tests/test_testing_commands.py tests/integration/legacy/
```

#### 其他测试
```bash
mv src/tests/parity_comprehensive tests/parity/
```

#### 删除重复/过时测试
```bash
rm src/tests/test_query_engine.py  # 已有新版
rm src/tests/test_permissions.py   # 已有新版
rm src/tests/test_integration.py   # 需重写
```

### Step 3: 删除空目录
```bash
rm -rf src/tests/
```

### Step 4: 验证
```bash
# 运行测试确保没有破坏
pytest tests/ -v --collect-only | head -50
```

## 合并后目录结构

```
tests/
├── conftest.py                    # 全局fixtures
├── base.py                        # 测试基类
├── README.md                      # 测试文档
├── fixtures/                      # 测试数据
├── unit/                          # 单元测试
│   ├── tools/                     # 工具测试
│   │   ├── test_bash.py
│   │   ├── test_file_tools.py
│   │   ├── test_git.py
│   │   ├── test_git_complete.py
│   │   └── legacy/               # 从src/tests/合并
│   │       ├── test_tools.py
│   │       ├── test_git_commands.py
│   │       ├── test_file_selector_tool.py
│   │       ├── test_ripgrep_tool.py
│   │       └── test_web_browser_tool.py
│   ├── core/                      # 核心功能
│   │   └── test_query_engine.py
│   ├── services/                  # 服务层
│   │   ├── test_permissions.py
│   │   └── legacy/               # 从src/tests/合并
│   │       ├── test_ai_security.py
│   │       ├── test_analytics_service.py
│   │       └── ...
│   └── tui/                       # TUI测试
│       └── legacy/               # 从src/tests/合并
│           ├── test_tui_enhanced.py
│           └── test_unicode_input.py
├── integration/                   # 集成测试
│   └── legacy/                   # 从src/tests/合并
│       ├── test_agent_system.py
│       ├── test_services_advanced.py
│       └── ...
├── e2e/                          # 端到端测试
├── parity/                       # 兼容性测试 (从src/tests/合并)
│   └── comprehensive/
└── __init__.py
```

## 好处

1. **单一测试源** - 避免 confusion
2. **统一结构** - 遵循 pytest 最佳实践
3. **简化配置** - 只需配置一个 testpaths
4. **清晰分层** - unit/integration/e2e 明确
5. **向后兼容** - 保留旧测试在 legacy/ 目录

## 后续工作

合并后可以逐步：
1. 将 `legacy/` 中的测试迁移到标准位置
2. 使用新的 `base.py` 基类重构
3. 删除重复的测试
4. 最终移除 `legacy/` 目录
