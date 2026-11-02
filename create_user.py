"""CLI utility to provision or update an authorized CryoTrack user account safely."""
import sys
import argparse
import getpass
from auth import create_or_update_user, VALID_ROLES


def main():
    parser = argparse.ArgumentParser(
        description="CryoTrack -- Provision or update an authorized user account with salted scrypt password hashing."
    )
    parser.add_argument("--email", help="User email address (e.g. admin@cryotrack.io)")
    parser.add_argument("--name", default=None, help="Full display name (e.g. Operations Lead)")
    parser.add_argument("--role", choices=VALID_ROLES, default="Administrator", help="Access role")
    parser.add_argument("--department", default=None, help="Assigned Department")
    parser.add_argument("--password", default=None, help="Password (omit to enter interactively via hidden prompt)")

    # Backwards-compatible positional invocation: python create_user.py <email_or_user> <password> [name] [role]
    dept_arg = None
    if len(sys.argv) >= 3 and not sys.argv[1].startswith("-"):
        email_arg = sys.argv[1]
        pwd_arg = sys.argv[2]
        name_arg = sys.argv[3] if len(sys.argv) > 3 else "Operations Administrator"
        role_arg = sys.argv[4] if len(sys.argv) > 4 else "Administrator"
    else:
        args = parser.parse_args()
        email_arg = args.email
        pwd_arg = args.password
        name_arg = args.name
        role_arg = args.role
        dept_arg = args.department

    print("=" * 64)
    print(" CryoTrack -- User & Administrator Provisioning Utility")
    print("=" * 64)

    if not email_arg:
        email_arg = input("Email address (e.g. admin@cryotrack.io): ").strip()
    if not email_arg:
        print("Error: Email address is required.")
        sys.exit(1)

    if not name_arg:
        name_arg = input("Full display name [Operations Administrator]: ").strip() or "Operations Administrator"

    if not pwd_arg:
        pwd_arg = getpass.getpass("Password (min 8 chars, letters + numbers): ")
        confirm = getpass.getpass("Confirm password: ")
        if pwd_arg != confirm:
            print("Error: Passwords do not match.")
            sys.exit(1)

    ok, result = create_or_update_user(email_arg, pwd_arg, full_name=name_arg, role=role_arg, department=dept_arg)
    if ok:
        print(f"SUCCESS: Provisioned '{result['email']}' with role '{result['role']}' in '{result['department']}'.")
        print("Security: Salted scrypt hash stored in instance/cryotrack_auth.sqlite (plaintext never stored).")
    else:
        print(f"ERROR: {result}")
        sys.exit(1)


if __name__ == "__main__":
    main()
