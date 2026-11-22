import io
import signal
import multiprocessing as mp
from .network_guard import block_network
from .tool_wrappers import build_tool_namespace 
from .final_answer import FinalAnswerSignal
from multiprocessing.connection import Connection
from .limits import timeout_handler, set_memory_limit
from contextlib import redirect_stdout, redirect_stderr
from .security import validate_code, build_execution_environment
from .schemas import SandboxConfig, ExecutionResult, ExecutionStatus


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
    config: SandboxConfig,
    tools: list
) -> None:
    control_signal = None
    block_network()
    execution_globals = build_execution_environment(config)
    tool_namespace = build_tool_namespace(tools, connection)
    execution_globals.update(tool_namespace)
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
    
    async def execute_code(self, code: str, session, tools):
        result = validate_code(self.config, code)
        if result:
            return result
        parent, child = mp.Pipe()
        process = mp.Process(
            target=worker,
            args=(child, code, self.config, tools)
        )
        process.start()
        child.close()

        while True:
            message = parent.recv()
            if isinstance(message, ExecutionResult):
                result = message
                break
            if message["type"] == "mcp_tool_call":
                tool_name = message["name"]
                arguments = message["arguments"]
                try:
                    result = await session.call_tool(tool_name, arguments)
                    parent.send({
                        "type": "mcp_tool_result",
                        "result": result.model_dump(mode="json")
                    })
                except Exception as e:
                    parent.send({
                        "type": "mcp_tool_error",
                        "error": str(e)
                    })
    
        parent.close()
        process.join()
        if result == "keyboard_interrupt":
            raise KeyboardInterrupt()

        if isinstance(result, tuple) and result[0] == "system_exit":
            raise SystemExit(result[1])

        return result
