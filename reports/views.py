from flask import render_template, request
from flask_login import login_required
from .routes import reports_bp
from models import Invoice
from datetime import datetime

@reports_bp.route('/sales')
@login_required
def sales_report():
	from_date = request.args.get('from_date', '')
	to_date = request.args.get('to_date', '')
	query = Invoice.query
	if from_date:
		query = query.filter(Invoice.date >= datetime.strptime(from_date, '%Y-%m-%d'))
	if to_date:
		query = query.filter(Invoice.date <= datetime.strptime(to_date, '%Y-%m-%d'))
	invoices = query.order_by(Invoice.date.desc()).all()
	return render_template('reports/sales.html', invoices=invoices, from_date=from_date, to_date=to_date)