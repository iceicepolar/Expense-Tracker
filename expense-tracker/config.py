import os
from datetime import timedelta

from dotenv import load_dotenv

#Gets the folder where your project is located
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

#Read .env into the environment before anything below looks for a setting.
#Nothing else loads it: `python app.py` runs the file directly, so without
#this the .env sits there being ignored and the app quietly falls back to
#SQLite. Real environment variables always win, so this changes nothing on
#Vercel - there is no .env there, and the dashboard values are already set.
load_dotenv(os.path.join(BASE_DIR, ".env"), override=False)

#Anything that is not the local machine. Session cookies get locked down and
#a real SECRET_KEY becomes mandatory once this is true.
IS_DEPLOYED = bool(os.environ.get("VERCEL"))

#Used only for local development. Hard-coding this was harmless while the app
#had nothing to protect, but it signs the login cookie now - anyone who reads
#the repository could forge one. Deployments must supply their own.
DEV_SECRET_KEY = "expense-tracker-dev-only-key"


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


def engine_options(url):
    """
    Connection settings that suit whichever database we ended up with.

    Shared with sync_to_cloud.py so the copy script and the app connect on
    identical terms - a pooler that rejects one would reject the other.
    """
    if url.startswith("sqlite"):
        return {}

    options = {
        #Serverless databases idle down, so verify a connection before using
        #it and do not hold pooled connections open across cold starts.
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    #Connection poolers running in transaction mode hand the same Postgres
    #connection to different clients between statements, so a server-side
    #prepared statement created by one request is gone - or worse, clashes -
    #by the next. psycopg makes them automatically after a few repeats of a
    #query, which turns into "prepared statement _pg3_0 already exists" once
    #the app has been running a little while. Switching them off costs a
    #negligible amount of planning time at this size.
    #
    #Both providers are affected, and neither advertises it in the connection
    #string beyond a naming convention:
    #    Supabase  aws-0-<region>.pooler.supabase.com:6543
    #    Neon      ep-<name>-pooler.<region>.aws.neon.tech
    pooled = (
        ":6543" in url
        or "pooler.supabase.com" in url
        or "-pooler." in url
    )
    if pooled:
        options["connect_args"] = {"prepare_threshold": None}

    return options


class Config:
    """
    Configuration settings for the Expense Tracker Application

    """

    #Signs the session cookie that says who is logged in. Forge this and you
    #are anybody, so a deployment without its own key is refused at boot
    #rather than quietly running on a key that is public in this repository.
    SECRET_KEY = os.environ.get("SECRET_KEY") or DEV_SECRET_KEY

    SECRET_KEY_MISSING = IS_DEPLOYED and not os.environ.get("SECRET_KEY")

    #-- login cookie hardening ---------------------------------------------

    #Keep JavaScript away from the cookie, so a stray XSS cannot read it.
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True

    #Do not send it along with requests started by other sites.
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SAMESITE = "Lax"

    #HTTPS only in production. Left off locally because dev runs on plain
    #http and the browser would simply drop the cookie.
    SESSION_COOKIE_SECURE = IS_DEPLOYED
    REMEMBER_COOKIE_SECURE = IS_DEPLOYED

    #Stay signed in for a month - this is an app people open daily from a
    #phone home screen, not a bank.
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    REMEMBER_COOKIE_DURATION = timedelta(days=30)

    #SQLite locally, Postgres when DATABASE_URL is present
    SQLALCHEMY_DATABASE_URI = _database_uri()

    #True when we are not on the local SQLite file
    IS_HOSTED_DB = not SQLALCHEMY_DATABASE_URI.startswith("sqlite")

    SQLALCHEMY_ENGINE_OPTIONS = engine_options(SQLALCHEMY_DATABASE_URI)

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
