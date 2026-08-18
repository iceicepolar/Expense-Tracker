"""
Registration, login and logout.

The whole scheme in three lines:

  register -> the password is hashed with scrypt and only the hash is stored
  login    -> the submitted password is hashed again and compared; on a match
              Flask drops a cookie signed with SECRET_KEY saying "user 7"
  after    -> every request reads that cookie, and every query in app.py adds
              `.filter(Expense.user_id == current_user.id)`

That last filter is the part that actually protects the data. A login page
without it is a doorman who checks IDs and then shows everyone into the same
room.
"""

from urllib.parse import urlparse

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import LoginManager, current_user, login_required, login_user, logout_user

from models import User, db

MIN_PASSWORD_LENGTH = 8

login_manager = LoginManager()

#Where anonymous visitors get sent, and what they are told when they land.
login_manager.login_view = "auth.login"
login_manager.login_message = "Please sign in to see your transactions."
login_manager.login_message_category = "error"

#Deliberately not "strong". Strong protection ties the session to the client's
#IP address, and a phone hopping between wifi and mobile data changes IP
#constantly - it would sign you out several times a day for no real gain. The
#cookie is already signed, HttpOnly and HTTPS-only in production.
login_manager.session_protection = "basic"

auth = Blueprint("auth", __name__)


@login_manager.user_loader
def load_user(user_id):
    """Turn the id stored in the cookie back into a User on each request."""
    return db.session.get(User, int(user_id))


def is_safe_next(target):
    """
    Only ever redirect back to our own pages.

    Without this check, /login?next=https://evil.example would bounce a
    freshly authenticated user straight off the site.
    """
    if not target:
        return False
    parsed = urlparse(target)
    return not parsed.scheme and not parsed.netloc and target.startswith("/")


def validate_credentials(email, password, confirm=None):
    """Shared field checks for the register form."""
    errors = {}

    #Deliberately loose: the only way to truly validate an address is to send
    #mail to it, and anything stricter mostly rejects real addresses.
    if not email:
        errors["email"] = "Email is required."
    elif "@" not in email or "." not in email.split("@")[-1]:
        errors["email"] = "Enter a valid email address."
    elif len(email) > 255:
        errors["email"] = "That email is too long."

    if not password:
        errors["password"] = "Password is required."
    elif len(password) < MIN_PASSWORD_LENGTH:
        errors["password"] = (
            f"Use at least {MIN_PASSWORD_LENGTH} characters."
        )

    if confirm is not None and password != confirm:
        errors["confirm"] = "The two passwords do not match."

    return errors


@auth.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = User.normalise_email(request.form.get("email"))
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""

        errors = validate_credentials(email, password, confirm)

        if not errors and User.query.filter_by(email=email).first():
            errors["email"] = "That email already has an account."

        if errors:
            return render_template(
                "register.html", data={"email": email}, errors=errors
            ), 400

        user = User(email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        #Straight in rather than bouncing them to the login form to retype
        #what they just typed.
        login_user(user, remember=True)

        flash("Account created. Your transactions are private to you.", "success")
        return redirect(url_for("dashboard"))

    return render_template("register.html", data={}, errors={})


@auth.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = User.normalise_email(request.form.get("email"))
        password = request.form.get("password") or ""

        user = User.query.filter_by(email=email).first()

        if user is None or not user.check_password(password):
            #One message for both cases on purpose. Saying "no such account"
            #would let anyone check which emails are registered here.
            flash("Wrong email or password.", "error")
            return render_template(
                "login.html",
                data={"email": email},
                errors={"password": "Wrong email or password."},
            ), 401

        login_user(user, remember=True)

        target = request.args.get("next")
        return redirect(target if is_safe_next(target) else url_for("dashboard"))

    return render_template("login.html", data={}, errors={})


@auth.route("/logout", methods=["POST"])
@login_required
def logout():
    """
    POST only. A plain <a href="/logout"> can be triggered by any other site
    embedding it as an image, which is a small but pointless annoyance.
    """
    logout_user()
    flash("Signed out.", "success")
    return redirect(url_for("auth.login"))
