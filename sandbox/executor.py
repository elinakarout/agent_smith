import io
import signal
import multiprocessing as mp
from multiprocessing.connection import Connection
from contextlib import redirect_stdout, redirect_stderr
from schemas import SandboxConfig, ExecutionResult, ExecutionStatus
from security import validate_code, build_execution_environment
from limits import timeout_handler, set_memory_limit


def run_code(code: str, execution_globals: dict) -> tuple:
    try:
        exec(code, execution_globals)
        status = ExecutionStatus.SUCCESS
        message = None

    except ImportError as e:
        status = ExecutionStatus.SECURITY_VIOLATION
        message = str(e)

    except TimeoutError:
        status = ExecutionStatus.TIMEOUT
        message = "Execution exceeded the maximum allowed time."

    except MemoryError:
        status = ExecutionStatus.MEMORY_LIMIT_EXCEEDED
        message = "Memory limit exceeded"

    except SystemExit as e:
        status = ExecutionStatus.EXCEPTION
        message = f"SystemExit: {e.code}"

    except Exception as e:
        status = ExecutionStatus.EXCEPTION
        message = str(e)

    return status, message


def worker(
    connection: Connection,
    code: str,
    config: SandboxConfig
) -> None:
    execution_globals = build_execution_environment(config)
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(config.max_execution_time_seconds)
    set_memory_limit(config)
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        try:
            status, message = run_code(code, execution_globals)
        finally:
            signal.alarm(0)
    
    stdout = stdout_buffer.getvalue()
    stderr = stderr_buffer.getvalue()
    answer = ExecutionResult(
        stdout=stdout,
        stderr=stderr,
        status_code=status,
        error_message=message
    )
    connection.send(answer)
    connection.close()


class SandboxExecutor():
    def __init__(self, config: SandboxConfig):
        self.config = config
    
    def execute_code(self, code: str):
        result = validate_code(self.config, code)
        if result:
            return result
        parent, child = mp.Pipe()
        process = mp.Process(
            target=worker,
            args=(child, code, self.config)
        )
        process.start()
        child.close()
        process.join()
        if process.is_alive():
            process.kill()
            process.join()
            parent.close()
            return ExecutionResult(
                status_code=ExecutionStatus.TIMEOUT,
                error_message="Execution exceeded the maximum allowed time."
            )
        result = parent.recv()
        parent.close()
        return result


