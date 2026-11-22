import asyncio
import ipaddress
import socket
from urllib.parse import urlparse


class BlockedURLError(ValueError):
    """A caller-supplied URL must not be fetched: bad scheme, non-standard port or a non-public address."""


# Networks that must never be reached with a citizen's URL: loopback, private, link-local (including the
# cloud metadata endpoint 169.254.169.254), CGNAT, benchmarking, documentation, multicast, reserved, IPv6 ULA,
# link-local and multicast. Every address the host resolves to is checked, not only the first one.
BLOCKED_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.88.99.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "::/127",
        "fc00::/7",
        "fe80::/10",
        "ff00::/8",
    )
)
ALLOWED_SCHEMES = ("http", "https")
ALLOWED_PORTS = frozenset({80, 443})


def is_blocked_address(address: str) -> bool:
    """True for loopback, private, link-local and other non-routable addresses; an IPv6 zone suffix is
    link-local by definition and is stripped before the lookup."""
    parsed = ipaddress.ip_address(address.split("%", 1)[0])
    return any(parsed in network for network in BLOCKED_NETWORKS)


async def resolve_host(host: str) -> list[str]:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None)
    except (socket.gaierror, OSError) as error:
        raise BlockedURLError(f"cannot resolve {host}") from error
    return [info[4][0] for info in infos]


async def assert_public_url(url: str) -> None:
    """Every address a URL resolves to must be public, with http/https on ports 80/443.
    Applied to the submitted URL and again to every redirect target."""
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise BlockedURLError(f"scheme {parsed.scheme!r} is not allowed")
    try:
        port = parsed.port
    except ValueError as error:
        raise BlockedURLError(f"invalid port in {url!r}") from error
    if port is not None and port not in ALLOWED_PORTS:
        raise BlockedURLError(f"port {port} is not allowed")
    host = (parsed.hostname or "").strip()
    if not host:
        raise BlockedURLError("URL has no host")
    for address in await resolve_host(host):
        if is_blocked_address(address):
            raise BlockedURLError(f"{host} resolves to a non-public address")
