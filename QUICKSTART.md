# PilotCode 快速开始指南

[中文](QUICKSTART.md) | [English](QUICKSTART_EN.md)

在 5 分钟内启动 PilotCode AI 编程助手。

---

## 1. 安装环境

### 系统要求
- Python 3.11 或更高版本
- Linux/macOS/Windows

### 安装步骤

```bash
# 克隆仓库
git clone <repository-url>
cd PilotCode

# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# 或: venv\Scripts\activate  # Windows

# 安装依赖
pip3 install -e .
```

**验证安装：**
```bash
python3 -m pilotcode --version
```

---

## 2. 配置 LLM

PilotCode 支持多种大语言模型，包括国际模型（OpenAI、Anthropic）和国内模型（DeepSeek、Qwen、GLM 等）。

### 方式一：交互式配置（推荐）

运行配置向导，按提示选择模型并输入 API 密钥：

```bash
python3 -m pilotcode configure
```

向导会引导你完成：
1. 选择模型类型（国际/国内/本地）
2. 选择具体模型
3. 输入 API 密钥
4. 可选设置（主题、自动压缩等）

### 方式二：快速配置（命令行）

如果你已经知道要使用的模型和 API 密钥：

```bash
# DeepSeek 示例
python3 -m pilotcode configure --model deepseek --api-key sk-xxx

# Qwen 示例
python3 -m pilotcode configure --model qwen --api-key sk-xxx

# OpenAI 示例
python3 -m pilotcode configure --model openai --api-key sk-xxx
```

### 方式三：环境变量

```bash
# 通用配置
export PILOTCODE_API_KEY="your-api-key"
export PILOTCODE_MODEL="deepseek"
export PILOTCODE_BASE_URL="https://api.deepseek.com/v1"

# 服务商特定（自动识别）
export OPENAI_API_KEY="sk-..."
export DEEPSEEK_API_KEY="sk-..."
export DASHSCOPE_API_KEY="sk-..."  # Qwen
export ZHIPU_API_KEY="..."         # GLM
```

### 方式四：手动配置文件

创建 `~/.config/pilotcode/settings.json`：

```bash
mkdir -p ~/.config/pilotcode
cat > ~/.config/pilotcode/settings.json << 'EOF'
{
  "theme": "default",
  "verbose": false,
  "auto_compact": true,
  "default_model": "deepseek",
  "model_provider": "deepseek",
  "api_key": "your-api-key",
  "base_url": "https://api.deepseek.com/v1"
}
EOF
```

### 支持的模型

| 模型 | 命令 | 描述 |
|------|------|------|
| DeepSeek | `--model deepseek` | 代码能力强，性价比高 |
| Qwen | `--model qwen` | 阿里通义千问 |
| GLM | `--model zhipu` | 智谱清言 |
| OpenAI | `--model openai` | GPT-4o |
| Claude | `--model anthropic` | Claude 3.5 Sonnet |
| Ollama | `--model ollama` | 本地运行，无需 API 密钥 |

查看所有支持的模型：
```bash
python3 -m pilotcode configure --list-models
```

### 查看当前配置

```bash
python3 -m pilotcode configure --show
```

---

## 3. 运行 PilotCode

### 启动交互式 TUI

```bash
# 默认启动（推荐）
python3 -m pilotcode

# 或使用启动脚本（Linux/macOS）
./pilotcode.sh

# Windows 使用
.\pilotcode.cmd

# 或使用别名（安装后）
pilotcode
pc
```

### 单次命令模式

```bash
# 执行单条命令后退出
python3 -m pilotcode -p "分析当前目录的代码结构"
```

### 简单 CLI 模式（无 TUI）

```bash
python3 -m pilotcode --simple
```

### 其他启动选项

```bash
# 指定工作目录
python3 -m pilotcode --cwd /path/to/project

# 自动允许所有工具执行（谨慎使用）
python3 -m pilotcode --auto-allow

# 显示详细日志
python3 -m pilotcode --verbose
```

---

## 快速验证

启动后，输入测试消息验证是否正常工作：

```
你好，请介绍一下自己
```

如果看到 AI 回复，说明配置成功！

---

## 常用命令

在 PilotCode 交互界面中，可以使用以下命令：

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助信息 |
| `/index` | 索引代码库（用于智能搜索） |
| `/search` | 语义/符号代码搜索 |
| `/model <name>` | 切换模型 |
| `/config` | 查看/修改配置 |
| `/theme` | 切换主题 |
| `/session` | 会话管理 |
| `/cost` | 查看用量统计 |
| `/quit` | 退出 |

---

## 代码索引与搜索

PilotCode 提供企业级的代码索引和智能搜索功能，帮助你快速理解和定位代码。

### 为什么要使用代码索引？

| 场景 | 无索引（Grep） | 有索引（Code Index） |
|------|--------------|-------------------|
| 查找函数定义 | 扫描所有文件（慢） | 毫秒级符号跳转 |
| 语义查询 | 不支持 | 支持自然语言搜索 |
| 大项目（1000+文件） | 性能急剧下降 | 依然快速 |
| 代码关系分析 | 手动整理 | 自动提取类/函数关系 |

### /index 命令 - 索引代码库

首次使用代码搜索前，需要先建立索引：

```bash
# 增量索引（只索引变化的文件，推荐）
/index

# 完整重新索引
/index full

# 查看索引统计
/index stats

# 清除索引
/index clear

# 导出/导入索引
/index export
/index import
```

**索引统计示例：**
```
📊 Index Statistics
Files: 369
Symbols: 3574
Snippets: 1777
Last Indexed: 2026-04-12 09:29:03

Languages:
  python: 369 files
  cpp: 42 files
  c: 15 files
```

### /search 命令 - 智能代码搜索

支持四种搜索方式：

#### 1. 语义搜索（默认）
使用自然语言描述你想找的代码：
```bash
# 搜索用户认证相关的代码
/search authentication logic

# 搜索数据库连接相关
/search database connection pool

# 搜索错误处理
/search error handling and retry
```

#### 2. 符号搜索（精确查找）
查找函数、类、变量定义：
```bash
# 查找类定义
/search -s UserModel

# 查找函数
/search -s authenticate_user

# 查找方法
/search -s calculate_total
```

#### 3. 正则搜索
使用正则表达式匹配：
```bash
# 查找所有类定义
/search -r "class \w+"

# 查找特定模式的函数
/search -r "def.*auth"

# 查找 TODO 注释
/search -r "TODO|FIXME|XXX"
```

#### 4. 文件搜索
按文件名搜索：
```bash
# 查找所有测试文件
/search -f "*test*.py"

# 查找配置文件
/search -f "config.*"
```

#### 高级过滤
```bash
# 按语言过滤
/search authentication -l python

# 按文件模式过滤
/search database -f "*.py"

# 限制结果数量
/search -s User -n 5
```

### 使用场景示例

#### 场景1：理解陌生项目
```bash
# 第一步：建立索引
/index full

# 查看项目概览
/index stats

# 搜索项目入口
/search main function

# 搜索核心类
/search -s "Main|App|Server"
```

#### 场景2：查找特定功能的实现
```bash
# 语义搜索更直观
/search password hashing

# 找到后查看具体实现
/search -s hash_password
```

#### 场景3：代码重构前分析
```bash
# 查找所有使用某函数的地方
/search -s old_function_name

# 查找继承关系
/search -r "class.*\(OldClass\)"
```

#### 场景4：C/C++ 项目开发
```bash
# 索引 C/C++ 项目
/index full

# 查找头文件中的宏
/search -r "#define MAX"

# 查找类定义（支持 .cpp/.cc/.cxx/.hpp/.hh/.hxx）
/search -s "MyClass"

# 查找函数实现
/search -s "process_data"
```

### 支持的编程语言

代码索引支持以下语言：

| 语言 | 扩展名 | 符号提取 |
|------|--------|----------|
| Python | `.py` | ✅ 类、函数、方法、变量 |
| C | `.c`, `.h` | ✅ 函数、结构体、宏、typedef |
| C++ | `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hh`, `.hxx` | ✅ 类、函数、方法、命名空间、模板 |
| JavaScript | `.js`, `.jsx` | ✅ 类、函数、方法 |
| TypeScript | `.ts`, `.tsx` | ✅ 类、接口、函数 |
| Go | `.go` | ✅ 函数、结构体 |
| Rust | `.rs` | ✅ 函数、结构体、trait |
| Java | `.java` | ✅ 类、方法、接口 |
| 其他 | `.rb`, `.php`, `.swift`, `.kt` | ⚠️ 基础支持 |

### 最佳实践

1. **首次使用项目时**：先运行 `/index full` 建立完整索引
2. **代码变化后**：运行 `/index` 进行增量更新
3. **查找具体符号**：使用 `/search -s SymbolName`（最快）
4. **探索性搜索**：使用语义搜索 `/search natural language query`
5. **大项目优化**：如果项目很大，首次索引可能需要 2-3 分钟

### 故障排除

```bash
# 搜索返回空结果？
/index stats          # 检查是否已索引
/index full           # 尝试重新索引

# 索引很慢？
/index clear          # 清除后重新索引
# 注意：首次索引大项目（1000+文件）需要几分钟是正常的

# 想查看索引了哪些文件？
/search -f "*.py" -n 50    # 列出前50个Python文件
```

---

## 获取 API 密钥

- **DeepSeek**: https://platform.deepseek.com/api_keys
- **Qwen (阿里云)**: https://dashscope.aliyun.com/api-key-management
- **Zhipu (智谱)**: https://open.bigmodel.cn/usercenter/apikeys
- **OpenAI**: https://platform.openai.com/api-keys
- **Anthropic**: https://console.anthropic.com/settings/keys

---

## 故障排除

### 检查配置
```bash
python3 -m pilotcode configure --show
```

### 测试 API 连接
```bash
curl $PILOTCODE_BASE_URL/models \
  -H "Authorization: Bearer $PILOTCODE_API_KEY"
```

### 重置配置
```bash
rm ~/.config/pilotcode/settings.json
python3 -m pilotcode configure  # 重新配置
```

---

## 下一步

- 阅读完整文档：[README.md](README.md)
- 了解架构设计：[docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md)
- 查看功能列表：[docs/features/FEATURE_LIST.md](docs/features/FEATURE_LIST.md)

---

**提示**: 首次使用建议从 DeepSeek 或 Qwen 开始，它们对中文支持更好且价格优惠。
