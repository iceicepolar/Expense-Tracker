import calendar
import os
from datetime import date, datetime
from itertools import groupby

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

from flask_login import current_user, login_required

from auth import auth as auth_blueprint, login_manager
from config import CATEGORIES, CATEGORY_COLORS, TRANSACTION_TYPES, Config
from models import Expense, Goal, GoalContribution, db
from schema import ensure_columns

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


def parse_goal_form(form):
    """
    Validate the goal add / edit form.

    Mirrors parse_form: raw values always come back so the page can be
    re-rendered with what was typed rather than blanked.
    """
    data = {
        "name": (form.get("name") or "").strip(),
        "target_amount": (form.get("target_amount") or "").strip(),
        "saved_amount": (form.get("saved_amount") or "").strip(),
        "target_date": (form.get("target_date") or "").strip(),
    }
    errors = {}

    if not data["name"]:
        errors["name"] = "Give the goal a name."
    elif len(data["name"]) > 120:
        errors["name"] = "Keep the name under 120 characters."

    try:
        target = float(data["target_amount"])
        if target <= 0:
            errors["target_amount"] = "The target must be more than zero."
        else:
            data["target_value"] = round(target, 2)
    except ValueError:
        errors["target_amount"] = "The target must be a number."

    #Blank means "nothing saved yet" rather than an error - most goals start
    #at zero and typing the 0 is busywork.
    if not data["saved_amount"]:
        data["saved_value"] = 0.0
    else:
        try:
            saved = float(data["saved_amount"])
            if saved < 0:
                errors["saved_amount"] = "Saved cannot be negative."
            else:
                data["saved_value"] = round(saved, 2)
        except ValueError:
            errors["saved_amount"] = "Saved must be a number."

    #The date is optional; only a malformed one is an error.
    if not data["target_date"]:
        data["date_value"] = None
    else:
        try:
            data["date_value"] = datetime.strptime(
                data["target_date"], "%Y-%m-%d"
            ).date()
        except ValueError:
            errors["target_date"] = "Use a valid date, or leave it empty."

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

    #Nothing during start-up may raise: an exception at import time takes the
    #whole serverless function down with an unreadable
    #FUNCTION_INVOCATION_FAILED, so failures are recorded and surfaced as a
    #readable page instead.
    app.config["DB_ERROR"] = None

    #Connect SQLAlchemy to the Flask. This builds the engine straight away,
    #so a missing driver or malformed URL fails here rather than on first use.
    try:
        db.init_app(app)
    except Exception as exc:
        app.logger.exception("Database setup failed")
        app.config["DB_ERROR"] = (
            f"Could not set up the database ({type(exc).__name__}): {exc}"
        )

    with app.app_context():
        #Only the local SQLite setup needs a folder on disk. Serverless
        #filesystems are read-only, so makedirs would crash on boot there.
        if app.config["DB_ERROR"] is None and not app.config["IS_HOSTED_DB"]:
            if os.environ.get("VERCEL"):
                app.config["DB_ERROR"] = (
                    "No DATABASE_URL is set. Serverless hosting has no "
                    "persistent disk, so the SQLite fallback cannot be used "
                    "here - add a Postgres connection string."
                )
            else:
                database_folder = os.path.join(app.root_path, 'database')

                #Create the database folder if missing
                try:
                    os.makedirs(database_folder, exist_ok=True)
                except OSError as exc:
                    app.config["DB_ERROR"] = f"Cannot create database folder: {exc}"

        if app.config["DB_ERROR"] is None:
            try:
                db.create_all()
                #create_all() never alters a table that already exists, so
                #columns added to a model after the fact have to be applied
                #separately. See REQUIRED_COLUMNS in schema.py.
                ensure_columns(db.engine, app.logger)
            except Exception as exc:
                app.logger.exception("Database initialisation failed")
                app.config["DB_ERROR"] = (
                    f"Could not reach the database ({type(exc).__name__}): {exc}"
                )

    #Refuse to serve rather than sign login cookies with the key that is
    #published in this repository - it would let anyone forge a session.
    if app.config["SECRET_KEY_MISSING"] and not app.config["DB_ERROR"]:
        app.config["DB_ERROR"] = (
            "No SECRET_KEY is set. It signs the login cookie, so without a "
            "private one anybody could forge a session and read every "
            "account. Generate one with "
            "`python -c \"import secrets; print(secrets.token_hex(32))\"` "
            "and add it to your environment variables."
        )

    #Turns the signed cookie back into `current_user` on every request.
    login_manager.init_app(app)
    app.register_blueprint(auth_blueprint)

    # -- ownership ----------------------------------------------------------

    def owned():
        """
        Every transaction query starts here.

        Scoping at a single choke point is the whole defence: a query that
        forgets `.filter_by(user_id=...)` silently returns other people's
        money, and that mistake is invisible in testing when you only have
        one account.
        """
        return Expense.query.filter_by(user_id=current_user.id)

    def owned_or_none(expense_id):
        """
        Fetch one row *by id and owner together*.

        Looking it up by id alone and checking ownership afterwards is the
        classic hole - /edit/5 would happily load somebody else's row for
        anyone who guessed the number.
        """
        return owned().filter_by(id=expense_id).first()

    def owned_goals():
        """Goals belong to an account exactly as transactions do."""
        return Goal.query.filter_by(user_id=current_user.id)

    def owned_goal_or_none(goal_id):
        return owned_goals().filter_by(id=goal_id).first()

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

    def recorded_months():
        """Every month this account has data in, newest first, plus today."""
        recorded = [
            month_key(row[0])
            for row in db.session.query(Expense.transaction_date)
            .filter(Expense.user_id == current_user.id)
            .distinct()
        ]
        current = month_key(date.today())
        return sorted({*recorded, current}, reverse=True), current

    def read_filters(months, current):
        """Pull the month / search / category / type filters off the query."""
        selected = request.args.get("month", current)
        if selected != "all" and selected not in months:
            selected = current

        return selected, {
            "q": (request.args.get("q") or "").strip(),
            "category": request.args.get("category", ""),
            "type": request.args.get("type", ""),
        }

    def month_neighbours(months, selected):
        """
        The months either side of the selected one, for the arrow buttons.

        Steps only through months that actually hold transactions - walking
        through a run of empty months to reach real data would be tedious and
        tells you nothing. `months` is newest-first, so the older month is the
        NEXT entry along and the newer one is the previous.
        """
        if selected == "all" or selected not in months:
            return None, None
        i = months.index(selected)
        older = months[i + 1] if i + 1 < len(months) else None
        newer = months[i - 1] if i > 0 else None
        return older, newer

    def apply_filters(selected, filters):
        """
        The one place filters turn into a query.

        Shared by the overview and the receipt view so the two can never drift
        into disagreeing about what "this month, food only" means.
        """
        query = owned()

        if selected != "all":
            start, end = month_bounds(selected)
            query = query.filter(Expense.transaction_date.between(start, end))
        if filters["q"]:
            query = query.filter(Expense.description.ilike(f"%{filters['q']}%"))
        if filters["category"] in CATEGORIES:
            query = query.filter(Expense.category == filters["category"])
        if filters["type"] in TRANSACTION_TYPES:
            query = query.filter(Expense.transaction_type == filters["type"])

        return query.order_by(
            Expense.transaction_date.desc(), Expense.id.desc()
        )

    @app.route('/')
    @login_required
    def dashboard():
        #Every month that already has data, newest first
        recorded = [
            month_key(row[0])
            for row in db.session.query(Expense.transaction_date)
            .filter(Expense.user_id == current_user.id)
            .distinct()
        ]
        current = month_key(date.today())
        months = sorted({*recorded, current}, reverse=True)

        selected = request.args.get("month", current)
        if selected != "all" and selected not in months:
            selected = current

        search = (request.args.get("q") or "").strip()
        category = request.args.get("category", "")
        tx_type = request.args.get("type", "")

        query = owned()

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

        older, newer = month_neighbours(months, selected)

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
            older_month=older,
            newer_month=newer,
            filter_args={
                k: v for k, v in
                (("q", search), ("category", category), ("type", tx_type))
                if v
            },
            chart_data=build_chart_data(selected),
        )

    def build_chart_data(selected):
        """Six-month trend plus a category breakdown, straight from the DB."""
        anchor = month_key(date.today()) if selected == "all" else selected
        window = [shift_month(anchor, offset) for offset in range(-5, 1)]

        start, _ = month_bounds(window[0])
        _, end = month_bounds(window[-1])

        rows = owned().filter(
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
            scoped = owned().all()
        else:
            s, e = month_bounds(selected)
            scoped = owned().filter(
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

    @app.route('/transactions')
    @login_required
    def transactions():
        """
        A statement-style history: every entry in date order, grouped by day.

        The overview answers "how am I doing"; this answers "what exactly
        happened, and when". Same rows, read differently.
        """
        months, current = recorded_months()
        selected, filters = read_filters(months, current)
        rows = apply_filters(selected, filters).all()
        older, newer = month_neighbours(months, selected)

        total_income = sum(r.amount for r in rows if r.is_income)
        total_expenses = sum(r.amount for r in rows if not r.is_income)

        #A running balance only means anything when nothing is filtered out -
        #under a search it would be the balance of an arbitrary subset, which
        #looks authoritative while being meaningless. Walk oldest to newest,
        #then flip back so the newest day still sits at the top.
        show_running = not (filters["q"] or filters["category"] or filters["type"])

        running = 0.0
        balances = {}
        for row in reversed(rows):
            running += row.signed_amount
            balances[row.id] = running

        groups = []
        for day, entries in groupby(rows, key=lambda r: r.transaction_date):
            entries = list(entries)
            groups.append(
                {
                    "date": day,
                    "entries": entries,
                    "income": sum(e.amount for e in entries if e.is_income),
                    "spent": sum(e.amount for e in entries if not e.is_income),
                    "net": sum(e.signed_amount for e in entries),
                    #Balance as at the end of this day
                    "balance": balances.get(entries[0].id, 0.0),
                }
            )

        return render_template(
            'transactions.html',
            groups=groups,
            count=len(rows),
            total_income=total_income,
            total_expenses=total_expenses,
            balance=total_income - total_expenses,
            months=[(m, month_label(m)) for m in months],
            selected_month=selected,
            period_label=(
                "All time" if selected == "all" else month_label(selected)
            ),
            filters=filters,
            older_month=older,
            newer_month=newer,
            filter_args={k: v for k, v in filters.items() if v},
            show_running=show_running,
        )

    # -- goals --------------------------------------------------------------

    @app.route('/goals')
    @login_required
    def goals():
        rows = owned_goals().order_by(Goal.created_at.desc()).all()

        #Finished goals sink to the bottom - what you are still saving for is
        #the useful part of the page.
        rows.sort(key=lambda g: (g.is_complete, -g.percent))

        return render_template(
            'goals.html',
            goals=rows,
            total_target=sum(g.target_amount for g in rows),
            total_saved=sum(g.saved_amount for g in rows),
        )

    @app.route('/goals/new', methods=['GET', 'POST'])
    @login_required
    def add_goal():
        if request.method == 'POST':
            data, errors = parse_goal_form(request.form)

            if errors:
                flash('Please fix the highlighted fields.', 'error')
                return render_template(
                    'goal_form.html', data=data, errors=errors,
                    goal=None, action=url_for('add_goal'),
                    submit_label='Create goal',
                ), 400

            goal = Goal(
                user_id=current_user.id,
                name=data["name"],
                target_amount=data["target_value"],
                saved_amount=0.0,
                target_date=data["date_value"],
            )
            db.session.add(goal)
            db.session.flush()

            #Anything already put aside becomes the first entry in the
            #goal's ledger, so saved_amount always has contributions behind
            #it rather than being a free-floating number.
            if data["saved_value"] > 0:
                db.session.add(
                    GoalContribution(
                        goal_id=goal.id,
                        user_id=current_user.id,
                        amount=data["saved_value"],
                        occurred_on=date.today(),
                        note="Already saved when the goal was created",
                    )
                )
                db.session.flush()
                goal.recalculate()

            db.session.commit()

            flash('Goal created.', 'success')
            return redirect(url_for('goals'))

        return render_template(
            'goal_form.html', data={}, errors={}, goal=None,
            action=url_for('add_goal'), submit_label='Create goal',
        )

    @app.route('/goals/<int:goal_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_goal(goal_id):
        goal = owned_goal_or_none(goal_id)
        if goal is None:
            flash('That goal no longer exists.', 'error')
            return redirect(url_for('goals'))

        if request.method == 'POST':
            data, errors = parse_goal_form(request.form)

            if errors:
                flash('Please fix the highlighted fields.', 'error')
                return render_template(
                    'goal_form.html', data=data, errors=errors, goal=goal,
                    action=url_for('edit_goal', goal_id=goal.id),
                    submit_label='Save changes',
                ), 400

            goal.name = data["name"]
            goal.target_amount = data["target_value"]
            goal.target_date = data["date_value"]
            #saved_amount is not editable here - it is the sum of the goal's
            #contributions. Editing it directly is what let a goal claim 0
            #saved while its entries said otherwise.
            db.session.commit()

            flash('Goal updated.', 'success')
            return redirect(url_for('goals'))

        return render_template(
            'goal_form.html',
            goal=goal,
            data={
                "name": goal.name,
                "target_amount": f"{goal.target_amount:.2f}",
                "target_date": (
                    goal.target_date.isoformat() if goal.target_date else ""
                ),
            },
            errors={},
            action=url_for('edit_goal', goal_id=goal.id),
            submit_label='Save changes',
        )

    @app.route('/goals/<int:goal_id>/contribute', methods=['POST'])
    @login_required
    def contribute_goal(goal_id):
        """
        Put money towards a goal.

        Recorded only against the goal. Writing a matching Savings expense
        was the previous behaviour and it was wrong: moving money into
        savings is not spending, so a large transfer buried the dashboard
        under a "Spent" figure that had nothing to do with daily costs.
        """
        goal = owned_goal_or_none(goal_id)
        if goal is None:
            flash('That goal no longer exists.', 'error')
            return redirect(url_for('goals'))

        raw = (request.form.get("amount") or "").strip()
        try:
            amount = round(float(raw), 2)
        except ValueError:
            flash('Enter a number to add.', 'error')
            return redirect(url_for('goals'))

        if amount <= 0:
            flash('Enter an amount greater than zero.', 'error')
            return redirect(url_for('goals'))

        db.session.add(
            GoalContribution(
                goal_id=goal.id,
                user_id=current_user.id,
                amount=amount,
                occurred_on=date.today(),
                note=(request.form.get("note") or "").strip()[:150] or None,
            )
        )
        #flush so the new row is visible to recalculate() before committing
        db.session.flush()
        goal.recalculate()
        db.session.commit()

        if goal.is_complete:
            flash(f'{goal.name} is fully funded.', 'success')
        else:
            flash(f'Added to {goal.name}.', 'success')
        return redirect(url_for('goals'))

    @app.route('/goals/<int:goal_id>/contribution/<int:contribution_id>/delete',
               methods=['POST'])
    @login_required
    def delete_contribution(goal_id, contribution_id):
        goal = owned_goal_or_none(goal_id)
        if goal is None:
            flash('That goal no longer exists.', 'error')
            return redirect(url_for('goals'))

        #Matched on goal AND owner, so a contribution id from another
        #account cannot be removed by guessing the number.
        entry = GoalContribution.query.filter_by(
            id=contribution_id, goal_id=goal.id, user_id=current_user.id
        ).first()

        if entry is None:
            flash('That entry no longer exists.', 'error')
        else:
            db.session.delete(entry)
            db.session.flush()
            goal.recalculate()
            db.session.commit()
            flash('Entry removed.', 'success')

        return redirect(url_for('goals'))

    @app.route('/goals/<int:goal_id>/delete', methods=['POST'])
    @login_required
    def delete_goal(goal_id):
        goal = owned_goal_or_none(goal_id)
        if goal is None:
            flash('That goal no longer exists.', 'error')
        else:
            db.session.delete(goal)
            db.session.commit()
            flash('Goal deleted.', 'success')
        return redirect(url_for('goals'))

    @app.route('/add', methods=['GET', 'POST'])
    @login_required
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
                    user_id=current_user.id,
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
    @login_required
    def edit_expense(expense_id):
        #Somebody else's id lands here as "no longer exists" rather than a
        #"not yours" message, which would confirm the row is real.
        expense = owned_or_none(expense_id)
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
    @login_required
    def delete_expense(expense_id):
        expense = owned_or_none(expense_id)
        if expense is None:
            flash('That transaction no longer exists.', 'error')
        else:
            db.session.delete(expense)
            db.session.commit()
            flash('Transaction deleted.', 'success')
        return redirect(request.referrer or url_for('dashboard'))

    @app.route('/api/transactions')
    @login_required
    def api_transactions():
        rows = owned().order_by(Expense.transaction_date.desc()).all()
        return jsonify([row.to_dict() for row in rows])

    #Routes that must keep working even when the database is unreachable,
    #otherwise the installed app cannot boot or show its offline page.
    DB_FREE_ENDPOINTS = {
        "health",
        "static",
        "manifest",
        "service_worker",
        "icons",
        "offline_page",
    }

    @app.before_request
    def block_when_database_is_down():
        """Show the reason instead of letting every route explode."""
        if app.config["DB_ERROR"] and request.endpoint not in DB_FREE_ENDPOINTS:
            return render_template(
                'db_error.html', message=app.config["DB_ERROR"]
            ), 503

    @app.route('/health')
    def health():
        """Deployment diagnostics. Deliberately reveals no credentials."""
        uri = app.config["SQLALCHEMY_DATABASE_URI"]
        return jsonify(
            {
                "ok": app.config["DB_ERROR"] is None,
                "driver": uri.split("://", 1)[0],
                "database_url_set": bool(
                    os.environ.get("DATABASE_URL")
                    or os.environ.get("POSTGRES_URL")
                ),
                "secret_key_set": bool(os.environ.get("SECRET_KEY")),
                "error": app.config["DB_ERROR"],
            }
        )

    # -- PWA files ----------------------------------------------------------
    #In production Vercel serves everything under public/ straight from its
    #CDN, so these routes only ever run during local development. The service
    #worker has to live at the root to control the whole site.

    def _public(filename, **kwargs):
        return send_from_directory(
            os.path.join(app.root_path, 'public'), filename, **kwargs
        )

    @app.route('/manifest.json')
    def manifest():
        return _public('manifest.json', mimetype='application/manifest+json')

    @app.route('/sw.js')
    def service_worker():
        response = _public('sw.js', mimetype='application/javascript')
        #Never let a stale worker pin itself in the browser cache
        response.headers['Cache-Control'] = 'no-cache'
        return response

    @app.route('/icons/<path:filename>')
    def icons(filename):
        return send_from_directory(
            os.path.join(app.root_path, 'public', 'icons'), filename
        )

    @app.route('/offline')
    def offline_page():
        return render_template('offline.html')

    @app.errorhandler(404)
    def not_found(_):
        return render_template('404.html'), 404

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
