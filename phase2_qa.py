import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests
from werkzeug.serving import make_server
from werkzeug.security import generate_password_hash

from app import app
from models import db, Invoice, Payment, Product, Customer, User, ActivityLog


BASE_URL = "http://127.0.0.1:5055"
ADMIN_USER = "admin"
ADMIN_PASS = "Admin@12345"
APPROVER_USER = "qa_approver"
APPROVER_PASS = "Approver@123"


class ServerThread(threading.Thread):
    def __init__(self, app_obj, host="127.0.0.1", port=5055):
        super().__init__(daemon=True)
        self.server = make_server(host, port, app_obj)
        self.ctx = app_obj.app_context()
        self.ctx.push()

    def run(self):
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()
        self.ctx.pop()


class Phase2Failure(Exception):
    pass


def assert_true(condition, message):
    if not condition:
        raise Phase2Failure(message)


def setup_test_baseline():
    with app.app_context():
        db.create_all()
        admin = User.query.filter_by(username=ADMIN_USER).first()
        if admin is None:
            admin = User(username=ADMIN_USER, password_hash=generate_password_hash(ADMIN_PASS), role="admin")
            db.session.add(admin)
        else:
            admin.password_hash = generate_password_hash(ADMIN_PASS)
            admin.role = "admin"

        approver = User.query.filter_by(username=APPROVER_USER).first()
        if approver is None:
            approver = User(username=APPROVER_USER, password_hash=generate_password_hash(APPROVER_PASS), role="approver")
            db.session.add(approver)
        else:
            approver.password_hash = generate_password_hash(APPROVER_PASS)
            approver.role = "approver"

        cust = Customer.query.filter_by(name="QA Load Customer").first()
        if cust is None:
            cust = Customer(name="QA Load Customer", gstin="33ABCDE1234F1Z5", address="Tirunelveli")
            db.session.add(cust)

        prod = Product.query.filter_by(name="QA Load Product").first()
        if prod is None:
            prod = Product(name="QA Load Product", hsn_code="09042211", gst_percent=5.0, price=100.0)
            db.session.add(prod)

        db.session.commit()


def login(username, password):
    sess = requests.Session()
    resp = sess.post(
        f"{BASE_URL}/auth/login",
        data={"username": username, "password": password},
        allow_redirects=True,
        timeout=20,
    )
    if "Change Password" in resp.text:
        # Force-change flow can happen if credential baseline changed by other tests.
        cp = sess.post(
            f"{BASE_URL}/auth/change-password",
            data={
                "current_password": password,
                "new_password": password,
                "confirm_password": password,
            },
            allow_redirects=True,
            timeout=20,
        )
        assert_true(cp.status_code == 200, f"Change password flow failed for {username}")
    assert_true(resp.status_code == 200, f"Login failed for {username}")
    return sess


def browser_smoke(browser_name):
    outcome = {"browser": browser_name, "status": "PASS", "details": []}
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        if browser_name == "chrome":
            opts = webdriver.ChromeOptions()
            opts.add_argument("--headless=new")
            opts.add_argument("--window-size=1366,900")
            driver = webdriver.Chrome(options=opts)
        elif browser_name == "edge":
            opts = webdriver.EdgeOptions()
            opts.add_argument("--headless=new")
            opts.add_argument("--window-size=1366,900")
            driver = webdriver.Edge(options=opts)
        else:
            raise RuntimeError("Unsupported browser")

        try:
            driver.get(f"{BASE_URL}/auth/login")
            wait = WebDriverWait(driver, 12)
            wait.until(EC.presence_of_element_located((By.NAME, "username")))
            driver.find_element(By.NAME, "username").send_keys(ADMIN_USER)
            driver.find_element(By.NAME, "password").send_keys(ADMIN_PASS)
            driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

            # Handle forced-change flows based on URL or form presence.
            time.sleep(0.5)
            page_text = driver.page_source.lower()
            if "change-password" in driver.current_url or "change password" in page_text:
                wait.until(EC.presence_of_element_located((By.NAME, "current_password")))
                driver.find_element(By.NAME, "current_password").send_keys(ADMIN_PASS)
                driver.find_element(By.NAME, "new_password").send_keys(ADMIN_PASS)
                driver.find_element(By.NAME, "confirm_password").send_keys(ADMIN_PASS)
                driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

            wait.until(lambda d: ("sales dashboard" in d.page_source.lower()) or ("dashboard" in d.page_source.lower()))
            assert_true("dashboard" in driver.page_source.lower() or "sales dashboard" in driver.page_source.lower(), f"{browser_name}: dashboard not visible after login")
            outcome["details"].append("Login + dashboard")

            for path in ["/products/", "/customers/", "/invoices/", "/reports/sales", "/users/activity-logs"]:
                driver.get(f"{BASE_URL}{path}")
                assert_true("error" not in driver.title.lower(), f"{browser_name}: error title on {path}")
                outcome["details"].append(f"Open {path}")

        finally:
            driver.quit()

    except Exception as exc:
        outcome["status"] = "FAIL"
        outcome["error"] = str(exc)

    return outcome


def create_invoice_for_race(admin_sess):
    with app.app_context():
        cust = Customer.query.filter_by(name="QA Load Customer").first()
        prod = Product.query.filter_by(name="QA Load Product").first()
        assert_true(cust is not None and prod is not None, "Missing baseline customer/product for race test")

    resp = admin_sess.post(
        f"{BASE_URL}/invoices/",
        data={
            "customer_id": str(cust.id),
            "product_id": [str(prod.id)],
            "quantity": ["2"],
        },
        allow_redirects=True,
        timeout=20,
    )
    assert_true(resp.status_code == 200, "Failed to create invoice for race test")

    with app.app_context():
        inv = Invoice.query.order_by(Invoice.id.desc()).first()
        assert_true(inv is not None, "No invoice created for race test")
        return inv.id


def race_test(admin_sess, approver_sess):
    invoice_id = create_invoice_for_race(admin_sess)

    # add initial payment
    r = admin_sess.post(
        f"{BASE_URL}/invoices/{invoice_id}/receive-payment",
        data={
            "amount": "100",
            "payment_date": datetime.now().strftime("%Y-%m-%d"),
            "payment_mode": "upi",
            "reference_no": "RACE-INIT",
            "notes": "race init",
        },
        allow_redirects=True,
        timeout=20,
    )
    assert_true(r.status_code == 200, "Could not create initial payment for race test")

    with app.app_context():
        p = Payment.query.filter_by(invoice_id=invoice_id).order_by(Payment.id.desc()).first()
        assert_true(p is not None, "No payment found for race test")
        payment_id = p.id

    barrier = threading.Barrier(2)

    def do_edit():
        barrier.wait(timeout=10)
        return approver_sess.post(
            f"{BASE_URL}/invoices/payments/{payment_id}/edit",
            data={
                "amount": "80",
                "payment_date": datetime.now().strftime("%Y-%m-%d"),
                "payment_mode": "cash",
                "reference_no": "RACE-EDIT",
                "notes": "edited concurrently",
            },
            allow_redirects=True,
            timeout=20,
        )

    def do_reverse():
        barrier.wait(timeout=10)
        return admin_sess.post(
            f"{BASE_URL}/invoices/payments/{payment_id}/reverse",
            data={"reversal_reason": "Race simulation"},
            allow_redirects=True,
            timeout=20,
        )

    with ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(do_edit)
        f2 = ex.submit(do_reverse)
        resp1 = f1.result()
        resp2 = f2.result()

    assert_true(resp1.status_code == 200 and resp2.status_code == 200, "Race operations returned non-200 responses")

    with app.app_context():
        inv = Invoice.query.get(invoice_id)
        assert_true(inv is not None, "Invoice missing after race test")
        payments = Payment.query.filter_by(invoice_id=invoice_id).all()
        paid_total = round(sum(float(x.amount) for x in payments), 2)
        assert_true(round(float(inv.paid_amount or 0), 2) == paid_total, "Invoice paid_amount mismatch after race")
        expected_balance = round(float(inv.total) - paid_total, 2)
        assert_true(round(float(inv.balance_amount or 0), 2) == expected_balance, "Invoice balance mismatch after race")
        assert_true((inv.payment_status in ("unpaid", "partial", "paid")), "Invalid payment status after race")

    return {
        "status": "PASS",
        "invoice_id": invoice_id,
        "responses": [resp1.status_code, resp2.status_code],
    }


def stress_run(admin_sess, invoice_count=120):
    with app.app_context():
        cust = Customer.query.filter_by(name="QA Load Customer").first()
        prod = Product.query.filter_by(name="QA Load Product").first()
        assert_true(cust is not None and prod is not None, "Missing baseline entities for stress")
        baseline_created_logs = ActivityLog.query.filter_by(action="Invoice Created").count()
        baseline_payment_logs = ActivityLog.query.filter_by(action="Invoice Payment Received").count()

    t0 = time.time()
    created = 0
    payment_ok = 0

    for i in range(invoice_count):
        r1 = admin_sess.post(
            f"{BASE_URL}/invoices/",
            data={
                "customer_id": str(cust.id),
                "product_id": [str(prod.id)],
                "quantity": ["1"],
            },
            allow_redirects=True,
            timeout=30,
        )
        if r1.status_code == 200:
            created += 1
        else:
            continue

        with app.app_context():
            inv = Invoice.query.order_by(Invoice.id.desc()).first()
            inv_id = inv.id

        r2 = admin_sess.post(
            f"{BASE_URL}/invoices/{inv_id}/receive-payment",
            data={
                "amount": "50",
                "payment_date": datetime.now().strftime("%Y-%m-%d"),
                "payment_mode": "upi",
                "reference_no": f"STRESS-{i}",
                "notes": "stress payment",
            },
            allow_redirects=True,
            timeout=30,
        )
        if r2.status_code == 200:
            payment_ok += 1

    duration = time.time() - t0

    with app.app_context():
        created_logs = ActivityLog.query.filter_by(action="Invoice Created").count() - baseline_created_logs
        payment_logs = ActivityLog.query.filter_by(action="Invoice Payment Received").count() - baseline_payment_logs

    assert_true(created == invoice_count, f"Stress create mismatch: expected {invoice_count}, got {created}")
    assert_true(payment_ok == invoice_count, f"Stress payment mismatch: expected {invoice_count}, got {payment_ok}")
    assert_true(created_logs >= invoice_count, "Missing invoice created logs in stress run")
    assert_true(payment_logs >= invoice_count, "Missing payment received logs in stress run")

    return {
        "status": "PASS",
        "invoice_count": invoice_count,
        "created": created,
        "payments": payment_ok,
        "duration_sec": round(duration, 2),
        "throughput_ops_per_sec": round((created + payment_ok) / duration, 2) if duration > 0 else None,
    }


def main():
    report = {
        "started_at": datetime.now().isoformat(),
        "cross_browser": [],
        "concurrency": None,
        "stress": None,
        "overall": "PASS",
        "notes": [],
    }

    setup_test_baseline()

    server = ServerThread(app)
    server.start()
    time.sleep(1.2)

    try:
        admin_sess = login(ADMIN_USER, ADMIN_PASS)
        approver_sess = login(APPROVER_USER, APPROVER_PASS)

        for browser in ["chrome", "edge"]:
            result = browser_smoke(browser)
            report["cross_browser"].append(result)
            if result.get("status") != "PASS":
                report["overall"] = "FAIL"

        report["concurrency"] = race_test(admin_sess, approver_sess)
        report["stress"] = stress_run(admin_sess, invoice_count=120)

    except Exception as exc:
        report["overall"] = "FAIL"
        report["notes"].append(str(exc))
    finally:
        server.shutdown()

    report["ended_at"] = datetime.now().isoformat()
    print("=== PHASE-2 QA REPORT ===")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
