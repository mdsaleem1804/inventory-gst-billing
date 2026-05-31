from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from sqlalchemy import inspect, text, func

db = SQLAlchemy()

# Unit model (after db is initialized)
class Unit(db.Model):
    __tablename__ = 'units'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), unique=True, nullable=False)
    abbreviation = db.Column(db.String(16), unique=True, nullable=False)
    products = db.relationship('Product', backref='unit', lazy=True)

# AuditMixin must be defined after db is initialized
class AuditMixin(object):
    created_by = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)


class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(32), default='staff', nullable=False)  # 'admin' or 'staff'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# Activity log for auditing
class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    username = db.Column(db.String(64))
    action = db.Column(db.String(256))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    details = db.Column(db.Text)
    user = db.relationship('User')

class Product(db.Model, AuditMixin):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    hsn_code = db.Column(db.String(32), nullable=False)
    gst_percent = db.Column(db.Float, nullable=False)
    price = db.Column(db.Float, nullable=False)
    unit_id = db.Column(db.Integer, db.ForeignKey('units.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Invoice(db.Model, AuditMixin):
    __tablename__ = 'invoices'
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(32), unique=True, nullable=False)
    customer_name = db.Column(db.String(128), nullable=False)
    customer_gstin = db.Column(db.String(32))
    customer_address = db.Column(db.String(256))
    date = db.Column(db.DateTime, default=datetime.utcnow)
    total = db.Column(db.Float, nullable=False)
    cgst = db.Column(db.Float, nullable=False)
    sgst = db.Column(db.Float, nullable=False)
    payment_status = db.Column(db.String(16), nullable=False, default='unpaid')
    paid_amount = db.Column(db.Float, nullable=False, default=0)
    balance_amount = db.Column(db.Float, nullable=False, default=0)
    payment_date = db.Column(db.DateTime, nullable=True)
    payment_mode = db.Column(db.String(32), nullable=True)
    reference_no = db.Column(db.String(64), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    user = db.relationship('User', backref='invoices')
    items = db.relationship('InvoiceItem', backref='invoice', lazy=True)
    payments = db.relationship('Payment', backref='invoice', lazy=True, cascade='all, delete-orphan')

class InvoiceItem(db.Model, AuditMixin):
    __tablename__ = 'invoice_items'
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'))
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    gst_percent = db.Column(db.Float, nullable=False)
    cgst = db.Column(db.Float, nullable=False)
    sgst = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)
    product = db.relationship('Product')


class Payment(db.Model, AuditMixin):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    payment_mode = db.Column(db.String(32), nullable=True)
    bank_account_id = db.Column(db.Integer, db.ForeignKey('bank_accounts.id'), nullable=True)
    reference_no = db.Column(db.String(64), nullable=True)
    notes = db.Column(db.String(256), nullable=True)
    received_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    received_by_user = db.relationship('User')
    bank_account = db.relationship('BankAccount')


class BankAccount(db.Model, AuditMixin):
    __tablename__ = 'bank_accounts'
    id = db.Column(db.Integer, primary_key=True)
    account_name = db.Column(db.String(128), unique=True, nullable=False)
    account_type = db.Column(db.String(32), nullable=False, default='current')
    opening_balance = db.Column(db.Float, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class ExpenseCategory(db.Model, AuditMixin):
    __tablename__ = 'expense_categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class Expense(db.Model, AuditMixin):
    __tablename__ = 'expenses'
    id = db.Column(db.Integer, primary_key=True)
    expense_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    category_id = db.Column(db.Integer, db.ForeignKey('expense_categories.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_mode = db.Column(db.String(32), nullable=False, default='cash')
    bank_account_id = db.Column(db.Integer, db.ForeignKey('bank_accounts.id'), nullable=True)
    reference_no = db.Column(db.String(64), nullable=True)
    description = db.Column(db.String(256), nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    category = db.relationship('ExpenseCategory')
    bank_account = db.relationship('BankAccount')
    created_by_user = db.relationship('User')

class Customer(db.Model, AuditMixin):
    __tablename__ = 'customers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    gstin = db.Column(db.String(20))
    address = db.Column(db.String(200))


# Company model for storing company information
class Company(db.Model):
    __tablename__ = 'company'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(128), nullable=False)
    header = db.Column(db.String(256), nullable=True)
    gst_number = db.Column(db.String(32), nullable=False)
    phone_number = db.Column(db.String(32), nullable=True)
    address = db.Column(db.String(256), nullable=True)
    logo = db.Column(db.String(256), nullable=True)  # Path to logo image
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def _normalize_payment_mode_value(mode):
    if mode is None:
        return None
    value = str(mode).strip().lower().replace('-', ' ').replace('_', ' ')
    if not value:
        return None
    if value in {'cash'}:
        return 'cash'
    if value in {'upi'}:
        return 'upi'
    if value in {'card', 'credit card', 'debit card'}:
        return 'card'
    if value in {'bank transfer', 'banktransfer', 'neft', 'rtgs', 'imps'}:
        return 'bank_transfer'
    if value in {'cheque', 'check'}:
        return 'cheque'
    return value.replace(' ', '_')


def ensure_billing_schema():
    inspector = inspect(db.engine)
    table_names = inspector.get_table_names()

    if 'invoices' in table_names:
        columns = {col['name'] for col in inspector.get_columns('invoices')}
        alter_statements = []
        if 'payment_status' not in columns:
            alter_statements.append("ALTER TABLE invoices ADD COLUMN payment_status VARCHAR(16) DEFAULT 'unpaid'")
        if 'paid_amount' not in columns:
            alter_statements.append("ALTER TABLE invoices ADD COLUMN paid_amount FLOAT DEFAULT 0")
        if 'balance_amount' not in columns:
            alter_statements.append("ALTER TABLE invoices ADD COLUMN balance_amount FLOAT DEFAULT 0")
        if 'payment_date' not in columns:
            alter_statements.append("ALTER TABLE invoices ADD COLUMN payment_date DATETIME")
        if 'payment_mode' not in columns:
            alter_statements.append("ALTER TABLE invoices ADD COLUMN payment_mode VARCHAR(32)")
        if 'reference_no' not in columns:
            alter_statements.append("ALTER TABLE invoices ADD COLUMN reference_no VARCHAR(64)")

        if alter_statements:
            with db.engine.begin() as connection:
                for stmt in alter_statements:
                    connection.execute(text(stmt))

        with db.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE invoices
                    SET
                        paid_amount = COALESCE(paid_amount, 0),
                        balance_amount = CASE
                            WHEN balance_amount IS NULL OR balance_amount = 0 THEN total - COALESCE(paid_amount, 0)
                            ELSE balance_amount
                        END,
                        payment_status = CASE
                            WHEN COALESCE(paid_amount, 0) <= 0 THEN 'unpaid'
                            WHEN total - COALESCE(paid_amount, 0) <= 0 THEN 'paid'
                            ELSE 'partial'
                        END
                    """
                )
            )

    BankAccount.__table__.create(bind=db.engine, checkfirst=True)
    ExpenseCategory.__table__.create(bind=db.engine, checkfirst=True)
    Expense.__table__.create(bind=db.engine, checkfirst=True)
    if 'invoices' in table_names:
        Payment.__table__.create(bind=db.engine, checkfirst=True)

    inspector = inspect(db.engine)
    table_names = inspector.get_table_names()
    if 'payments' in table_names:
        payment_columns = {col['name'] for col in inspector.get_columns('payments')}
        alter_statements = []
        if 'bank_account_id' not in payment_columns:
            alter_statements.append('ALTER TABLE payments ADD COLUMN bank_account_id INTEGER')
        if alter_statements:
            with db.engine.begin() as connection:
                for stmt in alter_statements:
                    connection.execute(text(stmt))

    # Seed default expense categories once for usability.
    default_categories = ['Rent', 'Salary', 'Utilities', 'Transport', 'Maintenance', 'Miscellaneous']
    for name in default_categories:
        existing = ExpenseCategory.query.filter(func.lower(ExpenseCategory.name) == name.lower()).first()
        if not existing:
            db.session.add(ExpenseCategory(name=name))

    # Normalize historical payment mode values to keep reporting consistent.
    changed = False
    if 'payments' in table_names:
        for pay in Payment.query.all():
            normalized = _normalize_payment_mode_value(pay.payment_mode)
            if normalized != pay.payment_mode:
                pay.payment_mode = normalized
                changed = True

    if 'invoices' in table_names:
        for inv in Invoice.query.all():
            normalized = _normalize_payment_mode_value(inv.payment_mode)
            if normalized != inv.payment_mode:
                inv.payment_mode = normalized
                changed = True

    if 'expenses' in table_names:
        for exp in Expense.query.all():
            normalized = _normalize_payment_mode_value(exp.payment_mode)
            if normalized != exp.payment_mode:
                exp.payment_mode = normalized or 'cash'
                changed = True

    if changed or db.session.new:
        db.session.commit()
