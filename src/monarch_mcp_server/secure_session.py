"""
Secure session management for Monarch Money MCP Server.

Uses the system keyring when available, with an automatic file-based
fallback for environments without a keyring backend (e.g. WSL, headless Linux).
"""

import logging
import os
import stat
import tempfile
from pathlib import Path
from typing import Optional

import keyring
from monarchmoney import MonarchMoney

logger = logging.getLogger(__name__)

# Keyring service identifiers
KEYRING_SERVICE = "com.mcp.monarch-mcp-server"
KEYRING_USERNAME = "monarch-token"

# File-based fallback location
_TOKEN_DIR = Path.home() / ".monarch-mcp-server"
_TOKEN_FILE = _TOKEN_DIR / "token"

# A fleet-managed token: the fleet runtime points this server at one fleet's own
# ``KEY=VALUE`` file (`fleet auth monarch` installs and rotates it). When the pointer is
# set it is the only store — no keyring, no ~/.monarch-mcp-server fallback — so a fleet
# can never quietly run on another fleet's (or the operator's) token, and this server
# never writes it.
TOKEN_FILE_VAR = "MONARCH_TOKEN_FILE"
TOKEN_KEY = "MONARCH_TOKEN"


def fleet_token_file() -> Optional[Path]:
    """The fleet-managed token file, or ``None`` when this server runs standalone."""
    raw = os.environ.get(TOKEN_FILE_VAR)
    return Path(raw).expanduser() if raw else None


def reauth_hint() -> str:
    """The one command that installs a fresh token for this server's deployment."""
    path = fleet_token_file()
    if path is not None:
        return (
            f"run `fleet auth monarch --fleet <fleet>` to reinstall the token at {path}"
        )
    return "run `python login_setup.py` in the monarch-mcp-server checkout"


def _read_fleet_token(path: Path) -> Optional[str]:
    if not path.is_file():
        logger.info(f"🔍 No fleet token file at {path}")
        return None
    for line in path.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key.strip() == TOKEN_KEY:
            value = value.strip().strip("'\"")
            if value:
                logger.info(f"✅ Token loaded from {path}")
                return value
    logger.info(f"🔍 No {TOKEN_KEY} in {path}")
    return None


def _keyring_available() -> bool:
    """Check whether a usable keyring backend is available."""
    try:
        return keyring.get_keyring().priority > 0
    except Exception:
        return False


class SecureMonarchSession:
    """Manages Monarch Money sessions securely using the system keyring,
    falling back to a file-based store when no keyring backend is available."""

    # -- file-based helpers --------------------------------------------------

    def _save_token_file(self, token: str) -> None:
        _TOKEN_DIR.mkdir(parents=True, exist_ok=True, mode=stat.S_IRWXU)
        _TOKEN_DIR.chmod(stat.S_IRWXU)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=_TOKEN_DIR, delete=False
            ) as destination:
                temporary_path = Path(destination.name)
                destination.write(token)
                destination.flush()
                os.fsync(destination.fileno())
            os.replace(temporary_path, _TOKEN_FILE)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        logger.info(f"✅ Token saved to {_TOKEN_FILE}")

    def _load_token_file(self) -> Optional[str]:
        if _TOKEN_FILE.is_file():
            token = _TOKEN_FILE.read_text().strip()
            if token:
                logger.info(f"✅ Token loaded from {_TOKEN_FILE}")
                return token
        return None

    # -- public API ----------------------------------------------------------

    def save_token(self, token: str) -> None:
        """Save the authentication token to the system keyring or file fallback."""
        if fleet_token_file() is not None:
            raise RuntimeError(
                f"Token is fleet-managed; not saved here. {reauth_hint()}"
            )
        if _keyring_available():
            try:
                keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, token)
            except Exception as e:
                logger.warning(f"⚠️  Keyring save failed, falling back to file: {e}")
            else:
                _TOKEN_FILE.unlink(missing_ok=True)
                logger.info("✅ Token saved securely to keyring")
                return

        self._save_token_file(token)

    def load_token(self) -> Optional[str]:
        """Load the authentication token from the fleet's file when one is pointed at,
        else from the system keyring or file fallback."""
        fleet_file = fleet_token_file()
        if fleet_file is not None:
            return _read_fleet_token(fleet_file)
        if _keyring_available():
            try:
                token = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
                if token:
                    logger.info("✅ Token loaded from keyring")
                    return token
                else:
                    logger.info("🔍 No token found in keyring")
            except Exception as e:
                logger.warning(f"⚠️  Keyring load failed, trying file fallback: {e}")

        token = self._load_token_file()
        if token:
            return token
        logger.info("🔍 No token found")
        return None

    def get_authenticated_client(self) -> Optional[MonarchMoney]:
        """Get an authenticated MonarchMoney client."""
        token = self.load_token()
        if not token:
            return None

        try:
            client = MonarchMoney(token=token)
            logger.info("✅ MonarchMoney client created with stored token")
            return client
        except Exception as e:
            logger.error(f"❌ Failed to create MonarchMoney client: {e}")
            return None

    def save_authenticated_session(self, mm: MonarchMoney) -> None:
        """Save the session from an authenticated MonarchMoney instance."""
        token = mm.token
        if not isinstance(token, str) or not token.strip():
            raise RuntimeError("Monarch did not provide a session token")
        self.save_token(token.strip())


# Global session manager instance
secure_session = SecureMonarchSession()
