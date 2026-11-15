import io
import signal
import multiprocessing as mp
from network_guard import block_network
from final_answer import FinalAnswerSignal
from multiprocessing.connection import Connection
from limits import timeout_handler, set_memory_limit
from contextlib import redirect_stdout, redirect_stderr
from security import validate_code, build_execution_environment
from schemas import SandboxConfig, ExecutionResult, ExecutionStatus


def run_code(code: str, execution_globals: dict) -> tuple:
    try:
        exec(code, execution_globals)
        status = ExecutionStatus.SUCCESS
        message = None

    except FinalAnswerSignal as e:
        raise FinalAnswerSignal(e)
    except ImportError as e:
        status = ExecutionStatus.SECURITY_VIOLATION
        message = str(e)
    
    except PermissionError as e:
        status = ExecutionStatus.SECURITY_VIOLATION
        message = str(e)

    except TimeoutError:
        status = ExecutionStatus.TIMEOUT
        message = "Execution exceeded the maximum allowed time."

    except MemoryError:
        status = ExecutionStatus.MEMORY_LIMIT_EXCEEDED
        message = "Memory limit exceeded"

    except Exception as e:
        status = ExecutionStatus.EXCEPTION
        message = str(e)

    return status, message


def worker(
    connection: Connection,
    code: str,
    config: SandboxConfig
) -> None:
    control_signal = None
    block_network()
    execution_globals = build_execution_environment(config)
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(config.max_execution_time_seconds)
    set_memory_limit(config)
    message = None
    final_answer = None
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        try:
            status, message = run_code(code, execution_globals)
        except FinalAnswerSignal as e:
            final_answer = str(e)
            status = ExecutionStatus.SUCCESS
        except KeyboardInterrupt:
            control_signal = "keyboard_interrupt"
        except SystemExit as e:
            control_signal = ("system_exit", e.code)
        finally:
            signal.alarm(0)
        if control_signal is not None:
            connection.send(control_signal)
            connection.close()
            return
    stdout = stdout_buffer.getvalue()
    stderr = stderr_buffer.getvalue()
    answer = ExecutionResult(
        stdout=stdout,
        stderr=stderr,
        status_code=status,
        final_answer=final_answer,
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
        if result == "keyboard_interrupt":
            raise KeyboardInterrupt()

        if isinstance(result, tuple) and result[0] == "system_exit":
            raise SystemExit(result[1])

        return result


