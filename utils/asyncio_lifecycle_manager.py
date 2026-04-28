"""
Asyncio Lifecycle Manager

Centralized management of event loop lifecycle to prevent "Event loop is closed" errors
when aiosqlite worker threads try to communicate with closed loops.

Handles:
- Registration and tracking of event loops and databases
- Safe coroutine scheduling across thread boundaries
- Graceful shutdown sequence: close databases → stop loops → join threads
- Recovery from loop closure exceptions
"""

import asyncio
import logging
import threading
import time
from typing import Optional, Dict, List, Callable, Coroutine, Any
from contextlib import suppress

logger = logging.getLogger(__name__)


class AsyncioLifecycleManager:
    """Central coordinator for asyncio event loop lifecycle management."""

    _instance = None
    _lock = threading.Lock()
    
    # Registry of all managed loops and their metadata
    _loops: Dict[int, Dict[str, Any]] = {}  # {loop_id: {"loop": loop, "databases": [...], "thread_id": ...}}
    _databases: Dict[int, Dict[str, Any]] = {}  # {db_id: {"manager": manager, "loop": loop}}
    _shutdown_handlers: List[Callable[[], None]] = []
    
    _is_shutting_down = False
    _shutdown_timeout = 30  # seconds

    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register_loop(cls, loop: asyncio.AbstractEventLoop, loop_name: str = None, thread_id: int = None) -> int:
        """
        Register an event loop for lifecycle management.
        
        Args:
            loop: The event loop to register
            loop_name: Optional name for debugging (e.g., "main", "bg_scheduler", "captions_thread_1")
            thread_id: Optional thread ID (auto-detected if not provided)
        
        Returns:
            Unique loop ID for later reference
        """
        if thread_id is None:
            thread_id = threading.get_ident()
        
        loop_id = id(loop)
        
        with cls._lock:
            cls._loops[loop_id] = {
                "loop": loop,
                "name": loop_name or f"loop_{loop_id}",
                "thread_id": thread_id,
                "databases": [],
                "registered_at": time.time(),
            }
        
        return loop_id

    @classmethod
    def register_database(cls, db_manager: Any, loop: asyncio.AbstractEventLoop, db_name: str = None) -> int:
        """
        Register a database manager for coordinated shutdown.
        
        Args:
            db_manager: The database manager instance (DVRDB, etc.)
            loop: The event loop managing this database
            db_name: Optional name for debugging
        
        Returns:
            Unique database ID
        """
        db_id = id(db_manager)
        loop_id = id(loop)
        
        with cls._lock:
            # Register loop if not already registered
            if loop_id not in cls._loops:
                cls.register_loop(loop, db_name or "unregistered_loop")
            
            cls._databases[db_id] = {
                "manager": db_manager,
                "loop_id": loop_id,
                "name": db_name or f"db_{db_id}",
                "registered_at": time.time(),
            }
            
            # Add to loop's database list
            cls._loops[loop_id]["databases"].append(db_id)
        
        return db_id

    @classmethod
    def register_shutdown_handler(cls, handler: Callable[[], None]):
        """
        Register a callback to be called during shutdown.
        Handlers are called in reverse registration order (LIFO).
        
        Args:
            handler: Callable that takes no arguments
        """
        with cls._lock:
            cls._shutdown_handlers.append(handler)

    @classmethod
    def safe_schedule_on_loop(
        cls, 
        coro: Coroutine, 
        loop: asyncio.AbstractEventLoop, 
        timeout: float = 5.0,
        fallback_to_bg: bool = True
    ) -> bool:
        """
        Safely schedule a coroutine on a specific event loop.
        
        Handles the case where the loop might be closed by catching RuntimeError
        and optionally falling back to a background loop.
        
        Args:
            coro: Coroutine to schedule
            loop: Target event loop
            timeout: How long to wait for the loop to be available
            fallback_to_bg: If target loop is closed, try to schedule on background loop
        
        Returns:
            True if scheduling succeeded, False otherwise
        """
        if cls._is_shutting_down:
            logger.warning("Cannot schedule coroutine during shutdown")
            return False
        
        loop_id = id(loop)
        loop_name = cls._loops.get(loop_id, {}).get("name", "unknown")
        
        # Try target loop first
        try:
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(coro, loop)
                return True
            else:
                logger.warning(f"Loop {loop_name} is not running")
        except RuntimeError as e:
            logger.warning(f"Failed to schedule on loop {loop_name}: {e}")
            if "closed" in str(e).lower():
                if not fallback_to_bg:
                    return False
        
        # Fallback to background loop if available
        if fallback_to_bg:
            try:
                from utils.async_scheduler import AsyncScheduler
                if AsyncScheduler.schedule_nonblocking(coro):
                    return True
            except Exception as e:
                logger.error(f"Fallback to background loop failed: {e}")
        
        return False

    @classmethod
    def is_loop_running(cls, loop: asyncio.AbstractEventLoop) -> bool:
        """Check if a loop is running and not closed."""
        try:
            return loop.is_running() and not loop._closed
        except (AttributeError, RuntimeError):
            return False

    @classmethod
    async def graceful_shutdown(cls, timeout: float = None):
        """
        Perform graceful shutdown of all managed resources.
        
        Sequence:
        1. Call registered shutdown handlers
        2. Close all registered databases (waits for aiosqlite worker threads)
        3. Stop all background event loops
        4. Join all worker threads
        
        Args:
            timeout: Maximum seconds to wait for shutdown (uses class default if None)
        """
        if timeout is None:
            timeout = cls._shutdown_timeout
        
        with cls._lock:
            if cls._is_shutting_down:
                logger.warning("Shutdown already in progress")
                return
            cls._is_shutting_down = True
        
        start_time = time.time()
        
        try:
            # 1. Call shutdown handlers in reverse order (LIFO)
            for handler in reversed(cls._shutdown_handlers):
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler()
                    else:
                        handler()
                except Exception as e:
                    logger.error(f"Error in shutdown handler {handler.__name__}: {e}")
        
            # 2. Close all registered databases
            with cls._lock:
                db_ids = list(cls._databases.keys())
            
            for db_id in db_ids:
                try:
                    with cls._lock:
                        db_entry = cls._databases.get(db_id)
                        if not db_entry:
                            continue
                        db_manager = db_entry["manager"]
                    
                    # Call disconnect on database manager
                    if hasattr(db_manager, 'disconnect'):
                        await db_manager.disconnect()
                    elif hasattr(db_manager, 'close'):
                        await db_manager.close()
                    
                except Exception as e:
                    logger.error(f"Error closing database {db_id}: {e}")
        
            # 3. Stop background loops and clean up
            with cls._lock:
                loop_ids = list(cls._loops.keys())
            
            for loop_id in loop_ids:
                try:
                    with cls._lock:
                        loop_entry = cls._loops.get(loop_id)
                        if not loop_entry:
                            continue
                        loop = loop_entry["loop"]
                        loop_name = loop_entry["name"]
                    
                    # Only stop loops that aren't the current running loop
                    try:
                        current_loop = asyncio.get_running_loop()
                        if loop is current_loop:
                            continue
                    except RuntimeError:
                        pass  # No running loop in this thread
                    
                    # Stop the loop
                    if loop.is_running():
                        loop.call_soon_threadsafe(loop.stop)
                
                except Exception as e:
                    logger.error(f"Error stopping loop {loop_id}: {e}")
        
            # 4. Wait for all threads to finish (except current thread and daemon threads)
            current_thread = threading.current_thread()
            remaining_time = timeout - (time.time() - start_time)
            
            # Only wait briefly for non-daemon threads to finish
            # Don't wait too long as asyncio.run() will clean up automatically
            max_thread_wait = min(2.0, remaining_time)  # Max 2 seconds
            if max_thread_wait > 0:
                for thread in list(threading.enumerate()):
                    if thread is current_thread or thread is threading.main_thread():
                        continue
                    if thread.daemon:
                        continue  # Don't wait for daemon threads
                    
                    try:
                        thread.join(timeout=0.2)  # Short timeout per thread
                    except Exception as e:
                        logger.warning(f"Error joining thread {thread.name}: {e}")
        
        except Exception as e:
            logger.error(f"Error during graceful shutdown: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            with cls._lock:
                cls._is_shutting_down = False

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """Get current status of all managed resources for debugging."""
        with cls._lock:
            loops_status = {}
            for loop_id, entry in cls._loops.items():
                loop = entry["loop"]
                loops_status[entry["name"]] = {
                    "is_running": loop.is_running() if not loop._closed else False,
                    "is_closed": loop._closed,
                    "thread_id": entry["thread_id"],
                    "databases": len(entry["databases"]),
                }
            
            return {
                "is_shutting_down": cls._is_shutting_down,
                "loops": loops_status,
                "total_databases": len(cls._databases),
                "shutdown_handlers": len(cls._shutdown_handlers),
            }

    @classmethod
    def reset(cls):
        """Reset manager state (for testing)."""
        with cls._lock:
            cls._loops.clear()
            cls._databases.clear()
            cls._shutdown_handlers.clear()
            cls._is_shutting_down = False
