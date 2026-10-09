"""Fresh native replay with all seven network surfaces blocked before AFRE imports."""

import socket
import sys
from pathlib import Path


def main() -> None:
    class DeniedSocket(socket.socket):
        def __new__(cls, *args: object, **kwargs: object) -> "DeniedSocket":
            raise AssertionError("network forbidden in multiple-testing replay")

    def denied(*args: object, **kwargs: object) -> None:
        raise AssertionError("network forbidden in multiple-testing replay")

    for name in (
        "socket",
        "create_connection",
        "getaddrinfo",
        "gethostbyname",
        "gethostbyname_ex",
        "gethostbyaddr",
        "socketpair",
    ):
        setattr(socket, name, DeniedSocket if name == "socket" else denied)
    from examples.multiple_testing_demo import run

    result = run(Path(sys.argv[1]), reverse=sys.argv[2] == "reverse")
    print(result["digest"])


if __name__ == "__main__":
    main()
