import random
from datetime import datetime, timedelta
from app import app
from models import db, User, Product, Customer, Invoice, InvoiceItem
from werkzeug.security import generate_password_hash

PRODUCTS = [
    {"name": "ஆச்சி மட்டன் மசாலா (50g)", "hsn_code": "09109100", "gst_percent": 5, "price": 18.57},
    {"name": "ஆச்சி சிக்கன் மசாலா (50g)", "hsn_code": "09109101", "gst_percent": 5, "price": 18.57},
    {"name": "ஆச்சி பிரியாணி மசாலா (100g)", "hsn_code": "09109102", "gst_percent": 5, "price": 36.00},
    {"name": "ஆச்சி மிளகாய் தூள் (200g)", "hsn_code": "09042211", "gst_percent": 5, "price": 62.50},
    {"name": "ஆச்சி மஞ்சள் தூள் (100g)", "hsn_code": "09109103", "gst_percent": 5, "price": 18.00},
    {"name": "ஆச்சி மல்லித்தூள் (100g)", "hsn_code": "09109104", "gst_percent": 5, "price": 20.00},
    {"name": "ஆச்சி கரம் மசாலா (50g)", "hsn_code": "09109105", "gst_percent": 5, "price": 19.00},
    {"name": "ஆச்சி சாம்பார் தூள் (200g)", "hsn_code": "09109106", "gst_percent": 5, "price": 60.00},
    {"name": "ஆச்சி ரசம் தூள் (100g)", "hsn_code": "09109107", "gst_percent": 5, "price": 18.00},
    {"name": "ஆச்சி கறிவேப்பிலை பொடி (50g)", "hsn_code": "09109108", "gst_percent": 5, "price": 22.00},
]

ADDRESSES = [
    "Palayamkottai, Tirunelveli",
    "Melapalayam, Tirunelveli",
    "Vannarapettai, Tirunelveli",
    "Tenkasi Road, Tirunelveli",
    "Veeravanallur, Tirunelveli",
    "Cheranmahadevi, Tirunelveli",
    "Ambasamudram, Tirunelveli",
    "Manur, Tirunelveli",
    "Sankaran Kovil, Tirunelveli",
    "Alangulam, Tirunelveli"
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
        tirunelveli_customers = [
            {"name": "S. Kumar", "gstin": random_gstin(), "address": "Palayamkottai, Tirunelveli"},
            {"name": "Meena Reddy", "gstin": random_gstin(), "address": "Melapalayam, Tirunelveli"},
            {"name": "Mallika", "gstin": random_gstin(), "address": "Vannarapettai, Tirunelveli"},
            {"name": "R. Prakash", "gstin": random_gstin(), "address": "Tenkasi Road, Tirunelveli"},
            {"name": "A. Suresh", "gstin": random_gstin(), "address": "Veeravanallur, Tirunelveli"},
            {"name": "Latha", "gstin": random_gstin(), "address": "Cheranmahadevi, Tirunelveli"},
            {"name": "Arun Kumar", "gstin": random_gstin(), "address": "Ambasamudram, Tirunelveli"},
            {"name": "Divya", "gstin": random_gstin(), "address": "Manur, Tirunelveli"},
            {"name": "Manoj", "gstin": random_gstin(), "address": "Sankaran Kovil, Tirunelveli"},
            {"name": "Sneha", "gstin": random_gstin(), "address": "Alangulam, Tirunelveli"},
        ]
        for cust in tirunelveli_customers:
            db.session.add(Customer(**cust))
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
