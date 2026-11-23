import socket
import _socket
from typing import Any, NoReturn


def block_network() -> None:
    """Disable network access by monkey-patching socket functions in socket and _socket modules.

    Replaces socket creation and name resolution functions with stubs that raise PermissionError.
    """
    def blocked_network(*args: Any, **kwargs: Any) -> NoReturn:
        """Raise PermissionError when any network operation is attempted.

        Args:
            *args: Positional arguments provided to the intercepted socket call.
            **kwargs: Keyword arguments provided to the intercepted socket call.

        Raises:
            PermissionError: Always raised to block network access.
        """
        raise PermissionError(
            "Network access is disabled within the sandbox"
        )

    blocked_names = [
        "socket",
        "SocketType",
        "create_connection",
        "create_server",
        "socketpair",
        "fromfd",
        "getaddrinfo",
        "gethostbyname",
        "gethostbyname_ex",
        "gethostbyaddr",
        "getnameinfo",
        "getfqdn",
    ]

    for name in blocked_names:
        if hasattr(socket, name):
            setattr(socket, name, blocked_network)

    low_level_names = [
        "socket",
        "socketpair",
        "getaddrinfo",
        "gethostbyname",
        "gethostbyaddr",
        "getnameinfo",
    ]

    for name in low_level_names:
        if hasattr(_socket, name):
            setattr(_socket, name, blocked_network)
