import pytest

from app import fetcher

PUBLIC_TEST_ADDRESS = "93.184.216.34"


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    """Tests run offline: every host name resolves to one public address unless a test says otherwise."""

    async def resolve(host: str) -> list[str]:
        return [PUBLIC_TEST_ADDRESS]

    monkeypatch.setattr(fetcher, "resolve_host", resolve)
