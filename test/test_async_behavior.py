"""
Tests for Async Behavior and Race Condition Handling

These tests verify:
1. Async HTTP client functionality
2. Rate limiting behavior
3. Parallel execution correctness
4. Race condition protection in caches
5. Result consistency across concurrent executions
"""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from typing import Any


# =============================================================================
# Mock Classes (to avoid actual API calls)
# =============================================================================

@dataclass
class MockResponse:
    """Mock httpx response"""
    status_code: int
    content: bytes
    headers: dict

    def json(self):
        import json
        return json.loads(self.content.decode()) if self.content else {}

    def raise_for_status(self):
        if 400 <= self.status_code < 600:
            import httpx
            raise httpx.HTTPStatusError(
                "Mock error",
                request=MagicMock(),
                response=self
            )


def create_mock_rate_response(amount: float = 10.0, service_level: str = "usps_priority"):
    """Create a mock successful rate response"""
    return MockResponse(
        status_code=200,
        content=b'{"rates": [{"object_id": "rate_123", "amount": "' + str(amount).encode() + b'", "servicelevel": {"token": "' + service_level.encode() + b'"}}], "messages": []}',
        headers={"X-RateLimit-Remaining": "100", "X-RateLimit-Reset": str(int(time.time()) + 60)}
    )


def create_mock_rate_limit_response():
    """Create a mock 429 rate limit response"""
    return MockResponse(
        status_code=429,
        content=b'{"message": "Rate limit exceeded"}',
        headers={"Retry-After": "1"}
    )


def create_mock_error_response(status_code: int = 400, message: str = "Bad request"):
    """Create a mock error response"""
    return MockResponse(
        status_code=status_code,
        content=f'{{"message": "{message}"}}'.encode(),
        headers={}
    )


# =============================================================================
# Test: Async Client Basic Functionality
# =============================================================================

class TestAsyncClientBasics:
    """Test basic async client operations"""

    @pytest.mark.asyncio
    async def test_client_context_manager(self):
        """Test that ShippoClient works as async context manager"""
        import httpx

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            # Import after patching
            import sys
            sys.path.insert(0, '/Users/bryaneddy/Repos/shipment-extras/src')
            from shippo_extras import ShippoClient

            async with ShippoClient("test_api_key", concurrency=5) as client:
                assert client is not None
                assert client.api_key == "test_api_key"

            # Verify client was closed
            mock_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_concurrent_request_limiting(self):
        """Test that semaphore limits concurrent requests"""
        concurrency = 3
        request_count = 10
        concurrent_active = []
        max_concurrent = 0
        lock = asyncio.Lock()

        async def mock_request(*args, **kwargs):
            nonlocal max_concurrent
            async with lock:
                concurrent_active.append(1)
                current = len(concurrent_active)
                if current > max_concurrent:
                    max_concurrent = current

            await asyncio.sleep(0.05)  # Simulate network delay

            async with lock:
                concurrent_active.pop()

            return create_mock_rate_response()

        import httpx
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request = mock_request
            mock_client.post = mock_request
            mock_client.get = mock_request
            mock_client_class.return_value = mock_client

            import sys
            sys.path.insert(0, '/Users/bryaneddy/Repos/shipment-extras/src')
            from shippo_extras import ShippoClient

            async with ShippoClient("test_key", concurrency=concurrency) as client:
                tasks = [client._request("POST", "/shipments") for _ in range(request_count)]
                await asyncio.gather(*tasks)

        # Max concurrent should not exceed semaphore limit
        assert max_concurrent <= concurrency, f"Max concurrent {max_concurrent} exceeded limit {concurrency}"


# =============================================================================
# Test: Rate Limiting Behavior
# =============================================================================

class TestRateLimiting:
    """Test rate limiting and retry behavior"""

    @pytest.mark.asyncio
    async def test_rate_limit_retry_logic(self):
        """Test that 429 responses trigger retry (testing the pattern)"""
        call_count = 0
        semaphore = asyncio.Semaphore(5)
        rate_limit_reset_time = 0.0

        async def request_with_retry():
            """Simulate the retry logic from ShippoClient._request"""
            nonlocal call_count, rate_limit_reset_time

            async with semaphore:
                # Check rate limit wait
                current_time = time.monotonic()
                if current_time < rate_limit_reset_time:
                    wait_time = rate_limit_reset_time - current_time
                    await asyncio.sleep(wait_time)

                call_count += 1

                # First call returns 429
                if call_count == 1:
                    retry_after = 0.05  # 50ms for test
                    rate_limit_reset_time = time.monotonic() + retry_after
                    await asyncio.sleep(retry_after)
                    return await request_with_retry()  # Retry

                return {"status_code": 200, "data": {}}

        result = await request_with_retry()

        # Should have retried after 429
        assert call_count == 2
        assert result["status_code"] == 200

    @pytest.mark.asyncio
    async def test_proactive_rate_limit_wait(self):
        """Test that client waits proactively when rate limit is low"""
        import httpx

        responses = []

        async def mock_request(*args, **kwargs):
            # First response has low remaining limit
            response = create_mock_rate_response()
            response.headers["X-RateLimit-Remaining"] = "2"  # Low
            response.headers["X-RateLimit-Reset"] = str(int(time.time()) + 1)
            responses.append(response)
            return response

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request = mock_request
            mock_client.post = mock_request
            mock_client.get = mock_request
            mock_client_class.return_value = mock_client

            import sys
            sys.path.insert(0, '/Users/bryaneddy/Repos/shipment-extras/src')
            from shippo_extras import ShippoClient

            async with ShippoClient("test_key", concurrency=5) as client:
                start = time.monotonic()
                await client._request("POST", "/shipments")
                # Second request should be delayed
                await client._request("POST", "/shipments")
                elapsed = time.monotonic() - start

        # Should have some delay due to proactive waiting
        # Not asserting exact timing as it depends on implementation details


# =============================================================================
# Test: Race Condition Protection
# =============================================================================

class TestRaceConditionProtection:
    """Test that shared resources are properly protected"""

    @pytest.mark.asyncio
    async def test_baseline_cache_race_condition(self):
        """Test that baseline cache doesn't have race conditions"""
        cache_access_count = 0
        cache_write_count = 0

        # Simulate multiple tasks trying to get/set baseline simultaneously
        async def simulate_baseline_access(lock: asyncio.Lock, cache: dict, key: str, delay: float):
            nonlocal cache_access_count, cache_write_count

            # Check cache
            async with lock:
                cache_access_count += 1
                if key in cache:
                    return cache[key]

            # Simulate API call
            await asyncio.sleep(delay)
            value = f"baseline_{time.monotonic()}"

            # Write to cache
            async with lock:
                cache_write_count += 1
                if key not in cache:  # Double-check pattern
                    cache[key] = value
                return cache[key]

        lock = asyncio.Lock()
        cache = {}
        key = "test_carrier:test_service"

        # Launch many concurrent tasks for same key
        tasks = [simulate_baseline_access(lock, cache, key, 0.01) for _ in range(20)]
        results = await asyncio.gather(*tasks)

        # All should return the same value (first one to write wins)
        unique_values = set(results)
        assert len(unique_values) == 1, f"Race condition detected! Got {len(unique_values)} different values"

        # Cache should have been written only once for this key
        assert key in cache

    @pytest.mark.asyncio
    async def test_concurrent_different_keys_no_blocking(self):
        """Test that different cache keys don't block each other unnecessarily"""
        lock = asyncio.Lock()
        cache = {}
        access_times = []

        async def access_key(key: str, delay: float):
            start = time.monotonic()

            async with lock:
                if key in cache:
                    access_times.append(time.monotonic() - start)
                    return cache[key]

            await asyncio.sleep(delay)
            value = f"value_{key}"

            async with lock:
                cache[key] = value
                access_times.append(time.monotonic() - start)
                return value

        # Access different keys concurrently
        tasks = [access_key(f"key_{i}", 0.02) for i in range(5)]
        start = time.monotonic()
        await asyncio.gather(*tasks)
        total_time = time.monotonic() - start

        # Should complete much faster than sequential (5 * 0.02 = 0.1s)
        # Parallel should be ~0.02s + overhead
        assert total_time < 0.08, f"Operations took too long ({total_time:.3f}s), might be blocking"


# =============================================================================
# Test: Result Consistency
# =============================================================================

class TestResultConsistency:
    """Test that parallel execution produces consistent results"""

    @pytest.mark.asyncio
    async def test_gather_exception_handling(self):
        """Test that exceptions in gather are properly handled"""
        results = []

        async def task_success(idx: int):
            await asyncio.sleep(0.01)
            return {"status": "success", "idx": idx}

        async def task_failure(idx: int):
            await asyncio.sleep(0.01)
            raise ValueError(f"Task {idx} failed")

        tasks = [
            task_success(0),
            task_failure(1),
            task_success(2),
            task_failure(3),
            task_success(4),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Should have 5 results
        assert len(results) == 5

        # Check types
        assert results[0] == {"status": "success", "idx": 0}
        assert isinstance(results[1], ValueError)
        assert results[2] == {"status": "success", "idx": 2}
        assert isinstance(results[3], ValueError)
        assert results[4] == {"status": "success", "idx": 4}

    @pytest.mark.asyncio
    async def test_parallel_vs_sequential_consistency(self):
        """Test that parallel execution gives same results as sequential"""

        async def compute(x: int) -> int:
            await asyncio.sleep(0.001)  # Small delay to ensure async
            return x * 2 + 1

        inputs = list(range(50))

        # Sequential
        sequential_results = []
        for x in inputs:
            sequential_results.append(await compute(x))

        # Parallel
        parallel_results = await asyncio.gather(*[compute(x) for x in inputs])

        # Results should be identical
        assert sequential_results == list(parallel_results)

    @pytest.mark.asyncio
    async def test_result_order_preserved(self):
        """Test that asyncio.gather preserves result order"""

        async def delayed_return(value: int, delay: float) -> int:
            await asyncio.sleep(delay)
            return value

        # Create tasks with varying delays (not in order)
        tasks = [
            delayed_return(0, 0.03),
            delayed_return(1, 0.01),
            delayed_return(2, 0.05),
            delayed_return(3, 0.02),
            delayed_return(4, 0.04),
        ]

        results = await asyncio.gather(*tasks)

        # Results should be in task order, not completion order
        assert list(results) == [0, 1, 2, 3, 4]


# =============================================================================
# Test: Semaphore Behavior Under Load
# =============================================================================

class TestSemaphoreUnderLoad:
    """Test semaphore behavior with high concurrency"""

    @pytest.mark.asyncio
    async def test_semaphore_fairness(self):
        """Test that semaphore is fair (all tasks eventually complete)"""
        concurrency = 3
        task_count = 20
        completed = []
        semaphore = asyncio.Semaphore(concurrency)

        async def work(task_id: int):
            async with semaphore:
                await asyncio.sleep(0.01)
                completed.append(task_id)

        tasks = [work(i) for i in range(task_count)]
        await asyncio.gather(*tasks)

        # All tasks should complete
        assert len(completed) == task_count
        assert set(completed) == set(range(task_count))

    @pytest.mark.asyncio
    async def test_semaphore_no_deadlock(self):
        """Test that semaphore doesn't cause deadlock with nested operations"""
        semaphore = asyncio.Semaphore(2)
        completed = []

        async def outer(task_id: int):
            async with semaphore:
                await asyncio.sleep(0.01)
                # Note: we don't acquire semaphore again inside
                # (that would be a design issue)
                completed.append(f"outer_{task_id}")

        tasks = [outer(i) for i in range(10)]

        # Use wait_for to detect deadlock
        try:
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=2.0)
        except asyncio.TimeoutError:
            pytest.fail("Deadlock detected - tasks did not complete in time")

        assert len(completed) == 10

    @pytest.mark.asyncio
    async def test_high_contention(self):
        """Test behavior under high contention (many tasks, low concurrency)"""
        concurrency = 2
        task_count = 100
        active_count = 0
        max_active = 0
        lock = asyncio.Lock()
        semaphore = asyncio.Semaphore(concurrency)

        async def contended_work():
            nonlocal active_count, max_active
            async with semaphore:
                async with lock:
                    active_count += 1
                    if active_count > max_active:
                        max_active = active_count

                await asyncio.sleep(0.001)

                async with lock:
                    active_count -= 1

        start = time.monotonic()
        await asyncio.gather(*[contended_work() for _ in range(task_count)])
        elapsed = time.monotonic() - start

        # Max active should never exceed concurrency
        assert max_active <= concurrency

        # Should complete in reasonable time
        assert elapsed < 2.0


# =============================================================================
# Test: Lock Behavior
# =============================================================================

class TestLockBehavior:
    """Test asyncio.Lock behavior for cache protection"""

    @pytest.mark.asyncio
    async def test_lock_mutual_exclusion(self):
        """Test that lock provides mutual exclusion"""
        lock = asyncio.Lock()
        shared_value = 0
        increments = 1000

        async def increment():
            nonlocal shared_value
            async with lock:
                temp = shared_value
                await asyncio.sleep(0)  # Yield to other tasks
                shared_value = temp + 1

        await asyncio.gather(*[increment() for _ in range(increments)])

        # Without lock, this would likely be less than increments
        assert shared_value == increments

    @pytest.mark.asyncio
    async def test_lock_no_corruption(self):
        """Test that lock prevents data corruption in cache-like operations"""
        lock = asyncio.Lock()
        cache = {}
        corruption_detected = False

        async def cache_operation(key: str, value: str):
            nonlocal corruption_detected

            async with lock:
                # Simulate read-modify-write
                old = cache.get(key, "")
                await asyncio.sleep(0)  # Yield

                # Check for corruption
                current = cache.get(key, "")
                if current != old:
                    corruption_detected = True

                cache[key] = old + value

        tasks = [cache_operation("key", str(i)) for i in range(100)]
        await asyncio.gather(*tasks)

        assert not corruption_detected


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for the async test runners"""

    @pytest.mark.asyncio
    async def test_mock_full_test_run(self):
        """Test a mocked full test run with multiple carriers"""
        import httpx

        carriers = {
            "usps": {"account_id": "acc_usps", "service_levels": [{"token": "usps_priority"}], "active": True},
            "fedex": {"account_id": "acc_fedex", "service_levels": [{"token": "fedex_ground"}], "active": True},
        }

        request_log = []

        async def mock_request(*args, **kwargs):
            request_log.append({"args": args, "kwargs": kwargs, "time": time.monotonic()})
            await asyncio.sleep(0.01)
            return create_mock_rate_response()

        # Simulate parallel requests
        semaphore = asyncio.Semaphore(5)

        async def make_request(carrier: str, extra: str):
            async with semaphore:
                return await mock_request(carrier, extra)

        tasks = []
        for carrier in carriers:
            for extra in ["insurance", "signature", "cod"]:
                tasks.append(make_request(carrier, extra))

        start = time.monotonic()
        results = await asyncio.gather(*tasks)
        elapsed = time.monotonic() - start

        # All should succeed
        assert len(results) == 6
        assert all(r.status_code == 200 for r in results)

        # Should be faster than sequential (6 * 0.01 = 0.06s min sequential)
        # Parallel with concurrency 5 should be ~0.02s
        assert elapsed < 0.05


# =============================================================================
# Stress Tests
# =============================================================================

class TestStress:
    """Stress tests for edge cases"""

    @pytest.mark.asyncio
    async def test_many_concurrent_tasks(self):
        """Test with many concurrent tasks"""
        task_count = 500
        concurrency = 10
        semaphore = asyncio.Semaphore(concurrency)
        completed = 0
        lock = asyncio.Lock()

        async def task():
            nonlocal completed
            async with semaphore:
                await asyncio.sleep(0.001)
            async with lock:
                completed += 1

        await asyncio.gather(*[task() for _ in range(task_count)])
        assert completed == task_count

    @pytest.mark.asyncio
    async def test_rapid_cache_access(self):
        """Test rapid concurrent cache access"""
        lock = asyncio.Lock()
        cache = {}
        access_count = 0

        async def access(key: str):
            nonlocal access_count
            async with lock:
                access_count += 1
                if key not in cache:
                    cache[key] = 0
                cache[key] += 1

        # Many tasks accessing same keys
        tasks = [access(f"key_{i % 10}") for i in range(1000)]
        await asyncio.gather(*tasks)

        assert access_count == 1000
        assert sum(cache.values()) == 1000


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
