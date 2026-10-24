"""A managed token file does not consult another credential store."""

import importlib.util
import os
import stat
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import keyring
import pytest

from monarch_mcp_server import secure_session as session_source
from monarch_mcp_server.secure_session import SecureMonarchSession


def test_managed_session_does_not_probe_keyring(tmp_path, monkeypatch):
    monkeypatch.setenv("MONARCH_TOKEN_FILE", str(tmp_path / "missing.env"))
    lookup = Mock(side_effect=AssertionError("No keyring access in a managed realm"))
    monkeypatch.setattr(keyring, "get_keyring", lookup)

    session = SecureMonarchSession()

    assert session.load_token() is None
    lookup.assert_not_called()


def test_session_can_precede_loading_its_managed_token_path(tmp_path, monkeypatch):
    monkeypatch.delenv("MONARCH_TOKEN_FILE", raising=False)
    lookup = Mock(side_effect=AssertionError("Backend selection must be lazy"))
    monkeypatch.setattr(keyring, "get_keyring", lookup)
    session = SecureMonarchSession()
    monkeypatch.setenv("MONARCH_TOKEN_FILE", str(tmp_path / "missing.env"))

    assert session.load_token() is None
    lookup.assert_not_called()


@pytest.mark.parametrize(
    "name,priority,available",
    [
        ("Keyring", 5, True),
        ("ChainerBackend", 10, True),
        ("Keyring", 0, False),
        ("Keyring", -1, False),
        ("OtherBackend", -1, False),
    ],
)
def test_backend_capability_comes_from_priority_without_credential_writes(
    monkeypatch, name, priority, available
):
    monkeypatch.delenv("MONARCH_TOKEN_FILE", raising=False)
    backend = type(name, (), {"priority": priority})()
    monkeypatch.setattr(keyring, "get_keyring", lambda: backend)
    read = Mock(return_value="fixture-token")
    write = Mock(side_effect=AssertionError("Availability does not write credentials"))
    monkeypatch.setattr(keyring, "get_password", read)
    monkeypatch.setattr(keyring, "set_password", write)
    monkeypatch.setattr(keyring, "delete_password", write)
    with monkeypatch.context() as filesystem:
        filesystem.setattr(Path, "is_file", lambda self: False)
        token = SecureMonarchSession().load_token()

    if available:
        assert token == "fixture-token"
        read.assert_called_once()
    else:
        assert token is None
        read.assert_not_called()
    write.assert_not_called()


def test_empty_keyring_preserves_the_existing_file_fallback(monkeypatch):
    monkeypatch.delenv("MONARCH_TOKEN_FILE", raising=False)
    backend = type("FixtureBackend", (), {"priority": 5})()
    monkeypatch.setattr(keyring, "get_keyring", lambda: backend)
    monkeypatch.setattr(keyring, "get_password", Mock(return_value=None))
    with monkeypatch.context() as filesystem:
        filesystem.setattr(Path, "is_file", lambda self: True)
        filesystem.setattr(Path, "read_text", lambda self: "fallback-token")
        token = SecureMonarchSession().load_token()

    assert token == "fallback-token"


def test_backend_reselection_uses_the_provider_current_capability(monkeypatch):
    monkeypatch.delenv("MONARCH_TOKEN_FILE", raising=False)
    backend = type("Keyring", (), {"priority": -1})()
    monkeypatch.setattr(keyring, "get_keyring", lambda: backend)
    monkeypatch.setattr(keyring, "get_password", Mock(return_value="fixture-token"))
    session = SecureMonarchSession()
    with monkeypatch.context() as filesystem:
        filesystem.setattr(Path, "is_file", lambda self: False)
        first = session.load_token()
        backend.priority = 5
        second = session.load_token()

    assert first is None
    assert second == "fixture-token"


@pytest.fixture
def isolated_file_session(tmp_path, monkeypatch):
    monkeypatch.delenv("MONARCH_TOKEN_FILE", raising=False)
    monkeypatch.chdir(tmp_path)
    backend = type("FileOnlyBackend", (), {"priority": -1})()
    monkeypatch.setattr(keyring, "get_keyring", lambda: backend)
    # Bind the actual owner's default paths to a temporary home at module startup.
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    spec = importlib.util.spec_from_file_location(
        "session_publication_fixture", session_source.__file__
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    token_file = tmp_path / ".monarch-mcp-server" / "token"
    token_file.parent.mkdir(mode=0o755)
    token_file.write_text("old-token")
    token_file.chmod(0o644)
    return module.secure_session, token_file


def test_file_publication_keeps_old_readers_off_the_new_token(isolated_file_session):
    session, token_file = isolated_file_session
    with token_file.open() as old_reader:
        session.save_token("new-token")
        old_contents = old_reader.read()

    assert old_contents == "old-token"
    assert token_file.read_text() == "new-token"
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(token_file.parent.stat().st_mode) == 0o700


def test_failed_publication_preserves_the_old_token_and_cleans_temporary_files(
    isolated_file_session, monkeypatch
):
    session, token_file = isolated_file_session
    monkeypatch.setattr(
        os, "replace", Mock(side_effect=OSError("fixture publication failure"))
    )

    with pytest.raises(OSError):
        session.save_token("new-token")

    assert token_file.read_text() == "old-token"
    assert list(token_file.parent.iterdir()) == [token_file]


@pytest.mark.parametrize("token", [None, "", "   ", 123])
def test_authenticated_client_needs_a_token_before_publication(monkeypatch, token):
    session = SecureMonarchSession()
    publication = Mock()
    monkeypatch.setattr(session, "save_token", publication)

    with pytest.raises(RuntimeError):
        session.save_authenticated_session(SimpleNamespace(token=token))

    publication.assert_not_called()
