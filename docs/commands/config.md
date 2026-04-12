# /config 命令

配置管理命令，用于查看和修改 PilotCode 的设置。

## 作用

- 查看当前配置
- 修改配置项
- 重置配置

## 基本用法

```bash
/config [subcommand]
```

## 子命令

| 子命令 | 说明 |
|--------|------|
| (无) | 显示当前配置 |
| `set <key> <value>` | 设置配置项 |
| `get <key>` | 获取配置项 |
| `reset` | 重置为默认配置 |

## 使用示例

### 查看当前配置

```bash
/config
```

输出示例：
```json
{
  "theme": "default",
  "verbose": false,
  "auto_compact": true,
  "default_model": "deepseek",
  "model_provider": "deepseek",
  "api_key": "sk-****",
  "base_url": "https://api.deepseek.com/v1"
}
```

### 设置配置项

```bash
# 设置主题
/config set theme dark

# 启用详细模式
/config set verbose true

# 设置默认模型
/config set default_model qwen
```

### 获取配置项

```bash
# 获取当前主题
/config get theme

# 获取当前模型
/config get default_model
```

### 重置配置

```bash
# 重置为默认配置
/config reset
```

## 常用配置项

| 配置项 | 说明 | 可选值 |
|--------|------|--------|
| `theme` | 界面主题 | `default`, `dark`, `light` |
| `verbose` | 详细模式 | `true`, `false` |
| `auto_compact` | 自动压缩历史 | `true`, `false` |
| `default_model` | 默认模型 | 模型名称 |
| `model_provider` | 模型提供商 | `deepseek`, `openai`, `qwen` 等 |

## 配置文件位置

配置文件存储在：

```
~/.config/pilotcode/settings.json
```

## 使用场景

### 场景1：切换模型

```bash
# 查看当前模型
/config get default_model

# 切换到 Qwen
/config set default_model qwen

# 验证切换
/config get default_model
```

### 场景2：切换主题

```bash
# 切换到暗色主题
/config set theme dark

# 切回默认主题
/config set theme default
```

### 场景3：查看完整配置

```bash
# 显示所有配置
/config
```

## 相关命令

- `/model` - 快速切换模型
- `/theme` - 快速切换主题