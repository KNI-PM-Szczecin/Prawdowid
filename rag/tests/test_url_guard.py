import asyncio

import pytest

from app import url_guard
from app.url_guard import BlockedURLError, assert_public_url, is_blocked_address


@pytest.fixture(autouse=True)
def resolved(monkeypatch):
    """DNS is always stubbed: guard tests never touch the network."""
    addresses = {"gov.pl": ["93.184.216.34"]}

    async def resolve(host):
        if host not in addresses:
            raise BlockedURLError(f"cannot resolve {host}")
        return addresses[host]

    monkeypatch.setattr(url_guard, "resolve_host", resolve)
    return addresses


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.1.2.3",
        "169.254.169.254",
        "192.168.0.1",
        "172.16.0.5",
        "100.64.0.1",
        "::1",
        "fc00::1",
        "fe80::1",
    ],
)
def test_private_and_link_local_addresses_are_blocked(address):
    assert is_blocked_address(address)


def test_public_address_is_allowed():
    assert not is_blocked_address("93.184.216.34")


def test_public_host_passes():
    assert asyncio.run(assert_public_url("https://gov.pl/x")) is None


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000/x",
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://fc00::1/",
        "https://internal.corp:8080/x",
        "ftp://gov.pl/x",
        "https://no-such-host.test/x",
    ],
)
def test_internal_and_invalid_urls_are_rejected(url):
    with pytest.raises(BlockedURLError):
        asyncio.run(assert_public_url(url))


def test_zone_scoped_address_is_blocked(monkeypatch):
    async def resolve(host):
        return ["fe80::1%eth0"]

    monkeypatch.setattr(url_guard, "resolve_host", resolve)
    with pytest.raises(BlockedURLError):
        asyncio.run(assert_public_url("https://gov.pl/x"))
