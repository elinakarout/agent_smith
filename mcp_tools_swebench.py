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

def read_file(filepath, start_line, end_line):
    if start_line > end_line:
        return ""
    if start_line < 1:
        return ""
    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()
            result=""
            for i in range(start_line - 1, min(len(lines), end_line)):
                result = result + (f"{i + 1}:" + lines[i])
        return result
    except FileNotFoundError:
        return "File Not Found"


def edit_file(filepath, old_str, new_str):
    if old_str == "":
        return "Error: String to replace is \"\"\n"
    if old_str == new_str:
        return "Error: String and Replacement Are Equal\n"
    try:
        with open(filepath, 'r') as f:
            content = f.read()
            occurences = content.count(old_str)
            if occurences > 1:
                return f"Error: {occurences} Occurences Found\n"
            if occurences == 0:
                return "Error: Couldn't Find String\n"
        with open(filepath, 'w') as f:
            content = content.replace(old_str, new_str)
            f.write(content)
            return "String Replaced Successfully\n"
        
    except FileNotFoundError:
        return "Error: File Not Found\n"
    except PermissionError:
        return "Error: Permission Denied\n"


def list_files(directory, pattern):
    return "\n".join(glob.glob(f"{directory}/**/{pattern}", recursive=True))


def search_code(pattern, file_pattern):

    files = list_files("/testbed", file_pattern).split("\n") # /testbed needs testing, for normal testing without a repo use . or any directory
    occurences = []
    for file in files:
        try:
            filepath = os.path.abspath(file)
            with open(filepath, "r") as f:
                lines = f.readlines()
            for i, line in enumerate(lines):
                if pattern in line:
                    occurences.append(
                        f"{filepath}:{i + 1} {line.rstrip()}"
                    )
        except (FileNotFoundError, PermissionError, IsADirectoryError):
            continue

    return "\n".join(occurences)

def search_function_or_class_definition_in_code(name):
    results = []

    files = list_files("/testbed", "*").splitlines()  # /testbed needs testing, for normal testing without a repo use . or any directory

    escaped_name = re.escape(name)

    for filepath in files:
        if not filepath:
            continue

        patterns = [
            r"^\s*def\s+{name}\s*\(",
            r"^\s*async\s+def\s+{name}\s*\(",
            r"^\s*class\s+{name}\b",
        ]

        if not patterns:
            continue

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line_number, line in enumerate(f, start=1):
                    for pattern in patterns:
                        regex = pattern.format(name=escaped_name)

                        if re.search(regex, line):
                            results.append(
                                f"{os.path.abspath(filepath)}:"
                                f"{line_number} {line.rstrip()}"
                            )
                            break

        except (OSError, UnicodeError):
            continue

    if not results:
        return f"{name} not found"
    return "\n".join(results)

def find_references(name, filepath, line):
    filepath = Path(filepath).resolve()

    if not filepath.is_file():
        return f"Error: File not found: {filepath}"

    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
    except (OSError, SyntaxError, UnicodeError) as exc:
        return f"Error parsing {filepath}: {exc}"

    # Verify that the requested definition exists.
    definition = None

    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            if node.name == name and node.lineno == line:
                definition = node
                break

    if definition is None:
        return f"Error: Definition '{name}' not found at line {line}"

    root = Path(__file__).resolve().parent

    # Search the project (adjust root to your repository root).
    results = []

    for py_file in root.rglob("*.py"):
        if EXCLUDED_DIRS.intersection(py_file.parts):
            continue
        try:
            code = py_file.read_text(encoding="utf-8")
            parsed = ast.parse(code, filename=str(py_file))
        except (OSError, SyntaxError, UnicodeError):
            continue

        for node in ast.walk(parsed):
            if isinstance(node, ast.Name) and node.id == name:
                results.append(
                    f"{py_file}:{node.lineno} "
                    f"{code.splitlines()[node.lineno - 1].strip()}"
                )

            elif isinstance(node, ast.Attribute) and node.attr == name:
                results.append(
                    f"{py_file}:{node.lineno} "
                    f"{code.splitlines()[node.lineno - 1].strip()}"
                )

    for py_file in root.rglob("*.py"):
        if EXCLUDED_DIRS.intersection(py_file.parts):
            continue

        print(py_file)
    return "\n".join(set(results))

def run_command(command, workdir):
    result = subprocess.run(
        shlex.split(command),
        capture_output=True,
        text=True,
        cwd=workdir
    )

    return result.stdout


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
    return run_command("git diff HEAD", "/testbed") # needs testing

# For testing purposes

# print(read_file("agent_mbpp/__main__.py", 10, 20), end='')

# print(edit_file("test.py", "# Should we", "#hhhhhhhhhh"), end="")

# print(list_files("**", "*.py"))

# print(search_code("def search_code(pattern, file_pattern)", "*.py"))

# print(search_function_or_class_definition_in_code("DEFINITION_PATTERNS"))

# print(find_references("ExecutionResult", "/sgoinfre/hdaoun/agent_smith/sandbox/schemas.py", 40))

# run_command("cat schemas.py", "/sgoinfre/hdaoun/agent_smith/sandbox")
