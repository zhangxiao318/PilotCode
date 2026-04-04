# Qwen API 设置指南

## 默认配置

代码中已预配置为 `http://172.19.201.40:3509/v1`，通常无需修改即可直接使用。

---

## 方法 1: 使用命令行配置（推荐）

```bash
cd /home/zx/mycc/pilotcode_py

# 查看当前配置
./run.sh config --list

# 设置API密钥（如果需要）
./run.sh config --set api_key --value "your-api-key"

# 设置模型名称（Qwen）
./run.sh config --set default_model --value "qwen"

# 验证配置
./run.sh config --list
```

---

## 方法 2: 手动创建全局配置文件

创建文件 `~/.config/pilotcode/settings.json`：

```bash
mkdir -p ~/.config/pilotcode
cat > ~/.config/pilotcode/settings.json << 'EOF'
{
  "theme": "default",
  "verbose": false,
  "auto_compact": true,
  "api_key": "your-api-key-if-needed",
  "base_url": "http://172.19.201.40:3509/v1",
  "default_model": "qwen",
  "allowed_tools": [],
  "mcp_servers": {}
}
EOF
```

---

## 方法 3: 项目级配置

在项目目录创建 `.pilotcode.json`：

```bash
cd /your/project/path
cat > .pilotcode.json << 'EOF'
{
  "allowed_tools": [],
  "mcp_servers": {},
  "custom_instructions": "Use Qwen model for this project"
}
EOF
```

全局配置会合并项目级配置。

---

## 方法 4: 使用环境变量

```bash
# 临时设置（当前终端）
export OPENAI_BASE_URL="http://172.19.201.40:3509/v1"
export LOCAL_API_KEY="your-api-key"
./run.sh

# 或添加到 ~/.bashrc 永久生效
echo 'export OPENAI_BASE_URL="http://172.19.201.40:3509/v1"' >> ~/.bashrc
source ~/.bashrc
```

---

## 测试API连接

启动后输入测试命令：

```bash
./run.sh
```

然后输入：
```
你好，请介绍一下自己
```

如果能正常回复，说明API配置正确。

---

## 常见问题

### 1. 连接超时

检查服务器是否可访问：
```bash
curl http://172.19.201.40:3509/v1/models
```

### 2. 认证错误

如果Qwen服务需要API密钥：
```bash
./run.sh config --set api_key --value "your-key"
```

### 3. 模型名称问题

不同部署方式可能使用不同的模型名称：
- `qwen` - 默认Qwen模型
- `qwen-7b` - 指定7B版本
- `qwen-14b` - 指定14B版本
- `default` - 使用服务器默认模型

尝试不同的模型名称：
```bash
./run.sh config --set default_model --value "qwen-7b"
```

### 4. 查看完整请求日志

启用verbose模式：
```bash
./run.sh main --verbose
```

---

## 快速设置脚本

一键配置：

```bash
#!/bin/bash
# setup_qwen.sh

mkdir -p ~/.config/pilotcode

cat > ~/.config/pilotcode/settings.json << 'EOF'
{
  "theme": "default",
  "verbose": false,
  "auto_compact": true,
  "api_key": null,
  "base_url": "http://172.19.201.40:3509/v1",
  "default_model": "qwen",
  "allowed_tools": [],
  "mcp_servers": {}
}
EOF

echo "Qwen API配置完成！"
echo "配置路径: ~/.config/pilotcode/settings.json"
echo ""
echo "启动命令: ./run.sh"
```

保存并执行：
```bash
chmod +x setup_qwen.sh
./setup_qwen.sh
./run.sh
```
