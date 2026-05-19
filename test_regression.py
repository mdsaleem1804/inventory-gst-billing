from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
import time
from datetime import datetime, timedelta
import uuid
from selenium.webdriver.common.keys import Keys
import os

BASE_URL = "http://localhost:5000"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin"

results = []

def report(operation, passed, error=None):
    results.append((operation, passed, error))
    if passed:
        print(f"[PASS] {operation}")
    else:
        print(f"[FAIL] {operation}: {error}")

def print_summary():
    total = len(results)
    passed = sum(1 for r in results if r[1])
    failed = total - passed
    print("\n--- TEST SUMMARY ---")
    print(f"Total: {total}")
    print(f"Passed: {passed} ({(passed/total)*100:.1f}%)")
    print(f"Failed: {failed} ({(failed/total)*100:.1f}%)")
    if failed:
        print("\nFailures:")
        for op, ok, err in results:
            if not ok:
                print(f"- {op}: {err}")

def login(driver):
    try:
        driver.get(f"{BASE_URL}/auth/login")
        driver.find_element(By.NAME, "username").send_keys(ADMIN_USERNAME)
        driver.find_element(By.NAME, "password").send_keys(ADMIN_PASSWORD)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(1)
        report("Login as admin", True)
    except Exception as e:
        report("Login as admin", False, str(e))

# --- Customer Flows ---
def add_customer(driver, name, gstin, address):
    try:
        driver.get(f"{BASE_URL}/customers/")
        driver.find_element(By.NAME, "name").send_keys(name)
        driver.find_element(By.NAME, "gstin").send_keys(gstin)
        driver.find_element(By.NAME, "address").send_keys(address)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(1)
        report(f"Add customer {name}", True)
    except Exception as e:
        report(f"Add customer {name}", False, str(e))

def edit_customer(driver, old_name, new_name):
    try:
        driver.get(f"{BASE_URL}/customers/")
        search_box = driver.find_element(By.NAME, "search")
        search_box.clear()
        search_box.send_keys(old_name)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(1)
        driver.find_element(By.LINK_TEXT, "Edit").click()
        name_input = driver.find_element(By.NAME, "name")
        name_input.clear()
        name_input.send_keys(new_name)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(1)
        report(f"Edit customer {old_name} to {new_name}", True)
    except Exception as e:
        report(f"Edit customer {old_name} to {new_name}", False, str(e))

def delete_customer(driver, name):
    try:
        driver.get(f"{BASE_URL}/customers/")
        search_box = driver.find_element(By.NAME, "search")
        search_box.clear()
        search_box.send_keys(name)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(1)
        driver.find_element(By.XPATH, "//button[contains(text(),'Delete')]").click()
        driver.switch_to.alert.accept()
        time.sleep(1)
        report(f"Delete customer {name}", True)
    except Exception as e:
        report(f"Delete customer {name}", False, str(e))

def search_customer(driver, name):
    try:
        driver.get(f"{BASE_URL}/customers/")
        search_box = driver.find_element(By.NAME, "search")
        search_box.clear()
        search_box.send_keys(name)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(1)
        assert name in driver.page_source
        report(f"Search customer {name}", True)
    except Exception as e:
        report(f"Search customer {name}", False, str(e))

# --- Product Flows ---
def add_product(driver, name, hsn, gst, price):
    try:
        driver.get(f"{BASE_URL}/products/")
        driver.find_element(By.NAME, "name").send_keys(name)
        driver.find_element(By.NAME, "hsn_code").send_keys(hsn)
        driver.find_element(By.NAME, "gst_percent").send_keys(str(gst))
        driver.find_element(By.NAME, "price").send_keys(str(price))
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(1)
        report(f"Add product {name}", True)
    except Exception as e:
        report(f"Add product {name}", False, str(e))

def edit_product(driver, old_name, new_name):
    try:
        driver.get(f"{BASE_URL}/products/")
        search_box = driver.find_element(By.NAME, "search")
        search_box.clear()
        search_box.send_keys(old_name)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(1)
        driver.find_element(By.LINK_TEXT, "Edit").click()
        name_input = driver.find_element(By.NAME, "name")
        name_input.clear()
        name_input.send_keys(new_name)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(1)
        report(f"Edit product {old_name} to {new_name}", True)
    except Exception as e:
        report(f"Edit product {old_name} to {new_name}", False, str(e))

def delete_product(driver, name):
    try:
        driver.get(f"{BASE_URL}/products/")
        search_box = driver.find_element(By.NAME, "search")
        search_box.clear()
        search_box.send_keys(name)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(1)
        driver.find_element(By.XPATH, "//button[contains(text(),'Delete')]").click()
        driver.switch_to.alert.accept()
        time.sleep(1)
        report(f"Delete product {name}", True)
    except Exception as e:
        report(f"Delete product {name}", False, str(e))

def search_product(driver, name):
    try:
        driver.get(f"{BASE_URL}/products/")
        search_box = driver.find_element(By.NAME, "search")
        search_box.clear()
        search_box.send_keys(name)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(1)
        assert name in driver.page_source
        report(f"Search product {name}", True)
    except Exception as e:
        report(f"Search product {name}", False, str(e))

# --- Invoice Flows ---
def add_invoice(driver, customer, product, date):
    try:
        driver.get(f"{BASE_URL}/invoices/")
        driver.find_element(By.LINK_TEXT, "New Invoice").click()
        time.sleep(1)
        Select(driver.find_element(By.NAME, "customer_id")).select_by_visible_text(customer)
        time.sleep(0.5)
        try:
            date_input = driver.find_element(By.NAME, "date")
            date_input.clear()
            date_input.send_keys(date)
        except Exception:
            pass
        Select(driver.find_element(By.NAME, "product_id")).select_by_index(1)
        qty_input = driver.find_element(By.NAME, "quantity")
        qty_input.clear()
        qty_input.send_keys("1")
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(1)
        report(f"Add invoice for {customer} - {product}", True)
    except Exception as e:
        report(f"Add invoice for {customer} - {product}", False, str(e))

def search_invoice(driver, search_term):
    try:
        driver.get(f"{BASE_URL}/invoices/")
        search_box = driver.find_element(By.NAME, "search")
        search_box.clear()
        search_box.send_keys(search_term)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(1)
        assert search_term in driver.page_source
        report(f"Search invoice {search_term}", True)
    except Exception as e:
        report(f"Search invoice {search_term}", False, str(e))

# --- Report Flows ---
def test_report_view(driver, url, report_name):
    try:
        driver.get(url)
        time.sleep(1)
        assert report_name.lower() in driver.page_source.lower()
        report(f"View {report_name} report page", True)
    except Exception as e:
        report(f"View {report_name} report page", False, str(e))

def test_report_filter(driver, url, search_term, report_name):
    try:
        driver.get(url)
        time.sleep(1)
        search_box = driver.find_element(By.NAME, "search")
        search_box.clear()
        search_box.send_keys(search_term)
        search_box.send_keys(Keys.RETURN)
        time.sleep(1)
        assert search_term.lower() in driver.page_source.lower()
        report(f"Filter {report_name} report by '{search_term}'", True)
    except Exception as e:
        report(f"Filter {report_name} report by '{search_term}'", False, str(e))

def test_report_print(driver, url, report_name):
    try:
        driver.get(url)
        time.sleep(1)
        driver.find_element(By.XPATH, "//button[contains(text(),'Print')]").click()
        time.sleep(1)
        # Can't assert print dialog, but can check no error
        report(f"Print {report_name} report", True)
    except Exception as e:
        report(f"Print {report_name} report", False, str(e))

def test_report_export(driver, url, export_text, report_name):
    try:
        driver.get(url)
        time.sleep(1)
        driver.find_element(By.LINK_TEXT, export_text).click()
        time.sleep(2)
        # Can't assert file download in all browsers, but can check no error
        report(f"Export {report_name} report as {export_text}", True)
    except Exception as e:
        report(f"Export {report_name} report as {export_text}", False, str(e))

def main():
    driver = webdriver.Chrome()
    driver.maximize_window()
    try:
        unique_id = str(uuid.uuid4())[:8]
        login(driver)
        # --- Customer ---
        cust_name = f"Test Customer {unique_id}"
        cust_gstin = f"GSTIN{unique_id}"
        cust_addr = f"Address {unique_id}"
        cust_name_edited = f"{cust_name} Edited"
        add_customer(driver, cust_name, cust_gstin, cust_addr)
        search_customer(driver, cust_name)
        edit_customer(driver, cust_name, cust_name_edited)
        delete_customer(driver, cust_name_edited)
        # --- Product ---
        prod_name = f"Test Product {unique_id}"
        prod_hsn = f"HSN{unique_id}"
        prod_gst = 5.0
        prod_price = 123.45
        prod_name_edited = f"{prod_name} Edited"
        add_product(driver, prod_name, prod_hsn, prod_gst, prod_price)
        search_product(driver, prod_name)
        edit_product(driver, prod_name, prod_name_edited)
        delete_product(driver, prod_name_edited)
        # --- Invoice ---
        # Add customer and product again for invoice
        add_customer(driver, cust_name, cust_gstin, cust_addr)
        add_product(driver, prod_name, prod_hsn, prod_gst, prod_price)
        today = datetime.now().strftime("%Y-%m-%d")
        add_invoice(driver, cust_name, prod_name, today)
        search_invoice(driver, cust_name)
        # --- Reports ---
        test_report_view(driver, f"{BASE_URL}/reports/sales", "Sales")
        test_report_filter(driver, f"{BASE_URL}/reports/sales", cust_name, "Sales")
        test_report_print(driver, f"{BASE_URL}/reports/sales", "Sales")
        test_report_export(driver, f"{BASE_URL}/reports/sales", "Export Excel", "Sales")
        test_report_export(driver, f"{BASE_URL}/reports/sales", "Export PDF", "Sales")
        test_report_view(driver, f"{BASE_URL}/reports/products", "Product")
        test_report_filter(driver, f"{BASE_URL}/reports/products", prod_name, "Product")
        test_report_print(driver, f"{BASE_URL}/reports/products", "Product")
        test_report_export(driver, f"{BASE_URL}/reports/products", "Export Excel", "Product")
        test_report_export(driver, f"{BASE_URL}/reports/products", "Export PDF", "Product")
        test_report_view(driver, f"{BASE_URL}/reports/customers", "Customer")
        test_report_filter(driver, f"{BASE_URL}/reports/customers", cust_name, "Customer")
        test_report_print(driver, f"{BASE_URL}/reports/customers", "Customer")
        test_report_export(driver, f"{BASE_URL}/reports/customers", "Export Excel", "Customer")
        test_report_export(driver, f"{BASE_URL}/reports/customers", "Export PDF", "Customer")
    finally:
        print_summary()
        driver.quit()

if __name__ == "__main__":
    main()
