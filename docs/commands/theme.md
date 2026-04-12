# /theme 命令

切换界面主题。

## 作用

- 切换终端界面颜色主题
- 适应不同的环境光线
- 个性化界面外观

## 基本用法

```bash
/theme [theme_name]
```

## 可用主题

| 主题 | 说明 |
|------|------|
| `default` | 默认主题（自动检测） |
| `dark` | 深色主题 |
| `light` | 浅色主题 |

## 使用示例

### 查看当前主题

```bash
/theme
```

输出：
```
Current theme: default
Available themes: default, dark, light
```

### 切换到深色主题

```bash
/theme dark
```

### 切换到浅色主题

```bash
/theme light
```

### 恢复默认主题

```bash
/theme default
```

## 使用场景

### 场景1：夜间开发

```bash
# 晚上使用时切换到深色主题，保护眼睛
/theme dark
```

### 场景2：光线充足环境

```bash
# 白天或光线好的地方使用浅色主题
/theme light
```

### 场景3：系统主题切换

```bash
# 根据系统主题自动调整（default）
/theme default
```

## 与 /config 的关系

主题设置也会保存在配置中，等效于：

```bash
/config set theme dark
```

## 相关命令

- `/config` - 完整配置管理