# /cost 命令

查看使用统计和成本信息。

## 作用

- 查看 Token 使用量
- 查看 API 调用成本
- 统计当前会话和累计使用

## 基本用法

```bash
/cost [options]
```

## 选项

| 选项 | 说明 |
|------|------|
| (无) | 显示当前会话统计 |
| `total` | 显示累计统计 |
| `reset` | 重置统计 |

## 使用示例

### 查看当前会话统计

```bash
/cost
```

输出示例：
```
📊 Current Session Usage:
  Messages: 42
  Input tokens: 12,345
  Output tokens: 3,456
  Total tokens: 15,801
  Estimated cost: $0.0234
```

### 查看累计统计

```bash
/cost total
```

输出示例：
```
📊 Total Usage:
  Sessions: 15
  Total messages: 523
  Total tokens: 156,789
  Total cost: $0.2345

By model:
  deepseek:  $0.1800 (76.7%)
  qwen:      $0.0400 (17.1%)
  openai:    $0.0145 (6.2%)
```

### 重置统计

```bash
/cost reset
```

## 成本计算

成本根据使用的模型和 Token 数量计算：

| 模型 | 输入价格 | 输出价格 |
|------|----------|----------|
| DeepSeek | $0.14/1M tokens | $0.28/1M tokens |
| Qwen | $0.50/1M tokens | $1.00/1M tokens |
| GPT-4o | $2.50/1M tokens | $10.00/1M tokens |
| Claude 3.5 | $3.00/1M tokens | $15.00/1M tokens |

注意：实际价格以各服务商官方为准，仅供参考。

## 使用场景

### 场景1：监控使用情况

```bash
# 定期检查使用量
/cost
```

### 场景2：月度统计

```bash
# 查看累计使用（月度统计）
/cost total
```

### 场景3：控制成本

```bash
# 查看当前会话成本
/cost

# 如果成本较高，可以考虑
/compact  # 压缩会话历史
```

## 相关命令

- `/compact` - 压缩会话历史以降低成本
- `/model` - 切换到更经济的模型