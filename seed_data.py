import os
import random
import shutil
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from app import app
from models import (
    db,
    ActivityLog,
    BankAccount,
    Company,
    Customer,
    Expense,
    ExpenseCategory,
    Invoice,
    InvoiceItem,
    Payment,
    Product,
    Unit,
    User,
)

RNG = random.Random(20260531)
SEED_TAG = 'TVL_WEEKLY_SEED'

TIRUNELVELI_PRODUCTS = [
    {'name': 'Aachi Sambar Powder (200g)', 'hsn_code': '09109106', 'gst_percent': 5, 'price': 62.0},
    {'name': 'Aachi Rasam Powder (100g)', 'hsn_code': '09109107', 'gst_percent': 5, 'price': 28.0},
    {'name': 'Aachi Chicken Masala (50g)', 'hsn_code': '09109101', 'gst_percent': 5, 'price': 25.0},
    {'name': 'Aachi Mutton Masala (50g)', 'hsn_code': '09109100', 'gst_percent': 5, 'price': 27.0},
    {'name': 'Aachi Turmeric Powder (100g)', 'hsn_code': '09109103', 'gst_percent': 5, 'price': 22.0},
    {'name': 'Aachi Chilli Powder (200g)', 'hsn_code': '09042211', 'gst_percent': 5, 'price': 68.0},
    {'name': 'Toor Dal (1kg)', 'hsn_code': '07139010', 'gst_percent': 5, 'price': 148.0},
    {'name': 'Urad Dal (1kg)', 'hsn_code': '07133100', 'gst_percent': 5, 'price': 132.0},
    {'name': 'Groundnut Oil (1L)', 'hsn_code': '15089091', 'gst_percent': 5, 'price': 175.0},
    {'name': 'Coconut Oil (1L)', 'hsn_code': '15131100', 'gst_percent': 5, 'price': 210.0},
    {'name': 'Idli Rice (5kg)', 'hsn_code': '10063090', 'gst_percent': 5, 'price': 325.0},
    {'name': 'Tamarind (500g)', 'hsn_code': '08134010', 'gst_percent': 5, 'price': 78.0},
]

TIRUNELVELI_CUSTOMERS = [
    {'name': 'Sree Murugan Stores', 'gstin': '33AABCS1111L1Z1', 'address': 'Palayamkottai, Tirunelveli'},
    {'name': 'Nellai Traders', 'gstin': '33AABCN2222M1Z2', 'address': 'Vannarpettai, Tirunelveli'},
    {'name': 'Tamirabarani Super Mart', 'gstin': '33AABCT3333N1Z3', 'address': 'Melapalayam, Tirunelveli'},
    {'name': 'Arul Agency', 'gstin': '33AABCA4444P1Z4', 'address': 'Ambasamudram, Tirunelveli'},
    {'name': 'Sankarankovil Maligai', 'gstin': '33AABCS5555Q1Z5', 'address': 'Sankarankovil, Tirunelveli'},
    {'name': 'Kurinji Department Store', 'gstin': '33AABCK6666R1Z6', 'address': 'Tenkasi Road, Tirunelveli'},
    {'name': 'Anbu Stores', 'gstin': '33AABCA7777S1Z7', 'address': 'Cheranmahadevi, Tirunelveli'},
    {'name': 'Nellai Fresh Mart', 'gstin': '33AABCN8888T1Z8', 'address': 'Manur, Tirunelveli'},
]


def _sqlite_db_path():
    uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if uri.startswith('sqlite:///'):
        return uri.replace('sqlite:///', '', 1)
    return None


def _create_backup(tag):
    db_path = _sqlite_db_path()
    if not db_path or not os.path.exists(db_path):
        return None
    backups_dir = os.path.join(os.path.dirname(db_path), 'backups')
    os.makedirs(backups_dir, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(backups_dir, f'app_{tag}_{ts}.db')
    db.session.commit()
    db.engine.dispose()
    shutil.copy2(db_path, backup_path)
    return backup_path


def _ensure_user(username, password, role):
    user = User.query.filter_by(username=username).first()
    if not user:
        user = User(username=username, password_hash=generate_password_hash(password), role=role)
        db.session.add(user)
        db.session.flush()
    return user


def _ensure_unit(name, abbreviation):
    unit = Unit.query.filter((Unit.name == name) | (Unit.abbreviation == abbreviation)).first()
    if not unit:
        unit = Unit(name=name, abbreviation=abbreviation)
        db.session.add(unit)
        db.session.flush()
    return unit


def _ensure_company():
    company = Company.query.first()
    if not company:
        company = Company(
            title='Nellai Bill Mart',
            header='Tirunelveli GST Billing and Inventory',
            gst_number='33ABCDE1234F1Z5',
            phone_number='0462-2501234',
            address='No. 12, South Bypass Road, Palayamkottai, Tirunelveli - 627002',
            logo=None,
        )
        db.session.add(company)
    return company


def _ensure_products(default_unit):
    created = 0
    for prod in TIRUNELVELI_PRODUCTS:
        existing = Product.query.filter_by(name=prod['name']).first()
        if existing:
            continue
        db.session.add(
            Product(
                name=prod['name'],
                hsn_code=prod['hsn_code'],
                gst_percent=prod['gst_percent'],
                price=prod['price'],
                unit_id=default_unit.id,
            )
        )
        created += 1
    return created


def _ensure_customers():
    created = 0
    for customer in TIRUNELVELI_CUSTOMERS:
        existing = Customer.query.filter_by(name=customer['name']).first()
        if existing:
            continue
        db.session.add(Customer(**customer))
        created += 1
    return created


def _ensure_bank_accounts():
    accounts = [
        ('IOB - Tirunelveli Main', 'current', 250000.0),
        ('SBI - Palayamkottai', 'current', 180000.0),
    ]
    created = 0
    for name, account_type, opening_balance in accounts:
        existing = BankAccount.query.filter_by(account_name=name).first()
        if existing:
            continue
        db.session.add(
            BankAccount(
                account_name=name,
                account_type=account_type,
                opening_balance=opening_balance,
                is_active=True,
            )
        )
        created += 1
    return created


def _ensure_expense_categories():
    names = ['Rent', 'Salary', 'Transport', 'Utilities', 'Maintenance', 'Miscellaneous']
    created = 0
    for name in names:
        existing = ExpenseCategory.query.filter_by(name=name).first()
        if existing:
            continue
        db.session.add(ExpenseCategory(name=name, is_active=True))
        created += 1
    return created


def _next_invoice_number():
    last = Invoice.query.order_by(Invoice.id.desc()).first()
    if last and last.invoice_number and last.invoice_number.startswith('INV'):
        try:
            return int(last.invoice_number[3:]) + 1
        except ValueError:
            return last.id + 1
    return 1


def _add_invoice_item(invoice_id, product, qty):
    item_total = round(product.price * qty, 2)
    item_gst = round(item_total * product.gst_percent / 100.0, 2)
    item_cgst = round(item_gst / 2.0, 2)
    item_sgst = round(item_gst / 2.0, 2)
    line_total = round(item_total + item_gst, 2)
    db.session.add(
        InvoiceItem(
            invoice_id=invoice_id,
            product_id=product.id,
            quantity=qty,
            price=product.price,
            gst_percent=product.gst_percent,
            cgst=item_cgst,
            sgst=item_sgst,
            total=line_total,
        )
    )
    return item_cgst, item_sgst, line_total


def _seed_weekly_invoices(admin_user, customers, products, bank_accounts):
    payment_modes = ['cash', 'upi', 'bank_transfer', 'card', 'cheque']
    next_no = _next_invoice_number()
    created_invoices = 0
    created_payments = 0

    for offset in range(6, -1, -1):
        day = (datetime.now() - timedelta(days=offset)).replace(hour=11, minute=30, second=0, microsecond=0)
        for _ in range(4):
            customer = RNG.choice(customers)
            invoice = Invoice(
                invoice_number=f'INV{next_no:05d}',
                customer_name=customer.name,
                customer_gstin=customer.gstin,
                customer_address=customer.address,
                date=day,
                total=0,
                cgst=0,
                sgst=0,
                payment_status='unpaid',
                paid_amount=0,
                balance_amount=0,
                user_id=admin_user.id,
            )
            db.session.add(invoice)
            db.session.flush()

            num_items = RNG.randint(1, 3)
            selected_products = RNG.sample(products, num_items)
            cgst_total = 0.0
            sgst_total = 0.0
            grand_total = 0.0
            for prod in selected_products:
                qty = RNG.randint(1, 6)
                item_cgst, item_sgst, line_total = _add_invoice_item(invoice.id, prod, qty)
                cgst_total += item_cgst
                sgst_total += item_sgst
                grand_total += line_total

            invoice.cgst = round(cgst_total, 2)
            invoice.sgst = round(sgst_total, 2)
            invoice.total = round(grand_total, 2)

            status_roll = RNG.random()
            if status_roll < 0.40:
                target_paid = invoice.total
            elif status_roll < 0.75:
                target_paid = round(invoice.total * RNG.uniform(0.35, 0.8), 2)
            else:
                target_paid = 0.0

            if target_paid > 0:
                split_count = 1 if target_paid == invoice.total or RNG.random() < 0.65 else 2
                remaining = target_paid
                for split_idx in range(split_count):
                    if split_idx == split_count - 1:
                        pay_amount = round(remaining, 2)
                    else:
                        pay_amount = round(max(1.0, remaining * RNG.uniform(0.35, 0.65)), 2)
                        remaining = round(remaining - pay_amount, 2)

                    mode = RNG.choice(payment_modes)
                    bank_account_id = None
                    if mode != 'cash' and bank_accounts and RNG.random() < 0.85:
                        bank_account_id = RNG.choice(bank_accounts).id

                    payment = Payment(
                        invoice_id=invoice.id,
                        amount=pay_amount,
                        payment_date=day + timedelta(hours=split_idx + 1),
                        payment_mode=mode,
                        bank_account_id=bank_account_id,
                        reference_no=f'{SEED_TAG}-PAY-{invoice.invoice_number}-{split_idx + 1}',
                        notes=f'{SEED_TAG} payment',
                        received_by=admin_user.id,
                    )
                    db.session.add(payment)
                    created_payments += 1

            paid = round(target_paid, 2)
            balance = round(max(invoice.total - paid, 0.0), 2)
            invoice.paid_amount = paid
            invoice.balance_amount = balance
            if paid <= 0:
                invoice.payment_status = 'unpaid'
            elif balance <= 0:
                invoice.payment_status = 'paid'
            else:
                invoice.payment_status = 'partial'

            invoice.payment_mode = None
            invoice.reference_no = f'{SEED_TAG}-INV-{invoice.invoice_number}'
            next_no += 1
            created_invoices += 1

    return created_invoices, created_payments


def _seed_weekly_expenses(admin_user, bank_accounts):
    categories = ExpenseCategory.query.filter_by(is_active=True).all()
    created = 0
    for offset in range(6, -1, -1):
        day = (datetime.now() - timedelta(days=offset)).replace(hour=19, minute=0, second=0, microsecond=0)
        entries = [
            ('Transport', RNG.uniform(250, 1200), 'cash'),
            ('Utilities', RNG.uniform(300, 1800), 'bank_transfer'),
            ('Maintenance', RNG.uniform(200, 1500), 'upi'),
        ]
        for cat_name, amount, mode in entries:
            category = next((c for c in categories if c.name == cat_name), None)
            if not category:
                continue
            bank_account_id = None
            if mode != 'cash' and bank_accounts:
                bank_account_id = RNG.choice(bank_accounts).id
            db.session.add(
                Expense(
                    expense_date=day,
                    category_id=category.id,
                    amount=round(amount, 2),
                    payment_mode=mode,
                    bank_account_id=bank_account_id,
                    reference_no=f'{SEED_TAG}-EXP-{day.strftime("%Y%m%d")}-{cat_name[:3].upper()}',
                    description=f'{cat_name} expense for Tirunelveli operations ({SEED_TAG})',
                    created_by_user_id=admin_user.id,
                )
            )
            created += 1
    return created


def _add_activity_log(user, action, details):
    db.session.add(
        ActivityLog(
            user_id=user.id,
            username=user.username,
            action=action,
            details=details,
        )
    )


with app.app_context():
    pre_backup = _create_backup('before_seed')

    admin = _ensure_user('admin', 'admin', 'admin')
    _ensure_user('approver', 'approver123', 'approver')
    _ensure_user('staff1', 'staff123', 'staff')

    default_unit = _ensure_unit('Nos', 'NOS')
    _ensure_company()
    product_created = _ensure_products(default_unit)
    customer_created = _ensure_customers()
    bank_created = _ensure_bank_accounts()
    category_created = _ensure_expense_categories()

    db.session.commit()

    products = Product.query.order_by(Product.id.asc()).all()
    customers = Customer.query.order_by(Customer.id.asc()).all()
    bank_accounts = BankAccount.query.filter_by(is_active=True).order_by(BankAccount.id.asc()).all()

    invoice_created, payment_created = _seed_weekly_invoices(admin, customers, products, bank_accounts)
    expense_created = _seed_weekly_expenses(admin, bank_accounts)

    _add_activity_log(
        admin,
        'Weekly Test Data Seeded',
        (
            f'{SEED_TAG}: products={product_created}, customers={customer_created}, '
            f'bank_accounts={bank_created}, categories={category_created}, '
            f'invoices={invoice_created}, payments={payment_created}, expenses={expense_created}'
        ),
    )

    db.session.commit()
    post_backup = _create_backup('after_seed')

    print('Seeding complete for last 7 days (Tirunelveli-focused).')
    print(f'Products created this run: {product_created}')
    print(f'Customers created this run: {customer_created}')
    print(f'Bank accounts created this run: {bank_created}')
    print(f'Expense categories created this run: {category_created}')
    print(f'Invoices created: {invoice_created}')
    print(f'Payments created: {payment_created}')
    print(f'Expenses created: {expense_created}')
    if pre_backup:
        print(f'Backup before seeding: {pre_backup}')
    if post_backup:
        print(f'Backup after seeding: {post_backup}')
