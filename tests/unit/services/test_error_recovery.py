"""Tests for error recovery and retry logic."""

import pytest
import asyncio
from unittest.mock import AsyncMock
from pilotcode.services.error_recovery import (
    ErrorClassifier,
    ErrorCategory,
    RetryHandler,
    RetryConfig,
    CircuitBreaker,
    with_retry,
)


class TestErrorClassifier:
    """Test error classification."""

    def test_classify_rate_limit(self):
        """Test rate limit error classification."""
        error = Exception("Rate limit exceeded: 429 Too Many Requests")
        category = ErrorClassifier.classify_error(error)
        assert category == ErrorCategory.RATE_LIMIT

    def test_classify_authentication(self):
        """Test authentication error classification."""
        error = Exception("Unauthorized: Invalid API key")
        category = ErrorClassifier.classify_error(error)
        assert category == ErrorCategory.AUTHENTICATION

    def test_classify_timeout(self):
        """Test timeout error classification."""
        error = Exception("Connection timed out")
        category = ErrorClassifier.classify_error(error)
        assert category == ErrorCategory.TIMEOUT

    def test_classify_network(self):
        """Test network error classification."""
        error = Exception("Network unreachable")
        category = ErrorClassifier.classify_error(error)
        assert category == ErrorCategory.NETWORK

    def test_classify_transient(self):
        """Test transient error classification."""
        error = Exception("Service temporarily unavailable (503)")
        category = ErrorClassifier.classify_error(error)
        assert category == ErrorCategory.TRANSIENT

    def test_classify_permanent(self):
        """Test permanent error classification."""
        error = Exception("Bad request: Invalid parameter (400)")
        category = ErrorClassifier.classify_error(error)
        assert category == ErrorCategory.PERMANENT

    def test_classify_unknown(self):
        """Test unknown error classification."""
        error = Exception("Something completely unexpected")
        category = ErrorClassifier.classify_error(error)
        assert category == ErrorCategory.UNKNOWN


class TestRetryHandler:
    """Test retry handler functionality."""

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        """Test successful execution without retry."""
        handler = RetryHandler(RetryConfig(max_attempts=3))

        mock_fn = AsyncMock(return_value="success")

        result = await handler.execute_with_retry(mock_fn, "arg1", kwarg1="value1")

        assert result.success is True
        assert result.result == "success"
        assert result.attempts == 1
        mock_fn.assert_called_once_with("arg1", kwarg1="value1")

    @pytest.mark.asyncio
    async def test_retry_on_transient_error(self):
        """Test retry on transient error."""
        config = RetryConfig(max_attempts=3, base_delay=0.01)
        handler = RetryHandler(config)

        mock_fn = AsyncMock(
            side_effect=[
                Exception("Service temporarily unavailable"),
                Exception("Service temporarily unavailable"),
                "success",
            ]
        )

        result = await handler.execute_with_retry(mock_fn)

        assert result.success is True
        assert result.attempts == 3
        assert mock_fn.call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_permanent_error(self):
        """Test no retry on permanent error."""
        config = RetryConfig(max_attempts=3)
        handler = RetryHandler(config)

        mock_fn = AsyncMock(side_effect=Exception("Bad request: Invalid parameter"))

        result = await handler.execute_with_retry(mock_fn)

        assert result.success is False
        assert result.error_category == ErrorCategory.PERMANENT
        assert mock_fn.call_count == 1  # No retry

    @pytest.mark.asyncio
    async def test_no_retry_on_auth_error(self):
        """Test no retry on authentication error."""
        config = RetryConfig(max_attempts=3)
        handler = RetryHandler(config)

        mock_fn = AsyncMock(side_effect=Exception("Unauthorized: Invalid API key"))

        result = await handler.execute_with_retry(mock_fn)

        assert result.success is False
        assert result.error_category == ErrorCategory.AUTHENTICATION
        assert mock_fn.call_count == 1  # No retry

    @pytest.mark.asyncio
    async def test_all_attempts_fail(self):
        """Test when all retry attempts fail."""
        config = RetryConfig(max_attempts=3, base_delay=0.01)
        handler = RetryHandler(config)

        mock_fn = AsyncMock(side_effect=Exception("Network error"))

        result = await handler.execute_with_retry(mock_fn)

        assert result.success is False
        assert result.attempts == 3
        assert mock_fn.call_count == 3

    def test_calculate_delay(self):
        """Test delay calculation."""
        config = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter=False)
        handler = RetryHandler(config)

        delay0 = handler.calculate_delay(0)
        delay1 = handler.calculate_delay(1)
        delay2 = handler.calculate_delay(2)

        assert delay0 == 1.0
        assert delay1 == 2.0
        assert delay2 == 4.0

    def test_calculate_delay_with_max(self):
        """Test delay calculation respects max_delay."""
        config = RetryConfig(base_delay=1.0, max_delay=5.0, exponential_base=10.0, jitter=False)
        handler = RetryHandler(config)

        delay = handler.calculate_delay(10)  # Would be 1 * 10^10 without max

        assert delay == 5.0

    def test_calculate_delay_with_jitter(self):
        """Test delay calculation with jitter."""
        config = RetryConfig(base_delay=1.0, jitter=True)
        handler = RetryHandler(config)

        delay = handler.calculate_delay(0)

        # Jitter adds ±20%, so delay should be between 0.8 and 1.2
        assert 0.8 <= delay <= 1.2


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    @pytest.mark.asyncio
    async def test_closed_state_allows_execution(self):
        """Test that closed circuit allows execution."""
        cb = CircuitBreaker()

        mock_fn = AsyncMock(return_value="success")

        result = await cb.execute(mock_fn)

        assert result == "success"
        assert cb.state == "closed"

    @pytest.mark.asyncio
    async def test_opens_after_failures(self):
        """Test circuit opens after threshold failures."""
        cb = CircuitBreaker(failure_threshold=3)
        mock_fn = AsyncMock(side_effect=Exception("Error"))

        # First 3 failures
        for _ in range(3):
            with pytest.raises(Exception):
                await cb.execute(mock_fn)

        # Circuit should now be open
        assert cb.state == "open"
        assert cb.failures == 3

    @pytest.mark.asyncio
    async def test_open_state_blocks_execution(self):
        """Test that open circuit blocks execution."""
        cb = CircuitBreaker()
        cb.state = "open"
        cb.last_failure_time = __import__("datetime").datetime.now()

        mock_fn = AsyncMock(return_value="success")

        with pytest.raises(Exception, match="Circuit breaker is open"):
            await cb.execute(mock_fn)

        mock_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_half_open_after_timeout(self):
        """Test circuit goes to half-open after timeout."""
        cb = CircuitBreaker(recovery_timeout=0.01)
        cb.state = "open"
        cb.last_failure_time = __import__("datetime").datetime.now()

        # Wait for timeout
        await asyncio.sleep(0.02)

        # Should be able to execute now
        mock_fn = AsyncMock(return_value="success")
        result = await cb.execute(mock_fn)

        assert result == "success"
        assert cb.state == "half-open"

    @pytest.mark.asyncio
    async def test_closes_after_half_open_successes(self):
        """Test circuit closes after half-open successes."""
        cb = CircuitBreaker(half_open_max_calls=2, recovery_timeout=0)
        cb.state = "half-open"

        mock_fn = AsyncMock(return_value="success")

        await cb.execute(mock_fn)
        await cb.execute(mock_fn)

        assert cb.state == "closed"
        assert cb.failures == 0

    @pytest.mark.asyncio
    async def test_reopens_on_half_open_failure(self):
        """Test circuit reopens on failure in half-open state."""
        cb = CircuitBreaker(half_open_max_calls=3, recovery_timeout=0)
        cb.state = "half-open"
        cb.half_open_calls = 1

        mock_fn = AsyncMock(side_effect=Exception("Error"))

        with pytest.raises(Exception):
            await cb.execute(mock_fn)

        assert cb.state == "open"


class TestWithRetryConvenience:
    """Test with_retry convenience function."""

    @pytest.mark.asyncio
    async def test_with_retry_success(self):
        """Test with_retry with successful execution."""
        mock_fn = AsyncMock(return_value="success")

        result = await with_retry(mock_fn, max_attempts=3)

        assert result.success is True
        assert result.result == "success"

    @pytest.mark.asyncio
    async def test_with_retry_eventual_success(self):
        """Test with_retry that eventually succeeds."""
        mock_fn = AsyncMock(side_effect=[Exception("Transient error"), "success"])

        result = await with_retry(mock_fn, max_attempts=3)

        assert result.success is True
        assert result.attempts == 2
