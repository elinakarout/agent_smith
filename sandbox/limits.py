import resource
from schemas import SandboxConfig


def timeout_handler(signum, frame):
    raise TimeoutError("Execution exceeded the maximum allowed time.")


def set_memory_limit(config: SandboxConfig) -> None:
    memory_limit = config.max_memory_mb * 1024 * 1024
    resource.setrlimit(
        resource.RLIMIT_AS,
        (memory_limit, memory_limit)
    )
