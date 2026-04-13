# PilotCode Web UI

## 概述

PilotCode 现在支持通过 `/web` 命令启动 Web UI，用户可以通过浏览器进行交互。

## 使用方法

### 启动 Web UI

在 PilotCode 中输入：

```
/web
```

这将启动 Web 服务器并自动打开浏览器。

### 命令选项

```
/web --port 8081       # 使用不同端口（默认 8080）
/web --host 0.0.0.0    # 监听所有网络接口
/web --no-browser      # 不自动打开浏览器
```

### 界面功能

- **侧边栏会话管理**：创建、切换和管理多个会话
- **实时对话**：与 AI 助手进行实时交互
- **代码高亮**：自动检测并高亮代码块
- **工具调用显示**：展开/收起查看工具调用详情
- **响应式布局**：支持调整侧边栏宽度

## 技术架构

### 文件结构

```
src/pilotcode/web/
├── __init__.py           # Web 模块初始化
├── server.py             # HTTP + WebSocket 服务器
└── static/
    ├── index.html        # 主页面
    └── assets/
        ├── styles.css    # 样式（像素级匹配参考设计）
        ├── app.js        # 前端应用逻辑
        └── logo.png      # 应用图标
```

### 服务器端口

- HTTP 服务器：默认 8080
- WebSocket 服务器：默认 8081 (HTTP端口+1)

## 设计要求

Web UI 的设计参考 `D:\Source\2026\sample\Kimi Code Web UI.htm`，实现了像素级一致的：

- 配色方案（浅色/深色主题）
- 布局结构（侧边栏 + 主内容区）
- 组件样式（按钮、输入框、消息气泡）
- 交互细节（加载动画、悬停效果）

## 依赖

- `websockets>=12.0.0`（已添加到 pyproject.toml）

## 注意事项

1. Web UI 需要独立安装依赖：`pip install websockets`
2. 首次启动可能需要几秒钟初始化
3. 服务器运行在本地，不会暴露到公网（除非使用 `--host 0.0.0.0`）
