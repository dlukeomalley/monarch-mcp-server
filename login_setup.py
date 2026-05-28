#!/usr/bin/env python3
"""
Standalone script to perform interactive Monarch Money login with MFA support.
Run this script to authenticate and save a session file that the MCP server can use.
"""

import asyncio
import getpass
import sys
from pathlib import Path

# Add the src directory to the Python path for imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from monarchmoney import MonarchMoney, RequireMFAException
from dotenv import load_dotenv
from monarch_mcp_server.secure_session import secure_session

async def main():
    load_dotenv()
    
    print("\n🏦 Monarch Money - Claude Desktop Setup")
    print("=" * 45)
    print("This will authenticate you once and save a session")
    print("for seamless access through Claude Desktop.\n")
    
    # Check the version first
    try:
        import monarchmoney
        print(f"📦 MonarchMoney version: {getattr(monarchmoney, '__version__', 'unknown')}")
    except Exception as e:
        print(f"⚠️  Could not check version: {e}")
    
    mm = MonarchMoney()
    
    try:
        # Clear any existing sessions (both old pickle files and keyring)
        secure_session.delete_token()
        print("🗑️ Cleared existing secure sessions")
        
        # Ask about MFA setup
        print("\n🔐 Security Check:")
        has_mfa = input("Do you have MFA (Multi-Factor Authentication) enabled on your Monarch Money account? (y/n): ").strip().lower()
        
        if has_mfa not in ['y', 'yes']:
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
            if proceed not in ['y', 'yes']:
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
                print("Set a password first, then re-run this script and choose 1 or 2.")
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
            print("       short-lived 'features' token and will return 401 on every call.")
            token = getpass.getpass("\nPaste your session token: ").strip()
            if not token:
                print("❌ No token provided. Exiting.")
                return
            # Reject the short-lived features JWT up front (mirrors the library guard).
            # A JWT has exactly two dots: header.payload.signature.
            if token.count(".") == 2:
                print("\n❌ That looks like the 1-hour 'features' JWT (xxx.yyy.zzz), not")
                print("   the long-lived login token. It will return 401 on every call.")
                return
            # Re-initialize with the token so the Authorization header is set correctly.
            # set_token() only stores the value but does not update _headers.
            mm = MonarchMoney(token=token)
            print("✅ Token set")
        else:
            print(f"❌ Invalid choice: {login_method!r}. Please run again and pick 1, 2, or 3.")
            return

        if login_method in ("1", "2"):
            # Try login without MFA first
            try:
                await mm.login(email, password, use_saved_session=False, save_session=True)
                print("✅ Login successful!")

            except RequireMFAException:
                print("🔐 MFA code required")
                mfa_code = input("Two Factor Code: ")

                # Use the same instance for MFA
                await mm.multi_factor_authenticate(email, password, mfa_code)
                print("✅ MFA authentication successful")
                mm.save_session()  # Manually save the session
        
        # Test the connection first
        print("\nTesting connection...")
        try:
            # Try a simple test call that should work
            print("Calling get_accounts()...")
            accounts = await mm.get_accounts()
            print(f"Response received: {type(accounts)}")
            if accounts and isinstance(accounts, dict):
                account_count = len(accounts.get("accounts", []))
                print(f"✅ Found {account_count} accounts")
            else:
                print("❌ No accounts data returned or unexpected format")
                print(f"Response type: {type(accounts)}")
                print(f"Response content: {accounts}")
                return
        except Exception as test_error:
            err = str(test_error)
            print(f"❌ Connection test failed: {err}")
            print(f"Error type: {type(test_error).__name__}")

            # A 401/403 means the token was accepted format-wise but the server
            # rejected it — almost always the wrong or expired token, not an API
            # change. This is the most common failure for the SSO/manual path.
            if "401" in err or "403" in err or "unauthorized" in err.lower():
                print("\n🔐 The server rejected the token (401/403).")
                if login_method == "2":
                    print("   This means the pasted token is wrong or expired.")
                    print("   Make sure you copied the 'Authorization: Token' value")
                    print("   from an api.monarch.com/graphql request — NOT the")
                    print("   1-hour features JWT (xxx.yyy.zzz) and NOT a localStorage")
                    print("   value. Re-run this script and paste a fresh token.")
                else:
                    print("   Your credentials were accepted but the session token")
                    print("   was rejected. Re-run this script to log in again.")
            else:
                print("\n⚠️  Unexpected error talking to Monarch.")
                print("   If this looks like a schema/field error, the library may be")
                print("   out of date: uv lock --upgrade-package monarchmoneycommunity")
            return
        
        # Save session securely to keyring
        try:
            print(f"\n🔐 Saving session securely to system keyring...")
            secure_session.save_authenticated_session(mm)
            print(f"✅ Session saved securely to keyring!")
                
        except Exception as save_error:
            print(f"❌ Could not save session to keyring: {save_error}")
            print("You may need to run the login again.")
        
        print("\n🎉 Setup complete! You can now use these tools in Claude Desktop:")
        print("   • get_accounts - View all your accounts")  
        print("   • get_transactions - Recent transactions")
        print("   • get_budgets - Budget information")
        print("   • get_cashflow - Income/expense analysis")
        print("\n💡 Session will persist across Claude restarts!")
        
    except Exception as e:
        print(f"\n❌ Login failed: {e}")
        print("\nPlease check your credentials and try again.")
        print(f"Error type: {type(e)}")

if __name__ == "__main__":
    asyncio.run(main())