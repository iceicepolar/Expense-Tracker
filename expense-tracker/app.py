import calendar
import os
from datetime import date, datetime

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from config import CATEGORIES, CATEGORY_COLORS, TRANSACTION_TYPES, Config
from models import Expense, db

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def month_key(value):
    """Turn a date into the 'YYYY-MM' key used by the month filter."""
    return value.strftime("%Y-%m")


def month_bounds(key):
    """First and last day of the month described by a 'YYYY-MM' string."""
    year, month = (int(part) for part in key.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def shift_month(key, offset):
    """Move a 'YYYY-MM' key backwards / forwards by `offset` months."""
    year, month = (int(part) for part in key.split("-"))
    index = year * 12 + (month - 1) + offset
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def month_label(key):
    year, month = (int(part) for part in key.split("-"))
    return f"{calendar.month_name[month]} {year}"


def parse_form(form):
    """
    Validate the add / edit form.

    Returns (data, errors). `data` always holds the raw values so the form can
    be re-rendered with what the user typed instead of wiping it clean.
    """
    data = {
        "description": (form.get("description") or "").strip(),
        "category": (form.get("category") or "").strip(),
        "amount": (form.get("amount") or "").strip(),
        "transaction_type": (form.get("transaction_type") or "").strip(),
        "transaction_date": (form.get("transaction_date") or "").strip(),
    }
    errors = {}

    if not data["description"]:
        errors["description"] = "Description is required."
    elif len(data["description"]) > 150:
        errors["description"] = "Keep the description under 150 characters."

    if data["category"] not in CATEGORIES:
        errors["category"] = "Pick a category from the list."

    try:
        amount = float(data["amount"])
        if amount <= 0:
            errors["amount"] = "Amount must be greater than zero."
        else:
            data["amount_value"] = round(amount, 2)
    except ValueError:
        errors["amount"] = "Amount must be a number."

    if data["transaction_type"] not in TRANSACTION_TYPES:
        errors["transaction_type"] = "Choose Income or Expense."

    try:
        data["date_value"] = datetime.strptime(
            data["transaction_date"], "%Y-%m-%d"
        ).date()
    except ValueError:
        errors["transaction_date"] = "Use a valid date."

    return data, errors


def create_app():
    """
    Creates and configures the Flask application

    """

    #Assets live in public/static so Vercel's CDN can serve them directly;
    #Flask serves the same folder at the same URLs during local development.
    app = Flask(__name__, static_folder='public/static')

    #Load settings from config.py
    app.config.from_object(Config)

    #Connect SQLAlchemy to the Flask
    db.init_app(app)

    #Create database tables if they don't exist
    with app.app_context():
        #Only the local SQLite setup needs a folder on disk. Serverless
        #filesystems are read-only, so makedirs would crash on boot there.
        if not app.config["IS_HOSTED_DB"]:
            database_folder = os.path.join(app.root_path, 'database')

            #Create the database folder if missing
            if not os.path.exists(database_folder):
                os.makedirs(database_folder)

        db.create_all()

    # -- template helpers ---------------------------------------------------

    @app.template_filter("money")
    def money(value):
        symbol = app.config["CURRENCY_SYMBOL"]
        return f"{symbol}{abs(value or 0):,.2f}"

    @app.context_processor
    def inject_globals():
        return {
            "categories": CATEGORIES,
            "transaction_types": TRANSACTION_TYPES,
            "today": date.today().isoformat(),
        }

    # -- routes -------------------------------------------------------------

    @app.route('/')
    def dashboard():
        #Every month that already has data, newest first
        recorded = [
            month_key(row[0])
            for row in db.session.query(Expense.transaction_date).distinct()
        ]
        current = month_key(date.today())
        months = sorted({*recorded, current}, reverse=True)

        selected = request.args.get("month", current)
        if selected != "all" and selected not in months:
            selected = current

        search = (request.args.get("q") or "").strip()
        category = request.args.get("category", "")
        tx_type = request.args.get("type", "")

        query = Expense.query

        if selected != "all":
            start, end = month_bounds(selected)
            query = query.filter(Expense.transaction_date.between(start, end))
        if search:
            query = query.filter(Expense.description.ilike(f"%{search}%"))
        if category in CATEGORIES:
            query = query.filter(Expense.category == category)
        if tx_type in TRANSACTION_TYPES:
            query = query.filter(Expense.transaction_type == tx_type)

        expenses = query.order_by(
            Expense.transaction_date.desc(), Expense.id.desc()
        ).all()

        total_expenses = sum(e.amount for e in expenses if not e.is_income)
        total_income = sum(e.amount for e in expenses if e.is_income)
        balance = total_income - total_expenses

        return render_template(
            'dashboard.html',
            expenses=expenses,
            total_expenses=total_expenses,
            total_income=total_income,
            balance=balance,
            months=[(m, month_label(m)) for m in months],
            selected_month=selected,
            period_label=(
                "All time" if selected == "all" else month_label(selected)
            ),
            filters={"q": search, "category": category, "type": tx_type},
            chart_data=build_chart_data(selected),
        )

    def build_chart_data(selected):
        """Six-month trend plus a category breakdown, straight from the DB."""
        anchor = month_key(date.today()) if selected == "all" else selected
        window = [shift_month(anchor, offset) for offset in range(-5, 1)]

        start, _ = month_bounds(window[0])
        _, end = month_bounds(window[-1])

        rows = Expense.query.filter(
            Expense.transaction_date.between(start, end)
        ).all()

        income = {key: 0.0 for key in window}
        spent = {key: 0.0 for key in window}
        for row in rows:
            key = month_key(row.transaction_date)
            if key in income:
                (income if row.is_income else spent)[key] += row.amount

        #Category slices use the selected period only
        if selected == "all":
            scoped = Expense.query.all()
        else:
            s, e = month_bounds(selected)
            scoped = Expense.query.filter(
                Expense.transaction_date.between(s, e)
            ).all()

        by_category = {}
        for row in scoped:
            if not row.is_income:
                by_category[row.category] = (
                    by_category.get(row.category, 0) + row.amount
                )
        ordered = sorted(by_category.items(), key=lambda i: i[1], reverse=True)

        return {
            "trend": {
                "labels": [month_label(m).split(" ")[0][:3] for m in window],
                "income": [round(income[m], 2) for m in window],
                "expenses": [round(spent[m], 2) for m in window],
            },
            "categories": {
                "labels": [name for name, _ in ordered],
                "values": [round(total, 2) for _, total in ordered],
                "colors": [
                    CATEGORY_COLORS.get(name, "#8b8ea6") for name, _ in ordered
                ],
            },
        }

    @app.route('/add', methods=['GET', 'POST'])
    def add_expense():
        if request.method == 'POST':
            data, errors = parse_form(request.form)

            if errors:
                flash('Please fix the highlighted fields.', 'error')
                return render_template(
                    'add_expense.html', data=data, errors=errors
                ), 400

            db.session.add(
                Expense(
                    description=data["description"],
                    category=data["category"],
                    amount=data["amount_value"],
                    transaction_type=data["transaction_type"],
                    transaction_date=data["date_value"],
                )
            )
            db.session.commit()

            flash('Transaction added successfully.', 'success')
            return redirect(url_for('dashboard'))

        return render_template(
            'add_expense.html',
            data={"transaction_date": date.today().isoformat(),
                  "transaction_type": "Expense"},
            errors={},
        )

    @app.route('/edit/<int:expense_id>', methods=['GET', 'POST'])
    def edit_expense(expense_id):
        expense = db.session.get(Expense, expense_id)
        if expense is None:
            flash('That transaction no longer exists.', 'error')
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            data, errors = parse_form(request.form)

            if errors:
                flash('Please fix the highlighted fields.', 'error')
                return render_template(
                    'edit_expense.html',
                    expense=expense,
                    data=data,
                    errors=errors,
                ), 400

            expense.description = data["description"]
            expense.category = data["category"]
            expense.amount = data["amount_value"]
            expense.transaction_type = data["transaction_type"]
            expense.transaction_date = data["date_value"]
            db.session.commit()

            flash('Transaction updated.', 'success')
            return redirect(url_for('dashboard'))

        return render_template(
            'edit_expense.html',
            expense=expense,
            data={
                "description": expense.description,
                "category": expense.category,
                "amount": f"{expense.amount:.2f}",
                "transaction_type": expense.transaction_type,
                "transaction_date": expense.transaction_date.isoformat(),
            },
            errors={},
        )

    @app.route('/delete/<int:expense_id>', methods=['POST'])
    def delete_expense(expense_id):
        expense = db.session.get(Expense, expense_id)
        if expense is None:
            flash('That transaction no longer exists.', 'error')
        else:
            db.session.delete(expense)
            db.session.commit()
            flash('Transaction deleted.', 'success')
        return redirect(request.referrer or url_for('dashboard'))

    @app.route('/api/transactions')
    def api_transactions():
        rows = Expense.query.order_by(Expense.transaction_date.desc()).all()
        return jsonify([row.to_dict() for row in rows])

    @app.errorhandler(404)
    def not_found(_):
        return render_template('404.html'), 404

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
