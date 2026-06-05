from flask import Blueprint, render_template, request
from flask_login import login_required

dashboard_bp = Blueprint('dashboard', __name__)

from models import db, Invoice, InvoiceItem, Product, Customer, Payment, Expense, FollowUpTask, PromiseToPay, ActivityLog
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

    from_date_value = from_date_obj.strftime('%Y-%m-%d')
    to_date_value = to_date_obj.strftime('%Y-%m-%d')

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
            Invoice.customer_name,
            Invoice.total.label('invoice_total'),
            Invoice.paid_amount.label('invoice_paid_amount'),
            Invoice.payment_status.label('invoice_payment_status')
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

    # Collection and cashflow KPIs
    today_collections = (
        db.session.query(func.coalesce(func.sum(Payment.amount), 0.0))
        .filter(func.date(Payment.payment_date) == today)
        .scalar()
        or 0
    )
    today_expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0.0))
        .filter(func.date(Expense.expense_date) == today)
        .scalar()
        or 0
    )
    today_net_cash_flow = round(float(today_collections) - float(today_expenses), 2)

    last_7_days = today - timedelta(days=6)
    collections_7_days = (
        db.session.query(func.coalesce(func.sum(Payment.amount), 0.0))
        .filter(func.date(Payment.payment_date) >= last_7_days, func.date(Payment.payment_date) <= today)
        .scalar()
        or 0
    )
    expenses_7_days = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0.0))
        .filter(func.date(Expense.expense_date) >= last_7_days, func.date(Expense.expense_date) <= today)
        .scalar()
        or 0
    )
    net_cash_flow_7_days = round(float(collections_7_days) - float(expenses_7_days), 2)

    yesterday = today - timedelta(days=1)
    yesterday_collections = (
        db.session.query(func.coalesce(func.sum(Payment.amount), 0.0))
        .filter(func.date(Payment.payment_date) == yesterday)
        .scalar()
        or 0
    )
    avg_daily_collections_7_days = round(float(collections_7_days) / 7.0, 2)

    collections_trend = [
        {'label': 'Yesterday', 'value': round(float(yesterday_collections), 2), 'bar_class': 'bg-secondary'},
        {'label': 'Today', 'value': round(float(today_collections), 2), 'bar_class': 'bg-success'},
        {'label': '7-Day Avg', 'value': avg_daily_collections_7_days, 'bar_class': 'bg-primary'},
    ]
    trend_max_value = max([point['value'] for point in collections_trend] + [1.0])
    for point in collections_trend:
        point['percent'] = round((point['value'] / trend_max_value) * 100.0, 2) if trend_max_value > 0 else 0.0

    # Receivables and aging
    outstanding_invoices = (
        Invoice.query
        .filter((Invoice.balance_amount if Invoice.balance_amount is not None else 0) > 0)
        .order_by(Invoice.date.asc())
        .all()
    )

    total_outstanding = 0.0
    overdue_amount = 0.0
    overdue_invoices = 0
    aging_buckets = {
        '0_30': 0.0,
        '31_60': 0.0,
        '61_90': 0.0,
        '90_plus': 0.0,
    }

    for inv in outstanding_invoices:
        inv_balance = round(float(inv.balance_amount or 0), 2)
        inv_date = inv.date.date() if inv.date else today
        age_days = max((today - inv_date).days, 0)
        total_outstanding += inv_balance

        if inv_date < today:
            overdue_invoices += 1
            overdue_amount += inv_balance

        if age_days <= 30:
            aging_buckets['0_30'] += inv_balance
        elif age_days <= 60:
            aging_buckets['31_60'] += inv_balance
        elif age_days <= 90:
            aging_buckets['61_90'] += inv_balance
        else:
            aging_buckets['90_plus'] += inv_balance

    aging_buckets = {k: round(v, 2) for k, v in aging_buckets.items()}
    total_outstanding = round(total_outstanding, 2)
    overdue_amount = round(overdue_amount, 2)

    aging_composition = [
        {
            'key': '0_30',
            'label': '0-30 days',
            'amount': aging_buckets['0_30'],
            'bar_class': 'bg-success',
        },
        {
            'key': '31_60',
            'label': '31-60 days',
            'amount': aging_buckets['31_60'],
            'bar_class': 'bg-info',
        },
        {
            'key': '61_90',
            'label': '61-90 days',
            'amount': aging_buckets['61_90'],
            'bar_class': 'bg-warning',
        },
        {
            'key': '90_plus',
            'label': '90+ days',
            'amount': aging_buckets['90_plus'],
            'bar_class': 'bg-danger',
        },
    ]
    for bucket in aging_composition:
        bucket['percent'] = round((float(bucket['amount']) / float(total_outstanding)) * 100.0, 2) if total_outstanding > 0 else 0.0

    # Follow-up and commitment workloads
    follow_up_open_count = FollowUpTask.query.filter(FollowUpTask.status == 'open').count()
    follow_up_due_today_count = FollowUpTask.query.filter(FollowUpTask.status == 'open', FollowUpTask.due_date == today).count()
    follow_up_overdue_count = FollowUpTask.query.filter(FollowUpTask.status == 'open', FollowUpTask.due_date.isnot(None), FollowUpTask.due_date < today).count()

    promise_open_count = PromiseToPay.query.filter(PromiseToPay.status == 'open').count()
    promise_due_today_count = PromiseToPay.query.filter(PromiseToPay.status == 'open', PromiseToPay.promised_date == today).count()
    promise_broken_count = PromiseToPay.query.filter(PromiseToPay.status == 'open', PromiseToPay.promised_date.isnot(None), PromiseToPay.promised_date < today).count()

    # Top outstanding customers
    top_due_customers = (
        db.session.query(
            Invoice.customer_name,
            func.sum(Invoice.balance_amount).label('outstanding'),
            func.count(Invoice.id).label('open_invoices')
        )
        .filter(Invoice.balance_amount > 0)
        .group_by(Invoice.customer_name)
        .order_by(desc('outstanding'))
        .limit(5)
        .all()
    )

    # Credit risk snapshot against customer credit limits
    customer_balance_map = {
        (row.customer_name or '').strip().lower(): round(float(row.outstanding or 0), 2)
        for row in (
            db.session.query(
                Invoice.customer_name.label('customer_name'),
                func.coalesce(func.sum(Invoice.balance_amount), 0.0).label('outstanding')
            )
            .group_by(Invoice.customer_name)
            .all()
        )
    }

    credit_risk_customers = []
    for customer in Customer.query.filter(Customer.credit_limit > 0).all():
        outstanding = customer_balance_map.get((customer.name or '').strip().lower(), 0.0)
        credit_limit = round(float(customer.credit_limit or 0), 2)
        over_limit = round(max(outstanding - credit_limit, 0.0), 2)
        if over_limit > 0:
            credit_risk_customers.append(
                {
                    'name': customer.name,
                    'credit_limit': credit_limit,
                    'outstanding': outstanding,
                    'over_limit': over_limit,
                }
            )
    credit_risk_customers.sort(key=lambda row: row['over_limit'], reverse=True)
    credit_risk_customers = credit_risk_customers[:5]

    recent_activity = (
        ActivityLog.query
        .order_by(ActivityLog.timestamp.desc(), ActivityLog.id.desc())
        .limit(8)
        .all()
    )

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
    sales_with_overpaid = []
    for sale in sales:
        sales_with_overpaid.append(
            {
                'id': sale.id,
                'product_name': sale.product_name,
                'quantity': sale.quantity,
                'price': sale.price,
                'gst': sale.gst,
                'total': sale.total,
                'invoice_id': sale.invoice_id,
                'customer_name': sale.customer_name,
                'invoice_total': round(float(sale.invoice_total or 0), 2),
                'invoice_paid_amount': round(float(sale.invoice_paid_amount or 0), 2),
                'invoice_payment_status': sale.invoice_payment_status,
                'overpaid_amount': round(max(float(sale.invoice_paid_amount or 0) - float(sale.invoice_total or 0), 0.0), 2),
            }
        )
    return render_template(
        'dashboard.html',
        today=today,
        from_date=from_date_value,
        to_date=to_date_value,
        sales=sales_with_overpaid,
        total_sales=total_sales,
        total_gst=total_gst,
        total_invoices=total_invoices,
        total_customers=total_customers,
        today_collections=today_collections,
        today_expenses=today_expenses,
        today_net_cash_flow=today_net_cash_flow,
        collections_7_days=collections_7_days,
        expenses_7_days=expenses_7_days,
        net_cash_flow_7_days=net_cash_flow_7_days,
        collections_trend=collections_trend,
        total_outstanding=total_outstanding,
        overdue_amount=overdue_amount,
        overdue_invoices=overdue_invoices,
        aging_buckets=aging_buckets,
        aging_composition=aging_composition,
        follow_up_open_count=follow_up_open_count,
        follow_up_due_today_count=follow_up_due_today_count,
        follow_up_overdue_count=follow_up_overdue_count,
        promise_open_count=promise_open_count,
        promise_due_today_count=promise_due_today_count,
        promise_broken_count=promise_broken_count,
        top_due_customers=top_due_customers,
        credit_risk_customers=credit_risk_customers,
        recent_activity=recent_activity,
        top_products=top_products,
        top_customers=top_customers
    )
