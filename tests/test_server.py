"""Authentication realm admission through the actual server owner."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from monarch_mcp_server import secure_session as session_module
from monarch_mcp_server import server


@pytest.mark.parametrize("contents", [None, "", "UNRELATED=fixture\n"])
def test_missing_fleet_token_never_uses_environment_login(
    tmp_path, monkeypatch, contents
):
    token_file = tmp_path / "monarch.env"
    if contents is not None:
        token_file.write_text(contents)
    monkeypatch.setenv("MONARCH_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("MONARCH_EMAIL", "fixture@example.invalid")
    monkeypatch.setenv("MONARCH_PASSWORD", "fixture-password")
    client = SimpleNamespace(login=AsyncMock(), token="fixture-token")
    constructor = Mock(return_value=client)
    monkeypatch.setattr(server, "MonarchMoney", constructor)

    with pytest.raises(RuntimeError):
        asyncio.run(server.get_monarch_client())

    constructor.assert_not_called()
    client.login.assert_not_awaited()


def test_fleet_token_file_supplies_its_own_client(tmp_path, monkeypatch):
    token_file = tmp_path / "monarch.env"
    token_file.write_text("MONARCH_TOKEN=fixture-token\n")
    monkeypatch.setenv("MONARCH_TOKEN_FILE", str(token_file))
    client = object()
    constructor = Mock(return_value=client)
    monkeypatch.setattr(session_module, "MonarchMoney", constructor)
    fallback = Mock(side_effect=AssertionError("No fallback client"))
    monkeypatch.setattr(server, "MonarchMoney", fallback)

    assert asyncio.run(server.get_monarch_client()) is client
    constructor.assert_called_once_with(token="fixture-token")
    fallback.assert_not_called()


def test_standalone_environment_login_remains_available(monkeypatch):
    monkeypatch.delenv("MONARCH_TOKEN_FILE", raising=False)
    monkeypatch.setenv("MONARCH_EMAIL", "fixture@example.invalid")
    monkeypatch.setenv("MONARCH_PASSWORD", "fixture-password")
    monkeypatch.setattr(server.secure_session, "get_authenticated_client", lambda: None)
    saved = Mock()
    monkeypatch.setattr(server.secure_session, "save_authenticated_session", saved)
    client = SimpleNamespace(login=AsyncMock())
    monkeypatch.setattr(server, "MonarchMoney", Mock(return_value=client))

    assert asyncio.run(server.get_monarch_client()) is client
    client.login.assert_awaited_once_with(
        "fixture@example.invalid",
        "fixture-password",
        use_saved_session=False,
        save_session=False,
    )
    saved.assert_called_once_with(client)


def test_auth_status_without_a_fleet_token_does_not_contact_monarch(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MONARCH_TOKEN_FILE", str(tmp_path / "missing.env"))
    constructor = Mock(side_effect=AssertionError("No provider call without a token"))
    monkeypatch.setattr(server, "MonarchMoney", constructor)

    result = server.check_auth_status()

    assert session_module.reauth_hint() in result
    constructor.assert_not_called()


def test_auth_status_verifies_the_token_from_the_managed_file(tmp_path, monkeypatch):
    token_file = tmp_path / "monarch.env"
    token_file.write_text("MONARCH_TOKEN=fixture-token\n")
    monkeypatch.setenv("MONARCH_TOKEN_FILE", str(token_file))
    client = SimpleNamespace(get_accounts=AsyncMock(return_value={"accounts": []}))
    constructor = Mock(return_value=client)
    monkeypatch.setattr(server, "MonarchMoney", constructor)

    server.check_auth_status()

    constructor.assert_called_once_with(token="fixture-token")
    client.get_accounts.assert_awaited_once()
