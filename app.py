from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime

app = Flask(__name__)

app.config['SECRET_KEY'] = 'your_secret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///expense_splitter.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# ---------------- MODELS ----------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False, unique=True)
    email = db.Column(db.String(150), nullable=False, unique=True)
    password = db.Column(db.String(100), nullable=False)

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    members = db.relationship('GroupMember', back_populates='group', lazy=True)

class GroupMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    group = db.relationship('Group', back_populates='members')
    user = db.relationship('User')  # For easy user attribute access in templates

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    paid_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    payer = db.relationship('User')  # To access payer username in templates
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

# -------------- LOGIN MANAGER --------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# -------------- ROUTES ----------------
@app.route('/')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)

@app.route('/signup', methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")

        if User.query.filter_by(email=email).first():
            flash("Email already exists", "error")
            return redirect(url_for('signup'))

        new_user = User(
            username=username,
            email=email,
            password=generate_password_hash(password, method="pbkdf2:sha256")
        )
        db.session.add(new_user)
        db.session.commit()
        flash("Account created! Please Login.", "success")
        return redirect(url_for('login'))

    return render_template("signup.html")

@app.route('/login', methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password, password):
            flash("Invalid credentials", "error")
            return redirect(url_for("login"))

        login_user(user)
        return redirect(url_for('groups'))

    return render_template("login.html")

@app.route("/groups")
@login_required
def groups():
    my_groups = GroupMember.query.filter_by(user_id=current_user.id).all()
    return render_template("groups.html", groups=my_groups)

@app.route('/create_group', methods=["GET", "POST"])
@login_required
def create_group():
    if request.method == "POST":
        name = request.form.get("name")
        if not name:
            flash("Group name required", 'error')
            return redirect(url_for('create_group'))

        new_group = Group(name=name, created_by=current_user.id)
        db.session.add(new_group)
        db.session.commit()

        membership = GroupMember(group_id=new_group.id, user_id=current_user.id)
        db.session.add(membership)
        db.session.commit()

        flash("Group created successfully", 'success')
        return redirect(url_for('groups'))

    return render_template("create_group.html")

@app.route('/group/<int:group_id>')
@login_required
def view_group(group_id):
    group = Group.query.get_or_404(group_id)
    expenses = Expense.query.filter_by(group_id=group_id).all()
    members = GroupMember.query.filter_by(group_id=group_id).all()

    balances = {m.user_id: 0 for m in members}

    if expenses and members:
        total_amount = sum(exp.amount for exp in expenses)
        share = total_amount / len(members)

        for exp in expenses:
            balances[exp.paid_by] += exp.amount

        for user_id in balances:
            balances[user_id] -= share

    balances_display = {
        User.query.get(uid).username: round(amount, 2)
        for uid, amount in balances.items()
    }

    return render_template(
        'view_group.html',
        group=group,
        expenses=expenses,
        balances=balances_display
    )

@app.route('/group/<int:group_id>/add_expense', methods=['GET', 'POST'])
@login_required
def add_expense(group_id):
    # Always fetch the group so both GET and POST have it
    group = Group.query.get_or_404(group_id)

    if request.method == 'POST':
        description = request.form.get('description')
        amount = request.form.get('amount')

        if not description or not amount:
            flash("Please enter all fields", "error")
            return redirect(url_for('add_expense', group_id=group_id))

        try:
            amount_value = float(amount)
        except ValueError:
            flash("Please enter a valid amount", "error")
            return redirect(url_for('add_expense', group_id=group_id))

        expense = Expense(
            group_id=group_id,
            paid_by=current_user.id,
            description=description,
            amount=amount_value
        )
        db.session.add(expense)
        db.session.commit()

        flash("Expense added!", "success")
        return redirect(url_for('view_group', group_id=group_id))

    # GET request — render the form page
    return render_template('add_expense.html', group=group)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# -------------- RUN APP ----------------
if __name__ == "__main__":
    os.makedirs("instance", exist_ok=True)
    with app.app_context():
        db.create_all()
    app.run(debug=True)
