# 项目清理报告

## 🔍 发现的无用/问题文件和代码

### 📄 空文件

| 文件 | 问题 | 建议 |
|------|------|------|
| `AGENTS.md` | 空文件（0行） | 删除或添加内容 |

### 🔧 重复文件

| 文件 | 重复对象 | 建议 |
|------|----------|------|
| `pilotcode` | `pilotcode.sh` | 删除其中一个，建议保留 `pilotcode.sh` |
| `demo.py` | `full_demo.py` | 合并为一个文件，或删除 `demo.py` |

### ⚠️ 环境特定配置

| 文件 | 问题 | 建议 |
|------|------|------|
| `config/settings.json` | 包含本地IP地址 (172.19.201.40) | 添加到 `.gitignore`，提供模板文件 |
| `setup_qwen.sh` | 包含特定IP地址的配置脚本 | 移动到 `scripts/` 或添加模板变量 |

### 🧪 孤立的测试文件

| 文件 | 问题 | 建议 |
|------|------|------|
| `test_all_tools.py` | 根目录下的独立测试，功能已被覆盖 | 删除或移动到 `tests/manual/` |
| `tests/tools/test_file_tools.py` | 不在标准测试目录结构 | 移动到 `tests/unit/tools/` 或合并 |
| `run_tests.py` | 功能已被 Makefile 替代 | 删除（使用 `make test` 替代） |

### 📝 代码质量问题

#### TODO/FIXME 注释（5处）
```
src/pilotcode/hooks/builtin_hooks.py:            # TODO: Add simple CLI permission prompt
src/pilotcode/permissions/permission_manager.py:        # TODO: Implement loading from config
src/pilotcode/tools/synthetic_output_tool.py:# TODO: Implement this functionality
src/pilotcode/tools/registry.py:        # TODO: Implement permission-based filtering
src/pilotcode/tools/registry.py:    # TODO: Implement filtering
```

### 📦 依赖问题

| 问题 | 说明 | 建议 |
|------|------|------|
| `requirements.txt` vs `pyproject.toml` | 依赖分散在两个文件 | 统一使用 `pyproject.toml`，删除 `requirements.txt` 或使其指向 pyproject.toml |

### 🗂️ 目录结构问题

| 问题 | 说明 | 建议 |
|------|------|------|
| `tests/tools/` | 孤立的测试目录 | 合并到 `tests/unit/tools/` |

---

## 🧹 清理建议清单

### 立即删除（确认无用）
```bash
# 空文件
rm AGENTS.md

# 重复文件（保留 pilotcode.sh）
rm pilotcode

# 根目录下的孤立测试
rm test_all_tools.py
rm run_tests.py

# 合并 demo 文件后删除
rm demo.py  # 保留 full_demo.py
```

### 移动/重构
```bash
# 移动测试文件
mv tests/tools/test_file_tools.py tests/unit/tools/
rmdir tests/tools  # 如果为空则删除

# 环境配置模板化
mv config/settings.json config/settings.json.example
# 添加 config/settings.json 到 .gitignore

# 脚本目录化
mkdir -p scripts
mv setup_qwen.sh scripts/
# 修改为模板形式，使用变量替代硬编码IP
```

### 配置更新
```bash
# 更新 .gitignore
echo "config/settings.json" >> .gitignore
echo "*.local" >> .gitignore
```

### 依赖统一
```bash
# 方案1: 删除 requirements.txt（推荐，如果使用 pyproject.toml）
rm requirements.txt

# 方案2: 或修改 requirements.txt 内容为：
# -e .
```

---

## 📊 清理效果预估

| 类别 | 数量 | 清理后效果 |
|------|------|-----------|
| 删除空文件 | 1 | 根目录更整洁 |
| 删除重复文件 | 2 | 减少混淆 |
| 删除孤立测试 | 2 | 测试结构统一 |
| 移动配置文件 | 2 | 环境配置更安全 |
| 解决TODO | 5 | 代码更完整 |

**预计删除/移动文件数：10个**

---

## ✅ 清理命令汇总

```bash
# 1. 删除无用文件
rm AGENTS.md pilotcode test_all_tools.py run_tests.py demo.py

# 2. 移动测试文件
mv tests/tools/test_file_tools.py tests/unit/tools/
rmdir tests/tools 2>/dev/null || true

# 3. 创建配置模板
cp config/settings.json config/settings.json.example
echo "config/settings.json" >> .gitignore

# 4. 移动脚本
mkdir -p scripts
mv setup_qwen.sh scripts/

# 5. 统一依赖（二选一）
# 方案A: 删除 requirements.txt
rm requirements.txt
# 方案B: 修改 requirements.txt 为指向 pyproject.toml
echo "-e ." > requirements.txt
```

---

## 📝 后续建议

1. **处理TODO注释**：优先处理 `synthetic_output_tool.py` 和 `registry.py` 中的TODO
2. **完善AGENTS.md**：如果保留，添加项目代理配置说明
3. **统一测试结构**：确保所有测试都在 `tests/unit/` 或 `tests/integration/` 下
4. **文档更新**：在 README.md 中添加开发环境配置说明
