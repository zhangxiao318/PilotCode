"""Error recovery and retry logic - ClaudeCode-style implementation.

This module provides:
1. Retry logic with exponential backoff
2. Error classification and handling
3. Circuit breaker pattern
4. Fallback strategies
"""

import asyncio
import random
from dataclasses import dataclass
from typing import Any, Callable, TypeVar
from enum import Enum
from datetime import datetime

T = TypeVar("T")


class ErrorCategory(Enum):
    """Categories of errors for handling strategies."""

    TRANSIENT = "transient"  # Temporary, retry likely to succeed
    PERMANENT = "permanent"  # Permanent, retry won't help
    RATE_LIMIT = "rate_limit"  # Rate limited, retry with backoff
    TIMEOUT = "timeout"  # Timeout, retry may help
    AUTHENTICATION = "auth"  # Authentication error, retry won't help
    NETWORK = "network"  # Network error, retry may help
    UNKNOWN = "unknown"  # Unknown error


@dataclass
class RetryConfig:
    """Configuration for retry logic."""

    max_attempts: int = 3
    base_delay: float = 1.0  # Base delay in seconds
    max_delay: float = 60.0  # Maximum delay
    exponential_base: float = 2.0
    jitter: bool = True  # Add random jitter to delay
    retryable_errors: list[type] | None = None


@dataclass
class RetryResult:
    """Result of a retry operation."""

    success: bool
    result: Any | None
    error: Exception | None
    attempts: int
    total_delay: float
    error_category: ErrorCategory


class ErrorClassifier:
    """Classify errors for appropriate handling."""

    @staticmethod
    def classify_error(error: Exception) -> ErrorCategory:
        """Classify an error into a category."""
        error_str = str(error).lower()
        type(error).__name__.lower()

        # Rate limiting
        if any(x in error_str for x in ["rate limit", "too many requests", "429", "ratelimit"]):
            return ErrorCategory.RATE_LIMIT

        # Authentication
        if any(x in error_str for x in ["unauthorized", "authentication", "api key", "401", "403"]):
            return ErrorCategory.AUTHENTICATION

        # Timeout
        if any(x in error_str for x in ["timeout", "timed out", "connection timed out"]):
            return ErrorCategory.TIMEOUT

        # Network
        if any(
            x in error_str for x in ["connection", "network", "unreachable", "refused", "reset"]
        ):
            return ErrorCategory.NETWORK

        # Transient API errors
        if any(
            x in error_str for x in ["temporary", "unavailable", "overload", "503", "502", "504"]
        ):
            return ErrorCategory.TRANSIENT

        # Permanent errors
        if any(x in error_str for x in ["not found", "invalid", "bad request", "400", "404"]):
            return ErrorCategory.PERMANENT

        return ErrorCategory.UNKNOWN


class RetryHandler:
    """Handle retries with exponential backoff."""

    def __init__(self, config: RetryConfig | None = None):
        self.config = config or RetryConfig()
        self.classifier = ErrorClassifier()

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for a retry attempt."""
        # Exponential backoff: base * (2 ^ attempt)
        delay = self.config.base_delay * (self.config.exponential_base**attempt)
        delay = min(delay, self.config.max_delay)

        if self.config.jitter:
            # Add random jitter (±20%)
            jitter = delay * 0.2 * (2 * random.random() - 1)
            delay += jitter

        return max(0, delay)

    async def execute_with_retry(self, fn: Callable[..., T], *args, **kwargs) -> RetryResult:
        """Execute a function with retry logic."""
        last_error: Exception | None = None
        total_delay = 0.0

        for attempt in range(self.config.max_attempts):
            try:
                result = await fn(*args, **kwargs)
                return RetryResult(
                    success=True,
                    result=result,
                    error=None,
                    attempts=attempt + 1,
                    total_delay=total_delay,
                    error_category=ErrorCategory.UNKNOWN,
                )

            except Exception as e:
                last_error = e
                category = self.classifier.classify_error(e)

                # Don't retry permanent errors
                if category == ErrorCategory.PERMANENT:
                    return RetryResult(
                        success=False,
                        result=None,
                        error=e,
                        attempts=attempt + 1,
                        total_delay=total_delay,
                        error_category=category,
                    )

                # Don't retry auth errors
                if category == ErrorCategory.AUTHENTICATION:
                    return RetryResult(
                        success=False,
                        result=None,
                        error=e,
                        attempts=attempt + 1,
                        total_delay=total_delay,
                        error_category=category,
                    )

                # If this was the last attempt, fail
                if attempt == self.config.max_attempts - 1:
                    break

                # Calculate and apply delay
                delay = self.calculate_delay(attempt)
                total_delay += delay

                # Special handling for rate limits
                if category == ErrorCategory.RATE_LIMIT:
                    delay = max(delay, 5.0)  # Minimum 5s for rate limits

                await asyncio.sleep(delay)

        return RetryResult(
            success=False,
            result=None,
            error=last_error,
            attempts=self.config.max_attempts,
            total_delay=total_delay,
            error_category=(
                self.classifier.classify_error(last_error) if last_error else ErrorCategory.UNKNOWN
            ),
        )


class CircuitBreaker:
    """Circuit breaker pattern for fault tolerance."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 3,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self.failures = 0
        self.last_failure_time: datetime | None = None
        self.state = "closed"  # closed, open, half-open
        self.half_open_calls = 0

    def can_execute(self) -> bool:
        """Check if execution is allowed."""
        if self.state == "closed":
            return True

        if self.state == "open":
            # Check if recovery timeout has passed
            if self.last_failure_time:
                elapsed = (datetime.now() - self.last_failure_time).total_seconds()
                if elapsed >= self.recovery_timeout:
                    self.state = "half-open"
                    self.half_open_calls = 0
                    return True
            return False

        if self.state == "half-open":
            return self.half_open_calls < self.half_open_max_calls

        return True

    def record_success(self):
        """Record a successful execution."""
        if self.state == "half-open":
            self.half_open_calls += 1
            if self.half_open_calls >= self.half_open_max_calls:
                # Recovery successful
                self.state = "closed"
                self.failures = 0
                self.last_failure_time = None
        else:
            self.failures = max(0, self.failures - 1)

    def record_failure(self):
        """Record a failed execution."""
        self.failures += 1
        self.last_failure_time = datetime.now()

        if self.state == "half-open":
            # Recovery failed, go back to open
            self.state = "open"
        elif self.failures >= self.failure_threshold:
            # Too many failures, open the circuit
            self.state = "open"

    async def execute(
        self, fn: Callable[..., T], fallback: Callable[..., T] | None = None, *args, **kwargs
    ) -> T:
        """Execute with circuit breaker protection."""
        if not self.can_execute():
            if fallback:
                return await fallback(*args, **kwargs)
            raise Exception(f"Circuit breaker is {self.state}")

        try:
            result = await fn(*args, **kwargs)
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise


class FallbackStrategy:
    """Strategies for fallback behavior."""

    @staticmethod
    def default_value(value: Any) -> Callable:
        """Return a default value on failure."""

        async def fallback(*args, **kwargs):
            return value

        return fallback

    @staticmethod
    def retry_with_simpler_params(simplified_params: dict) -> Callable:
        """Retry with simplified parameters."""

        async def fallback(fn, *args, **kwargs):
            # Merge simplified params
            new_kwargs = {**kwargs, **simplified_params}
            return await fn(*args, **new_kwargs)

        return fallback

    @staticmethod
    def alternative_provider(alternative_fn: Callable) -> Callable:
        """Use an alternative function/provider."""

        async def fallback(*args, **kwargs):
            return await alternative_fn(*args, **kwargs)

        return fallback


# Global retry handler
_default_retry_handler: RetryHandler | None = None


def get_retry_handler(config: RetryConfig | None = None) -> RetryHandler:
    """Get global retry handler."""
    global _default_retry_handler
    if _default_retry_handler is None:
        _default_retry_handler = RetryHandler(config)
    return _default_retry_handler


async def with_retry(fn: Callable[..., T], max_attempts: int = 3, *args, **kwargs) -> RetryResult:
    """Convenience function for retry logic."""
    config = RetryConfig(max_attempts=max_attempts)
    handler = RetryHandler(config)
    return await handler.execute_with_retry(fn, *args, **kwargs)
