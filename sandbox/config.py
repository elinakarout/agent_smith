import json
from .schemas import SandboxConfig


def read_config(file_path: str | None = None) -> SandboxConfig:
    """Read and parse the sandbox configuration from a JSON file.

    Args:
        file_path: Path to the JSON configuration file, or None to use default settings.

    Returns:
        SandboxConfig: Instantiated sandbox configuration object.

    Raises:
        ValueError: If the file is not found, contains invalid JSON, or another error occurs.
    """
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
