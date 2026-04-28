"""
Thread Context Manager Module
Provides context injection for thread_number tracking across sync and async operations.
Uses contextvars for async-safe storage and fallback to thread-local for sync contexts.
"""

import contextvars
import threading
from typing import Optional

# Context variable for async-safe thread number storage
_thread_number_context: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    'thread_number', default=None
)

# Thread-local storage for synchronous thread contexts
_thread_local = threading.local()


class ThreadContext:
    """
    Manages thread identification across sync and async contexts.
    
    Usage in ThreadPool:
        ```python
        for index, item in enumerate(items):
            thread_num = (index % max_threads) + 1
            ThreadContext.set_thread_context(thread_num)
            executor.submit(worker_func, item, thread_num)
        ```
    
    Usage in async:
        ```python
        for index, item in enumerate(items):
            thread_num = (index % batch_size) + 1
            ThreadContext.set_thread_context(thread_num)
            await process_item(item)
        ```
    
    Usage in functions:
        ```python
        def worker(item, thread_number=None):
            if thread_number is None:
                thread_number = ThreadContext.get_thread_context()
            LogManager.log_download_live("Processing item", thread_number=thread_number)
        ```
    """
    
    @staticmethod
    def set_thread_context(thread_number: Optional[int]) -> None:
        """
        Set the thread number for the current context.
        
        Works for both sync (ThreadPool) and async (asyncio) contexts:
        - In ThreadPool: Sets thread-local value (one per OS thread)
        - In async: Sets context variable (one per task)
        
        Args:
            thread_number: Logical thread identifier (typically 1-N range).
                          Set to None to clear context.
        """
        try:
            # Set context variable (works for async and sync)
            _thread_number_context.set(thread_number)
        except Exception:
            pass
        
        try:
            # Also set thread-local for traditional sync code
            _thread_local.thread_number = thread_number
        except Exception:
            pass
    
    @staticmethod
    def get_thread_context() -> Optional[int]:
        """
        Retrieve the thread number from current context.
        
        Returns the contextvar value if available (async/concurrent),
        otherwise falls back to thread-local storage (sync/ThreadPool).
        
        Returns:
            Logical thread identifier (1-N typically) or None if not set.
        """
        # Try to get from context variable first (works for async)
        try:
            context_value = _thread_number_context.get()
            if context_value is not None:
                return context_value
        except Exception:
            pass
        
        # Fallback to thread-local storage
        try:
            return getattr(_thread_local, 'thread_number', None)
        except Exception:
            pass
        
        return None
    
    @staticmethod
    def get_thread_context_or_ident() -> int:
        """
        Retrieve thread number from context, or fall back to 0 for non-threaded execution.
        
        This is a convenience method for LogManager fallback behavior.
        Returns the context value if set, otherwise returns 0.
        
        Returns:
            Logical thread identifier (1-N) or 0 for non-threaded execution
        """
        context_value = ThreadContext.get_thread_context()
        if context_value is not None:
            return context_value
        return 0
    
    @staticmethod
    def clear_context() -> None:
        """
        Clear thread context for cleanup.
        Useful when transitioning between operations or in thread pool cleanup.
        """
        ThreadContext.set_thread_context(None)
    
    @staticmethod
    def copy_context() -> contextvars.Context:
        """
        Create a copy of the current context for spawning new async tasks.
        
        Usage in asyncio:
            ```python
            ctx = ThreadContext.copy_context()
            asyncio.create_task(async_func(), context=ctx)
            ```
        
        Returns:
            contextvars.Context snapshot of current context
        """
        try:
            return contextvars.copy_context()
        except Exception:
            return None


# Convenience functions for module-level access

def set_thread_number(thread_number: Optional[int]) -> None:
    """Module-level convenience function to set thread number."""
    ThreadContext.set_thread_context(thread_number)


def get_thread_number() -> Optional[int]:
    """Module-level convenience function to get thread number."""
    return ThreadContext.get_thread_context()


def clear_thread_number() -> None:
    """Module-level convenience function to clear thread number."""
    ThreadContext.clear_context()
