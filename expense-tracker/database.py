"""
Small command line helper for inspecting / seeding the database.

    python database.py list    # print every stored transaction
    python database.py seed    # insert a few sample rows
    python database.py clear   # delete every row

Previously this module opened a raw sqlite connection at import time against
a path that did not exist, which crashed anything that imported it.  It now
goes through the Flask app so it always uses the configured database.
"""

import sys
from datetime import date, timedelta

from app import app
from models import Expense, db

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


def list_rows():
    rows = Expense.query.order_by(Expense.transaction_date.desc()).all()
    if not rows:
        print("No transactions yet.")
        return
    for row in rows:
        print(
            f"{row.id:>4}  {row.transaction_date}  "
            f"{row.transaction_type:<8} {row.category:<14} "
            f"{row.amount:>10,.2f}  {row.description}"
        )
    print(f"\n{len(rows)} transaction(s).")


def seed():
    today = date.today()
    for description, category, amount, kind, days_ago in SAMPLE:
        db.session.add(
            Expense(
                description=description,
                category=category,
                amount=amount,
                transaction_type=kind,
                transaction_date=today - timedelta(days=days_ago),
            )
        )
    db.session.commit()
    print(f"Inserted {len(SAMPLE)} sample transactions.")


def clear():
    deleted = Expense.query.delete()
    db.session.commit()
    print(f"Deleted {deleted} transaction(s).")


COMMANDS = {"list": list_rows, "seed": seed, "clear": clear}


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "list"

    if command not in COMMANDS:
        print(f"Unknown command '{command}'. Use: {', '.join(COMMANDS)}")
        sys.exit(1)

    with app.app_context():
        COMMANDS[command]()
