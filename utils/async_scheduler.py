import asyncio
import contextlib
import threading
import time
import logging

logger = logging.getLogger(__name__)


class AsyncScheduler:
    """Utility for scheduling coroutines from non-async contexts.

    Provides a background event loop and thread, and a helper to schedule
    coroutines safely whether called from inside an event loop or from a
    synchronous thread.
    """

    _bg_loop = None
    _bg_thread = None
    _bg_loop_lock = threading.Lock()
    _bg_loop_id = None

    @classmethod
    def _start_bg_loop(cls):
        bg_loop = getattr(cls, "_bg_loop", None)
        if bg_loop is not None and bg_loop.is_running():
            return

        def _run_loop():
            cls._bg_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(cls._bg_loop)
            
            # Register with lifecycle manager
            try:
                from utils.asyncio_lifecycle_manager import AsyncioLifecycleManager
                cls._bg_loop_id = AsyncioLifecycleManager.register_loop(
                    cls._bg_loop, 
                    loop_name="background_scheduler"
                )
                logger.debug("Registered background loop with AsyncioLifecycleManager")
            except Exception as e:
                logger.warning(f"Failed to register background loop: {e}")
            
            cls._bg_loop.run_forever()

        t = threading.Thread(target=_run_loop, daemon=True, name="AsyncScheduler_BackgroundLoop")
        t.start()
        cls._bg_thread = t

        # wait briefly for the loop to be ready
        for _ in range(100):
            bg_loop = getattr(cls, "_bg_loop", None)
            if bg_loop is not None and bg_loop.is_running():
                break
            time.sleep(0.01)

    @classmethod
    def schedule_nonblocking(cls, coro, main_loop=None):
        """Schedule `coro` in an available event loop.

        Behavior mirrors the previous implementation used in
        `LivestreamDownloader`:
        - If called from inside a running event loop, schedule with
        `create_task` on that loop.
        - If a `main_loop` is provided and running, schedule on it.
        - Otherwise, ensure a background loop and schedule there.

        Returns True if scheduling succeeded, False otherwise.
        """
        # Try current running loop
        with contextlib.suppress(RuntimeError):
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
            return True
        
        # Try main loop if provided
        if main_loop is not None and getattr(main_loop, "is_running", lambda: False)():
            try:
                asyncio.run_coroutine_threadsafe(coro, main_loop)
                return True
            except RuntimeError as e:
                if "closed" in str(e).lower():
                    logger.warning(f"Main loop is closed: {e}")
                else:
                    logger.warning(f"Failed to schedule on main loop: {e}")
        
        # Try background loop
        with cls._bg_loop_lock:
            bg_loop = getattr(cls, "_bg_loop", None)
            if bg_loop is None or not bg_loop.is_running():
                cls._start_bg_loop()

        bg_loop = getattr(cls, "_bg_loop", None)
        if bg_loop is not None:
            try:
                asyncio.run_coroutine_threadsafe(coro, bg_loop)
                return True
            except RuntimeError as e:
                if "closed" in str(e).lower():
                    logger.error(f"Background loop is closed, scheduling failed: {e}")
                    # Mark loop as dead so it gets restarted next time
                    with cls._bg_loop_lock:
                        cls._bg_loop = None
                        cls._bg_thread = None
                else:
                    logger.warning(f"Failed to schedule on background loop: {e}")
        
        return False
    
    @classmethod
    def stop_bg_loop(cls):
        """Stop the background event loop gracefully."""
        with cls._bg_loop_lock:
            bg_loop = getattr(cls, "_bg_loop", None)
            if bg_loop is None:
                return
            
            if bg_loop.is_running():
                try:
                    bg_loop.call_soon_threadsafe(bg_loop.stop)
                    logger.debug("Stopped background event loop")
                except RuntimeError as e:
                    logger.warning(f"Error stopping background loop: {e}")
            
            # Try to close the loop (may fail if thread still has it)
            try:
                # Schedule the actual close
                def _close_loop():
                    if not bg_loop.is_closed():
                        bg_loop.close()
                
                bg_loop.call_soon_threadsafe(_close_loop)
            except RuntimeError as e:
                logger.warning(f"Could not schedule loop close: {e}")
            
            cls._bg_loop = None
            cls._bg_thread = None
