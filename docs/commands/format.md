# /format 命令

格式化代码，使用 `black` 或 `autopep8` 作为底层工具。

## 作用

- 自动格式化 Python 代码，统一代码风格
- 支持格式化单个文件或整个目录
- 额外参数透传给底层格式化工具

## 基本用法

```bash
/format                    # 格式化当前目录下的所有 Python 文件
/format src/foo.py         # 格式化指定文件
/format src/ --diff        # 显示 diff 而不实际写入（black）
/format --check            # 检查格式而不写入（black）
/format --line-length 120  # 设置行宽（black）
```

## 选项

所有参数都会透传给 `black`。常用选项：

| 选项 | 说明 |
|------|------|
| `--diff` | 显示改动差异，不写入文件 |
| `--check` | 检查格式，有未格式化文件时返回非 0 |
| `--line-length <n>` | 设置最大行宽（默认 88） |
| `--skip-string-normalization` | 不统一引号风格 |
| `--target-version` | 指定 Python 版本（如 py311） |

## 使用示例

### 场景1：格式化当前项目

```bash
/format
```

### 场景2：格式化指定文件

```bash
/format src/main.py
```

### 场景3：预览改动

```bash
/format --diff
```

### 场景4：使用 autopep8（black 不可用时）

如果系统中没有安装 `black`，命令会自动回退到 `autopep8`。

## 注意事项

- **目前仅支持 Python 语言**。如需支持其他语言（如 C/C++ 的 `clang-format`、JS/TS 的 `prettier` 等），请联系开发者。
- 格式化前建议先使用 `/lint` 检查代码问题。
- `black` 是不可配置风格的格式化工具，它会强制执行统一的 PEP 8 风格。

## 相关命令

- `/lint` - 代码静态检查
