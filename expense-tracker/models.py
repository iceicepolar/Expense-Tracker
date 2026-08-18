from datetime import date, datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

# Create the SQLAlchemy object
db = SQLAlchemy()


class User(db.Model, UserMixin):
    """
    One account. Owns its own transactions and can never see anybody else's.

    UserMixin supplies the four attributes Flask-Login looks for
    (is_authenticated / is_active / is_anonymous / get_id), so the only
    thing left for us to store is the login itself.
    """

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    #Stored lower-cased so "Me@x.com" and "me@x.com" cannot become two
    #accounts that each think they own the same inbox.
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)

    #Never the password itself - only a one-way scrypt hash of it. A stolen
    #copy of this table still cannot be turned back into anyone's password.
    password_hash = db.Column(db.String(255), nullable=False)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    #Deleting an account takes its transactions with it rather than leaving
    #rows behind that no longer belong to anyone.
    expenses = db.relationship(
        "Expense", backref="user", lazy=True, cascade="all, delete-orphan"
    )

    @staticmethod
    def normalise_email(value):
        return (value or "").strip().lower()

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    def __repr__(self):
        return f"<User {self.email}>"


class Expense(db.Model):
    __tablename__ = "expenses"

    id = db.Column(db.Integer, primary_key=True)

    #Which account this row belongs to. Every query in app.py filters on it -
    #that filter, not the login page, is what keeps accounts apart.
    #
    #Nullable so that adding the column to a table that already holds rows
    #does not fail. Transactions written from here on always set it, and
    #`python database.py claim <email>` adopts anything left over from before
    #accounts existed.
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True, index=True
    )

    description = db.Column(db.String(150), nullable=False)

    category = db.Column(db.String(50), nullable=False)

    amount = db.Column(db.Float, nullable=False)

    transaction_type = db.Column(db.String(20), nullable=False)

    transaction_date = db.Column(db.Date, nullable=False, default=date.today)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    #Optional free-text note. nullable=True because every transaction
    #already in the database predates this column and has none.
    notes = db.Column(db.String(300), nullable=True)

    @property
    def is_income(self):
        return self.transaction_type == "Income"

    @property
    def signed_amount(self):
        """Positive for income, negative for expenses."""
        return self.amount if self.is_income else -self.amount

    def to_dict(self):
        return {
            "id": self.id,
            "description": self.description,
            "category": self.category,
            "amount": self.amount,
            "transaction_type": self.transaction_type,
            "transaction_date": self.transaction_date.isoformat(),
            "notes": self.notes,
        }

    def __repr__(self):
        return f"<Expense {self.description}>"
