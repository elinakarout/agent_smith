import ast
import builtins
from typing import Any
from .final_answer import final_answer
from .permissions import make_guarded_open
from .schemas import ExecutionResult, ExecutionStatus, SandboxConfig
from .security_globals import DANGEROUS_ATTRIBUTES, EXECUTION_BUILTINS


def build_execution_environment(config: SandboxConfig) -> dict[str, Any]:
    """Construct a restricted global execution environment for sandboxed code.

    Args:
        config: Sandbox configuration with import allowlists and file permissions.

    Returns:
        dict[str, Any]: Dictionary of global variables and safe built-ins for execution.
    """
    original_import = builtins.__import__

    def is_authorized(name: str) -> bool:
        """Check if a module name matches any authorized import patterns.

        Args:
            name: Module name to check.

        Returns:
            bool: True if authorized, False otherwise.
        """
        for pattern in config.authorized_imports:
            if pattern == name:
                return True
            if pattern.endswith(".*"):
                prefix = pattern[:-2]
                if name == prefix or name.startswith(prefix + "."):
                    return True
            elif pattern.endswith("*"):
                prefix = pattern[:-1]
                if name.startswith(prefix):
                    return True
        return False

    def restricted_import(
        name: str,
        globals: dict[str, Any] | None = None,
        locals: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] | list[str] = (),
        level: int = 0
    ) -> Any:
        """Import a module only if it is authorized by the sandbox configuration.

        Args:
            name: Name of module to import.
            globals: Global execution context.
            locals: Local execution context.
            fromlist: Objects or submodules to import from the module.
            level: Relative import level (0 for absolute).

        Returns:
            Any: The imported module object.

        Raises:
            ImportError: If the module is not authorized.
        """
        base_name = name.split(".")[0]
        if not is_authorized(name) and not is_authorized(base_name):
            raise ImportError(f"Unauthorized import: {name}")
        return original_import(name, globals, locals, fromlist, level)

    execution_builtins = EXECUTION_BUILTINS.copy()
    execution_builtins["__import__"] = restricted_import
    execution_globals: dict[str, Any] = {
        "__builtins__": execution_builtins,
        "__name__": "__sandbox__",
        "open": make_guarded_open(config),
        "final_answer": final_answer
    }
    return execution_globals


def check_dunder_attributes(tree: ast.Module) -> str | None:
    """Inspect AST for unauthorized dunder attribute access or restricted names.

    Args:
        tree: Parsed AST module to inspect.

    Returns:
        str | None: Error message if restricted access is found, or None if safe.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                return (
                    f"Dunder attribute access is not allowed: {node.attr}"
                )

        elif isinstance(node, ast.Name):
            if node.id in {
                "__builtins__",
                "__loader__",
                "__spec__",
                "__package__",
            }:
                return (
                    f"Access to restricted name is not allowed: {node.id}"
                )
    return None


def check_imports(tree: ast.Module) -> list[str]:
    """Extract all base imported module names from an AST tree.

    Args:
        tree: Parsed AST module to inspect.

    Returns:
        list[str]: Unique base module names imported in the code.
    """
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                base_module = alias.name.split('.')[0]
                if base_module not in imports:
                    imports.append(base_module)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                base_module = node.module.split('.')[0]
                if base_module not in imports:
                    imports.append(base_module)
    return imports


def validate_code(config: SandboxConfig, code: str) -> ExecutionResult | None:
    """Validate Python code syntax and safety before execution.

    Args:
        config: Sandbox configuration.
        code: Python source code string to validate.

    Returns:
        ExecutionResult | None: An error result if validation fails, or None if valid.
    """
    try:
        tree = ast.parse(code)
        error_message = check_dunder_attributes(tree)
        if error_message:
            return ExecutionResult(
                status_code=ExecutionStatus.SECURITY_VIOLATION,
                error_message=error_message
            )
        return None
    except SyntaxError as e:
        return ExecutionResult(
            status_code=ExecutionStatus.EXCEPTION,
            error_message=f"Syntax error: {e}"
        )
    except ValueError as e:
        return ExecutionResult(
            status_code=ExecutionStatus.EXCEPTION,
            error_message=f"Value error: {e}"
        )
    except TypeError as e:
        return ExecutionResult(
            status_code=ExecutionStatus.EXCEPTION,
            error_message=f"TypeError error: {e}"
        )
