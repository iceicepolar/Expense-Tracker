from datetime import date, datetime

from flask_sqlalchemy import SQLAlchemy

# Create the SQLAlchemy object
db = SQLAlchemy()


class Expense(db.Model):
    __tablename__ = "expenses"

    id = db.Column(db.Integer, primary_key=True)

    description = db.Column(db.String(150), nullable=False)

    category = db.Column(db.String(50), nullable=False)

    amount = db.Column(db.Float, nullable=False)

    transaction_type = db.Column(db.String(20), nullable=False)

    transaction_date = db.Column(db.Date, nullable=False, default=date.today)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

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
        }

    def __repr__(self):
        return f"<Expense {self.description}>"
