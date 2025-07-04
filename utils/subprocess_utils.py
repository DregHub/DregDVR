import asyncio
import os
import traceback
from utils.logging_utils import LogManager


async def run_subprocess(command_str, log_file, called_process_error_msg, exception_msg, work_dir=None):
    "Run a subprocess command and log the output."
    LogManager.log_message(f"Running command: {' '.join(command_str)}", log_file)
    MiniLog = []
    try:
        # Set environment variable to force unbuffered output
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        # Use subprocess with unbuffered output
        process = await asyncio.create_subprocess_shell(
            " ".join(command_str),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=work_dir,
        )

        # Read stdout and stderr line by line in real-time
        async def read_stream(stream, log_file):
            while True:
                try:
                    line = await stream.readline()
                except (asyncio.LimitOverrunError, ValueError):
                    # Read a chunk if line is too long or separator not found
                    line = await stream.read(4096)
                if line:
                    LogManager.log_message(line.decode(errors="replace").strip(), log_file)
                    MiniLog.append(line.decode(errors="replace").strip())
                    # Keep only the last 20 lines
                    if len(MiniLog) > 20:
                        MiniLog.pop(0)
                else:
                    break

        await asyncio.gather(
            read_stream(process.stdout, log_file),
            read_stream(process.stderr, log_file),
        )

        # Wait for the process to complete
        await process.wait()

        # Check if the process exited with a non-zero status
        if process.returncode != 0:
            LogManager.log_message(f"{called_process_error_msg} : {process.returncode}", log_file)
        return MiniLog
    except Exception as e:
        LogManager.log_message(f"{exception_msg} : {e}\n{traceback.format_exc()} ", log_file)
        return MiniLog
