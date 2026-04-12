# Sources - 插件源管理

源模块提供从不同来源下载和安装插件的能力，支持 GitHub、Git、URL、本地目录等多种源类型。

---

## 模块结构

```
src/pilotcode/plugins/sources/
├── __init__.py              # 模块导出
├── base.py                  # PluginSource 基类
└── github.py                # GitHub 源实现
```

---

## 基础接口

### PluginSource

所有插件源的基类。

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

@dataclass
class DownloadResult:
    path: Path
    version: Optional[str] = None  # Git SHA 或版本标签
    success: bool = True
    error: Optional[str] = None

class PluginSource(ABC):
    @abstractmethod
    async def download(
        self, 
        source_config: dict, 
        target_path: Path, 
        force: bool = False
    ) -> DownloadResult:
        """下载插件到目标路径"""
        pass
    
    @abstractmethod
    def can_handle(self, source_type: str) -> bool:
        """检查是否可以处理此源类型"""
        pass
```

---

## 源类型

### GitHub 源

从 GitHub 仓库下载插件。

```python
from pilotcode.plugins.sources.github import GitHubSource

source = GitHubSource()

# 下载
result = await source.download(
    source_config={
        "source": "github",
        "repo": "anthropics/claude-code-plugins",
        "ref": "main",  # 分支或标签
        "path": "plugins/docker"  # 仓库内路径
    },
    target_path=Path("/tmp/docker-plugin"),
    force=False
)

if result.success:
    print(f"Downloaded to: {result.path}")
    print(f"Version: {result.version}")  # Git commit SHA
else:
    print(f"Error: {result.error}")
```

### Git 源

从任意 Git 仓库下载。

```python
result = await source.download(
    source_config={
        "source": "git",
        "url": "https://git.example.com/plugins.git",
        "ref": "v1.0.0"
    },
    target_path=Path("/tmp/plugin")
)
```

### URL 源

从直接 URL 下载。

```python
result = await source.download(
    source_config={
        "source": "url",
        "url": "https://example.com/plugin.zip"
    },
    target_path=Path("/tmp/plugin")
)
```

### 本地目录源

从本地目录复制。

```python
# 在 PluginManager 中处理
source_config = {
    "source": "directory",
    "path": "/path/to/local/plugin"
}

# 复制到目标
import shutil
shutil.copytree(
    Path("/path/to/local/plugin"),
    Path("/tmp/installed-plugin")
)
```

### 文件源

从本地文件加载。

```python
source_config = {
    "source": "file",
    "path": "/path/to/plugin.tar.gz"
}
```

---

## 市场源配置

### MarketplaceSource

```python
from pilotcode.plugins.core.types import MarketplaceSource

# GitHub 市场
source = MarketplaceSource(
    source="github",
    repo="anthropics/claude-code-plugins",
    ref="main",
    path="marketplace.json"
)

# Git 市场
source = MarketplaceSource(
    source="git",
    url="https://git.example.com/marketplace.git",
    ref="main"
)

# URL 市场
source = MarketplaceSource(
    source="url",
    url="https://example.com/marketplace.json"
)

# 本地文件
source = MarketplaceSource(
    source="file",
    path="/path/to/marketplace.json"
)

# 本地目录
source = MarketplaceSource(
    source="directory",
    path="/path/to/marketplace"
)
```

---

## 安装规格格式

### 完整规格

```
name@marketplace
```

示例：
- `docker@claude-plugins-official`
- `github@github-user/repo`

### 简写规格

只提供名称，自动搜索市场：

```
docker
```

### GitHub 直接安装

```
owner/repo/path
```

示例：
- `anthropics/claude-code-plugins/docker`
- `myuser/my-plugins/plugin-name`

---

## 实现自定义源

```python
from pathlib import Path
from pilotcode.plugins.sources.base import PluginSource, DownloadResult, SourceError

class S3Source(PluginSource):
    """AWS S3 插件源"""
    
    def can_handle(self, source_type: str) -> bool:
        return source_type == "s3"
    
    async def download(
        self,
        source_config: dict,
        target_path: Path,
        force: bool = False
    ) -> DownloadResult:
        bucket = source_config.get("bucket")
        key = source_config.get("key")
        
        if not bucket or not key:
            return DownloadResult(
                path=target_path,
                success=False,
                error="Missing bucket or key"
            )
        
        try:
            # 使用 boto3 下载
            import boto3
            s3 = boto3.client("s3")
            s3.download_file(bucket, key, str(target_path))
            
            return DownloadResult(
                path=target_path,
                version="latest",
                success=True
            )
        except Exception as e:
            return DownloadResult(
                path=target_path,
                success=False,
                error=str(e)
            )

# 注册源
from pilotcode.plugins.core.manager import PluginManager

manager = PluginManager()
manager.register_source(S3Source())
```

---

## 缓存管理

### 缓存路径

```
~/.config/pilotcode/plugins/
├── cache/
│   ├── github/
│   │   └── owner-repo-ref/
│   └── git/
│       └── hash/
└── installed.json
```

### 清理缓存

```python
from pilotcode.plugins.core.config import PluginConfig

config = PluginConfig()
cache_path = config.get_cache_path()

# 清理过期缓存
import shutil
from datetime import datetime, timedelta

for item in cache_path.iterdir():
    if item.is_dir():
        mtime = datetime.fromtimestamp(item.stat().st_mtime)
        if datetime.now() - mtime > timedelta(days=7):
            shutil.rmtree(item)
```

---

## 错误处理

```python
from pilotcode.plugins.sources.base import SourceError

try:
    result = await source.download(config, target_path)
    if not result.success:
        print(f"Download failed: {result.error}")
except SourceError as e:
    print(f"Source error: {e}")
```

常见错误：

| 错误 | 说明 |
|------|------|
| `Repository not found` | 仓库不存在 |
| `Ref not found` | 分支/标签不存在 |
| `Path not found` | 仓库内路径不存在 |
| `Network error` | 网络错误 |
| `Permission denied` | 权限不足 |

---

## 完整示例

### 从 GitHub 安装

```python
import asyncio
from pathlib import Path
from pilotcode.plugins.sources.github import GitHubSource

async def install_from_github():
    source = GitHubSource()
    
    # 下载插件
    result = await source.download(
        source_config={
            "source": "github",
            "repo": "anthropics/claude-code-plugins",
            "ref": "main",
            "path": "plugins/docker"
        },
        target_path=Path("/tmp/docker-plugin")
    )
    
    if result.success:
        print(f"✓ Downloaded: {result.path}")
        print(f"  Version: {result.version}")
        
        # 验证 manifest
        manifest_path = result.path / "plugin.json"
        if manifest_path.exists():
            import json
            with open(manifest_path) as f:
                manifest = json.load(f)
            print(f"  Plugin: {manifest['name']} v{manifest['version']}")
    else:
        print(f"✗ Error: {result.error}")

if __name__ == "__main__":
    asyncio.run(install_from_github())
```

### 自定义源注册

```python
from pilotcode.plugins.sources.base import PluginSource, DownloadResult

class NpmSource(PluginSource):
    """从 npm 安装插件"""
    
    def can_handle(self, source_type: str) -> bool:
        return source_type == "npm"
    
    async def download(self, source_config, target_path, force=False):
        package = source_config.get("package")
        version = source_config.get("version", "latest")
        
        # 使用 npm pack 下载
        import subprocess
        result = subprocess.run(
            ["npm", "pack", f"{package}@{version}", "--pack-destination", str(target_path)],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            return DownloadResult(
                path=target_path,
                version=version,
                success=True
            )
        else:
            return DownloadResult(
                path=target_path,
                success=False,
                error=result.stderr
            )

# 使用
async def install_from_npm():
    source = NpmSource()
    result = await source.download(
        {"source": "npm", "package": "@myorg/pilotcode-plugin", "version": "1.0.0"},
        Path("/tmp/npm-plugin")
    )
    return result
```

---

## 相关文档

- [插件核心管理](./core.md)
