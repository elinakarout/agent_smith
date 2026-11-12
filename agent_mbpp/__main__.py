from models.models import MBPPTaskInput, SolutionOutput
from pathlib import Path
from pydantic import ValidationError
import argparse

def run_model(model_name: str, provider_url: str):
    pass

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an MBPP task using an agent."
    )

    parser.add_argument(
        "--task-file",
        type=Path,
        required=True,
        help="Path to the MBPP task input JSON file."
    )

    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path where the output will be saved."
    )

    parser.add_argument(
        "--provider-url",
        type=str,
        default=None,
        help="LLM provider API URL (optional)."
    )

    parser.add_argument(
        "--model-name",
        type=str,
        default=None,
        help="Model name (optional)."
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    task_path = str(args.task_file)
    output_path = str(args.output)
    provider_url = str(args.provider_url)
    model_name = str(args.model_name)

    if not task_path.endswith(".json"):
        print("Error: task is not a json file")
        return
    try:
        with open(task_path, "r") as f:
            task_data = f.read()
            task = MBPPTaskInput.model_validate_json(task_data)
    except FileNotFoundError:
        print(f"Error: Task file not found: {task_path}")
        return

    except IsADirectoryError:
        print(f"Error: Expected a file, but got a directory: {task_path}")
        return

    except ValidationError as e:
        print(f"Error: Invalid task JSON: {e}")
        return

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w") as f:
            run_model(model_name, provider_url)

    except FileExistsError:
        print(
            "Error: The directory you are trying to create "
            "has the same name as an existing file."
        )
        return

main()
