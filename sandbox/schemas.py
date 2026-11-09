from typing import List, Optional, Any
from enum import Enum
from pydantic import BaseModel, Field


class SandboxConfig(BaseModel):
    """
    Sandbox configuration for student solutions.
    Uses allowlist approach: only imports in authorized_imports are allowed.
    Everything else is blocked by default.
    """
    authorized_imports: List[str] = Field(
        default_factory=lambda: [
            "math", "math.*",
            "collections", "collections.*",
            "itertools", "re", "json",
            "typing", "typing.*",
            "functools", "operator",
            "heapq", "bisect", "copy",
            "string", "random",
            "datetime", "datetime.*",
            "array", "cmath"
    ])
    allowed_directories: List[str] = Field(
        default_factory=lambda: [
            "/testbed", "/tmp/agent"
    ])
    max_execution_time_seconds: int = 30
    max_memory_mb: int = 512


class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    EXCEPTION = "exception"
    TIMEOUT = "timeout"
    MEMORY_LIMIT_EXCEEDED = "memory_limit_exceeded"
    SECURITY_VIOLATION = "security_violation"


class ExecutionResult(BaseModel):
    stdout: str = ""
    stderr: str = ""
    status_code: ExecutionStatus
    result: Optional[Any] = None
    final_answer: Optional[Any] = None
    error_message: Optional[str] = None
