import random
import re
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from app import app
from models import (
    db,
    ensure_billing_schema,
    User,
    Unit,
    Company,
    Customer,
    Product,
    Invoice,
    InvoiceItem,
    Payment,
    BankAccount,
    ExpenseCategory,
    Expense,
    FollowUpTask,
    PromiseToPay,
    ReminderTemplate,
    ActivityLog,
)

RNG = random.Random(20260604)

TAMIL_PRODUCTS = [
    {"name": "ஆச்சி மசாலா", "hsn_code": "09109110", "gst_percent": 5.0, "price": 62.0},
    {"name": "சக்தி மசாலா", "hsn_code": "09109111", "gst_percent": 5.0, "price": 58.0},
    {"name": "இட்லி மாவு", "hsn_code": "19059040", "gst_percent": 5.0, "price": 42.0},
    {"name": "தோசை மாவு", "hsn_code": "19059040", "gst_percent": 5.0, "price": 45.0},
    {"name": "சாம்பார் பொடி", "hsn_code": "09109120", "gst_percent": 5.0, "price": 49.0},
    {"name": "ரசம் பொடி", "hsn_code": "09109121", "gst_percent": 5.0, "price": 38.0},
    {"name": "மிளகாய் பொடி", "hsn_code": "09042212", "gst_percent": 5.0, "price": 86.0},
    {"name": "மஞ்சள் பொடி", "hsn_code": "09103010", "gst_percent": 5.0, "price": 36.0},
    {"name": "கொத்தமல்லி பொடி", "hsn_code": "09109913", "gst_percent": 5.0, "price": 40.0},
    {"name": "மிளகு பொடி", "hsn_code": "09041120", "gst_percent": 5.0, "price": 92.0},
    {"name": "தேங்காய் எண்ணெய் 1 லிட்டர்", "hsn_code": "15131100", "gst_percent": 5.0, "price": 210.0},
    {"name": "கடலை எண்ணெய் 1 லிட்டர்", "hsn_code": "15089091", "gst_percent": 5.0, "price": 176.0},
    {"name": "தூர் தால் 1 கிலோ", "hsn_code": "07139010", "gst_percent": 5.0, "price": 154.0},
    {"name": "உளுந்து 1 கிலோ", "hsn_code": "07133100", "gst_percent": 5.0, "price": 136.0},
    {"name": "அரிசி 5 கிலோ", "hsn_code": "10063090", "gst_percent": 5.0, "price": 328.0},
    {"name": "சீரக சம்பா அரிசி", "hsn_code": "10063090", "gst_percent": 5.0, "price": 112.0},
    {"name": "கம்பு மாவு", "hsn_code": "11029090", "gst_percent": 5.0, "price": 54.0},
    {"name": "ராகி மாவு", "hsn_code": "11029090", "gst_percent": 5.0, "price": 57.0},
    {"name": "சுக்கு காபி பொடி", "hsn_code": "21011200", "gst_percent": 12.0, "price": 98.0},
    {"name": "நாட்டு சர்க்கரை", "hsn_code": "17011420", "gst_percent": 5.0, "price": 68.0},
]

TN_LOCATIONS = [
    ("சென்னை", "அண்ணா நகர்", "600040"),
    ("சென்னை", "அடையார்", "600020"),
    ("மதுரை", "கே.கே. நகர்", "625020"),
    ("மதுரை", "திருப்பரங்குன்றம்", "625005"),
    ("கோயம்புத்தூர்", "சரவணம்பட்டி", "641035"),
    ("கோயம்புத்தூர்", "ஆர்எஸ் புரம்", "641002"),
    ("திருச்சி", "சத்திரம்", "620002"),
    ("திருச்சி", "தில்லைநகர்", "620018"),
    ("சேலம்", "அஸ்தம்பட்டி", "636007"),
    ("சேலம்", "அம்மாபேட்டை", "636003"),
    ("திருநெல்வேலி", "பலயம்கோட்டை", "627002"),
    ("திருநெல்வேலி", "வண்ணார்பேட்டை", "627003"),
    ("ஈரோடு", "பெருந்துறை", "638052"),
    ("வேலூர்", "காட்ட்பாடி", "632007"),
    ("தூத்துக்குடி", "மில்லர்புரம்", "628008"),
]

SHOP_PREFIX = [
    "முருகன்", "அம்மா", "அருள்", "செல்வம்", "வள்ளி", "சக்தி", "கோபால்", "சிவா", "மாரி", "கவி",
    "லட்சுமி", "ஆதி", "விஜய்", "தமிழ்", "நெல்லை", "திரு", "மீனா", "கோமதி", "பூங்கொடி", "தென்றல்",
]

SHOP_SUFFIX = ["ஸ்டோர்ஸ்", "மார்ட்", "சூப்பர் மார்கெட்", "மளிகை", "டிரேடர்ஸ்", "டெபோ", "ஏஜென்சி"]

CONTACT_NAMES = [
    "ரமேஷ்", "கார்த்திக்", "முரளி", "சரவணன்", "விநோதினி", "சித்ரா", "லதா", "திலகா", "மணிகண்டன்", "யாழினி"
]

PAYMENT_MODES = ["cash", "upi", "bank_transfer", "card", "cheque"]


def make_gstin(i):
    letters = "ABCDE"
    pan = f"{letters[i % 5]}{letters[(i + 1) % 5]}{letters[(i + 2) % 5]}{letters[(i + 3) % 5]}{letters[(i + 4) % 5]}{1000 + i:04d}{chr(65 + (i % 26))}"
    return f"33{pan}1Z{(i % 9) + 1}"


def make_mobile(i):
    first = [9, 8, 7, 6][i % 4]
    return f"{first}{700000000 + i:09d}"


def reset_database():
    db.session.remove()
    db.drop_all()
    db.create_all()
    ensure_billing_schema()
    db.session.commit()


def bootstrap_master_data():
    admin = User.query.filter_by(username="admin").first()
    if admin is None:
        admin = User(username="admin", password_hash=generate_password_hash("Admin@12345"), role="admin")
        db.session.add(admin)
    else:
        admin.password_hash = generate_password_hash("Admin@12345")
        admin.role = "admin"

    approver = User.query.filter_by(username="approver").first()
    if approver is None:
        approver = User(username="approver", password_hash=generate_password_hash("Approver@12345"), role="approver")
        db.session.add(approver)

    staff1 = User.query.filter_by(username="staff1").first()
    if staff1 is None:
        staff1 = User(username="staff1", password_hash=generate_password_hash("Staff@12345"), role="staff")
        db.session.add(staff1)

    staff2 = User.query.filter_by(username="staff2").first()
    if staff2 is None:
        staff2 = User(username="staff2", password_hash=generate_password_hash("Staff@12345"), role="staff")
        db.session.add(staff2)

    unit = Unit.query.filter((Unit.name == "Nos") | (Unit.abbreviation == "NOS")).first()
    if unit is None:
        unit = Unit(name="Nos", abbreviation="NOS")
        db.session.add(unit)

    company = Company.query.first()
    if company is None:
        company = Company(
            title="தமிழ்நாடு டெமோ ரீடெயில்",
            header="Inventory GST Billing Demo",
            gst_number="33ABCDE1234F1Z5",
            phone_number="044-40001234",
            address="அண்ணா நகர், சென்னை, தமிழ்நாடு - 600040",
            finance_enabled=True,
            credit_block_on_exceed=False,
        )
        db.session.add(company)
    else:
        company.finance_enabled = True
        company.credit_block_on_exceed = False

    bank_accounts = []
    for account_name, account_type, opening_balance in [
        ("Indian Bank - Chennai", "current", 350000.0),
        ("SBI - Madurai", "current", 250000.0),
        ("IOB - Coimbatore", "current", 190000.0),
    ]:
        bank = BankAccount.query.filter_by(account_name=account_name).first()
        if bank is None:
            bank = BankAccount(
                account_name=account_name,
                account_type=account_type,
                opening_balance=opening_balance,
                is_active=True,
            )
            db.session.add(bank)
        else:
            bank.account_type = account_type
            bank.is_active = True
        bank_accounts.append(bank)

    categories = []
    for cat_name in ["Rent", "Salary", "Transport", "Utilities", "Maintenance"]:
        category = ExpenseCategory.query.filter_by(name=cat_name).first()
        if category is None:
            category = ExpenseCategory(name=cat_name, is_active=True)
            db.session.add(category)
        else:
            category.is_active = True
        categories.append(category)

    db.session.flush()

    products = []
    for prod in TAMIL_PRODUCTS:
        p = Product(
            name=prod["name"],
            hsn_code=prod["hsn_code"],
            gst_percent=prod["gst_percent"],
            price=prod["price"],
            unit_id=unit.id,
            created_by=admin.id,
            updated_by=admin.id,
        )
        products.append(p)
        db.session.add(p)

    db.session.flush()
    return {
        "admin": admin,
        "users": [admin, approver, staff1, staff2],
        "products": products,
        "bank_accounts": bank_accounts,
        "categories": categories,
    }


def seed_customers_and_transactions(master):
    admin = master["admin"]
    users = master["users"]
    products = master["products"]
    bank_accounts = master["bank_accounts"]
    categories = master["categories"]

    customers = []
    invoice_counter = 1
    total_invoices = 0
    total_payments = 0
    total_items = 0
    total_tasks = 0
    total_promises = 0

    for i in range(80):
        city, area, pincode = TN_LOCATIONS[i % len(TN_LOCATIONS)]
        name = f"{SHOP_PREFIX[i % len(SHOP_PREFIX)]} {area} {SHOP_SUFFIX[i % len(SHOP_SUFFIX)]} {i + 1:03d}"
        mobile = make_mobile(i)

        customer = Customer(
            name=name,
            gstin=make_gstin(i) if i % 6 != 0 else "",
            address=f"{12 + (i % 70)}/{(i % 20) + 1}, {area}, {city}, தமிழ்நாடு - {pincode}",
            contact_person=CONTACT_NAMES[i % len(CONTACT_NAMES)] if i % 5 != 0 else None,
            mobile_number=mobile,
            whatsapp_number=mobile if i % 4 != 0 else None,
            reminder_opt_in=(i % 7 != 0),
            credit_limit=round(RNG.uniform(15000, 120000), 2),
            created_by=admin.id,
            updated_by=admin.id,
        )
        db.session.add(customer)
        db.session.flush()
        customers.append(customer)

        txn_count = RNG.randint(5, 10)
        for j in range(txn_count):
            inv_date = datetime.now() - timedelta(days=RNG.randint(1, 180), hours=RNG.randint(0, 20))
            invoice = Invoice(
                invoice_number=f"INV{invoice_counter:05d}",
                customer_name=customer.name,
                customer_gstin=customer.gstin,
                customer_address=customer.address,
                date=inv_date,
                total=0.0,
                cgst=0.0,
                sgst=0.0,
                payment_status="unpaid",
                paid_amount=0.0,
                balance_amount=0.0,
                user_id=admin.id,
                created_by=admin.id,
                updated_by=admin.id,
            )
            db.session.add(invoice)
            db.session.flush()
            invoice_counter += 1

            line_count = RNG.randint(1, 4)
            chosen = RNG.sample(products, line_count)
            total = 0.0
            cgst = 0.0
            sgst = 0.0

            for prod in chosen:
                qty = RNG.randint(1, 8)
                item_total = round(prod.price * qty, 2)
                item_gst = round(item_total * prod.gst_percent / 100.0, 2)
                item_cgst = round(item_gst / 2.0, 2)
                item_sgst = round(item_gst / 2.0, 2)
                line_total = round(item_total + item_gst, 2)

                item = InvoiceItem(
                    invoice_id=invoice.id,
                    product_id=prod.id,
                    quantity=qty,
                    price=prod.price,
                    gst_percent=prod.gst_percent,
                    cgst=item_cgst,
                    sgst=item_sgst,
                    total=line_total,
                    created_by=admin.id,
                    updated_by=admin.id,
                )
                db.session.add(item)
                total += line_total
                cgst += item_cgst
                sgst += item_sgst
                total_items += 1

            total = round(total, 2)
            invoice.total = total
            invoice.cgst = round(cgst, 2)
            invoice.sgst = round(sgst, 2)

            roll = RNG.random()
            if roll < 0.35:
                target_paid = total
            elif roll < 0.78:
                target_paid = round(total * RNG.uniform(0.25, 0.85), 2)
            else:
                target_paid = 0.0

            if target_paid > 0:
                splits = 2 if target_paid < total and RNG.random() < 0.5 else 1
                remaining = target_paid
                for split in range(splits):
                    if split == splits - 1:
                        amount = round(remaining, 2)
                    else:
                        amount = round(max(1.0, remaining * RNG.uniform(0.35, 0.65)), 2)
                        remaining = round(remaining - amount, 2)

                    mode = PAYMENT_MODES[(i + j + split) % len(PAYMENT_MODES)]
                    bank_account_id = None
                    if mode != "cash":
                        bank_account_id = bank_accounts[(i + split) % len(bank_accounts)].id

                    payment = Payment(
                        invoice_id=invoice.id,
                        amount=amount,
                        payment_date=inv_date + timedelta(hours=split + 1),
                        payment_mode=mode,
                        bank_account_id=bank_account_id,
                        reference_no=f"PMT-{invoice.invoice_number}-{split + 1}",
                        notes="Demo payment entry",
                        received_by=users[(i + split) % len(users)].id,
                        created_by=admin.id,
                        updated_by=admin.id,
                    )
                    db.session.add(payment)
                    total_payments += 1

            paid = round(target_paid, 2)
            balance = round(max(total - paid, 0.0), 2)
            invoice.paid_amount = paid
            invoice.balance_amount = balance
            if paid <= 0:
                invoice.payment_status = "unpaid"
            elif balance <= 0:
                invoice.payment_status = "paid"
            else:
                invoice.payment_status = "partial"

            if invoice.payment_status != "paid" and RNG.random() < 0.45:
                task = FollowUpTask(
                    customer_id=customer.id,
                    invoice_id=invoice.id,
                    title="Payment follow-up call",
                    notes="Reminder and collection follow-up",
                    due_date=(datetime.now() + timedelta(days=RNG.randint(1, 14))).date(),
                    status="open",
                    assigned_to_user_id=users[(i + j) % len(users)].id,
                    created_by=admin.id,
                    updated_by=admin.id,
                )
                db.session.add(task)
                total_tasks += 1

            if invoice.payment_status == "partial" and RNG.random() < 0.35:
                promise = PromiseToPay(
                    customer_id=customer.id,
                    invoice_id=invoice.id,
                    promised_amount=round(balance * RNG.uniform(0.4, 1.0), 2),
                    promised_date=(datetime.now() + timedelta(days=RNG.randint(3, 20))).date(),
                    note="Customer committed tentative payment date",
                    status="open",
                    created_by=admin.id,
                    updated_by=admin.id,
                )
                db.session.add(promise)
                total_promises += 1

            total_invoices += 1

    for day in range(1, 61):
        expense_date = datetime.now() - timedelta(days=day)
        cat = categories[day % len(categories)]
        mode = PAYMENT_MODES[day % len(PAYMENT_MODES)]
        bank_account_id = None if mode == "cash" else bank_accounts[day % len(bank_accounts)].id
        db.session.add(
            Expense(
                expense_date=expense_date,
                category_id=cat.id,
                amount=round(RNG.uniform(350.0, 6500.0), 2),
                payment_mode=mode,
                bank_account_id=bank_account_id,
                reference_no=f"EXP-{expense_date.strftime('%Y%m%d')}",
                description=f"{cat.name} operational expense",
                created_by_user_id=admin.id,
                created_by=admin.id,
                updated_by=admin.id,
            )
        )

    db.session.flush()
    return {
        "customers": customers,
        "invoices": total_invoices,
        "payments": total_payments,
        "items": total_items,
        "tasks": total_tasks,
        "promises": total_promises,
    }


def run_data_quality_checks(customers):
    mobile_regex = re.compile(r"^[6-9][0-9]{9}$")

    invalid_mobile = [c.name for c in customers if not c.mobile_number or not mobile_regex.match(c.mobile_number)]
    per_customer_entries = {}
    for c in customers:
        invoice_count = Invoice.query.filter(Invoice.customer_name == c.name).count()
        per_customer_entries[c.id] = invoice_count

    bad_entry_counts = [cid for cid, count in per_customer_entries.items() if count < 5 or count > 10]

    mandatory = {
        "customers_missing_name": Customer.query.filter((Customer.name.is_(None)) | (Customer.name == "")).count(),
        "products_missing_required": Product.query.filter(
            (Product.name.is_(None)) | (Product.name == "") |
            (Product.hsn_code.is_(None)) | (Product.hsn_code == "")
        ).count(),
        "invoices_missing_required": Invoice.query.filter(
            (Invoice.invoice_number.is_(None)) | (Invoice.customer_name.is_(None))
        ).count(),
        "payments_missing_amount": Payment.query.filter(Payment.amount <= 0).count(),
    }

    optional = {
        "customers_without_contact_person": Customer.query.filter(Customer.contact_person.is_(None)).count(),
        "customers_without_whatsapp": Customer.query.filter(Customer.whatsapp_number.is_(None)).count(),
        "customers_without_gstin": Customer.query.filter((Customer.gstin.is_(None)) | (Customer.gstin == "")).count(),
        "invoices_without_reference": Invoice.query.filter((Invoice.reference_no.is_(None)) | (Invoice.reference_no == "")).count(),
        "payments_without_reference": Payment.query.filter((Payment.reference_no.is_(None)) | (Payment.reference_no == "")).count(),
    }

    if invalid_mobile:
        raise AssertionError(f"Invalid mobile numbers found for {len(invalid_mobile)} customers")
    if bad_entry_counts:
        raise AssertionError(f"Customers outside 5-10 invoice entry range: {len(bad_entry_counts)}")
    if any(value != 0 for value in mandatory.values()):
        raise AssertionError(f"Mandatory field check failed: {mandatory}")

    return mandatory, optional


def smoke_test_workflows(seed_customers):
    sample_customer = seed_customers[3]
    sample_product = Product.query.first()
    sample_user = User.query.filter_by(username="admin").first()

    with app.test_client() as client:
        login_resp = client.post(
            "/auth/login",
            data={"username": "admin", "password": "Admin@12345"},
            follow_redirects=True,
        )
        assert login_resp.status_code == 200, "Login failed"

        today = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")

        r1 = client.get(f"/customers/?search={sample_customer.name}", follow_redirects=True)
        assert r1.status_code == 200 and sample_customer.name.encode("utf-8") in r1.data, "Customer search failed"

        r2 = client.get(
            f"/invoices/?from_date={from_date}&to_date={today}&search={sample_customer.name}",
            follow_redirects=True,
        )
        assert r2.status_code == 200, "Invoice filter failed"

        before_count = Invoice.query.count()
        create_resp = client.post(
            "/invoices/",
            data={
                "customer_id": str(sample_customer.id),
                "product_id": [str(sample_product.id)],
                "quantity": ["2"],
                "billing_payment_type": "pay_now",
                "billing_payment_mode": "cash",
                "billing_amount_received": "500.00",
                "billing_payment_notes": "Smoke test invoice",
            },
            follow_redirects=True,
        )
        assert create_resp.status_code == 200, "Invoice create request failed"
        after_count = Invoice.query.count()
        assert after_count == before_count + 1, "Invoice generation workflow failed"

        ledger_resp = client.get(f"/customers/{sample_customer.id}/ledger", follow_redirects=True)
        assert ledger_resp.status_code == 200, "Customer ledger workflow failed"

        statement_csv = client.get(f"/customers/{sample_customer.id}/statement/export?format=csv", follow_redirects=True)
        assert statement_csv.status_code == 200 and "text/csv" in (statement_csv.content_type or ""), "Statement CSV export failed"

        tasks_resp = client.get("/customers/tasks?status=open", follow_redirects=True)
        assert tasks_resp.status_code == 200, "Follow-up tasks filter failed"

        sales = client.get(f"/reports/sales?from_date={from_date}&to_date={today}&search={sample_customer.name}", follow_redirects=True)
        assert sales.status_code == 200, "Sales report failed"

        sales_excel = client.get(f"/reports/sales?export=excel&search={sample_customer.name}", follow_redirects=True)
        assert sales_excel.status_code == 200 and "spreadsheetml" in (sales_excel.content_type or ""), "Sales Excel export failed"

        product_report = client.get("/reports/products?search=ஆச்சி", follow_redirects=True)
        assert product_report.status_code == 200, "Product report search failed"

        customer_report = client.get("/reports/customers?search=சென்னை", follow_redirects=True)
        assert customer_report.status_code == 200, "Customer report search failed"

        payment_report = client.get(
            f"/reports/payments?from_date={from_date}&to_date={today}&payment_mode=upi&status=partial",
            follow_redirects=True,
        )
        assert payment_report.status_code == 200, "Payment report filter failed"

        aging_report = client.get("/reports/outstanding-aging?priority_threshold=10000", follow_redirects=True)
        assert aging_report.status_code == 200, "Outstanding aging report failed"

        db.session.add(
            ActivityLog(
                user_id=sample_user.id,
                username=sample_user.username,
                action="Smoke Test Completed",
                details="Demo dataset smoke test completed successfully",
            )
        )
        db.session.commit()


def summarize(seed_counts, mandatory, optional):
    total_records = (
        User.query.count()
        + Unit.query.count()
        + Company.query.count()
        + Customer.query.count()
        + Product.query.count()
        + Invoice.query.count()
        + InvoiceItem.query.count()
        + Payment.query.count()
        + BankAccount.query.count()
        + ExpenseCategory.query.count()
        + Expense.query.count()
        + FollowUpTask.query.count()
        + PromiseToPay.query.count()
        + ReminderTemplate.query.count()
        + ActivityLog.query.count()
    )

    assert total_records >= 500, f"Total records below target: {total_records}"

    print("=== DEMO DATASET READY ===")
    print(f"Total records across core tables: {total_records}")
    print(f"Customers: {Customer.query.count()}")
    print(f"Products (Tamil): {Product.query.count()}")
    print(f"Invoices: {Invoice.query.count()}")
    print(f"Invoice Items: {InvoiceItem.query.count()}")
    print(f"Payments/Transactions: {Payment.query.count()}")
    print(f"Follow-Up Tasks: {FollowUpTask.query.count()}")
    print(f"Promise-to-Pay: {PromiseToPay.query.count()}")
    print(f"Expenses: {Expense.query.count()}")

    print("\nPer-customer transaction target (5-10 invoices): satisfied")
    print("Mandatory field checks:")
    for key, value in mandatory.items():
        print(f"  {key}: {value}")

    print("Optional field coverage:")
    for key, value in optional.items():
        print(f"  {key}: {value}")

    print("\nSmoke test status: PASS")


def main():
    with app.app_context():
        print("Resetting database and preparing realistic Tamil Nadu demo dataset...")
        reset_database()
        master = bootstrap_master_data()
        seed_counts = seed_customers_and_transactions(master)
        db.session.commit()

        mandatory, optional = run_data_quality_checks(seed_counts["customers"])
        smoke_test_workflows(seed_counts["customers"])
        summarize(seed_counts, mandatory, optional)


if __name__ == "__main__":
    main()
