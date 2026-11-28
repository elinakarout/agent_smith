import ast
import json
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, Optional, Tuple


def _parse_value(text: str) -> Any:
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except Exception:
        return text


def _dict_to_python_call(func_name: str, arguments: Dict[str, Any]) -> str:
    kwargs_str = ", ".join(
        f"{k}={repr(v)}" for k, v in arguments.items()
    )
    if func_name == "final_answer":
        return f"final_answer({kwargs_str})"

    return f"result = {func_name}({kwargs_str})\nprint(result)"


def _validate_syntax(code: str, warning: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    try:
        ast.parse(code)
        return code, warning
    except SyntaxError as e:
        return (None, f"[System Error: SyntaxError at line {e.lineno}: {e.msg}]")


def _extract_candidate_assignment(code: str) -> Optional[str]:
    """
    Extract the actual Python implementation from:

    candidate_code = '''
    def my_function():
        ...
    '''

    The assignment is parsed using AST, so arbitrary expressions
    are never evaluated.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        else:
            targets = [node.target]
            value = node.value
        is_candidate = any(isinstance(target, ast.Name) and target.id == "candidate_code" for target in targets)

        if not is_candidate or value is None:
            continue

        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            implementation = value.value.strip()
            if implementation:
                return implementation
    return None


def _remove_test_harness(code: str) -> str:
    """
    Remove top-level test-harness statements while preserving
    function definitions, classes, imports and assignments.

    This is a fallback for code blocks that contain a mixture
    of implementation and test execution.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code
    preserved = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            preserved.append(node)
        elif isinstance(node, ast.ClassDef):
            preserved.append(node)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            preserved.append(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            if not any(
                isinstance(target, ast.Name)
                and target.id == "candidate_code"
                for target in (
                    node.targets if isinstance(node, ast.Assign)
                    else [node.target]
                )
            ):
                preserved.append(node)

    if not preserved:
        return code
    return ast.unparse(ast.Module(body=preserved, type_ignores=[]))


def _extract_python(llm_output: str) -> Optional[str]:
    """
    Extract Python from Markdown or an unfenced response.
    """
    blocks = re.findall(
        r"```(?:python|py)?[ \t]*\r?\n(.*?)```",
        llm_output,
        re.DOTALL | re.IGNORECASE
    )
    if blocks:
        return "\n\n".join(
            block.strip()
            for block in blocks
            if block.strip()
        )
    unclosed = re.search(
        r"```(?:python|py)?[ \t]*\r?\n(.*?)(?:```|<end_code>|$)",
        llm_output,
        re.DOTALL | re.IGNORECASE
    )
    if unclosed:
        return unclosed.group(1).strip()
    return llm_output.strip()


def extract_code(llm_output: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract executable Python implementation.

    Returns:
        (code, warning)
    """
    if not llm_output or not llm_output.strip():
        return (None, "[System Error: Empty LLM response.]")
    code = _extract_python(llm_output)
    if not code:
        return None, "[System Error: No Python code found.]"
    candidate = _extract_candidate_assignment(code)
    if candidate is not None:
        code = candidate
    else:
        code = _remove_test_harness(code)
    code = code.strip()
    if not code:
        return None, "[System Error: Extracted implementation is empty.]"
    return _validate_syntax(code)
