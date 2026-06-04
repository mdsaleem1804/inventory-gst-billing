from flask import render_template, request, send_file, Response
from flask_login import login_required, current_user
from .routes import reports_bp
from models import db, Invoice, Product, Customer, ActivityLog, Payment, is_finance_feature_enabled
import io
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from datetime import datetime, timedelta
from sqlalchemy import func
from collections import defaultdict


def _export_amount(value):
	return f"{float(value or 0):.2f}"


def _log_report_export(action, details):
	db.session.add(
		ActivityLog(
			user_id=current_user.id,
			username=current_user.username,
			action=action,
			details=details,
		)
	)
	db.session.commit()


def _require_finance_reports():
	if not is_finance_feature_enabled():
		from flask import flash, redirect, url_for
		flash('Finance reporting is disabled for this customer.', 'warning')
		return redirect(url_for('dashboard.dashboard'))
	return None


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
				'Total': _export_amount(inv.total),
				'CGST': _export_amount(inv.cgst),
				'SGST': _export_amount(inv.sgst)
			} for inv in invoices
		])
		buffer = io.BytesIO()
		with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
			df.to_excel(writer, index=False, sheet_name='Sales Report')
		buffer.seek(0)
		_log_report_export('Sales Report Exported Excel', f'Sales rows={len(invoices)} from={from_date or "-"} to={to_date or "-"} search={search or "-"}')
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
		_log_report_export('Sales Report Exported PDF', f'Sales rows={len(invoices)} from={from_date or "-"} to={to_date or "-"} search={search or "-"}')
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
				'GST %': _export_amount(p.gst_percent),
				'Price': _export_amount(p.price)
			} for p in products
		])
		buffer = io.BytesIO()
		with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
			df.to_excel(writer, index=False, sheet_name='Product Report')
		buffer.seek(0)
		_log_report_export('Product Report Exported Excel', f'Product rows={len(products)} search={search or "-"}')
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
		_log_report_export('Product Report Exported PDF', f'Product rows={len(products)} search={search or "-"}')
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
		_log_report_export('Customer Report Exported Excel', f'Customer rows={len(customers)} search={search or "-"}')
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
		_log_report_export('Customer Report Exported PDF', f'Customer rows={len(customers)} search={search or "-"}')
		return send_file(buffer, as_attachment=True, download_name='customer_report.pdf', mimetype='application/pdf')
	return render_template('reports/customers.html', customers=customers, search=search)


@reports_bp.route('/payments')
@login_required
def payment_report():
	blocked = _require_finance_reports()
	if blocked:
		return blocked

	from_date = request.args.get('from_date', '')
	to_date = request.args.get('to_date', '')
	search = request.args.get('search', '')
	payment_mode = request.args.get('payment_mode', '')
	status = request.args.get('status', '')
	export = request.args.get('export', '')

	payment_query = db.session.query(Payment, Invoice).join(Invoice, Payment.invoice_id == Invoice.id)
	if from_date:
		payment_query = payment_query.filter(db.func.date(Payment.payment_date) >= from_date)
	if to_date:
		payment_query = payment_query.filter(db.func.date(Payment.payment_date) <= to_date)
	if search:
		payment_query = payment_query.filter(
			Invoice.customer_name.ilike(f'%{search}%') |
			Invoice.invoice_number.ilike(f'%{search}%')
		)
	if payment_mode:
		payment_query = payment_query.filter(Payment.payment_mode == payment_mode)
	if status:
		payment_query = payment_query.filter(Invoice.payment_status == status)

	payment_rows = payment_query.order_by(Payment.payment_date.desc(), Payment.id.desc()).all()

	filtered_collected = round(sum(float(pay.amount or 0) for pay, _ in payment_rows), 2)
	today_str = datetime.now().date().strftime('%Y-%m-%d')
	yesterday_str = (datetime.now().date() - timedelta(days=1)).strftime('%Y-%m-%d')
	today_collected = (
		db.session.query(func.coalesce(func.sum(Payment.amount), 0.0))
		.filter(db.func.date(Payment.payment_date) == today_str)
		.scalar() or 0.0
	)
	yesterday_collected = (
		db.session.query(func.coalesce(func.sum(Payment.amount), 0.0))
		.filter(db.func.date(Payment.payment_date) == yesterday_str)
		.scalar() or 0.0
	)
	outstanding_total = (
		db.session.query(func.coalesce(func.sum(Invoice.balance_amount), 0.0)).scalar() or 0.0
	)

	customer_summary_query = db.session.query(
		Invoice.customer_name.label('customer_name'),
		func.count(Invoice.id).label('invoice_count'),
		func.coalesce(func.sum(Invoice.total), 0.0).label('billed_total'),
		func.coalesce(func.sum(Invoice.paid_amount), 0.0).label('paid_total'),
		func.coalesce(func.sum(Invoice.balance_amount), 0.0).label('balance_total'),
	)
	if search:
		customer_summary_query = customer_summary_query.filter(Invoice.customer_name.ilike(f'%{search}%'))
	if status:
		customer_summary_query = customer_summary_query.filter(Invoice.payment_status == status)
	customer_summary_rows = customer_summary_query.group_by(Invoice.customer_name).order_by(Invoice.customer_name.asc()).all()

	collected_by_customer = {}
	for pay, inv in payment_rows:
		key = inv.customer_name
		collected_by_customer[key] = round(collected_by_customer.get(key, 0.0) + float(pay.amount or 0), 2)

	customer_summaries = []
	for row in customer_summary_rows:
		customer_summaries.append(
			{
				'customer_name': row.customer_name,
				'invoice_count': int(row.invoice_count or 0),
				'billed_total': round(float(row.billed_total or 0), 2),
				'paid_total': round(float(row.paid_total or 0), 2),
				'balance_total': round(float(row.balance_total or 0), 2),
				'collected_in_filter': round(float(collected_by_customer.get(row.customer_name, 0.0)), 2),
			}
		)

	payment_modes = [
		mode[0]
		for mode in db.session.query(Payment.payment_mode)
		.filter(Payment.payment_mode.isnot(None), Payment.payment_mode != '')
		.distinct()
		.order_by(Payment.payment_mode.asc())
		.all()
	]

	if export == 'csv':
		csv_df = pd.DataFrame([
			{
				'Payment Date': pay.payment_date.strftime('%Y-%m-%d'),
				'Invoice #': inv.invoice_number,
				'Customer': inv.customer_name,
				'Invoice Status': inv.payment_status,
				'Invoice Total': _export_amount(inv.total),
				'Invoice Paid': _export_amount(inv.paid_amount),
				'Invoice Balance': _export_amount(inv.balance_amount),
				'Payment Amount': _export_amount(pay.amount),
				'Payment Mode': pay.payment_mode,
				'Reference': pay.reference_no,
				'Notes': pay.notes,
				'Received By': pay.received_by_user.username if pay.received_by_user else '',
			}
			for pay, inv in payment_rows
		])
		csv_content = csv_df.to_csv(index=False)
		_log_report_export(
			'Payment Report Exported CSV',
			f'Payment rows={len(payment_rows)} from={from_date or "-"} to={to_date or "-"} search={search or "-"} mode={payment_mode or "-"} status={status or "-"}'
		)
		return Response(
			csv_content,
			mimetype='text/csv',
			headers={'Content-Disposition': 'attachment; filename=payment_report.csv'}
		)

	if export == 'excel':
		payments_df = pd.DataFrame([
			{
				'Payment Date': pay.payment_date.strftime('%Y-%m-%d'),
				'Invoice #': inv.invoice_number,
				'Customer': inv.customer_name,
				'Invoice Status': inv.payment_status,
				'Invoice Total': _export_amount(inv.total),
				'Invoice Paid': _export_amount(inv.paid_amount),
				'Invoice Balance': _export_amount(inv.balance_amount),
				'Payment Amount': _export_amount(pay.amount),
				'Payment Mode': pay.payment_mode,
				'Reference': pay.reference_no,
				'Notes': pay.notes,
				'Received By': pay.received_by_user.username if pay.received_by_user else '',
			}
			for pay, inv in payment_rows
		])
		customer_df = pd.DataFrame(customer_summaries)
		buffer = io.BytesIO()
		with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
			payments_df.to_excel(writer, index=False, sheet_name='Payment History')
			customer_df.to_excel(writer, index=False, sheet_name='Customer Summary')
		buffer.seek(0)
		_log_report_export(
			'Payment Report Exported Excel',
			f'Payment rows={len(payment_rows)} customers={len(customer_summaries)} from={from_date or "-"} to={to_date or "-"} search={search or "-"} mode={payment_mode or "-"} status={status or "-"}'
		)
		return send_file(
			buffer,
			as_attachment=True,
			download_name='payment_report.xlsx',
			mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
		)

	return render_template(
		'reports/payments.html',
		payment_rows=payment_rows,
		customer_summaries=customer_summaries,
		from_date=from_date,
		to_date=to_date,
		search=search,
		payment_mode=payment_mode,
		status=status,
		payment_modes=payment_modes,
		filtered_collected=round(float(filtered_collected), 2),
		today_collected=round(float(today_collected), 2),
		yesterday_collected=round(float(yesterday_collected), 2),
		outstanding_total=round(float(outstanding_total), 2),
	)


@reports_bp.route('/outstanding-aging')
@login_required
def outstanding_aging_report():
	blocked = _require_finance_reports()
	if blocked:
		return blocked

	as_of_date_str = request.args.get('as_of_date', '')
	search = request.args.get('search', '')
	priority_threshold = request.args.get('priority_threshold', '10000')
	export = request.args.get('export', '')

	try:
		priority_threshold_value = round(float(priority_threshold), 2)
	except (TypeError, ValueError):
		priority_threshold_value = 10000.0
	if priority_threshold_value < 0:
		priority_threshold_value = 0.0

	as_of_date = datetime.now().date()
	if as_of_date_str:
		try:
			as_of_date = datetime.strptime(as_of_date_str, '%Y-%m-%d').date()
		except ValueError:
			as_of_date = datetime.now().date()

	query = Invoice.query.filter((Invoice.balance_amount if Invoice.balance_amount is not None else 0) >= 0)
	query = query.filter(Invoice.balance_amount > 0)
	if search:
		query = query.filter(
			Invoice.customer_name.ilike(f'%{search}%') |
			Invoice.invoice_number.ilike(f'%{search}%')
		)

	invoices = query.order_by(Invoice.date.asc()).all()

	bucket_totals = {
		'0_30': 0.0,
		'31_60': 0.0,
		'61_90': 0.0,
		'90_plus': 0.0,
	}

	customer_bucket_map = defaultdict(
		lambda: {
			'customer_name': '',
			'invoice_count': 0,
			'0_30': 0.0,
			'31_60': 0.0,
			'61_90': 0.0,
			'90_plus': 0.0,
			'total_outstanding': 0.0,
			'oldest_days': 0,
		}
	)

	invoice_rows = []
	for inv in invoices:
		invoice_date = inv.date.date() if hasattr(inv.date, 'date') else inv.date
		age_days = (as_of_date - invoice_date).days if invoice_date else 0
		if age_days < 0:
			age_days = 0

		balance = round(float(inv.balance_amount or 0), 2)
		bucket_key = '0_30'
		if age_days <= 30:
			bucket_key = '0_30'
		elif age_days <= 60:
			bucket_key = '31_60'
		elif age_days <= 90:
			bucket_key = '61_90'
		else:
			bucket_key = '90_plus'

		bucket_totals[bucket_key] += balance

		customer_key = inv.customer_name or '-'
		customer_row = customer_bucket_map[customer_key]
		customer_row['customer_name'] = customer_key
		customer_row['invoice_count'] += 1
		customer_row[bucket_key] += balance
		customer_row['total_outstanding'] += balance
		customer_row['oldest_days'] = max(customer_row['oldest_days'], age_days)

		invoice_rows.append(
			{
				'invoice_number': inv.invoice_number,
				'customer_name': inv.customer_name,
				'invoice_date': invoice_date,
				'age_days': age_days,
				'bucket': bucket_key,
				'invoice_total': round(float(inv.total or 0), 2),
				'paid_amount': round(float(inv.paid_amount or 0), 2),
				'balance_amount': balance,
				'payment_status': inv.payment_status,
			}
		)

	customer_rows = []
	for row in customer_bucket_map.values():
		total_outstanding = round(float(row['total_outstanding']), 2)
		oldest_days = int(row['oldest_days'])
		priority_level = 'normal'
		if oldest_days > 60 and total_outstanding >= priority_threshold_value:
			priority_level = 'high'
		elif oldest_days > 30 and total_outstanding >= (priority_threshold_value * 0.5):
			priority_level = 'medium'
		customer_rows.append(
			{
				'customer_name': row['customer_name'],
				'invoice_count': row['invoice_count'],
				'0_30': round(float(row['0_30']), 2),
				'31_60': round(float(row['31_60']), 2),
				'61_90': round(float(row['61_90']), 2),
				'90_plus': round(float(row['90_plus']), 2),
				'total_outstanding': total_outstanding,
				'oldest_days': oldest_days,
				'priority_level': priority_level,
			}
		)

	customer_rows.sort(key=lambda r: (r['total_outstanding'], r['oldest_days']), reverse=True)

	bucket_totals = {k: round(float(v), 2) for k, v in bucket_totals.items()}
	grand_outstanding = round(sum(bucket_totals.values()), 2)
	high_priority_count = len([r for r in customer_rows if r['priority_level'] == 'high'])
	medium_priority_count = len([r for r in customer_rows if r['priority_level'] == 'medium'])

	if export == 'csv':
		df = pd.DataFrame(
			[
				{
					'Invoice #': row['invoice_number'],
					'Customer': row['customer_name'],
					'Invoice Date': row['invoice_date'].strftime('%Y-%m-%d') if row['invoice_date'] else '',
					'Age Days': row['age_days'],
					'Bucket': row['bucket'],
					'Invoice Total': _export_amount(row['invoice_total']),
					'Paid': _export_amount(row['paid_amount']),
					'Balance': _export_amount(row['balance_amount']),
					'Status': row['payment_status'],
				}
				for row in invoice_rows
			]
		)
		csv_content = df.to_csv(index=False)
		_log_report_export(
			'Outstanding Aging Exported CSV',
			f'Outstanding invoice_rows={len(invoice_rows)} as_of={as_of_date.strftime("%Y-%m-%d")} search={search or "-"}'
		)
		return Response(
			csv_content,
			mimetype='text/csv',
			headers={'Content-Disposition': 'attachment; filename=outstanding_aging_report.csv'}
		)

	if export == 'excel':
		invoice_df = pd.DataFrame(
			[
				{
					'Invoice #': row['invoice_number'],
					'Customer': row['customer_name'],
					'Invoice Date': row['invoice_date'].strftime('%Y-%m-%d') if row['invoice_date'] else '',
					'Age Days': row['age_days'],
					'Bucket': row['bucket'],
					'Invoice Total': _export_amount(row['invoice_total']),
					'Paid': _export_amount(row['paid_amount']),
					'Balance': _export_amount(row['balance_amount']),
					'Status': row['payment_status'],
				}
				for row in invoice_rows
			]
		)
		customer_df = pd.DataFrame(customer_rows)
		buffer = io.BytesIO()
		with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
			customer_df.to_excel(writer, index=False, sheet_name='Customer Aging')
			invoice_df.to_excel(writer, index=False, sheet_name='Invoice Aging')
		buffer.seek(0)
		_log_report_export(
			'Outstanding Aging Exported Excel',
			f'Outstanding invoice_rows={len(invoice_rows)} customers={len(customer_rows)} as_of={as_of_date.strftime("%Y-%m-%d")} search={search or "-"}'
		)
		return send_file(
			buffer,
			as_attachment=True,
			download_name='outstanding_aging_report.xlsx',
			mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
		)

	return render_template(
		'reports/outstanding_aging.html',
		as_of_date=as_of_date.strftime('%Y-%m-%d'),
		search=search,
		priority_threshold=priority_threshold_value,
		bucket_totals=bucket_totals,
		grand_outstanding=grand_outstanding,
		high_priority_count=high_priority_count,
		medium_priority_count=medium_priority_count,
		customer_rows=customer_rows,
		invoice_rows=invoice_rows,
	)