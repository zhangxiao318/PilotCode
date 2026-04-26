# API Key 明文存储 — 修改方案总结

> **问题**: `api_key` 以明文 JSON 存储在 `~/.config/pilotcode/settings.json`

---

## 已完成的操作

### 1. 新增文件：`src/pilotcode/utils/secure_storage.py` (326行)

分层安全存储，优先级：**环境变量 > OS密钥环 > AES加密文件**

核心能力：
- `get_api_key()` → 自动从最高优先级后端读取
- `store_api_key()` → 优先 keyring，降级加密文件
- `delete_api_key()` → 从所有后端移除
- `migrate_from_plaintext()` → 一次性迁移旧明文key
- 密钥由机器指纹（MAC地址+hostname+machine+home目录）PBKDF2派生

### 2. 修改文件：`src/pilotcode/utils/config.py`

- **`GlobalConfig.__post_init__`**: 新增自动从 SecureStorage 恢复 api_key
- **imports**: 新增 `secure_storage` 模块引用

### 3. 修改文件：`src/pilotcode/utils/configure.py`

- **`_confirm_and_save`**: 保存前自动将 api_key 存入 SecureStorage，从 settings.json 中清除
- 显示用户友好的 "🔐 API key stored securely" 提示

### 4. 修改文件：`pyproject.toml`

- 新增 `[project.optional-dependencies] secure = ["keyring", "cryptography"]`
- 两个依赖均为可选，未安装时自动降级

---

## 数据流变化

```
【改前】
用户输入 → GlobalConfig.api_key → json.dump(settings.json) → 明文存储 ❌

【改后】
用户输入 → GlobalConfig.api_key → store_api_key()
    ├─ keyring可用 → macOS Keychain / Linux Secret Service ✅
    └─ keyring不可用 → AES-GCM加密文件 (0600权限) ✅
GlobalConfig → json.dump(settings.json) → api_key已清除 ✅

启动时:
get_api_key() → env变量/keyring/加密文件 → 恢复到 GlobalConfig.api_key ✅
```

## 安装依赖（可选）

```bash
pip install pilotcode[secure]   # 推荐：完整安全
# 或：
pip install keyring cryptography  # 手动安装
```

## 安装步骤总结

```bash
# 1. 安装可选依赖
pip install keyring cryptography

# 2. 首次运行自动迁移
pilotcode  # 自动检测 settings.json 中的旧明文key → 迁移到安全存储

# 3. 验证
cat ~/.config/pilotcode/settings.json  # api_key 字段已移除
```
