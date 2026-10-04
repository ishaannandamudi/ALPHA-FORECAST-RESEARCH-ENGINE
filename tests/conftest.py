"""Every test runs offline, including accidental DNS and socket construction."""

import socket
from collections.abc import Iterator

import pytest

from examples.foundation_demo import Demo, build_demo


@pytest.fixture(autouse=True)
def deny_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def denied(*args: object, **kwargs: object) -> None:
        raise AssertionError("network is forbidden in AFRE tests")

    for name in (
        "socket",
        "create_connection",
        "getaddrinfo",
        "gethostbyname",
        "gethostbyname_ex",
        "gethostbyaddr",
        "socketpair",
    ):
        monkeypatch.setattr(socket, name, denied)
    yield


@pytest.fixture
def demo() -> Demo:
    return build_demo()
