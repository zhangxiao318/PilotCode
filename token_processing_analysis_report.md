# PilotCode Token处理机制分析报告

## 1. 概述

PilotCode实现了完整的token计算和显示机制，采用OpenCode-style的精确token计数方法，优先使用后端精确token化器，同时提供备用的启发式估算方法。

## 2. Token计算实现

### 2.1 精确Token计数器 (PreciseTokenizer)

- **支持的后端**：llama.cpp、vLLM、Ollama、OpenAI、Anthropic、DeepSeek等
- **实现方式**：
  - 优先使用后端的`/tokenize`或`/api/tokenize`端点进行精确计算
  - 对于云API（OpenAI/Anthropic等）使用API返回的使用信息
  - 支持消息级token计算（包括工具定义）
  - 提供缓存机制避免重复请求

### 2.2 启发式Token估算器 (TokenEstimator)

- **主要估算策略**：
  - 基于字符/单词/标点符号的加权估算
  - 针对不同语言（CJK）的比率调整
  - 代码和非代码内容的不同估算因子
  - 结果缓存机制避免重复计算

### 2.3 计算优先级

1. **API报告的使用量**：最权威的token使用数据
2. **精确后端token化器**：精确计算（llama.cpp/vLLM/Ollama等）
3. **启发式估算**：作为备用方案

## 3. Token显示机制

### 3.1 TUI状态栏显示

在`src/pilotcode/tui_v2/components/status/bar.py`中实现：

- 右侧显示上下文使用情况：`context: 56.3% (147.5k/262.1k)`
- 显示会话ID（如果存在）
- 实时更新token计数
- 支持处理状态指示

### 3.2 显示格式

- 使用`k`和`m`后缀表示大数字（如147.5k）
- 显示百分比使用率
- 显示当前token数和可用token数

## 4. 查询引擎集成

在`src/pilotcode/query_engine.py`中集成：

- 实现`count_tokens()`方法，按优先级计算token
- 支持API使用量缓存
- 集成自动压缩机制（在token过载时自动清理历史）
- 支持token预算状态检查

## 5. 特色功能

### 5.1 上下文溢出检测

- 实现OpenCode风格的溢出检测逻辑
- 检测是否超出可用输入上下文
- 触发自动压缩机制

### 5.2 Token预算管理

- 实现token使用状态检查
- 提供当前使用情况和剩余量的统计

### 5.3 缓存机制

- 精确tokenizer结果缓存
- 启发式估算结果缓存
- 避免重复的HTTP请求和计算

## 6. 总结

PilotCode的token处理机制具有以下特点：

1. **精确性优先**：优先使用后端精确token计数器
2. **容错性强**：提供多层估算方案作为备份
3. **显示直观**：TUI中直观显示token使用情况
4. **自动管理**：集成自动压缩和溢出检测
5. **性能优化**：通过缓存减少重复计算和API调用

该机制为用户提供了准确的token使用信息，并有效管理了上下文长度，确保模型性能和用户体验。