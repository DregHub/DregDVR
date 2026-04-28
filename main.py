import os
import sys
import traceback
import asyncio
import logging
import subprocess
import signal
from pathlib import Path
from utils.logging_utils import LogManager
from config.config_settings import DVR_Config
from utils.dependency_utils import DependencyManager
from utils.instance_manager import InstanceManager
from dvr_main import DVRMain
from utils.asyncio_lifecycle_manager import AsyncioLifecycleManager


# Configure logging to not show level and logger name
logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.info("Starting Dregg DVR")
_streamlit_process = None
_main_loop = None


async def graceful_async_shutdown():
    """Perform graceful async shutdown including database and loop cleanup."""
    global _main_loop
    try:
        # Call the lifecycle manager's graceful shutdown
        await AsyncioLifecycleManager.graceful_shutdown(timeout=10)
    except Exception as e:
        logging.error(f"Error during graceful async shutdown: {e}")
        import traceback as tb
        logging.error(tb.format_exc())


def signal_handler(signum, frame):
    """Handle termination signals gracefully."""
    global _streamlit_process, _main_loop

    # Stop Streamlit process
    if _streamlit_process and _streamlit_process.poll() is None:
        try:
            _streamlit_process.terminate()
            _streamlit_process.wait(timeout=10)
        except Exception as e:
            logging.error(f"Error terminating Streamlit: {e}")
            try:
                _streamlit_process.kill()
            except Exception:
                pass

    # Stop main event loop if running
    if _main_loop and _main_loop.is_running():
        try:
            _main_loop.call_soon_threadsafe(_main_loop.stop)
        except Exception as e:
            logging.warning(f"Error stopping main loop: {e}")

    sys.exit(0)


def create_required_dirs():
    """
    Create project, runtime and data profile directories and their subdirectories
    as defined in the configuration for all instances.
    """
    try:
        DVR_Config.Project_Root_Dir = os.path.dirname(os.path.abspath(__file__))

    except Exception as e:
        logging.error(
            f"Error creating required directories: {e}\n{traceback.format_exc()}"
        )
        raise


async def initialize_instances_async():
    """
    Asynchronously initialize all instances from the config.
    Returns the initialized instances or None if no instances exist.
    """
    try:
        initialized_instances = await InstanceManager.initialize_instances()

        if not initialized_instances:
            logging.info("Please create a DVR instance in the web interface.")
        return initialized_instances
    except Exception as e:
        logging.error(f"Error initializing instances: {e}\n{traceback.format_exc()}")
        raise


def start_streamlit_portal():
    """
    Start the Streamlit portal in a separate process using the official
    'python -m streamlit run' invocation recommended by Streamlit.

    NOTE: Uses logging instead of LogManager to avoid database access before event loop exists.
    """
    try:
        project_root = Path(__file__).parent
        ui_app_path = project_root / "ui" / "app.py"

        if not ui_app_path.exists():
            logging.error(f"Error: UI app not found at {ui_app_path}")
            return None

        os.chdir(project_root)
        cmd = [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(ui_app_path),
            "--server.headless=true",
            "--server.address=0.0.0.0",
            "--server.port=8501",
            "--server.enableCORS=false",
            "--server.enableXsrfProtection=false",
            "--logger.level=info",
        ]

        # IMPORTANT: Do NOT suppress output in Docker
        try:
            preexec_fn = os.setsid
        except AttributeError:
            preexec_fn = None
        process = subprocess.Popen(
            cmd,
            stdout=sys.stdout,
            stderr=sys.stderr,
            preexec_fn=preexec_fn,  # Process group for graceful termination
        )

        return process

    except Exception as e:
        logging.error(f"Error starting Streamlit portal: {e}\n{traceback.format_exc()}")
        return None


async def main():
    global _main_loop
    try:
        # Get the current event loop and register it with lifecycle manager
        _main_loop = asyncio.get_running_loop()
        try:
            AsyncioLifecycleManager.register_loop(_main_loop, loop_name="main_dvr_loop")
        except Exception as e:
            logging.error(f"Failed to register main loop: {e}")
            import traceback

            logging.error(traceback.format_exc())
            raise
        try:
            from db.dvr_db import DVRDB
            from db.log_db import LogDB

            await LogDB.get_global()
            await DVRDB.get_global()

        except Exception as e:
            logging.error(f"Error initializing database managers: {e}")
            import traceback as tb
            logging.error(tb.format_exc())
            raise

        try:
            await LogManager._ensure_database_schema()
        except Exception as e:
            logging.warning(f"Could not initialize logging database schema: {e}")

        create_required_dirs()
        initialized_instances = await initialize_instances_async()

        # Only start DVR tasks if there is at least 1 instance present
        if initialized_instances:
            dvr = DVRMain()
            result = await dvr.run_dvr()
        else:
            result = False
        return result

    except Exception as e:
        logging.error(f"Exception in main: {e}\n{traceback.format_exc()}")
        logging.error(f"FATAL ERROR: {e}\n{traceback.format_exc()}")
        return False
    finally:
        try:
            await graceful_async_shutdown()
        except Exception as e:
            logging.error(f"Error during shutdown: {e}")

        LogManager.flush_logs()
        LogManager.shutdown_logging()


if __name__ == "__main__":
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        project_root = Path(__file__).parent
        from config.config_settings import DVR_Config

        DVR_Config.Project_Root_Dir = str(project_root)
        DependencyManager.update_py_dependencies()
        _streamlit_process = start_streamlit_portal()

        tasks_started = asyncio.run(main())

        if not tasks_started:
            if _streamlit_process:
                try:
                    _streamlit_process.wait()
                except KeyboardInterrupt:
                    logging.info("Streamlit portal termination requested.")
                    _streamlit_process.terminate()
                    _streamlit_process.wait(timeout=5)
        else:
            if _streamlit_process and _streamlit_process.poll() is None:
                _streamlit_process.terminate()
                try:
                    _streamlit_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    _streamlit_process.kill()
                    _streamlit_process.wait()

    except KeyboardInterrupt:
        logging.info("Application interrupted by user.")
    except Exception as e:
        logging.error(f"Fatal error: {e}\n{traceback.format_exc()}")
    finally:
        if _streamlit_process and _streamlit_process.poll() is None:
            try:
                _streamlit_process.terminate()
                _streamlit_process.wait(timeout=5)
            except Exception:
                try:
                    _streamlit_process.kill()
                except Exception:
                    pass
