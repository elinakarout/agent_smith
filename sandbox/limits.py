import resource
from types import FrameType
from typing import Any, NoReturn
from .schemas import SandboxConfig


def timeout_handler(signum: int, frame: FrameType | Any | None) -> NoReturn:
    """Signal handler for execution timeout.

    Args:
        signum: The signal number intercepted (e.g. SIGALRM).
        frame: The current stack frame, or None.

    Raises:
        TimeoutError: Always raised when execution duration exceeds the allowed limit.
    """
    raise TimeoutError("Execution exceeded the maximum allowed time.")


def set_memory_limit(config: SandboxConfig) -> None:
    """Set the process address space limit (RLIMIT_AS) based on configuration.

    Args:
        config: Sandbox configuration specifying the memory limit in megabytes.
    """
    memory_limit = config.max_memory_mb * 1024 * 1024
    resource.setrlimit(
        resource.RLIMIT_AS,
        (memory_limit, memory_limit)
    )
