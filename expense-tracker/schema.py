"""
Tiny forward-only schema patcher.

`db.create_all()` only ever creates missing *tables* - it will not touch a
table that already exists. Since `expenses` predates accounts, the new
`user_id` column has to be added by hand or every query blows up with
"no such column: expenses.user_id" on the database you already have.

This runs on every boot and does nothing once the column is present, so it is
safe to leave in place. Anything more elaborate than this belongs in
Flask-Migrate.
"""

from sqlalchemy import inspect, text


def ensure_user_column(engine, logger=None):
    """
    Add expenses.user_id when an older copy of the table lacks it.

    Takes a plain SQLAlchemy engine rather than the Flask-SQLAlchemy object so
    that sync_to_cloud.py can run it against a second database without needing
    an application context.
    """
    inspector = inspect(engine)

    #Nothing to patch on a fresh database - create_all() already built the
    #table from the current model, column included.
    if "expenses" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("expenses")}
    if "user_id" in columns:
        return

    is_sqlite = engine.dialect.name == "sqlite"

    statements = ["ALTER TABLE expenses ADD COLUMN user_id INTEGER"]

    #SQLite cannot bolt a foreign key onto an existing table, and rebuilding
    #the table to get one is not worth the risk to real data. Postgres can,
    #so the hosted database gets the stronger guarantee.
    if not is_sqlite:
        statements.append(
            "ALTER TABLE expenses ADD CONSTRAINT expenses_user_id_fkey "
            "FOREIGN KEY (user_id) REFERENCES users (id)"
        )

    statements.append(
        "CREATE INDEX IF NOT EXISTS ix_expenses_user_id "
        "ON expenses (user_id)"
    )

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))

    if logger:
        logger.info("Added expenses.user_id to the existing table.")
