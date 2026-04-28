# /lint 命令

对代码进行静态检查，使用 `ruff` 或 `flake8` 作为底层工具。

## 作用

- 检查 Python 代码中的潜在错误和风格问题
- 支持 `--fix` 自动修复部分问题
- 额外参数透传给底层检查工具

## 基本用法

```bash
/lint                      # 检查当前目录下的所有 Python 文件
/lint src/foo.py           # 检查指定文件
/lint --fix                # 自动修复可修复的问题（ruff）
/lint --select E,W,F       # 只检查指定规则（ruff）
/lint --ignore E501        # 忽略指定规则（ruff）
```

## 选项

所有参数都会透传给 `ruff check`。常用选项：

| 选项 | 说明 |
|------|------|
| `--fix` | 自动修复可修复的问题 |
| `--select <rules>` | 只启用指定的规则 |
| `--ignore <rules>` | 忽略指定的规则 |
| `--show-source` | 显示问题源码上下文 |

## 使用示例

### 场景1：检查当前项目

```bash
/lint
```

### 场景2：检查并自动修复

```bash
/lint --fix
```

### 场景3：检查指定文件

```bash
/lint src/main.py
```

### 场景4：使用 flake8（ruff 不可用时）

如果系统中没有安装 `ruff`，命令会自动回退到 `flake8`。

## 注意事项

- **目前仅支持 Python 语言**。如需支持其他语言（如 C/C++ 的 `clang-tidy`、JS/TS 的 `eslint` 等），请联系开发者。
- 建议先运行 `/lint` 检查问题，确认无误后再运行 `/format` 格式化代码。
- `ruff` 是 Rust 编写的高速 linter，与 `flake8` 的规则兼容但速度更快。

## 相关命令

- `/format` - 代码格式化
