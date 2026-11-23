import glob
import os
import ast
import re
from pathlib import Path
import subprocess
import shlex

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    ".tox",
    "build",
    "dist",
}
container = None
eval_script = None


ALLOWED_DIRECTORIES = [
    Path("/testbed").resolve(),
    Path("/tmp/agent").resolve(),
]


def check_path_permission(filepath, must_exist=False):
    """
    Check whether a path is inside an authorized directory.

    Resolves symlinks and prevents path traversal.
    """

    try:
        path = Path(filepath).resolve(strict=must_exist)

        for allowed_dir in ALLOWED_DIRECTORIES:
            try:
                path.relative_to(allowed_dir)
                return path
            except ValueError:
                continue

        raise PermissionError(
            f"Access denied: {filepath} is outside allowed directories"
        )

    except (OSError, RuntimeError) as exc:
        raise PermissionError(f"Invalid or inaccessible path: {exc}")


def read_file(filepath, start_line, end_line):
    if start_line > end_line or start_line < 1:
        return ""

    try:
        filepath = check_path_permission(filepath, must_exist=True)

        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        result = ""

        for i in range(start_line - 1, min(len(lines), end_line)):
            result += f"{i + 1}: {lines[i]}"

        return result

    except PermissionError as e:
        return f"Error: {e}"
    except FileNotFoundError:
        return "File Not Found"
    except (OSError, UnicodeError) as e:
        return f"Error reading file: {e}"


def edit_file(filepath, old_str, new_str):
    if old_str == "":
        return 'Error: String to replace is ""\n'

    if old_str == new_str:
        return "Error: String and Replacement Are Equal\n"

    try:
        filepath = check_path_permission(filepath, must_exist=True)

        if not filepath.is_file():
            return "Error: Not a regular file\n"

        content = filepath.read_text(encoding="utf-8")

        occurrences = content.count(old_str)

        if occurrences > 1:
            return f"Error: {occurrences} Occurrences Found\n"

        if occurrences == 0:
            return "Error: Couldn't Find String\n"

        filepath.write_text(
            content.replace(old_str, new_str),
            encoding="utf-8"
        )

        return "String Replaced Successfully\n"

    except PermissionError as e:
        return f"Error: {e}\n"
    except FileNotFoundError:
        return "Error: File Not Found\n"
    except (OSError, UnicodeError) as e:
        return f"Error: {e}\n"


def list_files(directory, pattern):
    try:
        directory = check_path_permission(directory, must_exist=True)

        if not directory.is_dir():
            return "Error: Not a directory"

        results = []

        for filepath in directory.rglob(pattern):
            try:
                filepath = check_path_permission(
                    filepath,
                    must_exist=True
                )

                if EXCLUDED_DIRS.intersection(filepath.parts):
                    continue

                if filepath.is_file():
                    results.append(str(filepath))

            except (PermissionError, OSError):
                continue

        return "\n".join(results)

    except PermissionError as e:
        return f"Error: {e}"
    except OSError as e:
        return f"Error: {e}"

def search_code(pattern, file_pattern):
    try:
        root = check_path_permission("/testbed", must_exist=True)

        if not root.is_dir():
            return "Error: Search root is not a directory"

        files = list_files(str(root), file_pattern)

        if files.startswith("Error:"):
            return files

        occurrences = []

        for filepath in files.splitlines():
            if not filepath:
                continue

            try:
                filepath = check_path_permission(
                    filepath,
                    must_exist=True
                )

                if not filepath.is_file():
                    continue

                if EXCLUDED_DIRS.intersection(filepath.parts):
                    continue

                with filepath.open("r", encoding="utf-8") as f:
                    for line_number, line in enumerate(f, start=1):
                        if pattern in line:
                            occurrences.append(
                                f"{filepath}:{line_number} {line.rstrip()}"
                            )

            except (PermissionError, OSError, UnicodeError):
                continue

        return "\n".join(occurrences)

    except PermissionError as e:
        return f"Error: {e}"
    except OSError as e:
        return f"Error searching code: {e}"

def search_function_or_class_definition_in_code(name):
    results = []

    try:
        root = check_path_permission("/testbed", must_exist=True)

        if not root.is_dir():
            return "Error: Search root is not a directory"

        files = list_files(str(root), "*.py")

        if files.startswith("Error:"):
            return files

        escaped_name = re.escape(name)

        patterns = [
            rf"^\s*def\s+{escaped_name}\s*\(",
            rf"^\s*async\s+def\s+{escaped_name}\s*\(",
            rf"^\s*class\s+{escaped_name}\b",
        ]

        for filepath in files.splitlines():
            if not filepath:
                continue

            try:
                filepath = check_path_permission(
                    filepath,
                    must_exist=True
                )

                if not filepath.is_file():
                    continue

                if EXCLUDED_DIRS.intersection(filepath.parts):
                    continue

                with filepath.open("r", encoding="utf-8") as f:
                    for line_number, line in enumerate(f, start=1):
                        for pattern in patterns:
                            if re.search(pattern, line):
                                results.append(
                                    f"{filepath}:{line_number} "
                                    f"{line.rstrip()}"
                                )
                                break

            except (PermissionError, OSError, UnicodeError):
                continue

        if not results:
            return f"{name} not found"

        return "\n".join(results)

    except PermissionError as e:
        return f"Error: {e}"
    except OSError as e:
        return f"Error searching definitions: {e}"

def find_references(name, filepath, line):
    try:
        filepath = check_path_permission(
            filepath,
            must_exist=True
        )

        if not filepath.is_file():
            return f"Error: Not a file: {filepath}"

        if not isinstance(line, int) or line < 1:
            return "Error: Invalid line number"

        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))

    except PermissionError as e:
        return f"Error: {e}"
    except (OSError, SyntaxError, UnicodeError) as e:
        return f"Error parsing {filepath}: {e}"

    definition = None

    for node in ast.walk(tree):
        if isinstance(
            node,
            (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            if node.name == name and node.lineno == line:
                definition = node
                break

    if definition is None:
        return f"Error: Definition '{name}' not found at line {line}"

    try:
        root = check_path_permission("/testbed", must_exist=True)

        if not root.is_dir():
            return "Error: Search root is not a directory"

    except PermissionError as e:
        return f"Error: {e}"

    results = set()

    for py_file in root.rglob("*.py"):
        if EXCLUDED_DIRS.intersection(py_file.parts):
            continue

        try:
            py_file = check_path_permission(
                py_file,
                must_exist=True
            )

            if not py_file.is_file():
                continue

            code = py_file.read_text(encoding="utf-8")
            parsed = ast.parse(code, filename=str(py_file))
            lines = code.splitlines()

        except (PermissionError, OSError, SyntaxError, UnicodeError):
            continue

        for node in ast.walk(parsed):

            if isinstance(node, ast.Name) and node.id == name:
                results.add(
                    f"{py_file}:{node.lineno} "
                    f"{lines[node.lineno - 1].strip()}"
                )

            elif isinstance(node, ast.Attribute) and node.attr == name:
                results.add(
                    f"{py_file}:{node.lineno} "
                    f"{lines[node.lineno - 1].strip()}"
                )

    return "\n".join(sorted(results))

def run_command(command, workdir):
    try:
        workdir = check_path_permission(
            workdir,
            must_exist=True
        )

        if not workdir.is_dir():
            return {
                "error": "Working directory is not a directory"
            }

        result = subprocess.run(
            shlex.split(command),
            capture_output=True,
            text=True,
            cwd=str(workdir),
            timeout=120
        )

        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    except PermissionError as e:
        return {"error": str(e)}

    except subprocess.TimeoutExpired:
        return {"error": "Command execution timed out"}

    except (OSError, subprocess.SubprocessError) as e:
        return {"error": f"Error executing command: {e}"}

def configure_swebench(docker_container, task_eval_script):
    global container, eval_script

    container = docker_container
    eval_script = task_eval_script


def run_tests():
    if container is None or eval_script is None:
        return "Error: SWE-bench environment not initialized"

    try:
        result = container.exec_run(
            ["bash", "-lc", eval_script],
            workdir="/testbed",
            demux=True,
        )

        stdout, stderr = result.output

        return {
            "exit_code": result.exit_code,
            "stdout": stdout.decode(errors="replace") if stdout else "",
            "stderr": stderr.decode(errors="replace") if stderr else "",
        }

    except Exception as e:
        return f"Error executing tests: {e}"


def get_patch():
    try:
        repo_path = check_path_permission(
            "/testbed",
            must_exist=True
        )

        if not repo_path.is_dir():
            return "Error: Repository directory not found"

        result = subprocess.run(
            [
                "git",
                "-c",
                "core.fileMode=false",
                "diff",
            ],
            capture_output=True,
            text=True,
            cwd=str(repo_path),
            timeout=30
        )

        if result.returncode != 0:
            return f"Error getting patch:\n{result.stderr}"

        return result.stdout

    except PermissionError as e:
        return f"Error: {e}"

    except subprocess.TimeoutExpired:
        return "Error: Git diff timed out"

    except (OSError, subprocess.SubprocessError) as e:
        return f"Error getting patch: {e}"
    

# For testing purposes

# print(read_file("agent_mbpp/__main__.py", 10, 20), end='')

# print(edit_file("test.py", "# Should we", "#hhhhhhhhhh"), end="")

# print(list_files("/testbed", "*.py"))

# print(search_code("def search_code(pattern, file_pattern)", "*.py"))

# print(search_function_or_class_definition_in_code("DEFINITION_PATTERNS"))

# print(find_references("ExecutionResult", "/sgoinfre/hdaoun/agent_smith/sandbox/schemas.py", 40))

run_command("cat schemas.py", "/sgoinfre/hdaoun/agent_smith/sandbox")
