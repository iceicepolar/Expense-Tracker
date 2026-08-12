import os

#Gets the folder where your project is located
BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _database_uri():
    """
    Use a hosted Postgres when DATABASE_URL is set (Vercel / any host),
    otherwise fall back to the local SQLite file for development.

    Serverless hosts have a read-only, disposable filesystem, so SQLite
    cannot be used in production - the file is wiped between invocations.
    """
    url = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")

    if not url:
        return 'sqlite:///' + os.path.join(BASE_DIR, 'database', 'expenses.db')

    #SQLAlchemy 2.x needs an explicit driver; providers hand out the bare
    #'postgres://' or 'postgresql://' form.
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]

    return url


class Config:
    """
    Configuration settings for the Expense Tracker Application

    """

    #Secret key for Flask
    SECRET_KEY = os.environ.get(
        "SECRET_KEY",
        "expense-tracker-secret-key"
    )

    #SQLite locally, Postgres when DATABASE_URL is present
    SQLALCHEMY_DATABASE_URI = _database_uri()

    #True when we are not on the local SQLite file
    IS_HOSTED_DB = not SQLALCHEMY_DATABASE_URI.startswith("sqlite")

    #Serverless databases idle down, so verify a connection before using it
    #and do not hold pooled connections open across cold starts.
    SQLALCHEMY_ENGINE_OPTIONS = (
        {"pool_pre_ping": True, "pool_recycle": 280} if IS_HOSTED_DB else {}
    )

    #Disable modification tracking
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    #Symbol used everywhere amounts are displayed.
    #Override with the CURRENCY_SYMBOL environment variable if needed.
    CURRENCY_SYMBOL = os.environ.get("CURRENCY_SYMBOL", "₱")


#Categories offered in the add / edit forms
CATEGORIES = [
    "Food",
    "Transport",
    "Shopping",
    "Bills",
    "Health",
    "Entertainment",
    "Education",
    "Salary",
    "Savings",
    "Other",
]

#Colour used for each category in the doughnut chart
CATEGORY_COLORS = {
    "Food": "#d6a33d",
    "Transport": "#4f86ff",
    "Shopping": "#ff5d73",
    "Bills": "#33d69f",
    "Health": "#ff9d42",
    "Entertainment": "#8c52ff",
    "Education": "#22c9d6",
    "Salary": "#7bd651",
    "Savings": "#e879f9",
    "Other": "#8b8ea6",
}

TRANSACTION_TYPES = ["Expense", "Income"]
