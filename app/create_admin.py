"""Create the first site administrator.

    python -m app.create_admin --username admin --name "Site Admin"

The password is read from a prompt so it never lands in shell history. Admin
accounts are intentionally not creatable through the API: the only way in is here,
on the machine that hosts the database.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from app.admin_auth import create_admin_user
from app.bootstrap import ensure_schema
from app.database import SessionLocal, engine
from app.models import Base


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a Kundali site administrator.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--password", default=None, help="Omit to be prompted (preferred).")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)

    password = args.password
    if not password:
        password = getpass.getpass("Password (min 8 characters): ")
        if password != getpass.getpass("Confirm password: "):
            print("Passwords do not match.", file=sys.stderr)
            return 1

    db = SessionLocal()
    try:
        admin = create_admin_user(db, args.username, args.name, password)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print(f"Created admin '{admin.username}'. Sign in at /admin")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
