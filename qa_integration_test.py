from datetime import datetime

from app import app
from models import ActivityLog, Customer, Invoice, Payment, Product, User
from werkzeug.security import generate_password_hash


class TestFailure(Exception):
    pass


def assert_true(condition, message):
    if not condition:
        raise TestFailure(message)


def post_form(client, url, data, expected_status=200, follow_redirects=True):
    resp = client.post(url, data=data, follow_redirects=follow_redirects)
    assert_true(resp.status_code == expected_status, f"POST {url} expected {expected_status}, got {resp.status_code}")
    return resp


def get_page(client, url, expected_status=200, follow_redirects=True):
    resp = client.get(url, follow_redirects=follow_redirects)
    assert_true(resp.status_code == expected_status, f"GET {url} expected {expected_status}, got {resp.status_code}")
    return resp


def run_integration_suite():
    results = []

    with app.test_client() as client, app.app_context():
        # Ensure deterministic baseline for repeatable runs.
        admin = User.query.filter_by(username="admin").first()
        if admin is None:
            admin = User(username="admin", password_hash=generate_password_hash("admin"), role="admin")
            from models import db

            db.session.add(admin)
        else:
            admin.password_hash = generate_password_hash("admin")
            admin.role = "admin"
        from models import db

        db.session.commit()

        # 1) Login with default admin should force password change
        resp = post_form(
            client,
            "/auth/login",
            {"username": "admin", "password": "admin"},
            expected_status=200,
            follow_redirects=True,
        )
        assert_true(b"Change Password" in resp.data, "Default admin login did not force password change")
        results.append("PASS: Default admin forced to change password")

        # 2) Change password and verify dashboard access
        new_admin_password = "Admin@12345"
        resp = post_form(
            client,
            "/auth/change-password",
            {
                "current_password": "admin",
                "new_password": new_admin_password,
                "confirm_password": new_admin_password,
            },
            expected_status=200,
            follow_redirects=True,
        )
        assert_true(b"Sales Dashboard" in resp.data, "Admin password change did not return dashboard")
        results.append("PASS: Admin password changed and dashboard accessible")

        # 3) Add Tamil customer
        tamil_customer_name = "திருநெல்வேலி சோதனை வாடிக்கையாளர்"
        tamil_customer_address = "நெல்லை புதிய பேருந்து நிலையம் அருகில்"
        post_form(
            client,
            "/customers/",
            {
                "name": tamil_customer_name,
                "gstin": "33ABCDE1234F1Z5",
                "address": tamil_customer_address,
            },
            expected_status=200,
            follow_redirects=True,
        )
        customer = Customer.query.filter_by(name=tamil_customer_name).first()
        assert_true(customer is not None, "Tamil customer was not created")
        results.append("PASS: Tamil customer create flow")

        # 4) Add Tamil product
        tamil_product_name = "மிளகாய் தூள் சிறப்பு பாக்ஸ்"
        post_form(
            client,
            "/products/",
            {
                "name": tamil_product_name,
                "hsn_code": "09042211",
                "gst_percent": "5",
                "price": "120.50",
            },
            expected_status=200,
            follow_redirects=True,
        )
        product = Product.query.filter_by(name=tamil_product_name).first()
        assert_true(product is not None, "Tamil product was not created")
        results.append("PASS: Tamil product create flow")

        # 5) Create invoice with Tamil customer/product
        post_form(
            client,
            "/invoices/",
            {
                "customer_id": str(customer.id),
                "product_id": [str(product.id)],
                "quantity": ["2"],
            },
            expected_status=200,
            follow_redirects=True,
        )
        invoice = Invoice.query.filter_by(customer_name=tamil_customer_name).order_by(Invoice.id.desc()).first()
        assert_true(invoice is not None, "Invoice creation failed")
        assert_true(invoice.payment_status == "unpaid", "New invoice payment status should be unpaid")
        assert_true(round(float(invoice.balance_amount), 2) == round(float(invoice.total), 2), "New invoice balance should equal total")
        results.append("PASS: Invoice creation and initial payment fields")

        # 6) Receive payment (partial)
        post_form(
            client,
            f"/invoices/{invoice.id}/receive-payment",
            {
                "amount": "50",
                "payment_date": datetime.now().strftime("%Y-%m-%d"),
                "payment_mode": "upi",
                "reference_no": "UTR1001",
                "notes": "முதல் தவணை",
            },
            expected_status=200,
            follow_redirects=True,
        )
        invoice = Invoice.query.get(invoice.id)
        payment = Payment.query.filter_by(invoice_id=invoice.id).order_by(Payment.id.desc()).first()
        assert_true(payment is not None, "Payment record was not created")
        assert_true(invoice.payment_status in ("partial", "paid"), "Invoice payment status not updated after payment")
        results.append("PASS: Receive payment flow")

        # 7) Edit payment as admin and verify changes
        post_form(
            client,
            f"/invoices/payments/{payment.id}/edit",
            {
                "amount": "60",
                "payment_date": datetime.now().strftime("%Y-%m-%d"),
                "payment_mode": "cash",
                "reference_no": "CASH-1",
                "notes": "திருத்தப்பட்டது",
            },
            expected_status=200,
            follow_redirects=True,
        )
        edited_payment = Payment.query.get(payment.id)
        assert_true(edited_payment is not None, "Edited payment missing")
        assert_true(round(float(edited_payment.amount), 2) == 60.0, "Payment edit amount not saved")
        results.append("PASS: Payment edit flow")

        # 8) Reverse payment with reason and verify enforcement/audit
        post_form(
            client,
            f"/invoices/payments/{payment.id}/reverse",
            {"reversal_reason": "Customer requested cancellation"},
            expected_status=200,
            follow_redirects=True,
        )
        reversed_payment = Payment.query.get(payment.id)
        invoice = Invoice.query.get(invoice.id)
        assert_true(reversed_payment is None, "Payment reversal failed")
        assert_true(invoice.payment_status == "unpaid", "Invoice should return to unpaid after full reversal")
        results.append("PASS: Payment reversal with reason")

        # 9) Create second payment and verify reason-required validation
        post_form(
            client,
            f"/invoices/{invoice.id}/receive-payment",
            {
                "amount": "25",
                "payment_date": datetime.now().strftime("%Y-%m-%d"),
                "payment_mode": "upi",
                "reference_no": "UTR1002",
                "notes": "ரீடெஸ்ட்",
            },
            expected_status=200,
            follow_redirects=True,
        )
        payment2 = Payment.query.filter_by(invoice_id=invoice.id).order_by(Payment.id.desc()).first()
        assert_true(payment2 is not None, "Second payment not created")

        resp = post_form(
            client,
            f"/invoices/payments/{payment2.id}/reverse",
            {"reversal_reason": ""},
            expected_status=200,
            follow_redirects=True,
        )
        assert_true(b"Reversal reason is required" in resp.data, "Reversal reason mandatory validation failed")
        still_exists = Payment.query.get(payment2.id)
        assert_true(still_exists is not None, "Payment should not be reversed when reason is missing")
        results.append("PASS: Reversal reason mandatory validation")

        # 10) Export endpoints smoke checks
        resp = get_page(client, "/invoices/export/excel", expected_status=200, follow_redirects=True)
        assert_true(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in (resp.content_type or ""),
            "Invoices Excel export content type mismatch",
        )
        resp = get_page(client, "/reports/sales?export=excel", expected_status=200, follow_redirects=True)
        assert_true(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in (resp.content_type or ""),
            "Sales Excel export content type mismatch",
        )
        resp = get_page(client, "/reports/products?export=pdf", expected_status=200, follow_redirects=True)
        assert_true("application/pdf" in (resp.content_type or ""), "Products PDF export content type mismatch")
        results.append("PASS: Export endpoints smoke checks")

        # 11) Create staff user, verify invoice edit denied
        post_form(
            client,
            "/users/",
            {"username": "qa_staff", "password": "Staff@123", "role": "staff"},
            expected_status=200,
            follow_redirects=True,
        )
        staff = User.query.filter_by(username="qa_staff").first()
        assert_true(staff is not None, "Staff user creation failed")

        get_page(client, "/auth/logout", expected_status=200, follow_redirects=True)
        resp = post_form(
            client,
            "/auth/login",
            {"username": "qa_staff", "password": "Staff@123"},
            expected_status=200,
            follow_redirects=True,
        )
        assert_true(b"Sales Dashboard" in resp.data, "Staff login failed")

        resp = get_page(client, f"/invoices/?edit_id={invoice.id}", expected_status=200, follow_redirects=True)
        assert_true(b"Only admin or approver can edit invoices" in resp.data, "Staff invoice edit restriction failed")
        results.append("PASS: Staff permission restrictions")

        # 12) Activity log presence checks
        actions = [
            "Invoice Payment Received",
            "Invoice Payment Edited",
            "Invoice Payment Reversed",
            "Invoice Exported Excel",
            "Sales Report Exported Excel",
            "Product Report Exported PDF",
            "Invoice Edit Denied",
        ]
        missing = [a for a in actions if ActivityLog.query.filter_by(action=a).first() is None]
        assert_true(not missing, f"Missing activity logs: {missing}")
        results.append("PASS: Activity log traceability checks")

    return results


if __name__ == "__main__":
    try:
        lines = run_integration_suite()
        print("=== INTEGRATION TEST RESULT: PASS ===")
        for line in lines:
            print(line)
    except Exception as exc:
        print("=== INTEGRATION TEST RESULT: FAIL ===")
        print(str(exc))
        raise
