"""
Resilience utilities for A2A communication.

Implements retry logic, circuit breakers, and timeout handling for
production-grade agent-to-agent calls.
"""

import logging
import asyncio
from typing import Any, Callable, TypeVar, Optional, AsyncGenerator
from functools import wraps
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    AsyncRetrying
)

logger = logging.getLogger(__name__)

# Type variable for generic retry decorator
T = TypeVar('T')

# Define retriable exceptions
RETRIABLE_EXCEPTIONS = (
    asyncio.TimeoutError,
    ConnectionError,
    ConnectionResetError,
    # httpx.ConnectError,  # Add specific httpx errors if needed
    # httpx.ReadTimeout,
)

def async_retry_generator(**retry_kwargs):
    """
    A decorator factory for retrying async generators.
    
    Usage:
        @async_retry_generator(stop=stop_after_attempt(3))
        async def my_async_generator():
            ...
    """
    def decorator(async_gen_func):
        @wraps(async_gen_func)
        async def wrapper(*args, **kwargs):
            retryer = AsyncRetrying(
                stop=retry_kwargs.get('stop', stop_after_attempt(3)),
                wait=retry_kwargs.get('wait', wait_exponential(multiplier=1, min=1, max=10)),
                retry=retry_kwargs.get('retry', retry_if_exception_type(RETRIABLE_EXCEPTIONS)),
                before_sleep=retry_kwargs.get('before_sleep', before_sleep_log(logger, logging.WARNING)),
                reraise=True
            )
            
            async for attempt in retryer:
                with attempt:
                    try:
                        async for item in async_gen_func(*args, **kwargs):
                            yield item
                        return  # Stop iteration if generator completes successfully
                    except Exception as e:
                        logger.error(f"Attempt {attempt.retry_state.attempt_number} failed with {e.__class__.__name__}")
                        raise
        return wrapper
    return decorator


async def invoke_with_retry(async_func: Callable[..., AsyncGenerator], *args: Any) -> AsyncGenerator:
    """
    Asynchronously invokes a function (especially an async generator) with retry logic.

    This function is designed to handle transient errors for functions that yield results,
    which are common in streaming agent responses.
    """
    retrying_logic = AsyncRetrying(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )

    async for attempt in retrying_logic:
        with attempt:
            try:
                # We are retrying the entire generator iteration
                async for item in async_func(*args):
                    yield item
                # If the generator finishes without error, we're done.
                return
            except Exception as e:
                logger.warning(f"A2A call attempt {attempt.retry_state.attempt_number} failed: {e}")
                # Tenacity will catch this and decide whether to retry
                raise


class CircuitBreaker:
    """
    Circuit breaker pattern for A2A calls to prevent cascading failures.
    
    States:
    - CLOSED: Normal operation, calls pass through
    - OPEN: Too many failures, calls immediately fail
    - HALF_OPEN: Testing if service recovered
    
    Example:
        breaker = CircuitBreaker(failure_threshold=5, timeout=60)
        
        async with breaker:
            result = await agent.invoke(task)
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: int = 60,
        expected_exception: type = Exception
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            timeout: Seconds to wait before testing recovery
            expected_exception: Exception type that triggers the breaker
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"
        
    async def __aenter__(self):
        """Context manager entry."""
        if self.state == "OPEN":
            # Check if timeout has passed
            import time
            if time.time() - self.last_failure_time >= self.timeout:
                self.state = "HALF_OPEN"
                logger.info("Circuit breaker entering HALF_OPEN state")
            else:
                raise Exception("Circuit breaker is OPEN - too many recent failures")
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if exc_type is None:
            # Success
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
                logger.info("Circuit breaker recovered to CLOSED state")
            return False
        
        if isinstance(exc_val, self.expected_exception):
            self.failure_count += 1
            logger.warning(f"Circuit breaker failure count: {self.failure_count}/{self.failure_threshold}")
            
            if self.failure_count >= self.failure_threshold:
                import time
                self.state = "OPEN"
                self.last_failure_time = time.time()
                logger.error(f"Circuit breaker opened after {self.failure_count} failures")
                
        return False  # Don't suppress exception
