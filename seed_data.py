import random
from datetime import datetime, timedelta
from app import app
from models import db, User, Product, Customer, Invoice, InvoiceItem
from werkzeug.security import generate_password_hash

FIRST_NAMES = ["John", "Jane", "Alex", "Priya", "Rahul", "Sara", "David", "Amit", "Emily", "Vikram", "Anu", "Ravi", "Sneha", "Kumar", "Meena", "Suresh", "Lata", "Arun", "Divya", "Manoj"]
LAST_NAMES = ["Sharma", "Patel", "Singh", "Kumar", "Reddy", "Nair", "Gupta", "Das", "Mehta", "Joshi", "Bose", "Chopra", "Verma", "Rao", "Iyer", "Jain", "Kapoor", "Mishra", "Saxena", "Yadav"]
ADDRESSES = ["Chennai", "Mumbai", "Delhi", "Bangalore", "Hyderabad", "Pune", "Kolkata", "Ahmedabad", "Jaipur", "Lucknow"]

PRODUCTS = [
    {"name": "Pen", "hsn_code": "9608", "gst_percent": 12, "price": 10},
    {"name": "Notebook", "hsn_code": "4820", "gst_percent": 12, "price": 50},
    {"name": "Pencil", "hsn_code": "9609", "gst_percent": 5, "price": 5},
    {"name": "Eraser", "hsn_code": "4016", "gst_percent": 5, "price": 3},
    {"name": "Bag", "hsn_code": "4202", "gst_percent": 18, "price": 300},
    {"name": "Ruler", "hsn_code": "9017", "gst_percent": 12, "price": 15},
    {"name": "Sharpener", "hsn_code": "8214", "gst_percent": 5, "price": 7},
    {"name": "Marker", "hsn_code": "9608", "gst_percent": 12, "price": 25},
    {"name": "File", "hsn_code": "4820", "gst_percent": 12, "price": 40},
    {"name": "Stapler", "hsn_code": "8205", "gst_percent": 18, "price": 60}
]

def random_gstin():
    return f"{random.choice('1234567890')*2}{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')*5}{random.randint(1000,9999)}"

def random_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"

def random_address():
    return f"{random.choice(ADDRESSES)}, India"

with app.app_context():
    # Add admin user if not exists
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password_hash=generate_password_hash('admin'))
        db.session.add(admin)
        db.session.commit()

    # Add products if table is empty
    if Product.query.count() == 0:
        for prod in PRODUCTS:
            db.session.add(Product(**prod))
        db.session.commit()
        print('Products seeded.')

    # Add customers if table is empty
    if Customer.query.count() == 0:
        for i in range(40):
            name = random_name()
            gstin = random_gstin()
            address = random_address()
            db.session.add(Customer(name=name, gstin=gstin, address=address))
        db.session.commit()
        print('Customers seeded.')

    # Add invoices if table is empty
    if Invoice.query.count() == 0:
        customers = Customer.query.all()
        products = Product.query.all()
        today = datetime.now().date()
        invoice_number = 1
        for day_offset in range(25):
            invoice_date = today - timedelta(days=day_offset)
            for _ in range(10):
                cust = random.choice(customers)
                inv = Invoice(
                    invoice_number=f"INV{invoice_number:05d}",
                    customer_name=cust.name,
                    customer_gstin=cust.gstin,
                    customer_address=cust.address,
                    date=invoice_date,
                    total=0, cgst=0, sgst=0, user_id=1
                )
                db.session.add(inv)
                db.session.flush()  # get inv.id
                num_items = random.randint(1, 4)
                total = cgst = sgst = 0
                for _ in range(num_items):
                    prod = random.choice(products)
                    qty = random.randint(1, 10)
                    price = prod.price
                    gst_percent = prod.gst_percent
                    item_total = price * qty
                    item_gst = item_total * gst_percent / 100
                    item_cgst = item_gst / 2
                    item_sgst = item_gst / 2
                    total += item_total + item_gst
                    cgst += item_cgst
                    sgst += item_sgst
                    db.session.add(InvoiceItem(
                        invoice_id=inv.id,
                        product_id=prod.id,
                        quantity=qty,
                        price=price,
                        gst_percent=gst_percent,
                        cgst=item_cgst,
                        sgst=item_sgst,
                        total=item_total + item_gst
                    ))
                inv.total = total
                inv.cgst = cgst
                inv.sgst = sgst
                invoice_number += 1
        db.session.commit()
        print('Invoices seeded.')
    print('Seeding complete.')
