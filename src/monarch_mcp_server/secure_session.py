"""
Secure session management for Monarch Money MCP Server.

Uses the system keyring when available, with an automatic file-based
fallback for environments without a keyring backend (e.g. WSL, headless Linux).
"""

import logging
import os
import stat
from pathlib import Path
from typing import Optional
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
        return f"run `fleet auth monarch --fleet <fleet>` to reinstall the token at {path}"
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
        import keyring
        backend = keyring.get_keyring()
        # The fail backend means no real backend was found
        from keyrings.alt import file as _  # noqa: F401 – probe import
        # If we get here, keyrings.alt is installed but may be the only option.
        # Fall through and check the backend name.
    except ImportError:
        pass

    try:
        import keyring
        backend = keyring.get_keyring()
        backend_name = type(backend).__name__
        # These backends indicate no real keyring is available
        if backend_name in ("Keyring", "NullKeyring", "FailKeyring", "ChainerBackend"):
            # ChainerBackend may wrap a real backend — try a round-trip test
            if backend_name == "ChainerBackend":
                try:
                    keyring.set_password(KEYRING_SERVICE, "__probe__", "1")
                    keyring.delete_password(KEYRING_SERVICE, "__probe__")
                    return True
                except Exception:
                    return False
            return False
        return True
    except Exception:
        return False


class SecureMonarchSession:
    """Manages Monarch Money sessions securely using the system keyring,
    falling back to a file-based store when no keyring backend is available."""

    def __init__(self) -> None:
        self._use_keyring = _keyring_available()
        if self._use_keyring:
            logger.info("🔐 Using system keyring for token storage")
        else:
            logger.info("🔐 Keyring unavailable — using file-based token storage")

    # -- file-based helpers --------------------------------------------------

    def _save_token_file(self, token: str) -> None:
        _TOKEN_DIR.mkdir(parents=True, exist_ok=True)
        # Write with owner-only permissions
        _TOKEN_FILE.write_text(token)
        _TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600
        _TOKEN_DIR.chmod(stat.S_IRWXU)  # 700
        logger.info(f"✅ Token saved to {_TOKEN_FILE}")

    def _load_token_file(self) -> Optional[str]:
        if _TOKEN_FILE.is_file():
            token = _TOKEN_FILE.read_text().strip()
            if token:
                logger.info(f"✅ Token loaded from {_TOKEN_FILE}")
                return token
        return None

    def _delete_token_file(self) -> None:
        if _TOKEN_FILE.is_file():
            _TOKEN_FILE.unlink()
            logger.info(f"🗑️ Token file deleted: {_TOKEN_FILE}")
        # Remove directory if empty
        if _TOKEN_DIR.is_dir() and not list(_TOKEN_DIR.iterdir()):
            _TOKEN_DIR.rmdir()

    # -- public API ----------------------------------------------------------

    def save_token(self, token: str) -> None:
        """Save the authentication token to the system keyring or file fallback."""
        if fleet_token_file() is not None:
            logger.warning(f"⚠️  Token is fleet-managed; not saved here. {reauth_hint()}")
            return
        if self._use_keyring:
            try:
                import keyring
                keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, token)
                logger.info("✅ Token saved securely to keyring")
                self._cleanup_old_session_files()
                return
            except Exception as e:
                logger.warning(f"⚠️  Keyring save failed, falling back to file: {e}")

        self._save_token_file(token)
        self._cleanup_old_session_files()

    def load_token(self) -> Optional[str]:
        """Load the authentication token from the fleet's file when one is pointed at,
        else from the system keyring or file fallback."""
        fleet_file = fleet_token_file()
        if fleet_file is not None:
            return _read_fleet_token(fleet_file)
        if self._use_keyring:
            try:
                import keyring
                token = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
                if token:
                    logger.info("✅ Token loaded from keyring")
                    return token
                else:
                    logger.info("🔍 No token found in keyring")
                    return None
            except Exception as e:
                logger.warning(f"⚠️  Keyring load failed, trying file fallback: {e}")

        token = self._load_token_file()
        if token:
            return token
        logger.info("🔍 No token found")
        return None

    def delete_token(self) -> None:
        """Delete the authentication token from all storage backends."""
        if fleet_token_file() is not None:
            logger.warning(f"⚠️  Token is fleet-managed; not deleted here. {reauth_hint()}")
            return
        # Try keyring
        if self._use_keyring:
            try:
                import keyring
                keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
                logger.info("🗑️ Token deleted from keyring")
            except Exception:
                pass

        # Always try file cleanup too
        self._delete_token_file()
        self._cleanup_old_session_files()

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
        if mm.token:
            self.save_token(mm.token)
        else:
            logger.warning("⚠️  MonarchMoney instance has no token to save")

    def _cleanup_old_session_files(self) -> None:
        """Clean up old insecure session files."""
        cleanup_paths = [
            ".mm/mm_session.pickle",
            "monarch_session.json",
            ".mm",  # Remove the entire directory if empty
        ]

        for path in cleanup_paths:
            try:
                if os.path.exists(path):
                    if os.path.isfile(path):
                        os.remove(path)
                        logger.info(f"🗑️ Cleaned up old insecure session file: {path}")
                    elif os.path.isdir(path) and not os.listdir(path):
                        os.rmdir(path)
                        logger.info(f"🗑️ Cleaned up empty session directory: {path}")
            except Exception as e:
                logger.warning(f"⚠️  Could not clean up {path}: {e}")


# Global session manager instance
secure_session = SecureMonarchSession()
