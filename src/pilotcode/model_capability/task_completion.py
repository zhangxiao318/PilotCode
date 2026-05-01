"""Task completion dimension benchmarks (medium)."""

from __future__ import annotations

import ast
from typing import Any

from pilotcode.utils.model_client import Message

from .base import BenchmarkResult, _call_llm, _extract_code


async def test_code_generation_correctness() -> BenchmarkResult:
    """Test medium-difficulty code: TTL cache with capacity and expiration."""
    prompt = """Implement a Python class `TTLCache` with the following specification:

Requirements:
- `__init__(self, max_size: int, default_ttl: int)` — max_size is the maximum number of items to store. default_ttl is the default time-to-live in seconds.
- `set(self, key: str, value: Any, ttl: int = None) -> None` — store a key-value pair. If ttl is None, use default_ttl. If cache is at max_size, evict the oldest inserted item (simple FIFO eviction is acceptable).
- `get(self, key: str) -> Any` — return the value if it exists and has not expired. If expired or missing, return None.
- `delete(self, key: str) -> None` — remove the key if it exists.
- `keys(self) -> list[str]` — return all non-expired keys.

Use only the Python standard library. You may use `time.time()` for timestamps.

Output ONLY the class definition, no explanation, no markdown fences, no test code.
"""
    raw = await _call_llm(
        [Message(role="user", content=prompt)],
        temperature=0.2,
    )
    code = _extract_code(raw)

    error_msg = ""
    tests_passed = 0
    tests_total = 6
    try:
        tree = ast.parse(code)
        local_ns: dict[str, Any] = {}
        import time
        exec(compile(tree, "<string>", "exec"), {"__builtins__": __builtins__, "time": time}, local_ns)
        TTLCache = local_ns.get("TTLCache")

        if not TTLCache:
            raise ValueError("TTLCache class not found")

        # Test 1: basic set/get
        cache = TTLCache(3, 10)
        cache.set("a", 1)
        assert cache.get("a") == 1
        tests_passed += 1

        # Test 2: expiration
        cache2 = TTLCache(3, 0)
        cache2.set("x", 100)
        time.sleep(0.05)
        assert cache2.get("x") is None
        tests_passed += 1

        # Test 3: capacity eviction (FIFO)
        cache3 = TTLCache(2, 60)
        cache3.set("a", 1)
        cache3.set("b", 2)
        cache3.set("c", 3)
        assert cache3.get("a") is None
        assert cache3.get("b") == 2
        assert cache3.get("c") == 3
        tests_passed += 1

        # Test 4: delete
        cache4 = TTLCache(3, 60)
        cache4.set("a", 1)
        cache4.delete("a")
        assert cache4.get("a") is None
        tests_passed += 1

        # Test 5: custom ttl override
        cache5 = TTLCache(3, 60)
        cache5.set("a", 1, ttl=0)
        time.sleep(0.05)
        assert cache5.get("a") is None
        tests_passed += 1

        # Test 6: keys() returns only non-expired
        cache6 = TTLCache(3, 60)
        cache6.set("a", 1)
        cache6.set("b", 2, ttl=0)
        time.sleep(0.05)
        ks = cache6.keys()
        assert "a" in ks and "b" not in ks
        tests_passed += 1

    except AssertionError as e:
        error_msg = f"Assertion failed: {e}"
    except Exception as e:
        error_msg = str(e)

    score = tests_passed / tests_total
    return BenchmarkResult(
        test_name="code_generation_correctness",
        dimension="task_completion",
        sub_dimension="code_correctness",
        score=score,
        raw_output=code[:400],
        error=error_msg if error_msg else None,
        metadata={"tests_passed": tests_passed, "tests_total": tests_total},
    )


async def test_bug_fixing() -> BenchmarkResult:
    """Test concurrency bug: transfer without locking both accounts."""
    buggy_code = '''from threading import Lock

class BankAccount:
    def __init__(self, balance=0):
        self.balance = balance
        self.lock = Lock()

    def deposit(self, amount):
        with self.lock:
            self.balance += amount

    def transfer(self, other, amount):
        """Transfer amount from self to other. Thread-safe."""
        with self.lock:
            if self.balance >= amount:
                other.balance += amount
                self.balance -= amount
'''
    prompt = f"""Fix the concurrency bug in this Python class.

```python
{buggy_code}
```

The `transfer` method claims to be thread-safe but has a race condition when two threads transfer between the same accounts concurrently.

Requirements for the fix:
- Must be thread-safe for concurrent transfers between any pair of accounts.
- Must avoid deadlock (hint: consider lock ordering).
- Do NOT change the public API (keep `deposit`, `transfer` signatures).

Output ONLY the corrected class, no explanation, no markdown.
"""
    raw = await _call_llm(
        [Message(role="user", content=prompt)],
        temperature=0.2,
    )
    code = _extract_code(raw)

    error_msg = ""
    race_detected = True
    try:
        tree = ast.parse(code)
        local_ns: dict[str, Any] = {}
        exec(compile(tree, "<string>", "exec"), local_ns)
        BankAccount = local_ns.get("BankAccount")

        if not BankAccount:
            raise ValueError("BankAccount class not found")

        import threading

        a = BankAccount(1000)
        b = BankAccount(1000)
        expected_total = a.balance + b.balance

        errors = []

        def worker():
            try:
                for _ in range(100):
                    a.transfer(b, 1)
                    b.transfer(a, 1)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        if errors:
            raise errors[0]

        actual_total = a.balance + b.balance
        if actual_total != expected_total:
            raise AssertionError(
                f"Race condition: total {actual_total} != expected {expected_total}"
            )
        if a.balance < 0 or b.balance < 0:
            raise AssertionError(
                f"Negative balance: a={a.balance}, b={b.balance}"
            )

        race_detected = False

    except Exception as e:
        error_msg = str(e)

    score = 0.0 if race_detected else 1.0
    return BenchmarkResult(
        test_name="bug_fixing",
        dimension="task_completion",
        sub_dimension="code_correctness",
        score=score,
        raw_output=code[:400],
        error=error_msg if error_msg else None,
        metadata={"race_detected": race_detected},
    )
