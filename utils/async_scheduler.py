import asyncio
import contextlib
import threading
import time


class AsyncScheduler:
    """Utility for scheduling coroutines from non-async contexts.

    Provides a background event loop and thread, and a helper to schedule
    coroutines safely whether called from inside an event loop or from a
    synchronous thread.
    """

    _bg_loop = None
    _bg_thread = None
    _bg_loop_lock = threading.Lock()

    @classmethod
    def _start_bg_loop(cls):
        bg_loop = getattr(cls, "_bg_loop", None)
        if bg_loop is not None and bg_loop.is_running():
            return

        def _run_loop():
            cls._bg_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(cls._bg_loop)
            cls._bg_loop.run_forever()

        t = threading.Thread(target=_run_loop, daemon=True)
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
        with contextlib.suppress(RuntimeError):
            loop = asyncio.get_running_loop()
            loop.create_task(coro)
            return True
        if main_loop is not None and getattr(main_loop, "is_running", lambda: False)():
            with contextlib.suppress(Exception):
                asyncio.run_coroutine_threadsafe(coro, main_loop)
                return True
        with cls._bg_loop_lock:
            bg_loop = getattr(cls, "_bg_loop", None)
            if bg_loop is None or not bg_loop.is_running():
                cls._start_bg_loop()

        bg_loop = getattr(cls, "_bg_loop", None)
        if bg_loop is not None:
            with contextlib.suppress(Exception):
                asyncio.run_coroutine_threadsafe(coro, bg_loop)
                return True
        return False
