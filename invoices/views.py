
import pandas as pd
from flask import send_file, render_template, redirect, url_for, flash, request
import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from flask_login import login_required, current_user
from .routes import invoices_bp
from models import db, Invoice, InvoiceItem, Product
from datetime import datetime

@invoices_bp.route('/export/excel')
@login_required
def export_invoices_excel():
    invoices = Invoice.query.order_by(Invoice.date.desc()).all()
    data = []
    for inv in invoices:
        data.append({
            'Invoice #': inv.invoice_number,
            'Date': inv.date.strftime('%Y-%m-%d'),
            'Customer': inv.customer_name,
            'GSTIN': inv.customer_gstin,
            'Total': inv.total,
            'CGST': inv.cgst,
            'SGST': inv.sgst
        })
    df = pd.DataFrame(data)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Invoices')
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name='invoices.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@invoices_bp.route('/<int:invoice_id>/pdf')
@login_required
def download_invoice_pdf(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    items = invoice.items
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 50
    p.setFont('Helvetica-Bold', 16)
    p.drawString(200, y, 'TAX INVOICE')
    y -= 30
    p.setFont('Helvetica', 10)
    p.drawString(50, y, f'Invoice #: {invoice.invoice_number}')
    p.drawString(300, y, f'Date: {invoice.date.strftime("%d-%m-%Y")}')
    y -= 20
    p.drawString(50, y, f'Customer: {invoice.customer_name}')
    p.drawString(300, y, f'GSTIN: {invoice.customer_gstin}')
    y -= 20
    p.drawString(50, y, f'Address: {invoice.customer_address}')
    y -= 30
    p.setFont('Helvetica-Bold', 10)
    p.drawString(50, y, 'No.')
    p.drawString(80, y, 'Product')
    p.drawString(180, y, 'HSN')
    p.drawString(230, y, 'Qty')
    p.drawString(270, y, 'Price')
    p.drawString(320, y, 'GST %')
    p.drawString(370, y, 'CGST')
    p.drawString(420, y, 'SGST')
    p.drawString(470, y, 'Total')
    y -= 15
    p.setFont('Helvetica', 10)
    for idx, item in enumerate(items, 1):
        p.drawString(50, y, str(idx))
        p.drawString(80, y, item.product.name)
        p.drawString(180, y, item.product.hsn_code)
        p.drawString(230, y, str(item.quantity))
        p.drawString(270, y, str(item.price))
        p.drawString(320, y, str(item.gst_percent))
        p.drawString(370, y, str(item.cgst))
        p.drawString(420, y, str(item.sgst))
        p.drawString(470, y, str(item.total))
        y -= 15
        if y < 100:
            p.showPage()
            y = height - 50
    y -= 10
    p.setFont('Helvetica-Bold', 10)
    p.drawString(320, y, 'Grand Total:')
    p.drawString(420, y, str(invoice.total))
    y -= 15
    p.drawString(320, y, 'Total CGST:')
    p.drawString(420, y, str(invoice.cgst))
    y -= 15
    p.drawString(320, y, 'Total SGST:')
    p.drawString(420, y, str(invoice.sgst))
    p.showPage()
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f'invoice_{invoice.invoice_number}.pdf', mimetype='application/pdf')

@invoices_bp.route('/<int:invoice_id>')
@login_required
def view_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    items = invoice.items
    from models import Company
    company = Company.query.first()
    return render_template('invoices/view.html', invoice=invoice, items=items, company=company)


def get_next_invoice_number():
	last_invoice = Invoice.query.order_by(Invoice.id.desc()).first()
	if last_invoice:
		try:
			return f"INV{int(last_invoice.invoice_number[3:]) + 1:05d}"
		except:
			return f"INV{last_invoice.id + 1:05d}"
	return "INV00001"


@invoices_bp.route('/', methods=['GET', 'POST'])
@login_required
def crud_invoices():
    edit_id = request.args.get('edit_id', type=int)
    form_invoice = None
    products = Product.query.all()
    from models import Customer
    customers = Customer.query.order_by(Customer.name).all()
    if request.method == 'POST':
        # Delete
        delete_id = request.form.get('delete_id', type=int)
        if delete_id:
            invoice = Invoice.query.get(delete_id)
            if invoice:
                # Delete items first
                InvoiceItem.query.filter_by(invoice_id=invoice.id).delete()
                db.session.delete(invoice)
                db.session.commit()
                flash('Invoice deleted!', 'success')
            return redirect(url_for('invoices.crud_invoices'))
        # Add or Update
        iid = request.form.get('id', type=int)
        customer_id = request.form.get('customer_id', type=int)
        customer = Customer.query.get(customer_id) if customer_id else None
        customer_name = customer.name if customer else ''
        customer_gstin = customer.gstin if customer else ''
        customer_address = customer.address if customer else ''
        product_ids = request.form.getlist('product_id')
        quantities = request.form.getlist('quantity')
        items = []
        total = 0
        cgst = 0
        sgst = 0
        for i, product_id in enumerate(product_ids):
            product = Product.query.get(int(product_id))
            quantity = int(quantities[i])
            price = product.price
            gst_percent = product.gst_percent
            item_total = price * quantity
            item_gst = item_total * gst_percent / 100
            item_cgst = item_gst / 2
            item_sgst = item_gst / 2
            total += item_total + item_gst
            cgst += item_cgst
            sgst += item_sgst
            items.append({'product_id': product.id, 'quantity': quantity, 'price': price, 'gst_percent': gst_percent, 'cgst': item_cgst, 'sgst': item_sgst, 'total': item_total + item_gst})
        # Round totals to two decimals
        total = round(total, 2)
        cgst = round(cgst, 2)
        sgst = round(sgst, 2)
        if iid:
            invoice = Invoice.query.get(iid)
            if invoice:
                invoice.customer_name = customer_name
                invoice.customer_gstin = customer_gstin
                invoice.customer_address = customer_address
                invoice.total = total
                invoice.cgst = cgst
                invoice.sgst = sgst
                # Remove old items
                InvoiceItem.query.filter_by(invoice_id=invoice.id).delete()
                db.session.flush()
                for item in items:
                    db.session.add(InvoiceItem(invoice_id=invoice.id, **item))
                db.session.commit()
                flash('Invoice updated!', 'success')
        else:
            invoice = Invoice(
                invoice_number=get_next_invoice_number(),
                customer_name=customer_name,
                customer_gstin=customer_gstin,
                customer_address=customer_address,
                date=datetime.now(),
                total=total,
                cgst=cgst,
                sgst=sgst,
                user_id=current_user.id
            )
            db.session.add(invoice)
            db.session.flush()
            for item in items:
                db.session.add(InvoiceItem(invoice_id=invoice.id, **item))
            db.session.commit()
            flash('Invoice added!', 'success')
        return redirect(url_for('invoices.crud_invoices'))
    # GET
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    if not from_date and not to_date:
        today = datetime.now().strftime('%Y-%m-%d')
        from_date = to_date = today
    search = request.args.get('search', '')
    query = Invoice.query
    from sqlalchemy import func
    if from_date:
        query = query.filter(func.date(Invoice.date) >= from_date)
    if to_date:
        query = query.filter(func.date(Invoice.date) <= to_date)
    if search:
        query = query.filter(
            Invoice.invoice_number.ilike(f'%{search}%') |
            Invoice.customer_name.ilike(f'%{search}%')
        )
    if edit_id:
        form_invoice = Invoice.query.get(edit_id)
    invoices = query.order_by(Invoice.created_at.desc() if hasattr(Invoice, 'created_at') else Invoice.date.desc()).all()
    return render_template('invoices/crud.html', invoices=invoices, form_invoice=form_invoice, products=products, customers=customers, from_date=from_date, to_date=to_date, search=search)