import json
from schemas import SandboxConfig


def read_config(file_path: str) -> SandboxConfig:
    try:
        if not file_path:
            return SandboxConfig()
        with open(file_path, "r") as file:
            data = json.load(file)
        return SandboxConfig(**data)
    except json.JSONDecodeError:
        raise ValueError(f"{file_path} is of invalid Json!")
    except FileNotFoundError:
        raise ValueError(f"{file_path} is not found")
    except Exception as e:
        raise ValueError(e.strerror)

