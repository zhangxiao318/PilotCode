#!/bin/bash
# 快速配置Qwen API

mkdir -p ~/.config/pilotcode

cat > ~/.config/pilotcode/settings.json << 'CONFIG'
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
CONFIG

echo "✓ Qwen API配置完成！"
echo "配置路径: ~/.config/pilotcode/settings.json"
echo ""
echo "API地址: http://172.19.201.40:3509/v1"
echo "模型: qwen"
echo ""
echo "启动命令: ./run.sh"
