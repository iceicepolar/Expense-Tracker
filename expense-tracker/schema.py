"""
Tiny forward-only schema patcher.

`db.create_all()` only ever creates missing *tables* - it will not touch a
table that already exists. So every column added to models.py after a database
has been created must be added here too, or every query against that table
fails with "column expenses.<name> does not exist".

Add a row to REQUIRED_COLUMNS whenever you add a column to an existing model.
This runs on every boot and does nothing once the column is present, so it is
safe to leave in place. Anything more elaborate - renames, type changes,
backfills - belongs in Flask-Migrate.
"""

from sqlalchemy import inspect, text

#Columns that must exist on tables which predate them.
#
#  type_sql   portable enough for both SQLite and Postgres
#  fk         (table, column) to reference, Postgres only - SQLite cannot add
#             a foreign key to an existing table without rebuilding it, and
#             that is not worth the risk to real data
#  index      create an index on the new column
REQUIRED_COLUMNS = [
    {
        "table": "expenses",
        "column": "user_id",
        "type_sql": "INTEGER",
        "fk": ("users", "id"),
        "index": True,
    },
    {
        "table": "expenses",
        "column": "notes",
        "type_sql": "VARCHAR(300)",
    },
]


def ensure_columns(engine, logger=None):
    """Add any column in REQUIRED_COLUMNS that its table is missing."""
    inspector = inspect(engine)
    is_sqlite = engine.dialect.name == "sqlite"
    tables = set(inspector.get_table_names())
    added = []

    for spec in REQUIRED_COLUMNS:
        table, column = spec["table"], spec["column"]

        #A fresh database already has the column - create_all() built the
        #table from the current model.
        if table not in tables:
            continue
        if column in {c["name"] for c in inspector.get_columns(table)}:
            continue

        statements = [
            f"ALTER TABLE {table} ADD COLUMN {column} {spec['type_sql']}"
        ]

        if spec.get("fk") and not is_sqlite:
            ref_table, ref_column = spec["fk"]
            statements.append(
                f"ALTER TABLE {table} "
                f"ADD CONSTRAINT {table}_{column}_fkey "
                f"FOREIGN KEY ({column}) REFERENCES {ref_table} ({ref_column})"
            )

        if spec.get("index"):
            statements.append(
                f"CREATE INDEX IF NOT EXISTS ix_{table}_{column} "
                f"ON {table} ({column})"
            )

        with engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))

        added.append(f"{table}.{column}")

    if added and logger:
        logger.info("Added missing column(s): %s", ", ".join(added))

    return added
