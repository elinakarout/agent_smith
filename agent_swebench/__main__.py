import sys
from models.models import SWEBenchTaskInput, SolutionOutput
from pathlib import Path

def run_model():
    pass

def main() -> None:
    if len(sys.argv) == 5: # Should we include provider url and model name as mandatory parameters?
        args = sys.argv[1:]
        if args[0] != "--task-file":
            print("Error: Missing --task-file flag")
            return
        if args[2] != "--output":
            print("Error: Missing --output flag")    
            return
    else:
        print(
            "Error: Invalid Format"
            "\nYour command should be in the following format: "
            "\"uv run python -m agent_swebench --task-file task_path "
            "--output output_path\""
        )
        return
    task_path = args[1]
    output_path = Path(args[3])
    try:
        with open(task_path, "r") as f:
            task_data = f.read();
            task = SWEBenchTaskInput.model_validate_json(task_data)
    except FileNotFoundError:
        print("Error: File Not Found")
        return
    except NotADirectoryError as e:
        print(f"Error: {e}")
        return
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            run_model()
    except FileExistsError:
        print("Error: the directory you are trying to create has the " \
              "same name as an existing file"
        )
        return


main()