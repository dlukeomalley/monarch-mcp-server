"""Canceled authentication leaves the existing session intact."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import login_setup
from monarch_mcp_server.secure_session import SecureMonarchSession, reauth_hint


@pytest.fixture
def setup_flow(monkeypatch):
    monkeypatch.delenv("MONARCH_TOKEN_FILE", raising=False)
    monkeypatch.setattr(login_setup, "load_dotenv", lambda: False)
    monkeypatch.setattr(login_setup.getpass, "getpass", lambda prompt: "fixture-token")
    client = SimpleNamespace(
        token="fixture-token",
        login=AsyncMock(),
        multi_factor_authenticate=AsyncMock(),
        get_accounts=AsyncMock(return_value={"accounts": []}),
        save_session=Mock(),
    )
    session = Mock()
    monkeypatch.setattr(login_setup, "MonarchMoney", Mock(return_value=client))
    monkeypatch.setattr(login_setup, "secure_session", session)
    return client, session


def _answers(monkeypatch, *values):
    answers = iter(values)
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))


def test_canceling_setup_does_not_delete_the_existing_token(monkeypatch):
    monkeypatch.setattr(login_setup, "load_dotenv", lambda: False)
    monkeypatch.setattr(login_setup, "MonarchMoney", Mock())
    session = Mock()
    monkeypatch.setattr(login_setup, "secure_session", session)
    answers = iter(("n", "n"))
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    asyncio.run(login_setup.main())

    assert session.mock_calls == []


def test_password_login_does_not_use_the_library_pickle(setup_flow, monkeypatch):
    client, session = setup_flow
    _answers(monkeypatch, "y", "1", "fixture@example.invalid")

    asyncio.run(login_setup.main())

    client.login.assert_awaited_once_with(
        "fixture@example.invalid",
        "fixture-token",
        use_saved_session=False,
        save_session=False,
    )
    client.save_session.assert_not_called()
    session.save_authenticated_session.assert_called_once_with(client)


def test_mfa_does_not_publish_a_library_pickle(setup_flow, monkeypatch):
    client, session = setup_flow
    client.login.side_effect = login_setup.RequireMFAException()
    _answers(monkeypatch, "y", "1", "fixture@example.invalid", "fixture-code")

    asyncio.run(login_setup.main())

    client.multi_factor_authenticate.assert_awaited_once_with(
        "fixture@example.invalid", "fixture-token", "fixture-code"
    )
    client.save_session.assert_not_called()
    session.save_authenticated_session.assert_called_once_with(client)


def test_failed_session_publication_returns_a_failed_exit(setup_flow, monkeypatch):
    _, session = setup_flow
    session.save_authenticated_session.side_effect = OSError(
        "fixture publication failure"
    )
    _answers(monkeypatch, "y", "1", "fixture@example.invalid")

    with pytest.raises(SystemExit) as stopped:
        asyncio.run(login_setup.main())

    assert stopped.value.code == 1


def test_managed_bootstrap_cannot_report_an_unpublished_session(
    setup_flow, tmp_path, monkeypatch
):
    client, _ = setup_flow
    token_file = tmp_path / "monarch.env"
    token_file.write_text("MONARCH_TOKEN=existing-fleet-token\n")
    monkeypatch.setenv("MONARCH_TOKEN_FILE", str(token_file))
    monkeypatch.setattr(login_setup, "secure_session", SecureMonarchSession())
    _answers(monkeypatch, "y", "1", "fixture@example.invalid")

    with pytest.raises(SystemExit) as stopped:
        asyncio.run(login_setup.main())

    assert stopped.value.code == 1
    client.get_accounts.assert_awaited_once()
    assert token_file.read_text() == "MONARCH_TOKEN=existing-fleet-token\n"


@pytest.mark.parametrize("reply", [None, [], {}])
def test_invalid_verification_reply_cannot_publish_a_session(
    setup_flow, monkeypatch, reply
):
    client, session = setup_flow
    client.get_accounts.return_value = reply
    _answers(monkeypatch, "y", "1", "fixture@example.invalid")

    with pytest.raises(SystemExit) as stopped:
        asyncio.run(login_setup.main())

    assert stopped.value.code == 1
    session.save_authenticated_session.assert_not_called()


@pytest.mark.parametrize("method", ["2", "3"])
def test_verification_failure_uses_the_owned_recovery_command(
    setup_flow, monkeypatch, capsys, method
):
    client, session = setup_flow
    client.get_accounts.side_effect = RuntimeError("HTTP 401")
    if method == "2":
        _answers(monkeypatch, "y", method, "y", "fixture@example.invalid")
    else:
        _answers(monkeypatch, "y", method)

    with pytest.raises(SystemExit) as stopped:
        asyncio.run(login_setup.main())

    assert stopped.value.code == 1
    assert reauth_hint() in capsys.readouterr().out
    session.save_authenticated_session.assert_not_called()
