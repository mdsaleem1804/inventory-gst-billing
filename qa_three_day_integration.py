from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from app import app
from models import (
    ActivityLog,
    BankAccount,
    Customer,
    Expense,
    Invoice,
    Payment,
    Product,
    User,
    db,
)


class IntegrationFailure(Exception):
    pass


def assert_true(condition, message):
    if not condition:
        raise IntegrationFailure(message)


def post_form(client, url, data, expected_status=200):
    resp = client.post(url, data=data, follow_redirects=True)
    assert_true(resp.status_code == expected_status, f"POST {url} expected {expected_status}, got {resp.status_code}")
    return resp


def get_page(client, url, expected_status=200):
    resp = client.get(url, follow_redirects=True)
    assert_true(resp.status_code == expected_status, f"GET {url} expected {expected_status}, got {resp.status_code}")
    return resp


def login_admin(client, checks):
    candidate_passwords = ["admin", "Admin@12345"]
    for password in candidate_passwords:
        resp = post_form(client, "/auth/login", {"username": "admin", "password": password})
        if b"Change Password" in resp.data:
            new_password = "Admin@12345"
            resp = post_form(
                client,
                "/auth/change-password",
                {
                    "current_password": password,
                    "new_password": new_password,
                    "confirm_password": new_password,
                },
            )
            assert_true(b"Dashboard" in resp.data or b"Sales Dashboard" in resp.data, "Password change did not reach dashboard")
            checks.append("PASS: Admin forced password change handled")
            return

        if b"Dashboard" in resp.data or b"Sales Dashboard" in resp.data:
            checks.append("PASS: Admin login")
            return

    raise IntegrationFailure("Admin login failed")


def run_suite():
    checks = []
    today = datetime.now().date()
    day_minus_1 = today - timedelta(days=1)
    day_minus_2 = today - timedelta(days=2)
    date_strs = {
        "d0": today.strftime("%Y-%m-%d"),
        "d1": day_minus_1.strftime("%Y-%m-%d"),
        "d2": day_minus_2.strftime("%Y-%m-%d"),
    }
    prefix = f"INT{datetime.now().strftime('%H%M%S')}"

    with app.test_client() as client, app.app_context():
        admin = User.query.filter_by(username="admin").first()
        if admin is None:
            admin = User(username="admin", password_hash=generate_password_hash("admin"), role="admin")
            db.session.add(admin)
        else:
            admin.password_hash = generate_password_hash("admin")
            admin.role = "admin"
        db.session.commit()

        login_admin(client, checks)

        # 1) Create 3 customers
        customer_payloads = [
            {"name": f"{prefix}-Customer-1", "gstin": "33ABCDE1234F1Z5", "address": "Tirunelveli"},
            {"name": f"{prefix}-Customer-2", "gstin": "33ABCDE1234F2Z6", "address": "Palayamkottai"},
            {"name": f"{prefix}-Customer-3", "gstin": "33ABCDE1234F3Z7", "address": "Melapalayam"},
        ]
        for payload in customer_payloads:
            post_form(client, "/customers/", payload)

        customers = Customer.query.filter(Customer.name.like(f"{prefix}-%")).order_by(Customer.id.asc()).all()
        assert_true(len(customers) >= 3, "Expected at least 3 created customers")
        checks.append("PASS: Created 3 customers")

        # 2) Edit and search customer
        customer3 = customers[-1]
        edited_name = f"{prefix}-Customer-3-Edited"
        post_form(
            client,
            "/customers/",
            {"id": str(customer3.id), "name": edited_name, "gstin": customer3.gstin, "address": customer3.address},
        )
        search_resp = get_page(client, f"/customers/?search={prefix}-Customer-3-Edited")
        assert_true(edited_name.encode() in search_resp.data, "Edited customer not found in search")
        checks.append("PASS: Customer edit/search")

        # 3) Create 5 products
        product_payloads = [
            {"name": f"{prefix}-Product-1", "hsn_code": "100100", "gst_percent": "5", "price": "120.50"},
            {"name": f"{prefix}-Product-2", "hsn_code": "100200", "gst_percent": "12", "price": "250.00"},
            {"name": f"{prefix}-Product-3", "hsn_code": "100300", "gst_percent": "18", "price": "350.75"},
            {"name": f"{prefix}-Product-4", "hsn_code": "100400", "gst_percent": "5", "price": "80.00"},
            {"name": f"{prefix}-Product-5", "hsn_code": "100500", "gst_percent": "28", "price": "999.99"},
        ]
        for payload in product_payloads:
            post_form(client, "/products/", payload)

        products = Product.query.filter(Product.name.like(f"{prefix}-%")).order_by(Product.id.asc()).all()
        assert_true(len(products) >= 5, "Expected at least 5 created products")
        checks.append("PASS: Created 5 products")

        # 4) Edit and search product
        product5 = products[-1]
        edited_product_name = f"{prefix}-Product-5-Edited"
        post_form(
            client,
            "/products/",
            {
                "id": str(product5.id),
                "name": edited_product_name,
                "hsn_code": product5.hsn_code,
                "gst_percent": f"{product5.gst_percent:.2f}",
                "price": "1099.99",
            },
        )
        search_resp = get_page(client, f"/products/?search={prefix}-Product-5-Edited")
        assert_true(edited_product_name.encode() in search_resp.data, "Edited product not found in search")
        checks.append("PASS: Product edit/search")

        # 5) Add bank account for bank-mode flows
        bank_name = f"{prefix}-HDFC"
        post_form(
            client,
            "/finance/bank-accounts",
            {"account_name": bank_name, "account_type": "current", "opening_balance": "5000.00"},
        )
        bank = BankAccount.query.filter_by(account_name=bank_name).first()
        assert_true(bank is not None, "Bank account creation failed")
        checks.append("PASS: Bank account add")

        # 6) Create invoices for 3 customers using 5 products
        invoice_inputs = [
            (customers[0], [products[0], products[1]], ["2", "1"]),
            (customers[1], [products[2], products[3]], ["1", "3"]),
            (customers[2], [products[4]], ["1"]),
        ]

        created_invoices = []
        for cust, inv_products, qty in invoice_inputs:
            post_form(
                client,
                "/invoices/",
                {
                    "customer_id": str(cust.id),
                    "product_id": [str(p.id) for p in inv_products],
                    "quantity": qty,
                },
            )
            inv = Invoice.query.filter_by(customer_name=cust.name).order_by(Invoice.id.desc()).first()
            assert_true(inv is not None, f"Invoice creation failed for {cust.name}")
            created_invoices.append(inv)

        # Assign explicit last-3-day dates to invoices
        created_invoices[0].date = datetime.combine(day_minus_2, datetime.min.time())
        created_invoices[1].date = datetime.combine(day_minus_1, datetime.min.time())
        created_invoices[2].date = datetime.combine(today, datetime.min.time())
        db.session.commit()
        checks.append("PASS: Invoices created across last 3 dates")

        # 7) Payment operations: receive, edit, reverse, re-receive
        inv1, inv2, _inv3 = created_invoices

        post_form(
            client,
            f"/invoices/{inv1.id}/receive-payment",
            {
                "amount": "100.00",
                "payment_date": date_strs["d2"],
                "payment_mode": "upi",
                "bank_account_id": str(bank.id),
                "reference_no": f"{prefix}-UPI-1",
                "notes": "integration payment d-2",
            },
        )

        post_form(
            client,
            f"/invoices/{inv2.id}/receive-payment",
            {
                "amount": "50.00",
                "payment_date": date_strs["d1"],
                "payment_mode": "cash",
                "reference_no": f"{prefix}-CASH-1",
                "notes": "integration payment d-1",
            },
        )

        p2 = Payment.query.filter_by(invoice_id=inv2.id).order_by(Payment.id.desc()).first()
        assert_true(p2 is not None, "Initial payment for invoice 2 not found")

        post_form(
            client,
            f"/invoices/payments/{p2.id}/edit",
            {
                "amount": "60.00",
                "payment_date": date_strs["d1"],
                "payment_mode": "cash",
                "reference_no": f"{prefix}-CASH-1-EDIT",
                "notes": "edited",
            },
        )

        post_form(
            client,
            f"/invoices/payments/{p2.id}/reverse",
            {"reversal_reason": "integration reversal check", "invoice_id": str(inv2.id)},
        )

        inv2_refreshed = Invoice.query.get(inv2.id)
        final_due = round(float(inv2_refreshed.balance_amount or inv2_refreshed.total), 2)
        post_form(
            client,
            f"/invoices/{inv2.id}/receive-payment",
            {
                "amount": f"{final_due:.2f}",
                "payment_date": date_strs["d0"],
                "payment_mode": "cash",
                "reference_no": f"{prefix}-CASH-FINAL",
                "notes": "final payment",
            },
        )
        checks.append("PASS: Payment receive/edit/reverse/re-receive operations")

        # 8) Invoice delete operation on a disposable invoice
        post_form(
            client,
            "/invoices/",
            {
                "customer_id": str(customers[0].id),
                "product_id": [str(products[0].id)],
                "quantity": ["1"],
            },
        )
        disposable_invoice = Invoice.query.filter_by(customer_name=customers[0].name).order_by(Invoice.id.desc()).first()
        post_form(client, "/invoices/", {"delete_id": str(disposable_invoice.id)})
        deleted_invoice = Invoice.query.get(disposable_invoice.id)
        assert_true(deleted_invoice is None, "Invoice delete operation failed")
        checks.append("PASS: Invoice delete operation")

        # 9) Expense operations to validate finance reports in date window
        post_form(
            client,
            "/finance/expenses",
            {
                "expense_date": date_strs["d2"],
                "new_category": f"{prefix}-Transport",
                "amount": "120.25",
                "payment_mode": "cash",
                "reference_no": f"{prefix}-EXP-1",
                "description": "fuel",
            },
        )
        post_form(
            client,
            "/finance/expenses",
            {
                "expense_date": date_strs["d1"],
                "category_id": "",
                "new_category": f"{prefix}-Packing",
                "amount": "80.00",
                "payment_mode": "upi",
                "bank_account_id": str(bank.id),
                "reference_no": f"{prefix}-EXP-2",
                "description": "materials",
            },
        )
        assert_true(Expense.query.filter(Expense.reference_no.like(f"{prefix}-EXP-%")).count() >= 2, "Expense operations failed")
        checks.append("PASS: Expense operations")

        # 10) Customer delete operation (disposable record)
        disposable_name = f"{prefix}-Disposable-Customer"
        post_form(
            client,
            "/customers/",
            {"name": disposable_name, "gstin": "33ABCDE1234F9Z9", "address": "temp"},
        )
        disposable_customer = Customer.query.filter_by(name=disposable_name).first()
        post_form(client, "/customers/", {"delete_id": str(disposable_customer.id)})
        assert_true(Customer.query.get(disposable_customer.id) is None, "Customer delete failed")
        checks.append("PASS: Customer delete operation")

        # 11) Report validations for last 3 dates (today included)
        from_date = date_strs["d2"]
        to_date = date_strs["d0"]

        report_pages = [
            f"/reports/sales?from_date={from_date}&to_date={to_date}",
            "/reports/products",
            "/reports/customers",
            f"/reports/payments?from_date={from_date}&to_date={to_date}",
            f"/reports/outstanding-aging?as_of_date={to_date}",
            f"/finance/expenses?from_date={from_date}&to_date={to_date}",
            f"/finance/bank-book?from_date={from_date}&to_date={to_date}",
        ]
        for page in report_pages:
            resp = get_page(client, page)
            assert_true(resp.status_code == 200, f"Report page failed: {page}")

        exports = [
            (f"/reports/sales?from_date={from_date}&to_date={to_date}&export=excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("/reports/products?export=pdf", "application/pdf"),
            ("/reports/customers?export=excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            (f"/reports/payments?from_date={from_date}&to_date={to_date}&export=csv", "text/csv"),
            (f"/reports/outstanding-aging?as_of_date={to_date}&export=excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            (f"/finance/expenses?from_date={from_date}&to_date={to_date}&export=csv", "text/csv"),
            (f"/finance/bank-book?from_date={from_date}&to_date={to_date}&export=excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("/invoices/export/excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ]

        for url, expected_content in exports:
            resp = get_page(client, url)
            content_type = (resp.content_type or "").lower()
            assert_true(expected_content in content_type, f"Export content type mismatch for {url}: {content_type}")

        sales_html = get_page(client, f"/reports/sales?from_date={from_date}&to_date={to_date}")
        assert_true(prefix.encode() in sales_html.data, "Sales report did not include test records in date range")
        checks.append("PASS: Reports and exports validated")

        # 12) Final data assertions requested by user
        invoice_window_count = (
            Invoice.query.filter(db.func.date(Invoice.date) >= from_date)
            .filter(db.func.date(Invoice.date) <= to_date)
            .count()
        )
        customer_count = Customer.query.filter(Customer.name.like(f"{prefix}-%")).count()
        product_count = Product.query.filter(Product.name.like(f"{prefix}-%")).count()

        assert_true(customer_count >= 3, "Final customer count below 3")
        assert_true(product_count >= 5, "Final product count below 5")
        assert_true(invoice_window_count >= 3, "Invoice count in last-3-day window below 3")
        checks.append("PASS: Required minimum counts (3 customers, 5 products, 3-day invoices)")

        # Activity trail existence for report and payment flows
        expected_actions = [
            "Invoice Payment Received",
            "Invoice Payment Edited",
            "Invoice Payment Reversed",
            "Sales Report Exported Excel",
            "Payment Report Exported CSV",
            "Outstanding Aging Exported Excel",
            "Expense Report Exported CSV",
            "Bank Book Exported Excel",
        ]
        missing_actions = [a for a in expected_actions if ActivityLog.query.filter_by(action=a).first() is None]
        assert_true(not missing_actions, f"Missing activity logs: {missing_actions}")
        checks.append("PASS: Activity logs recorded for key operations")

        summary = {
            "prefix": prefix,
            "from_date": from_date,
            "to_date": to_date,
            "customers_created": customer_count,
            "products_created": product_count,
            "invoices_in_3day_window": invoice_window_count,
            "payments_for_test_data": Payment.query.join(Invoice, Payment.invoice_id == Invoice.id).filter(Invoice.customer_name.like(f"{prefix}-%")).count(),
            "expenses_for_test_data": Expense.query.filter(Expense.reference_no.like(f"{prefix}-EXP-%")).count(),
        }

    return checks, summary


if __name__ == "__main__":
    try:
        lines, summary_obj = run_suite()
        print("=== THREE-DAY INTEGRATION RESULT: PASS ===")
        for idx, line in enumerate(lines, start=1):
            print(f"{idx}. {line}")
        print("--- SUMMARY ---")
        for key, value in summary_obj.items():
            print(f"{key}: {value}")
    except Exception as exc:
        print("=== THREE-DAY INTEGRATION RESULT: FAIL ===")
        print(str(exc))
        raise
