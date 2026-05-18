from flask import Blueprint, render_template, request
from flask_login import login_required

dashboard_bp = Blueprint('dashboard', __name__)

from models import db, Invoice, InvoiceItem, Product, Customer
from sqlalchemy import func, desc
from datetime import datetime, timedelta


@dashboard_bp.route('/', methods=['GET', 'POST'])
@login_required
def dashboard():
    # Date filter
    today = datetime.now().date()
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    try:
        from_date_obj = datetime.strptime(from_date, '%Y-%m-%d').date() if from_date else today
    except:
        from_date_obj = today
    try:
        to_date_obj = datetime.strptime(to_date, '%Y-%m-%d').date() if to_date else today
    except:
        to_date_obj = today

    # Sales in date range
    sales = (
        db.session.query(
            InvoiceItem.id,
            Product.name.label('product_name'),
            InvoiceItem.quantity,
            InvoiceItem.price,
            (InvoiceItem.quantity * InvoiceItem.price * InvoiceItem.gst_percent / 100).label('gst'),
            (InvoiceItem.quantity * InvoiceItem.price + InvoiceItem.quantity * InvoiceItem.price * InvoiceItem.gst_percent / 100).label('total'),
            Invoice.id.label('invoice_id'),
            Invoice.customer_name
        )
        .join(Invoice, InvoiceItem.invoice_id == Invoice.id)
        .join(Product, InvoiceItem.product_id == Product.id)
        .filter(func.date(Invoice.date) >= from_date_obj, func.date(Invoice.date) <= to_date_obj)
        .order_by(Invoice.date.desc())
        .all()
    )
    # Summary
    total_sales = db.session.query(func.sum(Invoice.total)).filter(func.date(Invoice.date) >= from_date_obj, func.date(Invoice.date) <= to_date_obj).scalar() or 0
    total_gst = db.session.query(func.sum(Invoice.cgst + Invoice.sgst)).filter(func.date(Invoice.date) >= from_date_obj, func.date(Invoice.date) <= to_date_obj).scalar() or 0
    total_invoices = db.session.query(func.count(Invoice.id)).filter(func.date(Invoice.date) >= from_date_obj, func.date(Invoice.date) <= to_date_obj).scalar() or 0
    total_customers = db.session.query(func.count(Customer.id)).scalar() or 0
    # Top 5 products by sales (date range)
    top_products = (
        db.session.query(
            Product.name,
            func.sum(InvoiceItem.quantity).label('qty')
        )
        .join(InvoiceItem, InvoiceItem.product_id == Product.id)
        .join(Invoice, InvoiceItem.invoice_id == Invoice.id)
        .filter(func.date(Invoice.date) >= from_date_obj, func.date(Invoice.date) <= to_date_obj)
        .group_by(Product.name)
        .order_by(desc('qty'))
        .limit(5)
        .all()
    )
    # Customer analytics: Top 5 customers by sales
    top_customers = (
        db.session.query(
            Invoice.customer_name,
            func.sum(Invoice.total).label('total_sales'),
            func.count(Invoice.id).label('invoice_count')
        )
        .filter(func.date(Invoice.date) >= from_date_obj, func.date(Invoice.date) <= to_date_obj)
        .group_by(Invoice.customer_name)
        .order_by(desc('total_sales'))
        .limit(5)
        .all()
    )
    return render_template(
        'dashboard.html',
        today=today,
        from_date=from_date_obj,
        to_date=to_date_obj,
        sales=sales,
        total_sales=total_sales,
        total_gst=total_gst,
        total_invoices=total_invoices,
        total_customers=total_customers,
        top_products=top_products,
        top_customers=top_customers
    )
