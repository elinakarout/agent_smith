import socket
import _socket


def block_network():
    def blocked_network(*args, **kwargs):
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
