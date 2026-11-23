import os
import secrets
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import wraps
from io import BytesIO

import click
from dotenv import load_dotenv
from flask import Flask, abort, flash, make_response, redirect, render_template, request, send_file, session, url_for
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_
from werkzeug.security import check_password_hash, generate_password_hash
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:YOUR_DATABASE_PASSWORD@db.tgoxglzjwwvigvahoxml.supabase.co:5432/postgres?sslmode=require"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("COOKIE_SECURE", "false").lower() == "true"
app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["REMEMBER_COOKIE_SECURE"] = os.getenv("COOKIE_SECURE", "false").lower() == "true"
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

db = SQLAlchemy(app)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please sign in to continue."
login_manager.login_message_category = "info"


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")
    student_id = db.Column(db.String(40), unique=True, nullable=True, index=True)
    department = db.Column(db.String(100), nullable=True)
    academic_year = db.Column(db.String(30), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    fees = db.relationship("Fee", backref="student", lazy=True, cascade="all, delete-orphan")
    payments = db.relationship("Payment", backref="student", lazy=True, cascade="all, delete-orphan", foreign_keys="Payment.student_id")


class Fee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    fee_name = db.Column(db.String(120), nullable=False)
    academic_year = db.Column(db.String(30), nullable=False)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    payments = db.relationship("Payment", backref="fee", lazy=True, cascade="all, delete-orphan")

    @property
    def paid_amount(self):
        return sum((p.amount for p in self.payments), Decimal("0.00"))

    @property
    def balance(self):
        return max(Decimal("0.00"), Decimal(self.total_amount) - self.paid_amount)


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    receipt_no = db.Column(db.String(32), unique=True, nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    fee_id = db.Column(db.Integer, db.ForeignKey("fee.id"), nullable=False, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.String(30), nullable=False)
    reference = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.String(250), nullable=True)
    recorded_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    paid_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != "admin":
            abort(403)
        return fn(*args, **kwargs)
    return wrapped


def student_required(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != "student":
            abort(403)
        return fn(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_globals():
    return {"current_year": datetime.now().year}


@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("admin_dashboard" if current_user.role == "admin" else "student_dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin_dashboard" if current_user.role == "admin" else "student_dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            session.permanent = False
            next_url = request.args.get("next")
            if next_url and next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect(url_for("admin_dashboard" if user.role == "admin" else "student_dashboard"))
        flash("Email or password is incorrect.", "error")
    return render_template("login.html")


@app.post("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("login"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    student_count = User.query.filter_by(role="student").count()
    fee_total = db.session.query(func.coalesce(func.sum(Fee.total_amount), 0)).scalar()
    paid_total = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).scalar()
    outstanding = Decimal(str(fee_total)) - Decimal(str(paid_total))
    recent = Payment.query.order_by(Payment.paid_at.desc()).limit(8).all()
    return render_template("admin_dashboard.html", student_count=student_count,
                           fee_total=fee_total, paid_total=paid_total,
                           outstanding=max(Decimal("0.00"), outstanding), recent=recent)


@app.route("/admin/students", methods=["GET", "POST"])
@admin_required
def students():
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        sid = request.form.get("student_id", "").strip()
        department = request.form.get("department", "").strip()
        year = request.form.get("academic_year", "").strip()
        password = request.form.get("password", "")
        if not all([name, email, sid, password]):
            flash("Name, email, student ID and temporary password are required.", "error")
        elif len(password) < 10:
            flash("Temporary password must be at least 10 characters.", "error")
        elif User.query.filter(or_(User.email == email, User.student_id == sid)).first():
            flash("That email or student ID is already registered.", "error")
        else:
            db.session.add(User(full_name=name, email=email, student_id=sid,
                                department=department or None, academic_year=year or None,
                                password_hash=generate_password_hash(password), role="student"))
            db.session.commit()
            flash("Student account created.", "success")
            return redirect(url_for("students"))
    q = request.args.get("q", "").strip()
    query = User.query.filter_by(role="student")
    if q:
        query = query.filter(or_(User.full_name.ilike(f"%{q}%"),
                                 User.email.ilike(f"%{q}%"),
                                 User.student_id.ilike(f"%{q}%")))
    rows = query.order_by(User.full_name.asc()).all()
    return render_template("students.html", students=rows, search=q)


@app.route("/admin/students/<int:student_id>/delete", methods=["POST"])
@admin_required
def delete_student(student_id):
    student = User.query.filter_by(id=student_id, role="student").first_or_404()
    db.session.delete(student)
    db.session.commit()
    flash("Student and related fee records were deleted.", "success")
    return redirect(url_for("students"))


@app.route("/admin/fees", methods=["GET", "POST"])
@admin_required
def fees():
    if request.method == "POST":
        student = User.query.filter_by(id=request.form.get("student_id", type=int), role="student").first()
        name = request.form.get("fee_name", "").strip()
        year = request.form.get("academic_year", "").strip()
        try:
            amount = Decimal(request.form.get("total_amount", ""))
            due = date.fromisoformat(request.form["due_date"]) if request.form.get("due_date") else None
            if amount <= 0 or amount > Decimal("99999999.99"):
                raise InvalidOperation()
        except (InvalidOperation, ValueError, KeyError):
            flash("Enter a valid fee amount and due date.", "error")
        else:
            if not student or not name or not year:
                flash("Select a student and complete all required fields.", "error")
            else:
                db.session.add(Fee(student_id=student.id, fee_name=name, academic_year=year,
                                   total_amount=amount, due_date=due))
                db.session.commit()
                flash("Fee assigned successfully.", "success")
                return redirect(url_for("fees"))
    fee_rows = Fee.query.order_by(Fee.created_at.desc()).all()
    student_rows = User.query.filter_by(role="student").order_by(User.full_name).all()
    return render_template("fees.html", fees=fee_rows, students=student_rows)


@app.route("/admin/payments", methods=["GET", "POST"])
@admin_required
def payments():
    if request.method == "POST":
        fee = Fee.query.get_or_404(request.form.get("fee_id", type=int))
        try:
            amount = Decimal(request.form.get("amount", ""))
            if amount <= 0 or amount > fee.balance:
                raise InvalidOperation()
        except (InvalidOperation, TypeError):
            flash("Enter an amount greater than zero and no more than the outstanding balance.", "error")
        else:
            method = request.form.get("payment_method", "")
            if method not in {"Cash", "Bank Transfer", "UPI", "Card", "Cheque"}:
                flash("Choose a valid payment method.", "error")
            else:
                payment = Payment(
                    receipt_no="CFM-" + secrets.token_hex(5).upper(),
                    student_id=fee.student_id, fee_id=fee.id, amount=amount,
                    payment_method=method, reference=request.form.get("reference", "").strip()[:100] or None,
                    notes=request.form.get("notes", "").strip()[:250] or None,
                    recorded_by=current_user.id
                )
                db.session.add(payment)
                db.session.commit()
                flash(f"Payment recorded. Receipt {payment.receipt_no} is ready.", "success")
                return redirect(url_for("receipt", payment_id=payment.id))
    fee_rows = Fee.query.order_by(Fee.created_at.desc()).all()
    payment_rows = Payment.query.order_by(Payment.paid_at.desc()).limit(100).all()
    return render_template("payments.html", fees=fee_rows, payments=payment_rows)


@app.route("/admin/reports")
@admin_required
def reports():
    fee_rows = Fee.query.order_by(Fee.academic_year.desc(), Fee.id.desc()).all()
    paid = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).scalar()
    total = db.session.query(func.coalesce(func.sum(Fee.total_amount), 0)).scalar()
    return render_template("reports.html", fees=fee_rows, paid=paid, total=total,
                           outstanding=max(Decimal("0.00"), Decimal(str(total)) - Decimal(str(paid))))


@app.route("/student")
@student_required
def student_dashboard():
    fee_rows = Fee.query.filter_by(student_id=current_user.id).order_by(Fee.created_at.desc()).all()
    payments_rows = Payment.query.filter_by(student_id=current_user.id).order_by(Payment.paid_at.desc()).limit(10).all()
    total = sum((Decimal(f.total_amount) for f in fee_rows), Decimal("0.00"))
    paid = sum((f.paid_amount for f in fee_rows), Decimal("0.00"))
    return render_template("student_dashboard.html", fees=fee_rows, payments=payments_rows,
                           total=total, paid=paid, balance=max(Decimal("0.00"), total-paid))


@app.route("/student/receipts")
@student_required
def student_receipts():
    rows = Payment.query.filter_by(student_id=current_user.id).order_by(Payment.paid_at.desc()).all()
    return render_template("student_receipts.html", payments=rows)


def get_visible_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    if current_user.role == "student" and payment.student_id != current_user.id:
        abort(404)
    return payment


@app.route("/receipt/<int:payment_id>")
@login_required
def receipt(payment_id):
    payment = get_visible_payment(payment_id)
    return render_template("receipt.html", payment=payment)


@app.route("/receipt/<int:payment_id>/pdf")
@login_required
def receipt_pdf(payment_id):
    payment = get_visible_payment(payment_id)
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle(f"Fee receipt {payment.receipt_no}")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(55, 785, "COLLEGE FEE RECEIPT")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(55, 760, "Official payment record")
    pdf.line(55, 745, 540, 745)
    lines = [
        ("Receipt number", payment.receipt_no),
        ("Student name", payment.student.full_name),
        ("Student ID", payment.student.student_id or "-"),
        ("Email", payment.student.email),
        ("Fee", payment.fee.fee_name),
        ("Academic year", payment.fee.academic_year),
        ("Amount received", f"INR {payment.amount:,.2f}"),
        ("Payment method", payment.payment_method),
        ("Reference", payment.reference or "-"),
        ("Date", payment.paid_at.strftime("%d %B %Y, %I:%M %p")),
    ]
    y = 710
    for label, value in lines:
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(60, y, label)
        pdf.setFont("Helvetica", 10)
        pdf.drawString(205, y, str(value)[:70])
        y -= 30
    pdf.line(55, y-10, 540, y-10)
    pdf.setFont("Helvetica-Oblique", 9)
    pdf.drawString(60, y-35, "This receipt confirms a payment recorded by the college.")
    pdf.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"{payment.receipt_no}.pdf",
                     mimetype="application/pdf")


@app.route("/privacy")
def privacy():
    return render_template("legal.html", page_title="Privacy Policy", page_key="privacy")


@app.route("/terms")
def terms():
    return render_template("legal.html", page_title="Terms and Conditions", page_key="terms")


@app.errorhandler(403)
def forbidden(_):
    return render_template("error.html", code=403, message="You do not have permission to view this page."), 403


@app.errorhandler(404)
def not_found(_):
    return render_template("error.html", code=404, message="The page or record could not be found."), 404


@app.cli.command("init-db")
def init_db():
    """Create database tables."""
    db.create_all()
    click.echo("Database tables created.")


@app.cli.command("create-admin")
@click.option("--name", prompt="Admin full name")
@click.option("--email", prompt="Admin email")
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
def create_admin(name, email, password):
    """Create the first or an additional administrator."""
    email = email.strip().lower()
    if len(password) < 12:
        raise click.ClickException("Admin password must be at least 12 characters.")
    if User.query.filter_by(email=email).first():
        raise click.ClickException("An account with that email already exists.")
    db.session.add(User(full_name=name.strip(), email=email,
                        password_hash=generate_password_hash(password), role="admin"))
    db.session.commit()
    click.echo("Administrator created.")


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
