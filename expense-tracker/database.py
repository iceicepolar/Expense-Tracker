"""
Small command line helper for inspecting / seeding the database.

    python database.py list                 # print every stored transaction
    python database.py users                # list the accounts
    python database.py claim <email>        # give pre-account rows to a user
    python database.py seed <email>         # insert sample rows for a user
    python database.py clear <email>        # delete that user's rows

Transactions belong to an account now, so every command that writes needs to
be told which one.

Previously this module opened a raw sqlite connection at import time against
a path that did not exist, which crashed anything that imported it.  It now
goes through the Flask app so it always uses the configured database.
"""

import sys
from datetime import date, timedelta

from app import app
from models import Expense, User, db

SAMPLE = [
    ("Monthly salary", "Salary", 3200.00, "Income", 0),
    ("Rent", "Bills", 950.00, "Expense", 1),
    ("Groceries", "Food", 128.40, "Expense", 3),
    ("Bus pass", "Transport", 45.00, "Expense", 6),
    ("New headphones", "Shopping", 89.99, "Expense", 9),
    ("Pharmacy", "Health", 22.50, "Expense", 14),
    ("Freelance project", "Salary", 600.00, "Income", 20),
    ("Cinema", "Entertainment", 31.00, "Expense", 26),
]


def find_user(email):
    """Look up an account, or explain what is available and stop."""
    user = User.query.filter_by(email=User.normalise_email(email)).first()

    if user is None:
        print(f"No account with the email '{email}'.")
        known = User.query.order_by(User.id).all()
        if known:
            print("Known accounts: " + ", ".join(u.email for u in known))
        else:
            print("There are no accounts yet - register one in the app first.")
        sys.exit(1)

    return user


def list_rows(_email=None):
    rows = Expense.query.order_by(Expense.transaction_date.desc()).all()
    if not rows:
        print("No transactions yet.")
        return

    owners = {user.id: user.email for user in User.query.all()}

    for row in rows:
        owner = owners.get(row.user_id, "-- unclaimed --")
        print(
            f"{row.id:>4}  {row.transaction_date}  "
            f"{row.transaction_type:<8} {row.category:<14} "
            f"{row.amount:>10,.2f}  {row.description:<26} {owner}"
        )
    print(f"\n{len(rows)} transaction(s).")


def list_users(_email=None):
    users = User.query.order_by(User.id).all()
    if not users:
        print("No accounts yet.")
        return
    for user in users:
        count = Expense.query.filter_by(user_id=user.id).count()
        print(f"{user.id:>4}  {user.email:<40} {count:>4} transaction(s)")


def claim(email=None):
    """
    Hand every transaction written before accounts existed to one user.

    Those rows have user_id NULL, so they are invisible in the app - no query
    matches them. This adopts them once and then has nothing left to do.
    """
    if not email:
        print("Usage: python database.py claim <email>")
        sys.exit(1)

    user = find_user(email)

    orphans = Expense.query.filter(Expense.user_id.is_(None)).all()
    if not orphans:
        print("Nothing to claim - every transaction already has an owner.")
        return

    for row in orphans:
        row.user_id = user.id
    db.session.commit()

    print(f"Gave {len(orphans)} transaction(s) to {user.email}.")


def seed(email=None):
    if not email:
        print("Usage: python database.py seed <email>")
        sys.exit(1)

    user = find_user(email)
    today = date.today()

    for description, category, amount, kind, days_ago in SAMPLE:
        db.session.add(
            Expense(
                user_id=user.id,
                description=description,
                category=category,
                amount=amount,
                transaction_type=kind,
                transaction_date=today - timedelta(days=days_ago),
            )
        )
    db.session.commit()
    print(f"Inserted {len(SAMPLE)} sample transactions for {user.email}.")


def clear(email=None):
    if not email:
        print(
            "Usage: python database.py clear <email>\n"
            "An account is required so this cannot wipe everybody at once."
        )
        sys.exit(1)

    user = find_user(email)
    deleted = Expense.query.filter_by(user_id=user.id).delete()
    db.session.commit()
    print(f"Deleted {deleted} transaction(s) from {user.email}.")


COMMANDS = {
    "list": list_rows,
    "users": list_users,
    "claim": claim,
    "seed": seed,
    "clear": clear,
}


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "list"
    argument = sys.argv[2] if len(sys.argv) > 2 else None

    if command not in COMMANDS:
        print(f"Unknown command '{command}'. Use: {', '.join(COMMANDS)}")
        sys.exit(1)

    #app.py records start-up failures instead of raising, so without this the
    #real cause (a missing driver, a bad password) is buried under an
    #unrelated "Bind key 'None' is not in 'SQLALCHEMY_BINDS' config" traceback
    #from the first query.
    if app.config["DB_ERROR"]:
        print("Cannot reach the database.\n")
        print("  " + app.config["DB_ERROR"])
        sys.exit(1)

    with app.app_context():
        COMMANDS[command](argument)
