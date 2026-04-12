# Security - 安全与信任管理

安全模块提供插件的签名验证、信任管理和发布者验证功能，确保插件来源可信、内容完整。

---

## 模块结构

```
src/pilotcode/plugins/security/
├── __init__.py              # 模块导出
├── trust.py                 # 信任存储
├── signature.py             # 签名管理
└── verification.py          # 验证逻辑
```

---

## 信任存储 (TrustStore)

管理插件发布者的信任级别。

### 信任级别

```python
from pilotcode.plugins.security.trust import TrustLevel

TrustLevel.BLOCKED     # 明确阻止
TrustLevel.UNTRUSTED   # 未知/未验证
TrustLevel.VERIFIED    # 已验证身份
TrustLevel.TRUSTED     # 明确信任
TrustLevel.OFFICIAL    # 官方/精选
```

### 获取信任存储

```python
from pilotcode.plugins.security.trust import get_trust_store

trust_store = get_trust_store()
```

### 管理发布者

```python
# 获取发布者信息
publisher = trust_store.get_publisher("anthropics")

# 获取或创建
publisher = trust_store.get_or_create("new-publisher", name="New Publisher")

# 列出发布者
all_publishers = trust_store.list_publishers()
trusted_only = trust_store.list_publishers(TrustLevel.TRUSTED)

# 检查信任级别
level = trust_store.get_trust_level("anthropics")  # TrustLevel.OFFICIAL
is_blocked = trust_store.is_blocked("malicious-publisher")  # True
```

### 设置信任级别

```python
# 阻止发布者
trust_store.block("untrusted-publisher")

# 信任发布者
trust_store.trust("good-publisher", verified_by="admin")

# 验证发布者
trust_store.verify("publisher", verified_by="admin")

# 设置具体级别
from pilotcode.plugins.security.trust import TrustLevel
trust_store.set_trust_level("publisher", TrustLevel.TRUSTED, verified_by="admin")
```

### 权限检查

```python
# 检查是否可以安装
can_install = trust_store.can_install("publisher")

# 检查是否可以自动更新
can_auto = trust_store.can_auto_update("publisher")
```

### PublisherTrust

发布者信任信息：

```python
from pilotcode.plugins.security.trust import PublisherTrust

publisher = PublisherTrust(
    publisher_id="anthropics",
    name="Anthropic",
    trust_level=TrustLevel.OFFICIAL,
    public_key="-----BEGIN PUBLIC KEY-----...",
    fingerprint="SHA256:abc123...",
    first_seen="2024-01-15T10:00:00",
    last_seen="2024-01-20T15:30:00",
    verified_by="system",
    notes="Official marketplace"
)

# 检查权限
if publisher.can_install():
    print("Can install from this publisher")

if publisher.can_auto_update():
    print("Auto-updates allowed")
```

### 公钥管理

```python
# 添加公钥
trust_store.add_public_key(
    publisher_id="my-publisher",
    public_key="-----BEGIN PUBLIC KEY-----...",
    fingerprint="SHA256:xyz789"
)

# 获取公钥
public_key = trust_store.get_public_key("my-publisher")
```

### 信任存储文件

```
~/.config/pilotcode/trust_store.json
```

内容示例：

```json
{
  "publishers": [
    {
      "publisher_id": "anthropics",
      "name": "Anthropic",
      "trust_level": "official",
      "public_key": null,
      "fingerprint": null,
      "first_seen": "2024-01-15T10:00:00",
      "last_seen": "2024-01-20T15:30:00",
      "verified_by": "system",
      "notes": null
    }
  ],
  "updated": "2024-01-20T15:30:00"
}
```

---

## 签名管理 (SignatureManager)

管理插件的签名创建和验证。

### 获取管理器

```python
from pilotcode.plugins.security.signature import SignatureManager

sig_manager = SignatureManager()
# 或指定密钥目录
sig_manager = SignatureManager(keys_dir=Path("/custom/keys"))
```

### 创建签名

```python
from pathlib import Path
from pilotcode.plugins.security.signature import SignatureManager

sig_manager = SignatureManager()

# 计算内容哈希
content_hash = sig_manager.compute_hash(
    Path("/path/to/plugin"),
    algorithm="sha256"
)

# 创建签名
signature = sig_manager.create_signature(
    plugin_path=Path("/path/to/plugin"),
    plugin_name="my-plugin",
    plugin_version="1.0.0",
    signer="my-key",
    private_key="secret-key-here",
    expires_days=365,  # 可选：过期时间
    algorithm="sha256"
)
```

### 验证签名

```python
# 加载签名文件
signature = sig_manager.load_signature(Path("plugin.sig"))

# 检查是否过期
if signature.is_expired():
    print("Signature has expired!")

# 验证签名
is_valid = sig_manager.verify_signature(
    plugin_path=Path("/path/to/plugin"),
    signature=signature,
    public_key="public-key-here"
)

if is_valid:
    print("Signature verified!")
else:
    print("Invalid signature!")
```

### 保存/加载签名

```python
# 保存签名
sig_manager.save_signature(
    signature,
    Path("my-plugin.sig")
)

# 加载签名
signature = sig_manager.load_signature(Path("my-plugin.sig"))
```

### 密钥管理

```python
# 生成密钥对
private_key, public_key = sig_manager.generate_key_pair("my-key")

# 保存到: ~/.config/pilotcode/keys/my-key.json

# 加载密钥
private_key, public_key = sig_manager.load_key("my-key")
```

### PluginSignature

签名数据结构：

```python
from pilotcode.plugins.security.signature import PluginSignature
from datetime import datetime, timedelta

signature = PluginSignature(
    plugin_name="my-plugin",
    plugin_version="1.0.0",
    hash_algorithm="sha256",
    content_hash="abc123...",
    signer="my-key",
    timestamp=datetime.now().isoformat(),
    expires=(datetime.now() + timedelta(days=365)).isoformat(),
    signature="base64encoded..."
)

# 检查过期
if signature.is_expired():
    print("Signature expired")

# 获取签名数据（不含 signature 字段）
signing_data = signature.get_signing_data()
```

---

## 哈希计算

### 计算插件哈希

```python
# 计算目录内容的确定性哈希
hash_value = sig_manager.compute_hash(
    Path("/path/to/plugin"),
    algorithm="sha256"  # 或 "sha512"
)
# Returns: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
```

哈希算法：
- 遍历所有文件（按路径排序保证确定性）
- 包含相对路径和内容
- 使用分隔符避免冲突

---

## 签名文件格式

```json
{
  "plugin_name": "my-plugin",
  "plugin_version": "1.0.0",
  "hash_algorithm": "sha256",
  "content_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "signer": "my-key",
  "timestamp": "2024-01-15T10:30:00",
  "expires": "2025-01-15T10:30:00",
  "signature": "base64encodedsignature"
}
```

---

## 完整示例

### 插件作者签名流程

```python
import asyncio
from pathlib import Path
from pilotcode.plugins.security.signature import SignatureManager

async def sign_plugin():
    sig_manager = SignatureManager()
    
    plugin_path = Path("my-plugin")
    
    # 生成密钥对（首次）
    private_key, public_key = sig_manager.generate_key_pair("my-plugin-key")
    print(f"Public key: {public_key}")
    
    # 创建签名
    signature = sig_manager.create_signature(
        plugin_path=plugin_path,
        plugin_name="my-plugin",
        plugin_version="1.0.0",
        signer="my-plugin-key",
        private_key=private_key,
        expires_days=365
    )
    
    # 保存签名
    sig_manager.save_signature(signature, plugin_path / "plugin.sig")
    print(f"Signature saved to {plugin_path / 'plugin.sig'}")
    
    # 同时发布公钥供用户验证
    with open(plugin_path / "public_key.pem", "w") as f:
        f.write(public_key)

if __name__ == "__main__":
    asyncio.run(sign_plugin())
```

### 用户验证流程

```python
import asyncio
from pathlib import Path
from pilotcode.plugins.security.signature import SignatureManager
from pilotcode.plugins.security.trust import get_trust_store, TrustLevel

async def verify_and_install():
    sig_manager = SignatureManager()
    trust_store = get_trust_store()
    
    plugin_path = Path("downloaded-plugin")
    
    # 1. 检查发布者信任
    publisher = trust_store.get_or_create("plugin-author")
    if publisher.trust_level == TrustLevel.BLOCKED:
        print("Publisher is blocked!")
        return False
    
    # 2. 加载签名
    signature = sig_manager.load_signature(plugin_path / "plugin.sig")
    if not signature:
        print("No signature found!")
        return False
    
    # 3. 检查过期
    if signature.is_expired():
        print("Signature has expired!")
        return False
    
    # 4. 获取公钥（从信任存储或文件）
    public_key = trust_store.get_public_key("plugin-author")
    if not public_key:
        # 从文件加载
        with open(plugin_path / "public_key.pem") as f:
            public_key = f.read()
    
    # 5. 验证签名
    is_valid = sig_manager.verify_signature(
        plugin_path,
        signature,
        public_key
    )
    
    if is_valid:
        print("✓ Signature verified!")
        # 更新信任级别
        trust_store.trust("plugin-author", verified_by="user")
        return True
    else:
        print("✗ Invalid signature!")
        trust_store.block("plugin-author")
        return False

if __name__ == "__main__":
    asyncio.run(verify_and_install())
```

### 集成到安装流程

```python
from pilotcode.plugins import get_plugin_manager
from pilotcode.plugins.security.signature import SignatureManager
from pilotcode.plugins.security.trust import get_trust_store

async def secure_install(plugin_spec: str):
    manager = await get_plugin_manager()
    sig_manager = SignatureManager()
    trust_store = get_trust_store()
    
    # 安装插件
    plugin = await manager.install_plugin(plugin_spec)
    
    # 检查签名
    sig_path = plugin.path / "plugin.sig"
    if not sig_path.exists():
        print("Warning: Plugin is not signed")
        return plugin
    
    # 验证签名
    signature = sig_manager.load_signature(sig_path)
    public_key = trust_store.get_public_key(plugin.source)
    
    if not public_key:
        print(f"Warning: No public key for {plugin.source}")
        return plugin
    
    is_valid = sig_manager.verify_signature(
        plugin.path,
        signature,
        public_key
    )
    
    if is_valid:
        print(f"✓ {plugin.name} signature verified")
    else:
        print(f"✗ {plugin.name} signature invalid!")
        await manager.uninstall_plugin(plugin.name)
        raise Exception("Signature verification failed")
    
    return plugin
```

---

## 安全最佳实践

1. **始终验证签名**：生产环境要求所有插件签名
2. **使用信任存储**：维护可信发布者列表
3. **检查过期**：定期更新签名
4. **保护私钥**：私钥不应提交到版本控制
5. **使用强算法**：优先使用 sha512
6. **定期轮换密钥**：每年更新密钥对

---

## 相关文档

- [插件核心管理](./core.md)
- [企业策略](./policy.md)
