import io
import time
import types
import signal
import pickle
import asyncio
from typing import Any
import multiprocessing as mp
from collections.abc import Sequence
from .network_guard import block_network
from .final_answer import FinalAnswerSignal
from .tool_wrappers import build_tool_namespace
from multiprocessing.connection import Connection
from .limits import set_memory_limit, timeout_handler
from contextlib import redirect_stderr, redirect_stdout
from .security import build_execution_environment, validate_code
from .schemas import ExecutionResult, ExecutionStatus, SandboxConfig


def run_code(
    code: str,
    execution_globals: dict[str, Any]
) -> tuple[ExecutionStatus, str | None]:
    """Execute Python code within a restricted global environment.

    Args:
        code: Python source code string to execute.
        execution_globals: Global variable dictionary for the execution context.

    Returns:
        tuple[ExecutionStatus, str | None]: Status code and an error message if an exception was caught.

    Raises:
        FinalAnswerSignal: Propagated when final_answer() is called inside the sandbox.
    """
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


def worker_repl(
    connection: Connection,
    config: SandboxConfig,
    tools: Sequence[Any],
    initial_state: dict[str, Any] | None = None,
    initial_modules: dict[str, str] | None = None
) -> None:
    """Persistent worker for interactive REPL mode.

    Receives code blocks over the pipe in a loop, executes them in a shared
    namespace (preserving state between submissions), and sends back results.
    Exits when it receives None (shutdown sentinel) or a control signal.

    Args:
        connection: IPC connection to communicate with the host executor.
        config: Sandbox configuration parameters.
        tools: Collection of MCP tools available to the worker.
        initial_state: Optional dictionary of variables to restore into globals.
        initial_modules: Optional dictionary of module names to restore into globals.
    """
    block_network()
    execution_globals = build_execution_environment(config)
    tool_namespace = build_tool_namespace(tools, connection)
    execution_globals.update(tool_namespace)
    if initial_modules:
        for k, mod_name in initial_modules.items():
            try:
                execution_globals[k] = __import__(mod_name)
            except Exception:
                pass
    if initial_state:
        execution_globals.update(initial_state)
    set_memory_limit(config)

    while True:
        code = connection.recv()

        if code is None:
            break

        control_signal = None
        final_answer = None
        message = None
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(config.max_execution_time_seconds)

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
            break

        user_state = {}
        user_modules = {}
        for k, v in execution_globals.items():
            if not k.startswith("__") and k not in tool_namespace and k not in {"open", "final_answer"}:
                if isinstance(v, types.ModuleType):
                    user_modules[k] = v.__name__
                else:
                    try:
                        pickle.dumps(v)
                        user_state[k] = v
                    except Exception:
                        pass

        result = ExecutionResult(
            stdout=stdout_buffer.getvalue(),
            stderr=stderr_buffer.getvalue(),
            status_code=status,
            final_answer=final_answer,
            error_message=message,
            user_state=user_state,
            user_modules=user_modules
        )
        connection.send(result)

    connection.close()


def worker(
    connection: Connection,
    code: str,
    config: SandboxConfig,
    tools: Sequence[Any] | None
) -> None:
    """Worker process function for one-off sandbox code execution.

    Args:
        connection: IPC connection to communicate with the host executor.
        code: Python source code string to execute.
        config: Sandbox configuration parameters.
        tools: Collection of MCP tools available to the worker, or None.
    """
    control_signal = None
    block_network()
    execution_globals = build_execution_environment(config)
    tool_namespace = build_tool_namespace(tools or [], connection)
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


class SandboxExecutor:
    """Manages sandboxed execution environments for running untrusted Python code."""

    def __init__(self, config: SandboxConfig) -> None:
        """Initialize SandboxExecutor with configuration settings.

        Args:
            config: Sandbox configuration settings.
        """
        self.config: SandboxConfig = config
        self._repl_process: mp.Process | None = None
        self._repl_conn: Connection | None = None
        self._tools: Sequence[Any] = []
        self._latest_user_state: dict[str, Any] = {}
        self._latest_modules: dict[str, str] = {}

    def start_repl(
        self,
        tools: Sequence[Any] | None,
        initial_state: dict[str, Any] | None = None,
        initial_modules: dict[str, str] | None = None
    ) -> None:
        """Spawn the persistent REPL worker process.

        Args:
            tools: Collection of MCP tools to provide to the REPL, or None.
            initial_state: Optional dictionary of variables to seed into the REPL globals.
            initial_modules: Optional dictionary mapping variable names to module names to import.
        """
        self._tools = tools or []
        if initial_state is not None:
            self._latest_user_state = initial_state
        if initial_modules is not None:
            self._latest_modules = initial_modules

        parent, child = mp.Pipe()
        self._repl_conn = parent
        self._repl_process = mp.Process(
            target=worker_repl,
            args=(child, self.config, self._tools, self._latest_user_state, self._latest_modules)
        )
        self._repl_process.start()
        child.close()

    def stop_repl(self) -> None:
        """Gracefully shut down the REPL worker by sending the None sentinel."""
        if self._repl_conn:
            try:
                self._repl_conn.send(None)
            except Exception:
                pass
            self._repl_conn.close()
            self._repl_conn = None
        if self._repl_process:
            self._repl_process.join(timeout=1)
            if self._repl_process.is_alive():
                self._repl_process.kill()
            self._repl_process = None

    async def execute_repl(
        self,
        code: str,
        session: Any | None = None
    ) -> ExecutionResult:
        """Send one code block to the persistent REPL worker and return the result.

        State (variables, imports) is preserved across calls.
        Enforces Layer 1 subprocess timeout isolation: if the child process does not
        finish within max_execution_time_seconds, it is killed with SIGKILL.

        Args:
            code: Python source code string to execute.
            session: Optional MCP client session for handling tool calls.

        Returns:
            ExecutionResult: Result containing stdout, stderr, status code, and outputs.

        Raises:
            RuntimeError: If the REPL worker process is not running.
            KeyboardInterrupt: If execution was interrupted.
            SystemExit: If the executed code called exit() or sys.exit().
        """
        if self._repl_conn is None:
            raise RuntimeError("REPL worker is not running. Call start_repl() first.")

        validation_error = validate_code(self.config, code)
        if validation_error:
            return validation_error

        self._repl_conn.send(code)

        start_time = time.monotonic()
        timeout = float(self.config.max_execution_time_seconds)

        while True:
            elapsed = time.monotonic() - start_time
            remaining = max(0.05, timeout - elapsed)

            has_data = await asyncio.to_thread(self._repl_conn.poll, remaining)
            if not has_data:
                # Subprocess-level timeout enforcement (Layer 1 kill)
                if self._repl_process and self._repl_process.is_alive():
                    try:
                        self._repl_process.kill()
                        self._repl_process.join(timeout=1)
                    except Exception:
                        pass
                if self._repl_conn:
                    self._repl_conn.close()
                    self._repl_conn = None

                # Restart fresh worker for subsequent commands with preserved state
                self.start_repl(self._tools, initial_state=self._latest_user_state, initial_modules=self._latest_modules)

                return ExecutionResult(
                    stdout="",
                    stderr="",
                    status_code=ExecutionStatus.TIMEOUT,
                    error_message="Execution exceeded the maximum allowed time."
                )

            message = self._repl_conn.recv()

            if isinstance(message, ExecutionResult):
                if message.user_state:
                    self._latest_user_state.update(message.user_state)
                if message.user_modules:
                    self._latest_modules.update(message.user_modules)
                return message

            if message == "keyboard_interrupt":
                raise KeyboardInterrupt()

            if isinstance(message, tuple) and message[0] == "system_exit":
                raise SystemExit(message[1])

            # Forward MCP tool calls to the live session
            if isinstance(message, dict) and message.get("type") == "mcp_tool_call":
                tool_name = message["name"]
                arguments = message["arguments"]
                try:
                    tool_res = await session.call_tool(tool_name, arguments)
                    self._repl_conn.send({
                        "type": "mcp_tool_result",
                        "result": tool_res.model_dump(mode="json")
                    })
                except Exception as e:
                    self._repl_conn.send({
                        "type": "mcp_tool_error",
                        "error": str(e)
                    })
                start_time = time.monotonic() - elapsed
                continue

    async def execute_code(
        self,
        code: str,
        session: Any | None = None,
        tools: Sequence[Any] | None = None
    ) -> ExecutionResult:
        """Execute Python code in a fresh one-off sandboxed subprocess.

        Args:
            code: Python source code string to execute.
            session: Optional MCP client session for handling tool calls.
            tools: Optional collection of MCP tools to provide to the execution environment.

        Returns:
            ExecutionResult: Result containing stdout, stderr, and execution status.

        Raises:
            KeyboardInterrupt: If execution was interrupted.
            SystemExit: If the executed code called exit() or sys.exit().
        """
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
