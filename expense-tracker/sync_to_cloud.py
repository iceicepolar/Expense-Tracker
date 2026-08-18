"""
Copy the local SQLite data into a hosted database (Supabase / Neon / any Postgres).

    python sync_to_cloud.py "<connection-string>" --dry-run   # preview only
    python sync_to_cloud.py "<connection-string>"             # asks, then copies
    python sync_to_cloud.py "<connection-string>" --yes       # no prompt

With no argument it uses TARGET_DATABASE_URL, then DATABASE_URL - so once .env
points at the cloud there is nothing to type and no credential in your shell
history:

    python sync_to_cloud.py --dry-run

Deploying uploads your code, never `database/expenses.db` - that file lives on
this machine only. This walks the two databases and copies what is missing.

Accounts are matched by email and transactions by their contents, so nothing is
duplicated if you run it twice. It only ever INSERTs: no row in the target is
updated or deleted, so a mistake here cannot destroy live data.

Password hashes come across as-is, which means you sign in to the deployed site
with the same password you already use locally - no need to register again.
"""

import argparse
import os
import sys
from collections import Counter

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from config import BASE_DIR, engine_options  # noqa: F401  (also loads .env)
from models import Expense, User, db
from schema import ensure_columns

#Every column carried across, taken from the model rather than typed out, so
#a column added to models.py later cannot be silently dropped in transit.
#id is per-database and user_id is remapped to the target's own account row.
COPIED_FIELDS = [
    column.name
    for column in Expense.__table__.columns
    if column.name not in ("id", "user_id")
]

#Fields that decide whether two transactions are "the same" one. created_at is
#deliberately excluded - it records when a row was typed in, not what it is.
NATURAL_KEY = (
    "description",
    "category",
    "amount",
    "transaction_type",
    "transaction_date",
)


def normalise(url):
    """Same driver fix-up the app does, so both accept identical strings."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def describe(url):
    """A version of the URL safe to print - no password."""
    if "@" not in url:
        return url
    scheme, rest = url.split("://", 1)
    return f"{scheme}://***@{rest.split('@', 1)[1]}"


def key_of(expense):
    return tuple(getattr(expense, field) for field in NATURAL_KEY)


def copy(source_url, target_url, dry_run):
    source_engine = create_engine(source_url)
    target_engine = create_engine(target_url, **engine_options(target_url))

    #A dry run must not write anything - not even empty tables - so on a
    #brand-new target there is nothing to query yet and everything counts as
    #new. Outside a dry run the tables are built first, then an older target
    #that predates accounts gets its user_id column.
    target_ready = inspect(target_engine).has_table("users")

    if not dry_run:
        db.metadata.create_all(target_engine)
        ensure_columns(target_engine)
        target_ready = True
    elif not target_ready:
        print("\n  Target is empty - its tables will be created on the real run.")

    added_users = 0
    added_expenses = 0
    skipped_expenses = 0

    with Session(source_engine) as source, Session(target_engine) as target:
        source_users = source.scalars(select(User)).all()

        if not source_users:
            print("Nothing to copy - the local database has no accounts.")
            return 0

        for user in source_users:
            existing = (
                target.scalars(
                    select(User).where(User.email == user.email)
                ).first()
                if target_ready
                else None
            )

            if existing is None:
                print(f"\n  account  {user.email}  (new)")
                added_users += 1
                if dry_run:
                    #Without a real row there is no id to hang transactions
                    #off, so just report what would be copied and move on.
                    rows = source.scalars(
                        select(Expense).where(Expense.user_id == user.id)
                    ).all()
                    print(f"           {len(rows)} transaction(s) would be copied")
                    added_expenses += len(rows)
                    continue

                existing = User(
                    email=user.email,
                    password_hash=user.password_hash,
                    created_at=user.created_at,
                )
                target.add(existing)
                target.flush()  # assigns the new id
            else:
                print(f"\n  account  {user.email}  (already there)")

            source_rows = source.scalars(
                select(Expense).where(Expense.user_id == user.id)
            ).all()
            target_rows = target.scalars(
                select(Expense).where(Expense.user_id == existing.id)
            ).all()

            #Counting rather than set-matching, so two genuinely identical
            #transactions on the same day both survive the trip.
            have = Counter(key_of(row) for row in target_rows)

            for row in source_rows:
                key = key_of(row)
                if have[key] > 0:
                    have[key] -= 1
                    skipped_expenses += 1
                    continue

                added_expenses += 1
                if not dry_run:
                    target.add(
                        Expense(
                            user_id=existing.id,
                            **{f: getattr(row, f) for f in COPIED_FIELDS},
                        )
                    )

            print(
                f"           {len(source_rows)} local, "
                f"{len(target_rows)} already there"
            )

        if dry_run:
            target.rollback()
        else:
            target.commit()

    print("\n" + "-" * 58)
    verb = "would copy" if dry_run else "copied"
    print(f"  {verb}: {added_users} account(s), {added_expenses} transaction(s)")
    if skipped_expenses:
        print(f"  skipped {skipped_expenses} transaction(s) already present")
    if dry_run:
        print("\n  Dry run - no data was written. Re-run without --dry-run.")

    return added_expenses


def main():
    parser = argparse.ArgumentParser(
        description="Copy local SQLite data into a hosted Postgres database."
    )
    parser.add_argument(
        "target",
        nargs="?",
        #Falls back to DATABASE_URL because that is where .env already points
        #once you have switched over - no need for a second copy of the same
        #string. The source is always the local SQLite file, and main() refuses
        #to run if the two turn out to be the same database.
        default=(
            os.environ.get("TARGET_DATABASE_URL")
            or os.environ.get("DATABASE_URL")
        ),
        help=(
            "Target connection string. Defaults to TARGET_DATABASE_URL, then "
            "DATABASE_URL."
        ),
    )
    parser.add_argument(
        "--source",
        help="Read from this SQLite file instead of database/expenses.db.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be copied without writing anything.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt.",
    )
    args = parser.parse_args()

    if not args.target:
        parser.error(
            "No target given. Pass the connection string as an argument or "
            "set TARGET_DATABASE_URL."
        )

    source_path = args.source or os.path.join(BASE_DIR, "database", "expenses.db")
    if not os.path.exists(source_path):
        print(f"No local database at {source_path} - nothing to copy.")
        return 1

    source_url = "sqlite:///" + source_path
    target_url = normalise(args.target)

    if target_url.startswith("sqlite") and source_path in target_url:
        print("Source and target are the same database. Nothing to do.")
        return 1

    print("  from  " + source_path)
    print("  to    " + describe(target_url))

    if not args.dry_run and not args.yes:
        print(
            "\nThis inserts into the target database. Nothing is updated or "
            "deleted."
        )
        if input("Continue? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return 1

    copy(source_url, target_url, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
