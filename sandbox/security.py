import ast
from schemas import SandboxConfig, ExecutionResult, ExecutionStatus


def build_execution_environment(config: SandboxConfig) -> dict:
    original_import = __import__
    
    def restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name not in config.authorized_imports:
            raise ImportError(f"Unauthorized import: {name}")
        return original_import(name, globals, locals, fromlist, level)

    execution_builtins = (
        __builtins__.copy()
        if isinstance(__builtins__, dict)
        else vars(__builtins__).copy()
    )
    execution_builtins["__import__"] = restricted_import
    execution_globals = {"__builtins__": execution_builtins}
    return execution_globals


def check_imports(tree: ast.Module) -> list[str]:
    imports = []
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
    try:
        tree = ast.parse(code)
        imports = check_imports(tree)
        for module in imports:
            if module not in config.authorized_imports:
                return ExecutionResult(
                    status_code=ExecutionStatus.SECURITY_VIOLATION,
                    error_message=f"Unauthorized import: {module}"
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
