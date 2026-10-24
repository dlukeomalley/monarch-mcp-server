#!/usr/bin/env python3
"""
Standalone script to perform interactive Monarch Money login with MFA support.
Run this script to authenticate and save a session file that the MCP server can use.
"""

import asyncio
import getpass
import os
import sys
from pathlib import Path

# Ensure a CA bundle is available for TLS verification before any HTTPS happens.
# python.org's macOS build ships without a default cert.pem unless the installer's
# "Install Certificates.command" was run, which breaks HTTPS to api.monarch.com.
# certifi provides a portable bundle; setdefault respects an explicit override.
import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())

# Add the src directory to the Python path for imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from dotenv import load_dotenv
from monarchmoney import MonarchMoney, RequireMFAException

from monarch_mcp_server.secure_session import reauth_hint, secure_session


async def main() -> None:
    load_dotenv()

    print("\n🏦 Monarch Money - Claude Desktop Setup")
    print("=" * 45)
    print("This will authenticate you once and save a session")
    print("for seamless access through Claude Desktop.\n")

    # Check the version first
    try:
        import monarchmoney

        print(
            f"📦 MonarchMoney version: {getattr(monarchmoney, '__version__', 'unknown')}"
        )
    except Exception as e:
        print(f"⚠️  Could not check version: {e}")

    mm = MonarchMoney()

    try:
        # Ask about MFA setup
        print("\n🔐 Security Check:")
        has_mfa = (
            input(
                "Do you have MFA (Multi-Factor Authentication) enabled on your Monarch Money account? (y/n): "
            )
            .strip()
            .lower()
        )

        if has_mfa not in ["y", "yes"]:
            print("\n⚠️  SECURITY RECOMMENDATION:")
            print("=" * 50)
            print("You should enable MFA for your Monarch Money account.")
            print("MFA adds an extra layer of security to protect your financial data.")
            print("\nTo enable MFA:")
            print("1. Log into Monarch Money at https://monarchmoney.com")
            print("2. Go to Settings → Security")
            print("3. Enable Two-Factor Authentication")
            print("4. Follow the setup instructions\n")

            proceed = input("Continue with login anyway? (y/n): ").strip().lower()
            if proceed not in ["y", "yes"]:
                print("Login cancelled. Please set up MFA and try again.")
                return

        print("\nStarting login...")
        print("\nHow do you sign in to Monarch Money?")
        print("  1) Email and password")
        print("  2) Google / SSO (single sign-on)")
        print("  3) Advanced: paste a session token manually")
        login_method = input("Choice (1, 2, or 3): ").strip()

        if login_method == "1":
            email = input("Email: ")
            password = getpass.getpass("Password: ")
        elif login_method == "2":
            # The Monarch API authenticates with email + password (+ MFA). It has no
            # Google/SSO flow, and the web app does NOT expose a reusable login token
            # in cookies or localStorage that can be scraped. The supported path for
            # Google sign-in users is to set a password, then log in with it here.
            print("\nℹ️  The Monarch API doesn't support Google sign-in directly.")
            print("   Set a password on your account, then log in with it below:")
            print("   → https://app.monarchmoney.com/settings/security")
            print("   (You can keep using 'Sign in with Google' in the browser; the")
            print("    password just gives this script a way to authenticate.)")
            ready = input("\nHave you set a password? (y/n): ").strip().lower()
            if ready not in ("y", "yes"):
                print(
                    "Set a password first, then re-run this script and choose 1 or 2."
                )
                return
            email = input("Email: ")
            password = getpass.getpass("Password: ")
        elif login_method == "3":
            # Last-resort manual token entry. Only useful if you already have a valid
            # long-lived login token (e.g. from a prior session or another tool).
            # NOTE: Monarch's web app does not reliably expose this token in the
            # browser — if you can't find it, use option 1 or 2 instead.
            print("\n📋 Paste a long-lived Monarch login token.")
            print("   ⚠️  This must NOT be a JWT (xxx.yyy.zzz). A two-dot JWT is the")
            print(
                "       short-lived 'features' token and will return 401 on every call."
            )
            token = getpass.getpass("\nPaste your session token: ").strip()
            if not token:
                print("❌ No token provided. Exiting.")
                return
            # Reject the short-lived features JWT up front (mirrors the library guard).
            # A JWT has exactly two dots: header.payload.signature.
            if token.count(".") == 2:
                print(
                    "\n❌ That looks like the 1-hour 'features' JWT (xxx.yyy.zzz), not"
                )
                print(
                    "   the long-lived login token. It will return 401 on every call."
                )
                return
            # Re-initialize with the token so the Authorization header is set correctly.
            # set_token() only stores the value but does not update _headers.
            mm = MonarchMoney(token=token)
            print("✅ Token set")
        else:
            print(
                f"❌ Invalid choice: {login_method!r}. Please run again and pick 1, 2, or 3."
            )
            return

        if login_method in ("1", "2"):
            # Try login without MFA first
            try:
                await mm.login(
                    email, password, use_saved_session=False, save_session=False
                )
                print("✅ Login successful!")

            except RequireMFAException:
                print("🔐 MFA code required")
                mfa_code = input("Two Factor Code: ")

                # Use the same instance for MFA
                await mm.multi_factor_authenticate(email, password, mfa_code)
                print("✅ MFA authentication successful")

        # Test the connection first
        print("\nTesting connection...")
        accounts = await mm.get_accounts()
        if not isinstance(accounts, dict) or not accounts:
            raise RuntimeError("Monarch returned an invalid verification response")
        print("Connection verified")
        secure_session.save_authenticated_session(mm)
        print("Session saved")

        print("\n🎉 Setup complete! You can now use these tools in Claude Desktop:")
        print("   • get_accounts - View all your accounts")
        print("   • get_transactions - Recent transactions")
        print("   • get_budgets - Budget information")
        print("   • get_cashflow - Income/expense analysis")
        print("\n💡 Session will persist across Claude restarts!")

    except Exception as e:
        print(f"\nSetup failed: {e}")
        print(reauth_hint())
        raise SystemExit(1) from e


if __name__ == "__main__":
    asyncio.run(main())
