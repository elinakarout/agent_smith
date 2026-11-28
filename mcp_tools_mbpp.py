import argparse
import json
import os
import subprocess
import sys
import tempfile
from typing import Optional

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("MBPP Tools")

task: Optional[dict] = None
SOLUTION_PATH = "/tmp/agent/solution.py"
TEST_TIMEOUT = 10
MAX_OUTPUT_CHARS = 1000

_HARNESS = r'''
import sys, json, traceback
imports, code, tests = json.loads(sys.stdin.read())
ns = {}
try:
    exec("\n".join(imports), ns)
    exec(compile(code, "<solution>", "exec"), ns)
except BaseException:
    print("LOAD_ERROR: the solution code failed before any test ran")
    traceback.print_exc(file=sys.stdout)
    sys.exit(0)
passed = 0
for i, t in enumerate(tests, 1):
    try:
        exec(t, ns)
        passed += 1
    except AssertionError:
        print(f"FAIL test {i}: {t}")
    except BaseException as e:
        print(f"ERROR test {i}: {t}\n    {type(e).__name__}: {e}")
print(f"RESULT {passed}/{len(tests)} tests passed")
'''


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return (
        f"{text[:half]}\n\n[TRUNCATED: {len(text) - limit} characters omitted]\n\n"
        f"{text[-half:]}"
    )


@mcp.tool()
def run_tests() -> str:
    """Run the task's tests against the solution saved at /tmp/agent/solution.py.

    Save your function there first. Returns the pass count, or which tests
    failed and why.
    """
    if task is None:
        return "Error: no MBPP task loaded (the server was started without a task file)"

    try:
        with open(SOLUTION_PATH, encoding="utf-8") as f:
            code = f.read()
    except FileNotFoundError:
        return (
            f"Error: no solution found at {SOLUTION_PATH}. Save your function "
            f"there first, e.g. open('{SOLUTION_PATH}', 'w').write(code)."
        )
    if not code.strip():
        return f"Error: {SOLUTION_PATH} is empty"

    payload = json.dumps(
        [task.get("test_imports", []), code, task.get("test_list", [])]
    )

    with tempfile.TemporaryDirectory() as tmp:
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-c", _HARNESS],
                input=payload,
                capture_output=True,
                text=True,
                timeout=TEST_TIMEOUT,
                cwd=tmp,
            )
        except subprocess.TimeoutExpired:
            return (
                f"[TIMEOUT: tests exceeded {TEST_TIMEOUT}s and were killed. "
                f"Likely an infinite loop or very slow algorithm.]"
            )

    out = proc.stdout
    if proc.stderr:
        out += "\n--- stderr ---\n" + proc.stderr
    if not out.strip():
        out = f"No output from test runner (exit code {proc.returncode})."
    return _truncate(out)


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _load_task(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data.get("test_list"), list):
        raise ValueError("task file has no 'test_list'")
    return data


def main() -> None:
    global task

    parser = argparse.ArgumentParser(description="MBPP MCP tools (stdio server)")
    parser.add_argument(
        "--task-file",
        default=None,
        help="Path to the MBPP task JSON (test_imports, test_list)",
    )
    args, _ = parser.parse_known_args()

    os.makedirs(os.path.dirname(SOLUTION_PATH), exist_ok=True)

    if args.task_file:
        try:
            task = _load_task(args.task_file)
        except (OSError, ValueError) as e:
            _log(f"Error: cannot load task file {args.task_file!r}: {e}")
            sys.exit(1)
    else:
        _log("No --task-file given: run_tests() will return an error.")

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
