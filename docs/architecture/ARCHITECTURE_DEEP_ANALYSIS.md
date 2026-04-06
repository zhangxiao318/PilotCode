# Claude Code 深度架构分析 - 第二轮

## 已识别的缺失功能

### 1. Binary Feedback 机制 ⭐⭐⭐
**Claude Code 功能**: 用于程序员测试 prompt 稳定性
- 同时发送两个完全相同的请求给模型
- 比较结构化输出（tool_use）是否一致
- 如果不一致，说明模型对请求犹豫，需要优化 prompt
- 仅在 `USER_TYPE === 'ant'` 时启用（内部测试）

**实现计划**:
- [ ] `services/binary_feedback.py` - Binary Feedback 服务
- [ ] 双重请求并行发送
- [ ] Tool use 结果比较
- [ ] Prompt 稳定性报告

### 2. Conversation Fork / Summarize ⭐⭐⭐
**Claude Code 功能**: 清空对话历史但保留上下文摘要
- 使用 Sonnet 模型生成对话摘要
- 创建新的对话分支 (`setForkConvoWithMessagesOnTheNextRender`)
- 将摘要的 token 使用量设为 0
- 清理 getContext 和 getCodeStyle 缓存

**实现计划**:
- [ ] `services/conversation_fork.py` - 对话分叉服务
- [ ] 摘要生成逻辑
- [ ] Token 使用优化
- [ ] 缓存清理

### 3. ripgrep 集成 ⭐⭐⭐
**Claude Code 功能**: 高性能代码搜索
- 内置预编译 ripgrep 二进制文件
- 毫秒级代码库搜索
- 结果按修改时间排序
- 跨平台一致性

**实现计划**:
- [ ] `tools/ripgrep_tool.py` - ripgrep 工具
- [ ] 自动下载/使用系统 rg
- [ ] 结果排序和格式化
- [ ] 与现有 GrepTool 集成

### 4. 分层项目加载 ⭐⭐
**Claude Code 功能**: 按需加载项目结构
- 先获取高层次项目结构
- 根据需要深入特定目录
- 避免一次性加载过多内容

**实现计划**:
- [ ] `services/project_loader.py` - 分层项目加载器
- [ ] 惰性目录扫描
- [ ] 缓存层

### 5. 自动更新检查 ⭐⭐
**Claude Code 功能**: 自动检查新版本
- 启动时检查最新版本
- 提示用户更新
- 可选自动更新

**实现计划**:
- [ ] `services/update_checker.py` - 更新检查器
- [ ] GitHub API / PyPI 版本检查
- [ ] 更新提示

### 6. TUI 增强 ⭐⭐
**Claude Code 功能**: 丰富的终端 UI
- 消息渲染器（Ink 风格）
- 权限对话框
- 状态栏
- 主题系统

**当前状态**: 已有基础 TUI，需要增强

## 实施优先级

### P0 (本周实现)
1. Binary Feedback 机制
2. Conversation Fork

### P1 (下周实现)
3. ripgrep 集成
4. 自动更新检查

### P2 (后续)
5. 分层项目加载
6. TUI 增强
