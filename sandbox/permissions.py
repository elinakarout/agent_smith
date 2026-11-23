import builtins
import os

def make_guarded_open(config):
    def guarded_open(file, mode="r", *args, **kwargs):
        requested_path = os.fspath(file)
        resolved_path = os.path.realpath(requested_path)

        allowed = False

        for directory in config.allowed_directories:
            allowed_directory = os.path.realpath(directory)

            try:
                if os.path.commonpath(
                    [resolved_path, allowed_directory]
                ) == allowed_directory:
                    allowed = True
                    break
            except ValueError:
                continue

        if not allowed:
            raise PermissionError(
                f"Access denied: '{resolved_path}' is outside allowed directories"
            )

        if kwargs.get("opener") is not None:
            raise PermissionError("Custom file openers are not allowed")

        return builtins.open(file, mode, *args, **kwargs)

    return guarded_open