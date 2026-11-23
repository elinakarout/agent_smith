import re
from pathlib import PurePosixPath
from docker_manager.manager import DockerManager


docker_manager = None
eval_script = None

CONTAINER_TESTBED = "/testbed"


def configure_swebench(image, task_eval_script, testbed_path=None):
    global docker_manager, eval_script

    if not testbed_path:
        raise ValueError("testbed_path is required")

    docker_manager = DockerManager(
        image=image,
        working_dir="/testbed",
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
        workdir="/testbed",
    )

    if result.exit_code != 0:
        raise PermissionError("Path escapes the repository")

    if must_exist:
        result = docker_manager.container.exec_run(
            ["test", "-e", normalized],
            workdir="/testbed",
        )

        if result.exit_code != 0:
            raise FileNotFoundError(normalized)

    return normalized


def docker_exec(command, workdir="/testbed", timeout=120):
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
    }


def _error_result(error):
    return f"Error: {error}"



def read_file(filepath, start_line, end_line):
    if start_line < 1 or end_line < start_line:
        return ""

    try:
        filepath = validate_container_path(filepath, must_exist=True)

        result = docker_exec([
            "awk",
            f'NR >= {int(start_line)} && NR <= {int(end_line)} '
            '{printf "%d: %s\\n", NR, $0}',
            filepath,
        ])

        if result["exit_code"] != 0:
            return result["stderr"]

        return result["stdout"]

    except Exception as e:
        return f"Error reading file: {e}"


def edit_file(filepath, old_str, new_str):
    try:
        filepath = validate_container_path(filepath, must_exist=True)

        result = docker_exec([
            "perl",
            "-0777",
            "-i",
            "-e",
            """
            BEGIN {
                $old = shift @ARGV;
                $new = shift @ARGV;
            }
            """,
            old_str,
            new_str,
            filepath,
        ])

        return result["stdout"] or result["stderr"]

    except Exception as e:
        return f"Error editing file: {e}"


def list_files(directory, pattern):
    try:
        directory = validate_container_path(
            directory,
            must_exist=True,
        )

        result = docker_exec([
            "find",
            directory,
            "-type", "f",
            "-name", pattern,
            "-not", "-path", "*/.git/*",
            "-not", "-path", "*/.venv/*",
            "-not", "-path", "*/__pycache__/*",
            "-not", "-path", "*/node_modules/*",
            "-not", "-path", "*/.tox/*",
            "-not", "-path", "*/build/*",
            "-not", "-path", "*/dist/*",
        ])

        return (
            result["stdout"]
            if result["exit_code"] == 0
            else result["stderr"]
        )

    except Exception as e:
        return f"Error listing files: {e}"



def search_code(pattern, file_pattern):
    try:
        result = docker_exec([
            "grep",
            "-rn",
            "--include", file_pattern,
            "--exclude-dir=.git",
            "--exclude-dir=.venv",
            "--exclude-dir=__pycache__",
            "--exclude-dir=node_modules",
            "-F",
            "--",
            pattern,
            CONTAINER_TESTBED,
        ])

        if result["exit_code"] == 1:
            return ""

        if result["exit_code"] != 0:
            return result["stderr"]

        return result["stdout"]

    except Exception as e:
        return f"Error searching code: {e}"


def search_function_or_class_definition_in_code(name):
    try:
        escaped = re.escape(name)

        pattern = (
            rf"^[[:space:]]*(async[[:space:]]+)?def[[:space:]]+"
            rf"{escaped}[[:space:]]*\("
            rf"|^[[:space:]]*class[[:space:]]+"
            rf"{escaped}([^[:alnum:]_]|$)"
        )

        result = docker_exec([
            "grep",
            "-rnE",
            "--include=*.py",
            "--exclude-dir=.git",
            "--exclude-dir=.venv",
            "--exclude-dir=__pycache__",
            "--",
            pattern,
            CONTAINER_TESTBED,
        ])

        if result["exit_code"] == 1:
            return f"{name} not found"

        if result["exit_code"] != 0:
            return result["stderr"]

        return result["stdout"]

    except Exception as e:
        return f"Error searching definitions: {e}"


def find_references(name, filepath, line):
    try:
        filepath = validate_container_path(filepath, must_exist=True)

        result = docker_exec([
            "/usr/local/bin/find-python-references",
            name,
            filepath,
            str(line),
        ])

        return result["stdout"] or result["stderr"]

    except Exception as e:
        return f"Error finding references: {e}"


def run_command(command, workdir):
    try:
        workdir = validate_container_path(
            workdir,
            must_exist=True,
        )

        if not isinstance(command, str) or not command.strip():
            return {"error": "Invalid command"}

        return docker_exec(
            ["bash", "-lc", command],
            workdir=workdir,
            timeout=120,
        )

    except Exception as e:
        return {"error": f"Error executing command: {e}"}


def run_tests():
    if not eval_script:
        return {"error": "Evaluation script not configured"}

    try:
        return docker_exec(
            ["bash", "-lc", eval_script],
            workdir="/testbed",
            timeout=600,
        )

    except Exception as e:
        return {"error": f"Error executing tests: {e}"}


def get_patch():
    try:
        result = docker_exec([
            "git",
            "-c",
            "core.fileMode=false",
            "diff",
        ], workdir="/testbed", timeout=30)

        if result["exit_code"] != 0:
            return f"Error getting patch: {result['stderr']}"

        return result["stdout"]

    except Exception as e:
        return f"Error getting patch: {e}"


# if __name__ == "__main__":

#     configure_swebench(
#         image="swebench/sweb.eval.x86_64.sympy_1776_sympy-18189:latest",
#         task_eval_script="...",
#         testbed_path="/tmp/swebench/repository",
#     )

#     print(run_command("pwd", "."))

#     # print(list_files("..", "*.py"))

#     # print(search_code("def sympify", "*.py"))

#     # print(search_function_or_class_definition_in_code("sympify"))

#     # print(get_patch())
#     stop_swebench()
