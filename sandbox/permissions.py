import os
import builtins
from typing import Any, Callable
from .schemas import SandboxConfig


def make_guarded_open(config: SandboxConfig) -> Callable[..., Any]:
    """Create a guarded version of the built-in open function.

    Restricts file opening to specified allowed directories and blocks custom openers.

    Args:
        config: Sandbox configuration containing allowed directories.

    Returns:
        Callable[..., Any]: A guarded open function that enforces path restrictions.
    """
    def guarded_open(
        file: str | bytes | os.PathLike[Any],
        mode: str = "r",
        *args: Any,
        **kwargs: Any
    ) -> Any:
        """Open a file after validating that its path resides within allowed directories.

        Args:
            file: Path-like object or descriptor of the file to open.
            mode: Mode in which the file is opened. Defaults to 'r'.
            *args: Additional positional arguments forwarded to builtins.open.
            **kwargs: Additional keyword arguments forwarded to builtins.open.

        Returns:
            Any: The opened file object.

        Raises:
            PermissionError: If the path is outside allowed directories or a custom opener is passed.
        """
        requested_path = os.fspath(file)
        resolved_path = os.path.realpath(requested_path)

        allowed = False

        for directory in config.allowed_directories:
            allowed_directory = os.path.realpath(directory)

            try:
                if os.path.commonpath(
                    [resolved_path, allowed_directory]
                ) == allowed_directory:
                    allowed = True
                    break
            except ValueError:
                continue

        if not allowed:
            raise PermissionError(
                f"Access denied: '{resolved_path}' is outside allowed directories"
            )

        if kwargs.get("opener") is not None:
            raise PermissionError("Custom file openers are not allowed")

        return builtins.open(file, mode, *args, **kwargs)

    return guarded_open
