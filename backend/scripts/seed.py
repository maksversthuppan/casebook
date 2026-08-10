"""Seed the firm's advocates and clerks, or reset a forgotten password.

    uv run python -m scripts.seed              # create anyone missing
    uv run python -m scripts.seed --reset-all  # new password for everyone
    uv run python -m scripts.seed --reset priya@example.com

Passwords are generated here and only their hashes are stored, so they cannot be
read back later. Whatever is generated is written to `credentials.txt` next to
this project as well as printed, because terminal output gets lost.

Clerks have no login (CONTEXT.md, "Clerk") - they are only ever created, never
reset, and nothing is written out for them.
"""

import argparse
import asyncio
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Advocate, Clerk
from app.security import hash_password

# The firm's real advocates. Emails are placeholders (firstname@example.com)
# until real ones are chosen - only used to log in, not sent anything.
FIRM = [
    ("Sandhya Ajayghosh", "sandhya@example.com"),
    ("Abhirami", "abhirami@example.com"),
    ("Gouri", "gouri@example.com"),
    ("Anjana", "anjana@example.com"),
    ("Merlin", "merlin@example.com"),
    ("Bhasura", "bhasura@example.com"),
]

CLERKS = [
    "Sujatha NTA",
    "Shaji ATL",
    "Padma NDD",
]

CREDENTIALS_FILE = Path(__file__).resolve().parents[1] / "credentials.txt"


def _write_out(issued: list[tuple[str, str, str]]) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    width = max(len(email) for _, email, _ in issued)

    lines = [f"# Issued {stamp}", ""]
    lines += [f"{email:<{width}}  {password}   ({name})" for name, email, password in issued]
    block = "\n".join(lines)

    print("\n" + block)

    with CREDENTIALS_FILE.open("a", encoding="utf-8") as fh:
        fh.write(block + "\n\n")

    print(f"\nAlso written to {CREDENTIALS_FILE}")
    print("Hand these over in person, then delete that file.")


async def main(reset: set[str], reset_all: bool) -> None:
    issued: list[tuple[str, str, str]] = []

    async with SessionLocal() as db:
        existing = {
            a.email: a for a in (await db.execute(select(Advocate))).scalars()
        }

        for name, email in FIRM:
            email = email.lower()
            advocate = existing.get(email)
            wants_reset = reset_all or email in reset

            if advocate is not None and not wants_reset:
                print(f"  = {name} <{email}> already present")
                continue

            password = secrets.token_urlsafe(12)
            if advocate is None:
                db.add(Advocate(name=name, email=email, password_hash=hash_password(password)))
                print(f"  + {name} <{email}> created")
            else:
                advocate.password_hash = hash_password(password)
                print(f"  ~ {name} <{email}> password reset")
            issued.append((name, email, password))

        unknown = reset - {e.lower() for _, e in FIRM}
        if unknown:
            print(f"\n  ! not in FIRM, ignored: {', '.join(sorted(unknown))}")

        existing_clerks = {c.name for c in (await db.execute(select(Clerk))).scalars()}
        for name in CLERKS:
            if name in existing_clerks:
                print(f"  = {name} (clerk) already present")
                continue
            db.add(Clerk(name=name))
            print(f"  + {name} (clerk) created")

        await db.commit()

    if not issued:
        print("\nNothing to do. Use --reset <email> to issue a new password.")
        return

    _write_out(issued)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="append", default=[], metavar="EMAIL")
    parser.add_argument("--reset-all", action="store_true")
    args = parser.parse_args()

    try:
        asyncio.run(main({e.lower() for e in args.reset}, args.reset_all))
    except KeyboardInterrupt:
        sys.exit(1)
