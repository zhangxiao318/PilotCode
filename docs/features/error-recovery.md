# 错误恢复与重试

PilotCode 的错误恢复与重试系统提供容错能力，确保在临时故障时能够自动恢复，提高系统稳定性。

---

## 概述

在 AI 辅助开发过程中，可能遇到各种错误：
- **网络问题** - API 连接超时、断开
- **服务限流** - 请求频率过高被限制
- **临时故障** - 服务端偶发错误
- **认证问题** - API 密钥过期或无效

错误恢复系统自动处理这些情况，减少用户干预。

---

## 功能特性

### 错误分类

```python
class ErrorCategory(Enum):
    TRANSIENT = "transient"       # 瞬时错误 - 可重试
    RATE_LIMIT = "rate_limit"     # 限流错误 - 等待后重试
    TIMEOUT = "timeout"           # 超时错误 - 增加超时时间
    AUTH = "authentication"       # 认证错误 - 不重试
    PERMANENT = "permanent"       # 永久错误 - 不重试
    NETWORK = "network"           # 网络错误 - 可重试
```

### 重试策略

| 策略 | 适用场景 | 实现方式 |
|------|----------|----------|
| **指数退避** | 大多数错误 | 2^n 秒间隔 |
| **固定间隔** | 限流错误 | 固定等待时间 |
| **立即重试** | 瞬时错误 | 无延迟 |
| **不重试** | 认证/永久错误 | 直接失败 |

### 指数退避算法

```python
def calculate_delay(attempt: int, base_delay: float = 1.0) -> float:
    """
    计算重试延迟
    
    delay = base_delay * (2 ^ attempt) + jitter
    
    attempt 0: 1.0s + jitter
    attempt 1: 2.0s + jitter
    attempt 2: 4.0s + jitter
    attempt 3: 8.0s + jitter
    """
    delay = base_delay * (2 ** attempt)
    jitter = random.uniform(0, 0.5)  # 随机抖动避免惊群
    return delay + jitter
```

### 熔断器模式

当错误率过高时，暂时停止请求，防止级联故障：

```
状态转换:
CLOSED → OPEN (错误率 > 阈值)
OPEN → HALF_OPEN (超时后)
HALF_OPEN → CLOSED (测试成功)
HALF_OPEN → OPEN (测试失败)
```

---

## 相关代码

### 核心模块

```
src/pilotcode/
├── services/
│   ├── error_recovery.py         # 错误恢复服务
│   ├── retry_handler.py          # 重试处理器
│   └── circuit_breaker.py        # 熔断器实现
├── utils/
│   └── model_client.py           # 模型客户端（集成重试）
└── hooks/
    └── error_hooks.py            # 错误处理 Hooks
```

### 关键类

```python
# 重试配置
@dataclass
class RetryConfig:
    max_attempts: int = 3           # 最大重试次数
    base_delay: float = 1.0         # 基础延迟（秒）
    max_delay: float = 60.0         # 最大延迟
    exponential_base: float = 2.0   # 指数基数
    retryable_exceptions: List[Type[Exception]] = None

# 错误分类器
class ErrorClassifier:
    def classify(self, error: Exception) -> ErrorCategory:
        """将错误分类到对应类别"""
        error_msg = str(error).lower()
        
        if "rate limit" in error_msg or "429" in error_msg:
            return ErrorCategory.RATE_LIMIT
        elif "timeout" in error_msg or "timed out" in error_msg:
            return ErrorCategory.TIMEOUT
        elif "authentication" in error_msg or "401" in error_msg:
            return ErrorCategory.AUTH
        elif "connection" in error_msg or "network" in error_msg:
            return ErrorCategory.NETWORK
        elif "temporary" in error_msg or "transient" in error_msg:
            return ErrorCategory.TRANSIENT
        else:
            return ErrorCategory.PERMANENT
    
    def should_retry(self, category: ErrorCategory) -> bool:
        """判断是否应该重试"""
        return category in {
            ErrorCategory.TRANSIENT,
            ErrorCategory.RATE_LIMIT,
            ErrorCategory.TIMEOUT,
            ErrorCategory.NETWORK,
        }

# 重试处理器
class RetryHandler:
    def __init__(self, config: RetryConfig = None):
        self.config = config or RetryConfig()
        self.classifier = ErrorClassifier()
    
    async def execute_with_retry(
        self,
        operation: Callable,
        *args,
        **kwargs
    ) -> Result:
        """执行带重试的操作"""
        last_error = None
        
        for attempt in range(self.config.max_attempts):
            try:
                return await operation(*args, **kwargs)
            except Exception as e:
                last_error = e
                category = self.classifier.classify(e)
                
                if not self.classifier.should_retry(category):
                    raise  # 不重试的错误直接抛出
                
                if attempt < self.config.max_attempts - 1:
                    delay = self._calculate_delay(attempt, category)
                    logger.warning(f"Retry {attempt + 1}/{self.config.max_attempts} after {delay:.1f}s: {e}")
                    await asyncio.sleep(delay)
        
        raise last_error
    
    def _calculate_delay(self, attempt: int, category: ErrorCategory) -> float:
        """根据错误类型计算延迟"""
        if category == ErrorCategory.RATE_LIMIT:
            return 60.0  # 限流固定等待 60 秒
        
        # 指数退避
        delay = self.config.base_delay * (self.config.exponential_base ** attempt)
        delay = min(delay, self.config.max_delay)
        
        # 添加抖动
        jitter = random.uniform(0, 0.5)
        return delay + jitter

# 熔断器
class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,      # 触发熔断的失败次数
        recovery_timeout: float = 60.0,  # 恢复超时
        half_open_max_calls: int = 3     # 半开状态最大测试调用
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.last_failure_time = None
        self.half_open_calls = 0
    
    async def call(self, operation: Callable, *args, **kwargs):
        """通过熔断器调用操作"""
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
            else:
                raise CircuitBreakerOpen("Circuit breaker is open")
        
        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls >= self.half_open_max_calls:
                raise CircuitBreakerOpen("Circuit breaker half-open limit reached")
            self.half_open_calls += 1
        
        try:
            result = await operation(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        """成功时更新状态"""
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.failures = 0
            self.half_open_calls = 0
    
    def _on_failure(self):
        """失败时更新状态"""
        self.failures += 1
        self.last_failure_time = time.time()
        
        if self.failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
```

---

## 使用示例

### 基本重试

```python
from pilotcode.services.error_recovery import RetryHandler, RetryConfig

# 创建重试处理器
retry_handler = RetryHandler(RetryConfig(
    max_attempts=3,
    base_delay=1.0
))

# 执行带重试的操作
result = await retry_handler.execute_with_retry(
    model_client.chat_completion,
    messages=[...]
)
```

### 使用熔断器

```python
from pilotcode.services.circuit_breaker import CircuitBreaker

# 创建熔断器
circuit_breaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60.0
)

# 通过熔断器调用
result = await circuit_breaker.call(
    external_api.fetch_data,
    param="value"
)
```

### 命令行诊断

```bash
# 检查系统状态（包含错误统计）
/doctor

# 输出示例：
系统诊断报告:
  ✓ API 连接正常
  ✓ 配置有效
  ⚠ 最近 5 分钟有 3 次重试
  ✓ 熔断器状态: CLOSED
```

---

## 与其他工具对比

| 特性 | PilotCode | Claude Code | LangChain | 一般 HTTP 库 |
|------|-----------|-------------|-----------|--------------|
| **错误分类** | ✅ 智能分类 | ✅ | ✅ | ❌ |
| **指数退避** | ✅ | ✅ | ✅ | 手动实现 |
| **熔断器** | ✅ | ❌ | ❌ | ❌ |
| **抖动** | ✅ | ❌ | ✅ | 手动实现 |
| **降级策略** | ✅ | ❌ | ✅ | ❌ |
| **错误统计** | ✅ | ❌ | ❌ | ❌ |

### 优势

1. **智能分类** - 自动识别错误类型，采取不同策略
2. **熔断器** - 防止级联故障，保护系统稳定性
3. **降级策略** - 失败时自动切换到备选方案
4. **可视化** - 通过 /doctor 命令查看错误统计

### 劣势

1. **复杂度** - 实现比简单重试更复杂
2. **配置** - 需要根据场景调整参数

---

## 降级策略

当主要服务不可用时，自动切换到备选：

```python
class FallbackStrategy:
    def __init__(self, primary, fallback):
        self.primary = primary
        self.fallback = fallback
    
    async def execute(self, *args, **kwargs):
        try:
            return await self.primary(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Primary failed, using fallback: {e}")
            return await self.fallback(*args, **kwargs)

# 使用示例
strategy = FallbackStrategy(
    primary=gpt4_client,
    fallback=gpt35_client  # GPT-4 失败时使用 GPT-3.5
)
result = await strategy.execute(messages)
```

---

## 最佳实践

### 1. 合理设置重试次数

```python
# API 调用 - 3 次足够
RetryConfig(max_attempts=3)

# 重要操作 - 可以更多
RetryConfig(max_attempts=5)

# 写入操作 - 谨慎重试，避免重复
RetryConfig(max_attempts=1)
```

### 2. 区分可重试错误

```python
# 好的做法 - 区分错误类型
if isinstance(error, (TimeoutError, ConnectionError)):
    return True  # 可重试
if isinstance(error, AuthenticationError):
    return False  # 不重试

# 不好的做法 - 全部重试
return True  # 可能导致无限循环
```

### 3. 监控熔断器状态

```bash
# 定期检查系统健康
/doctor

# 关注熔断器状态
如果状态为 OPEN，暂停操作等待恢复
```

### 4. 设置合理的超时

```python
# 根据操作类型设置超时
QUICK_OPS_TIMEOUT = 10.0      # 快速操作
NORMAL_OPS_TIMEOUT = 30.0     # 普通操作
LONG_OPS_TIMEOUT = 120.0      # 长时间操作（如代码生成）
```

---

## 相关文档

- [诊断命令](../commands/doctor.md)
- [Hook 系统](./hook-system.md)
