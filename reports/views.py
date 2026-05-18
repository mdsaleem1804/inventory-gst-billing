from flask import render_template, request, send_file
from flask_login import login_required
from .routes import reports_bp
from models import Invoice, Product, Customer
import io
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from datetime import datetime


@reports_bp.route('/sales')
@login_required
def sales_report():
	from_date = request.args.get('from_date', '')
	to_date = request.args.get('to_date', '')
	search = request.args.get('search', '')
	export = request.args.get('export', '')
	query = Invoice.query
	if from_date:
		query = query.filter(Invoice.date >= datetime.strptime(from_date, '%Y-%m-%d'))
	if to_date:
		query = query.filter(Invoice.date <= datetime.strptime(to_date, '%Y-%m-%d'))
	if search:
		query = query.filter(
			Invoice.customer_name.ilike(f'%{search}%') |
			Invoice.invoice_number.ilike(f'%{search}%')
		)
	invoices = query.order_by(Invoice.date.desc()).all()
	if export == 'excel':
		df = pd.DataFrame([
			{
				'Date': inv.date.strftime('%Y-%m-%d'),
				'Invoice #': inv.invoice_number,
				'Customer': inv.customer_name,
				'Total': inv.total,
				'CGST': inv.cgst,
				'SGST': inv.sgst
			} for inv in invoices
		])
		buffer = io.BytesIO()
		with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
			df.to_excel(writer, index=False, sheet_name='Sales Report')
		buffer.seek(0)
		return send_file(buffer, as_attachment=True, download_name='sales_report.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
	if export == 'pdf':
		buffer = io.BytesIO()
		p = canvas.Canvas(buffer, pagesize=A4)
		width, height = A4
		y = height - 40
		p.setFont('Helvetica-Bold', 14)
		p.drawString(200, y, 'Sales Report')
		y -= 30
		p.setFont('Helvetica-Bold', 10)
		p.drawString(40, y, 'Date')
		p.drawString(100, y, 'Invoice #')
		p.drawString(180, y, 'Customer')
		p.drawString(320, y, 'Total')
		p.drawString(380, y, 'CGST')
		p.drawString(440, y, 'SGST')
		y -= 15
		p.setFont('Helvetica', 10)
		for inv in invoices:
			p.drawString(40, y, inv.date.strftime('%Y-%m-%d'))
			p.drawString(100, y, inv.invoice_number)
			p.drawString(180, y, inv.customer_name)
			p.drawString(320, y, str(inv.total))
			p.drawString(380, y, str(inv.cgst))
			p.drawString(440, y, str(inv.sgst))
			y -= 15
			if y < 60:
				p.showPage()
				y = height - 40
		p.save()
		buffer.seek(0)
		return send_file(buffer, as_attachment=True, download_name='sales_report.pdf', mimetype='application/pdf')
	return render_template('reports/sales.html', invoices=invoices, from_date=from_date, to_date=to_date, search=search)

@reports_bp.route('/products')
@login_required
def product_report():
	search = request.args.get('search', '')
	export = request.args.get('export', '')
	query = Product.query
	if search:
		query = query.filter(
			Product.name.ilike(f'%{search}%') |
			Product.hsn_code.ilike(f'%{search}%')
		)
	products = query.order_by(Product.id.desc()).all()
	if export == 'excel':
		df = pd.DataFrame([
			{
				'ID': p.id,
				'Name': p.name,
				'HSN Code': p.hsn_code,
				'GST %': p.gst_percent,
				'Price': p.price
			} for p in products
		])
		buffer = io.BytesIO()
		with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
			df.to_excel(writer, index=False, sheet_name='Product Report')
		buffer.seek(0)
		return send_file(buffer, as_attachment=True, download_name='product_report.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
	if export == 'pdf':
		buffer = io.BytesIO()
		p = canvas.Canvas(buffer, pagesize=A4)
		width, height = A4
		y = height - 40
		p.setFont('Helvetica-Bold', 14)
		p.drawString(200, y, 'Product Report')
		y -= 30
		p.setFont('Helvetica-Bold', 10)
		p.drawString(40, y, 'ID')
		p.drawString(80, y, 'Name')
		p.drawString(200, y, 'HSN Code')
		p.drawString(280, y, 'GST %')
		p.drawString(340, y, 'Price')
		y -= 15
		p.setFont('Helvetica', 10)
		for prod in products:
			p.drawString(40, y, str(prod.id))
			p.drawString(80, y, prod.name)
			p.drawString(200, y, prod.hsn_code)
			p.drawString(280, y, str(prod.gst_percent))
			p.drawString(340, y, str(prod.price))
			y -= 15
			if y < 60:
				p.showPage()
				y = height - 40
		p.save()
		buffer.seek(0)
		return send_file(buffer, as_attachment=True, download_name='product_report.pdf', mimetype='application/pdf')
	return render_template('reports/products.html', products=products, search=search)

@reports_bp.route('/customers')
@login_required
def customer_report():
	search = request.args.get('search', '')
	export = request.args.get('export', '')
	query = Customer.query
	if search:
		query = query.filter(
			Customer.name.ilike(f'%{search}%') |
			Customer.gstin.ilike(f'%{search}%')
		)
	customers = query.order_by(Customer.id.desc()).all()
	if export == 'excel':
		df = pd.DataFrame([
			{
				'ID': c.id,
				'Name': c.name,
				'GSTIN': c.gstin,
				'Address': c.address
			} for c in customers
		])
		buffer = io.BytesIO()
		with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
			df.to_excel(writer, index=False, sheet_name='Customer Report')
		buffer.seek(0)
		return send_file(buffer, as_attachment=True, download_name='customer_report.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
	if export == 'pdf':
		buffer = io.BytesIO()
		p = canvas.Canvas(buffer, pagesize=A4)
		width, height = A4
		y = height - 40
		p.setFont('Helvetica-Bold', 14)
		p.drawString(200, y, 'Customer Report')
		y -= 30
		p.setFont('Helvetica-Bold', 10)
		p.drawString(40, y, 'ID')
		p.drawString(80, y, 'Name')
		p.drawString(200, y, 'GSTIN')
		p.drawString(320, y, 'Address')
		y -= 15
		p.setFont('Helvetica', 10)
		for cust in customers:
			p.drawString(40, y, str(cust.id))
			p.drawString(80, y, cust.name)
			p.drawString(200, y, cust.gstin or '')
			p.drawString(320, y, cust.address or '')
			y -= 15
			if y < 60:
				p.showPage()
				y = height - 40
		p.save()
		buffer.seek(0)
		return send_file(buffer, as_attachment=True, download_name='customer_report.pdf', mimetype='application/pdf')
	return render_template('reports/customers.html', customers=customers, search=search)