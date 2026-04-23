# LLM 接口设置指南

本指南介绍如何配置 PilotCode 连接到大语言模型（LLM）API。

---

## 概述

PilotCode 支持多种 LLM 提供商：

- **OpenAI** (GPT-4, GPT-3.5)
- **Anthropic** (Claude)
- **本地模型** (Ollama, llama.cpp)
- **自定义 API** (兼容 OpenAI API 格式)

---

## 配置方式

PilotCode 支持三种配置方式（按优先级排序）：

1. **环境变量** - 临时覆盖，适合测试
2. **配置文件** - 持久化设置，日常使用
3. **交互式命令** - 动态修改，即时生效

---

## 方式一：交互式命令（推荐）

使用 `/config` 命令在运行时修改配置：

```bash
# 启动 PilotCode
./pilotcode

# 在交互式界面中执行
/config --list                    # 查看当前配置
/config --set api_key --value "sk-xxx"      # 设置 API 密钥
/config --set base_url --value "https://api.openai.com/v1"  # 设置 API 地址
/config --set default_model --value "gpt-4" # 设置默认模型
```

### 常用配置项

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `api_key` | API 密钥 | `sk-abc123...` |
| `base_url` | API 基础地址 | `https://api.openai.com/v1` |
| `default_model` | 默认模型 | `gpt-4`, `claude-3-sonnet` |
| `theme` | 界面主题 | `default`, `dark`, `light` |
| `verbose` | 详细日志 | `true`, `false` |
| `auto_compact` | 自动压缩上下文 | `true`, `false` |

---

## 方式二：配置文件

### 全局配置文件

位置：`~/.config/pilotcode/settings.json`

```bash
# 创建配置目录
mkdir -p ~/.config/pilotcode

# 创建配置文件
cat > ~/.config/pilotcode/settings.json << 'EOF'
{
  "theme": "default",
  "verbose": false,
  "auto_compact": true,
  "api_key": "your-api-key-here",
  "base_url": "https://api.openai.com/v1",
  "default_model": "gpt-4",
  "allowed_tools": [],
  "mcp_servers": {}
}
EOF
```

### 项目级配置

在项目根目录创建 `.pilotcode.json`：

```bash
cat > .pilotcode.json << 'EOF'
{
  "allowed_tools": ["Read", "Bash", "Grep"],
  "custom_instructions": "This is a Python project. Follow PEP 8."
}
EOF
```

项目配置会与全局配置合并，优先级更高。

---

## 方式三：环境变量

### 标准环境变量

```bash
# 临时设置（当前终端）
export PILOTCODE_API_KEY="sk-xxx"
export PILOTCODE_BASE_URL="https://api.openai.com/v1"
export PILOTCODE_MODEL="gpt-4"

# 启动 PilotCode
./pilotcode
```

### 兼容环境变量

为兼容其他工具，以下环境变量也受支持：

```bash
export OPENAI_API_KEY="sk-xxx"        # 等同于 PILOTCODE_API_KEY
export OPENAI_BASE_URL="https://..."  # 等同于 PILOTCODE_BASE_URL
export ANTHROPIC_API_KEY="sk-ant-..." # Anthropic 密钥
```

### 持久化环境变量

添加到 shell 配置文件：

```bash
# Bash
export PILOTCODE_API_KEY="sk-xxx" >> ~/.bashrc
source ~/.bashrc

# Zsh
export PILOTCODE_API_KEY="sk-xxx" >> ~/.zshrc
source ~/.zshrc
```

---

## 常见 LLM 配置示例

### OpenAI

```json
{
  "api_key": "sk-your-openai-key",
  "base_url": "https://api.openai.com/v1",
  "default_model": "gpt-4"
}
```

### Anthropic Claude

```json
{
  "api_key": "sk-ant-your-anthropic-key",
  "base_url": "https://api.anthropic.com/v1",
  "default_model": "claude-3-5-sonnet-20241022"
}
```

### Azure OpenAI

```json
{
  "api_key": "your-azure-key",
  "base_url": "https://your-resource.openai.azure.com/openai/deployments/your-deployment",
  "default_model": "gpt-4"
}
```

### Ollama (本地模型)

```json
{
  "api_key": "",
  "base_url": "http://localhost:11434/v1",
  "default_model": "ollama",
  "context_window": 128000
}
```

> 本地模型以 `settings.json` 为唯一配置来源。启动时会自动探测实际能力（上下文窗口、模型名等），发现不一致时提示确认后自动修复。

### 自定义 API (vLLM, TGI 等)

```json
{
  "api_key": "optional-key",
  "base_url": "http://localhost:8000/v1",
  "default_model": "vllm",
  "context_window": 204800
}
```

> vLLM 启动时会自动探测 `/v1/models` 获取实际模型 ID（如 `qwen-coder`），若与 `default_model` 不一致会提示确认后更新。

---

## 验证配置

### 启动检查

启动时会自动检查配置：

```bash
./pilotcode
```

如果配置正确，将直接进入交互界面。如果配置缺失，会显示提示。

### 测试连接

在交互界面中测试：

```
你好，请用一句话介绍自己
```

如果能收到回复，说明配置正确。

### 诊断命令

```
/doctor              # 运行诊断检查
/status              # 查看系统状态
/config --verify     # 验证配置
```

---

## 多模型切换

### 命令行参数

```bash
./pilotcode --model gpt-4        # 使用 GPT-4
./pilotcode --model claude-3     # 使用 Claude
```

### 运行时切换

```
/model gpt-4         # 切换到 GPT-4
/model claude-3      # 切换到 Claude
```

### 会话级切换

```
使用 GPT-4 分析这段代码
使用 Claude 总结文档
```

---

## 故障排除

### API 连接失败

```
Error: Connection failed
```

**解决方法：**
1. 检查网络连接
2. 验证 API 密钥
3. 检查 base_url 是否正确
4. 确认 API 服务可用

```bash
# 测试 API 可用性
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

### 认证错误

```
Error: Authentication failed
```

**解决方法：**
1. 检查 API 密钥是否过期
2. 确认密钥格式正确（以 `sk-` 开头）
3. 验证密钥权限

### 模型不可用

```
Error: Model not found
```

**解决方法：**
1. 检查模型名称拼写
2. 确认账户有权限访问该模型
3. 使用 `/models` 查看可用模型

### 超时错误

```
Error: Request timeout
```

**解决方法：**
1. 检查网络连接
2. 增加超时设置
3. 使用本地模型避免网络延迟

---

## 安全建议

1. **不要将 API 密钥提交到版本控制**
   ```bash
   echo ".pilotcode.json" >> .gitignore
   ```

2. **使用环境变量存储敏感信息**
   ```bash
   export PILOTCODE_API_KEY="$(cat ~/.api_key)"
   ```

3. **定期轮换 API 密钥**

4. **使用项目级配置隔离不同项目**

---

## 快速参考

| 操作 | 命令 |
|------|------|
| 查看配置 | `/config --list` |
| 设置 API 密钥 | `/config --set api_key --value "xxx"` |
| 设置模型 | `/config --set default_model --value "gpt-4"` |
| 验证配置 | `/config --verify` |
| 查看状态 | `/status` |
| 运行诊断 | `/doctor` |

---

## 相关文档

- [快速开始](./QUICKSTART.md)
- [Windows 安装指南](./WINDOWS_GUIDE.md)
