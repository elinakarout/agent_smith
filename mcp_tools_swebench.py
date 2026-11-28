import re
from pathlib import PurePosixPath

from docker_manager.manager import DockerManager
from mcp.server.mcpserver import MCPServer

CONTAINER_TESTBED = "/testbed"

MAX_OUTPUT_LINES = 100
MAX_OUTPUT_CHARS = 8000
MAX_READ_LINES = 400  

COMMAND_TIMEOUT = 120
TESTS_TIMEOUT = 600

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_EDIT_SCRIPT = r"""
import sys
path, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path, encoding="utf-8") as f:
    content = f.read()
count = content.count(old)
if count == 0:
    print("NOT_FOUND"); sys.exit(2)
if count > 1:
    print(f"AMBIGUOUS:{count}"); sys.exit(3)
updated = content.replace(old, new, 1)
with open(path, "w", encoding="utf-8") as f:
    f.write(updated)
if path.endswith(".py"):
    try:
        compile(updated, path, "exec")
    except SyntaxError as e:
        print(f"SYNTAX_ERROR:line {e.lineno}: {e.msg}"); sys.exit(4)
print("OK")
"""

_REFS_SCRIPT = r"""
import ast, os, sys
name, anchor, anchor_line = sys.argv[1], sys.argv[2], int(sys.argv[3])
try:
    with open(anchor, encoding="utf-8") as f:
        anchor_lines = f.read().splitlines()
except Exception as e:
    print(f"Error: cannot read {anchor}: {e}"); sys.exit(5)
if anchor_line > len(anchor_lines) or name not in anchor_lines[anchor_line - 1]:
    print(f"Error: {name!r} does not appear on line {anchor_line} of {anchor}. "
          f"Check the line number with read_file or "
          f"search_function_or_class_definition_in_code.")
    sys.exit(5)
SKIP = {".git", ".venv", "__pycache__", "node_modules", ".tox", "build", "dist"}
found = []
for root, dirs, files in os.walk("/testbed"):
    dirs[:] = [d for d in dirs if d not in SKIP]
    for fn in files:
        if not fn.endswith(".py"):
            continue
        path = os.path.join(root, fn)
        try:
            with open(path, encoding="utf-8") as f:
                src = f.read()
            tree = ast.parse(src)
        except Exception:
            continue
        src_lines = src.splitlines()
        hit_lines = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == name:
                hit_lines.add(node.lineno)
            elif isinstance(node, ast.Attribute) and node.attr == name:
                hit_lines.add(node.end_lineno)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
                hit_lines.add(node.lineno)
            elif isinstance(node, ast.arg) and node.arg == name:
                hit_lines.add(node.lineno)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    if name in (a.name.split(".")[-1], a.asname):
                        hit_lines.add(node.lineno)
        for ln in hit_lines:
            found.append((path, ln, src_lines[ln - 1].strip()[:200]))
found.sort(key=lambda r: (r[0] != anchor, r[0], r[1]))
for path, ln, text in found:
    print(f"{path}:{ln} {text}")
"""

mcp = MCPServer("MCP Server")

docker_manager = None
eval_script = None


def configure_swebench(image, task_eval_script, testbed_path=None):
    global docker_manager, eval_script

    if not testbed_path:
        raise ValueError("testbed_path is required")

    docker_manager = DockerManager(
        image=image,
        working_dir=CONTAINER_TESTBED,
    )

    eval_script = task_eval_script

    docker_manager.pull_image()
    docker_manager.start()


def stop_swebench():
    global docker_manager

    if docker_manager is not None:
        docker_manager.stop()
        docker_manager = None


def _ensure_container():
    if docker_manager is None or docker_manager.container is None:
        raise RuntimeError("Docker environment not initialized")


def validate_container_path(filepath, must_exist=False):
    """
    Validate a path inside /testbed.

    Paths are interpreted relative to /testbed unless absolute.
    Symlink resolution is also checked inside Docker.
    """
    if not isinstance(filepath, str) or not filepath:
        raise ValueError("Invalid filepath")

    path = PurePosixPath(filepath)

    if ".." in path.parts:
        raise PermissionError("Path traversal detected")

    if path.is_absolute():
        candidate = path
    else:
        candidate = PurePosixPath(CONTAINER_TESTBED) / path

    normalized = str(candidate)

    if not candidate.is_relative_to(PurePosixPath(CONTAINER_TESTBED)):
        raise PermissionError("Access denied")

    _ensure_container()

    result = docker_manager.container.exec_run(
        [
            "python3",
            "-c",
            (
                "import os,sys;"
                "p=os.path.realpath(sys.argv[1]);"
                "root=os.path.realpath('/testbed');"
                "sys.exit(0 if os.path.commonpath([p,root]) == root else 1);"
            ),
            normalized,
        ],
        workdir=CONTAINER_TESTBED,
    )

    if result.exit_code != 0:
        raise PermissionError("Path escapes the repository")

    if must_exist:
        result = docker_manager.container.exec_run(
            ["test", "-e", normalized],
            workdir=CONTAINER_TESTBED,
        )

        if result.exit_code != 0:
            raise FileNotFoundError(normalized)

    return normalized


def docker_exec(command, workdir=CONTAINER_TESTBED, timeout=COMMAND_TIMEOUT):
    """
    Execute a command inside the Docker container.

    command must be an argument list, not a shell string.
    """
    _ensure_container()

    workdir = validate_container_path(workdir, must_exist=True)

    if not isinstance(command, list) or not command:
        raise ValueError("Invalid command")

    result = docker_manager.container.exec_run(
        ["timeout", "--signal=TERM", f"{timeout}s", *command],
        workdir=workdir,
        demux=True,
    )

    stdout, stderr = result.output

    return {
        "exit_code": result.exit_code,
        "stdout": stdout.decode(errors="replace") if stdout else "",
        "stderr": stderr.decode(errors="replace") if stderr else "",
        "timed_out": result.exit_code == 124,
    }


def _truncate_lines(lines, hint, limit=MAX_OUTPUT_LINES):
    if len(lines) <= limit:
        return "\n".join(lines)
    shown = "\n".join(lines[:limit])
    return f"{shown}\n\n[TRUNCATED: showing {limit} of {len(lines)} lines. {hint}]"


def _truncate_text(text, limit=MAX_OUTPUT_CHARS):
    """Keep head and tail of long text; the end usually holds the summary."""
    if len(text) <= limit:
        return text
    half = limit // 2
    omitted = len(text) - limit
    return (
        f"{text[:half]}\n\n"
        f"[TRUNCATED: {omitted} characters omitted from the middle]\n\n"
        f"{text[-half:]}"
    )


def _format_exec(result, timeout_note):
    parts = []
    if result["timed_out"]:
        parts.append(f"[TIMEOUT: {timeout_note}. Output below is partial.]")
    parts.append(f"exit_code: {result['exit_code']}")
    if result["stdout"]:
        parts.append("--- stdout ---\n" + _truncate_text(result["stdout"]))
    if result["stderr"]:
        parts.append("--- stderr ---\n" + _truncate_text(result["stderr"]))
    return "\n".join(parts)


_LOC_RE = re.compile(r"^(.+?:\d+):")


def _spec_format(line):
    """'path:12:code' -> 'path:12 code' (the format the subject specifies)."""
    return _LOC_RE.sub(r"\1 ", line, count=1)


def _git_grep(flags, pattern, file_pattern, empty_message):
    """Run git grep in /testbed and return '/abs/path:line content' lines."""
    result = docker_exec(
        ["git", "grep", "-n", "--untracked", *flags, "-e", pattern, "--", file_pattern],
        workdir=CONTAINER_TESTBED,
    )

    if result["exit_code"] == 1:
        return empty_message

    if result["exit_code"] != 0:
        return f"Error: git grep failed: {result['stderr'].strip()}"

    lines = [
        _spec_format(f"{CONTAINER_TESTBED}/{line}")
        for line in result["stdout"].splitlines()
    ]
    return _truncate_lines(lines, "Narrow the pattern or file_pattern.")


@mcp.tool()
def read_file(filepath, start_line, end_line):
    """Read a file with line numbers ('N: content'). Shows at most 400 lines per call."""
    try:
        start_line = int(start_line)
        end_line = int(end_line)
    except (TypeError, ValueError):
        return "Error: start_line and end_line must be integers"

    if start_line < 1:
        return "Error: start_line must be at least 1"
    if end_line < start_line:
        return "Error: end_line cannot be less than start_line"

    capped_end = min(end_line, start_line + MAX_READ_LINES - 1)

    try:
        filepath = validate_container_path(filepath, must_exist=True)

        result = docker_exec([
            "awk",
            f'NR >= {start_line} && NR <= {capped_end} '
            '{printf "%d: %s\\n", NR, $0}',
            filepath,
        ])

        if result["exit_code"] != 0:
            return f"Error reading file: {result['stderr'].strip()}"

        if not result["stdout"]:
            return f"No lines in range {start_line}-{end_line} (file is shorter)."

        out = result["stdout"]
        if capped_end < end_line:
            out += (
                f"\n[TRUNCATED: showing at most {MAX_READ_LINES} lines. "
                f"Call again with start_line={capped_end + 1} to continue.]"
            )
        return out

    except Exception as e:
        return f"Error reading file: {e}"


@mcp.tool()
def edit_file(filepath, old_str, new_str):
    """Replace one exact occurrence of old_str with new_str in a file."""
    try:
        if not old_str:
            return "Error: old_str cannot be empty"

        filepath = validate_container_path(filepath, must_exist=True)

        result = docker_exec(
            ["python3", "-c", _EDIT_SCRIPT, filepath, old_str, new_str]
        )
        out = result["stdout"].strip()

        if result["exit_code"] == 0:
            return "File edited successfully"
        if out == "NOT_FOUND":
            return (
                "Error: old_str not found in file. Re-read the file and copy "
                "the text exactly, including whitespace."
            )
        if out.startswith("AMBIGUOUS"):
            n = out.split(":")[1]
            return (
                f"Error: old_str matches {n} places. Include more surrounding "
                f"lines so it is unique. No change was made."
            )
        if out.startswith("SYNTAX_ERROR"):
            return (
                f"Edit applied, but the file now has a syntax error "
                f"({out[len('SYNTAX_ERROR:'):]}). "
                f"Re-read the file around that line and fix it."
            )
        return f"Error editing file: {result['stderr'] or out}"

    except Exception as e:
        return f"Error editing file: {e}"


@mcp.tool()
def list_files(directory, pattern="*"):
    """List files under a directory matching a name pattern."""
    try:
        directory = validate_container_path(directory, must_exist=True)

        result = docker_exec([
            "find", directory, "-type", "f", "-name", pattern or "*",
            "-not", "-path", "*/.git/*",
            "-not", "-path", "*/.venv/*",
            "-not", "-path", "*/__pycache__/*",
            "-not", "-path", "*/node_modules/*",
            "-not", "-path", "*/.tox/*",
            "-not", "-path", "*/build/*",
            "-not", "-path", "*/dist/*",
        ])

        if result["exit_code"] != 0:
            return f"Error listing files: {result['stderr'].strip()}"

        lines = result["stdout"].splitlines()
        if not lines:
            return f"No files matching {pattern!r} under {directory}."
        return _truncate_lines(lines, "Use a narrower directory or pattern.")

    except Exception as e:
        return f"Error listing files: {e}"


@mcp.tool()
def search_code(pattern, file_pattern="*.py"):
    """grep-like regex search. Output: /abs/path:line content"""
    try:
        if not isinstance(pattern, str) or not pattern:
            return "Error: pattern cannot be empty"
        file_pattern = file_pattern or "*"
        return _git_grep(
            ["-E"], pattern, file_pattern,
            f"No matches for {pattern!r} in files matching {file_pattern!r}.",
        )
    except Exception as e:
        return f"Error searching code: {e}"


@mcp.tool()
def search_function_or_class_definition_in_code(name):
    """Find where a function or class is defined. Output: /abs/path:line content"""
    try:
        if not isinstance(name, str) or not IDENTIFIER_RE.match(name):
            return "Error: name must be a plain identifier (letters, digits, underscore)"

        pattern = (
            rf"^[[:space:]]*(async[[:space:]]+)?def[[:space:]]+{name}[[:space:]]*\("
            rf"|^[[:space:]]*class[[:space:]]+{name}([^[:alnum:]_]|$)"
        )
        return _git_grep(
            ["-E"], pattern, "*.py",
            f"No definition of function or class {name!r} found.",
        )
    except Exception as e:
        return f"Error searching definitions: {e}"


@mcp.tool()
def find_references(name, filepath, line):
    """Find code usages of the symbol `name` located at filepath:line.

    Output: /abs/path:line content (the file you pass is listed first).
    """
    try:
        if not isinstance(name, str) or not IDENTIFIER_RE.match(name):
            return "Error: name must be a plain identifier (letters, digits, underscore)"

        try:
            line = int(line)
        except (TypeError, ValueError):
            return "Error: line must be an integer"
        if line < 1:
            return "Error: line must be at least 1"

        filepath = validate_container_path(filepath, must_exist=True)

        result = docker_exec(
            ["python3", "-c", _REFS_SCRIPT, name, filepath, str(line)],
            timeout=60,
        )

        if result["exit_code"] == 5:
            return result["stdout"].strip()
        if result["exit_code"] != 0:
            return f"Error finding references: {result['stderr'].strip()}"

        lines = result["stdout"].splitlines()
        if not lines:
            return f"No references to {name!r} found."
        return _truncate_lines(lines, "Pass a more specific symbol or check usages with search_code.")

    except Exception as e:
        return f"Error finding references: {e}"


@mcp.tool()
def run_command(command, workdir=CONTAINER_TESTBED):
    """Run a shell command. Returns exit code, stdout and stderr as text."""
    try:
        workdir = validate_container_path(workdir, must_exist=True)

        if not isinstance(command, str) or not command.strip():
            return "Error: command must be a non-empty string"

        result = docker_exec(
            ["bash", "-lc", command], workdir=workdir, timeout=COMMAND_TIMEOUT
        )
        return _format_exec(
            result, f"command exceeded {COMMAND_TIMEOUT}s and was killed"
        )

    except Exception as e:
        return f"Error executing command: {e}"


@mcp.tool()
def run_tests():
    """Run the task's evaluation script. Returns exit code, stdout and stderr as text."""
    if not eval_script:
        return "Error: evaluation script not configured"

    try:
        result = docker_exec(
            ["bash", "-lc", eval_script],
            workdir=CONTAINER_TESTBED,
            timeout=TESTS_TIMEOUT,
        )
        return _format_exec(
            result, f"tests exceeded {TESTS_TIMEOUT}s and were killed"
        )

    except Exception as e:
        return f"Error executing tests: {e}"


@mcp.tool()
def get_patch():
    """Return the unified git diff of all changes made in the repository."""
    try:
        result = docker_exec(
            ["git", "-c", "core.fileMode=false", "diff"],
            workdir=CONTAINER_TESTBED,
            timeout=30,
        )

        if result["exit_code"] != 0:
            return f"Error getting patch: {result['stderr']}"

        return result["stdout"]

    except Exception as e:
        return f"Error getting patch: {e}"