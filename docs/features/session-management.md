# 会话管理

PilotCode 的会话管理系统提供对话历史的保存、恢复和组织功能，支持长期项目协作。

---

## 概述

会话管理使 AI 对话能够：
- **持久化保存** - 对话历史不丢失
- **随时恢复** - 跨会话继续工作
- **多项目管理** - 按项目组织会话
- **导出分享** - 分享对话记录

---

## 功能特性

### 会话元数据

每个会话包含丰富的元数据：

```python
class Session:
    id: str                         # 唯一标识 (UUID)
    name: str                       # 会话名称
    created_at: datetime            # 创建时间
    updated_at: datetime            # 最后更新时间
    project_path: Optional[str]     # 关联项目路径
    tags: List[str]                 # 标签
    summary: Optional[str]          # 自动生成的摘要
    message_count: int              # 消息数量
    token_count: int                # Token 数量
    is_archived: bool               # 是否归档
```

### 会话操作

| 操作 | 命令 | 说明 |
|------|------|------|
| **列出会话** | `/session list` | 显示所有会话 |
| **切换会话** | `/session switch <id>` | 切换到历史会话 |
| **重命名** | `/session rename <name>` | 修改会话名称 |
| **删除** | `/session delete <id>` | 删除会话 |
| **导出** | `/session export` | 导出会话 |
| **归档** | `/session archive` | 归档旧会话 |
| **搜索** | `/session search <query>` | 搜索会话 |

### 导出格式

支持多种导出格式：

```json
// JSON 格式（完整数据）
{
  "session": {
    "id": "uuid",
    "name": "Feature Implementation",
    "messages": [...],
    "metadata": {...}
  }
}
```

```markdown
<!-- Markdown 格式（可读） -->
# Session: Feature Implementation

## User
请帮我实现用户认证功能

## Assistant
我来帮你实现用户认证系统...
```

---

## 相关代码

### 核心模块

```
src/pilotcode/
├── services/
│   ├── session_manager.py        # SessionManager - 会话管理
│   ├── session_storage.py        # 会话存储后端
│   └── session_serializer.py     # 序列化/反序列化
├── commands/
│   └── session_commands.py       # /session 命令
└── tui_v2/
    └── components/
        └── session_browser.py    # 会话浏览器组件
```

### 关键类

```python
# 会话管理器
class SessionManager:
    def __init__(self, storage: SessionStorage):
        self.storage = storage
        self.current_session: Optional[Session] = None
    
    async def create_session(
        self,
        name: str,
        project_path: Optional[str] = None
    ) -> Session:
        """创建新会话"""
        session = Session(
            id=generate_uuid(),
            name=name,
            project_path=project_path,
            created_at=datetime.now()
        )
        await self.storage.save(session)
        return session
    
    async def load_session(self, session_id: str) -> Session:
        """加载会话"""
        session = await self.storage.load(session_id)
        self.current_session = session
        return session
    
    async def list_sessions(
        self,
        project_path: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> List[SessionInfo]:
        """列出会话，支持过滤"""
        sessions = await self.storage.list()
        
        if project_path:
            sessions = [s for s in sessions if s.project_path == project_path]
        
        if tags:
            sessions = [s for s in sessions if any(t in s.tags for t in tags)]
        
        return sessions
    
    async def export_session(
        self,
        session_id: str,
        format: str = "json",
        path: Optional[str] = None
    ) -> str:
        """导出会话"""
        session = await self.storage.load(session_id)
        
        if format == "json":
            content = json.dumps(session.to_dict(), indent=2)
        elif format == "markdown":
            content = self._to_markdown(session)
        
        if path:
            with open(path, 'w') as f:
                f.write(content)
        
        return content

# 会话存储接口
class SessionStorage(ABC):
    @abstractmethod
    async def save(self, session: Session) -> None: ...
    
    @abstractmethod
    async def load(self, session_id: str) -> Session: ...
    
    @abstractmethod
    async def delete(self, session_id: str) -> None: ...
    
    @abstractmethod
    async def list(self) -> List[SessionInfo]: ...

# 文件存储实现
class FileSessionStorage(SessionStorage):
    """基于文件的会话存储"""
    
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    async def save(self, session: Session) -> None:
        session_file = self.base_path / f"{session.id}.json"
        # 压缩存储以节省空间
        data = compress_session(session.to_dict())
        with open(session_file, 'w') as f:
            json.dump(data, f)
```

---

## 使用示例

### 会话管理命令

```bash
# 查看当前会话
/session

# 列出所有会话
/session list

# 创建新会话
/session new "User Auth Implementation"

# 切换到历史会话
/session switch abc-123-def

# 重命名会话
/session rename "Fixed Auth Bug"

# 导出会话
/session export --format markdown --path ./session.md

# 搜索会话
/session search "authentication"

# 归档旧会话
/session archive --older-than 30d
```

### 项目管理

```bash
# 查看当前项目的所有会话
/session list --project .

# 为会话添加标签
/session tag abc-123-def "important,milestone"

# 按标签过滤
/session list --tags "important"
```

---

## 与其他工具对比

| 特性 | PilotCode | Claude Code | ChatGPT | VS Code Copilot |
|------|-----------|-------------|---------|-----------------|
| **本地存储** | ✅ | ✅ | ❌ 云端 | ❌ |
| **项目关联** | ✅ | ✅ | ❌ | ✅ |
| **导出格式** | JSON/Markdown | 有限 | 有限 | ❌ |
| **会话标签** | ✅ | ❌ | ❌ | ❌ |
| **搜索历史** | ✅ | ❌ | ✅ | ❌ |
| **自动归档** | ✅ | ❌ | ❌ | ❌ |
| **会话恢复** | ✅ | ✅ | ✅ | ❌ |
| **压缩存储** | ✅ | ❌ | N/A | N/A |

### 优势

1. **项目关联** - 会话与项目绑定，便于项目级管理
2. **标签系统** - 支持多维度分类
3. **压缩存储** - 智能压缩节省磁盘空间
4. **导出灵活** - 支持多种格式导出

### 劣势

1. **无云端同步** - 会话仅限本地，换设备需手动迁移
2. **无 Web 界面** - 只能通过 CLI 管理

---

## 存储格式

### 会话文件结构

```
~/.local/share/pilotcode/sessions/
├── sessions.json           # 会话索引
├── abc-123.json.gz        # 压缩的会话数据
├── def-456.json.gz
└── archive/
    └── old-session.json.gz
```

### 压缩策略

```python
def compress_session(session: dict) -> dict:
    """
    压缩会话数据
    1. 移除重复的空格
    2. 压缩 Tool 输出
    3. 使用 gzip 压缩
    """
    # 压缩消息
    for message in session['messages']:
        if message.get('tool_result'):
            message['tool_result'] = compress_tool_result(
                message['tool_result']
            )
    
    # Gzip 压缩
    json_str = json.dumps(session)
    compressed = gzip.compress(json_str.encode())
    
    return {
        'compressed': True,
        'data': base64.b64encode(compressed).decode()
    }
```

---

## 最佳实践

### 1. 有意义的命名

```bash
# 好的命名
/session new "Fix login bug - OAuth integration"
/session new "Refactor database layer"

# 不好的命名
/session new "Session 1"
/session new "Chat"
```

### 2. 定期归档

```bash
# 归档 30 天前的会话
/session archive --older-than 30d

# 设置自动归档
# 在配置中
{
  "auto_archive_days": 30
}
```

### 3. 项目关联

```bash
# 在项目目录启动，自动关联
cd /my/project
./pilotcode

# 会话自动关联到 /my/project
```

### 4. 重要会话导出

```bash
# 里程碑会话导出备份
/session export <session-id> --path ./milestones/v1.0-implementation.md
```

### 5. 使用标签分类

```bash
/session tag <id> "bugfix,critical"
/session tag <id> "refactor,cleanup"
/session tag <id> "feature,milestone"

# 之后可以按标签过滤
/session list --tags "critical"
```

---

## 会话恢复

### 自动恢复

```python
# 启动时自动恢复上次会话
if config.get("auto_resume_last_session"):
    last_session = await session_manager.get_last_session()
    if last_session:
        await session_manager.load_session(last_session.id)
```

### 手动恢复

```bash
# 查看可恢复的会话
/session list --recent

# 选择恢复
/session switch <id>
```

---

## 相关文档

- [会话命令](../commands/session.md)
- [智能上下文压缩](./context-compaction.md)
