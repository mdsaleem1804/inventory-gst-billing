from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func
from urllib.parse import quote
import re
from datetime import datetime, date
from models import db, Customer, Invoice, Payment, ActivityLog, ReminderTemplate

customers_bp = Blueprint('customers', __name__, url_prefix='/customers')


def _sanitize_phone_for_whatsapp(raw_value):
    digits = ''.join(ch for ch in str(raw_value or '') if ch.isdigit())
    if not digits:
        return ''
    if len(digits) == 10:
        return f'91{digits}'
    if len(digits) > 10 and digits.startswith('0'):
        return digits.lstrip('0')
    return digits


def _parse_payment_metadata(notes):
    raw_notes = (notes or '').strip()
    cash_received = None
    change_returned = 0.0

    cash_match = re.search(r'(?:cash_received|bill_time_received)=([0-9]+(?:\.[0-9]+)?)', raw_notes)
    change_match = re.search(r'change_returned=([0-9]+(?:\.[0-9]+)?)', raw_notes)
    if cash_match:
        cash_received = round(float(cash_match.group(1)), 2)
    if change_match:
        change_returned = round(float(change_match.group(1)), 2)

    segments = [segment.strip() for segment in raw_notes.split('|') if segment.strip()]
    filtered_segments = [
        segment for segment in segments
        if 'cash_received=' not in segment and 'bill_time_received=' not in segment and 'change_returned=' not in segment
    ]
    clean_notes = ' | '.join(filtered_segments)

    return {
        'clean_notes': clean_notes,
        'cash_received': cash_received,
        'change_returned': change_returned,
    }


def _get_template_message(template_key, fallback_message):
    template = ReminderTemplate.query.filter_by(template_key=template_key, is_active=True).first()
    if template and template.message:
        return template.message
    return fallback_message


def _format_template_message(template_text, customer, invoice):
    pending_amount = round(float(invoice.balance_amount if invoice.balance_amount is not None else invoice.total or 0), 2)
    paid_amount = round(float(invoice.paid_amount or 0), 2)
    return template_text.format(
        customer_name=customer.name,
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.date.strftime('%d-%m-%Y') if invoice.date else '-',
        pending_amount=f'{pending_amount:.2f}',
        paid_amount=f'{paid_amount:.2f}',
    )


def _build_reminder_text(customer, invoice):
    is_overdue = (invoice.date.date() if invoice.date else date.today()) < date.today()
    template_key = 'overdue' if is_overdue else 'due_today'
    fallback_message = (
        'Hello {customer_name}, Invoice {invoice_number} dated {invoice_date} '
        'has pending amount Rs.{pending_amount}. Please clear the dues at the earliest. Thank you.'
    )
    template_text = _get_template_message(template_key, fallback_message)
    return _format_template_message(template_text, customer, invoice)


def _add_communication_log(action, details):
    db.session.add(
        ActivityLog(
            user_id=current_user.id,
            username=current_user.username,
            action=action,
            details=details,
            timestamp=datetime.utcnow(),
        )
    )
    db.session.commit()

@customers_bp.route('/', methods=['GET', 'POST'])
@login_required
def crud_customers():
    edit_id = request.args.get('edit_id', type=int)
    form_customer = None
    if request.method == 'POST':
        # Delete
        delete_id = request.form.get('delete_id', type=int)
        if delete_id:
            customer = Customer.query.get(delete_id)
            if customer:
                db.session.delete(customer)
                db.session.commit()
                flash('Customer deleted!', 'success')
            return redirect(url_for('customers.crud_customers'))
        # Add or Update
        cid = request.form.get('id', type=int)
        name = request.form['name'].strip()
        gstin = request.form['gstin'].strip()
        address = request.form['address'].strip()
        contact_person = request.form.get('contact_person', '').strip()
        mobile_number = request.form.get('mobile_number', '').strip()
        whatsapp_number = request.form.get('whatsapp_number', '').strip() or mobile_number
        reminder_opt_in = request.form.get('reminder_opt_in') == 'on'
        if cid:
            customer = Customer.query.get(cid)
            if customer:
                customer.name = name
                customer.gstin = gstin
                customer.address = address
                customer.contact_person = contact_person or None
                customer.mobile_number = mobile_number or None
                customer.whatsapp_number = whatsapp_number or None
                customer.reminder_opt_in = reminder_opt_in
                db.session.commit()
                flash('Customer updated!', 'success')
        else:
            customer = Customer(
                name=name,
                gstin=gstin,
                address=address,
                contact_person=contact_person or None,
                mobile_number=mobile_number or None,
                whatsapp_number=whatsapp_number or None,
                reminder_opt_in=reminder_opt_in,
            )
            db.session.add(customer)
            db.session.commit()
            flash('Customer added!', 'success')
        return redirect(url_for('customers.crud_customers'))
    # GET
    search = request.args.get('search', '')
    if edit_id:
        form_customer = Customer.query.get(edit_id)
    query = Customer.query
    if search:
        query = query.filter(
            Customer.name.ilike(f'%{search}%') |
            Customer.gstin.ilike(f'%{search}%') |
            Customer.mobile_number.ilike(f'%{search}%') |
            Customer.whatsapp_number.ilike(f'%{search}%')
        )
    customers = query.order_by(Customer.name).all()
    return render_template('customers/crud.html', customers=customers, form_customer=form_customer, search=search)


@customers_bp.route('/<int:customer_id>/ledger')
@login_required
def customer_ledger(customer_id):
    customer = Customer.query.get_or_404(customer_id)

    invoices = (
        Invoice.query
        .filter(func.lower(Invoice.customer_name) == customer.name.lower())
        .order_by(Invoice.date.desc(), Invoice.id.desc())
        .all()
    )

    invoice_ids = [inv.id for inv in invoices]
    payments = []
    if invoice_ids:
        payments = (
            Payment.query
            .filter(Payment.invoice_id.in_(invoice_ids))
            .order_by(Payment.payment_date.desc(), Payment.id.desc())
            .all()
        )

    entries = []
    for invoice in invoices:
        entries.append({
            'kind': 'invoice',
            'date': invoice.date,
            'invoice': invoice,
            'amount': round(float(invoice.total or 0), 2),
            'reference': invoice.invoice_number,
            'note': f'Invoice raised ({invoice.payment_status or "unpaid"})',
        })

    for payment in payments:
        payment_meta = _parse_payment_metadata(payment.notes)
        entries.append({
            'kind': 'payment',
            'date': payment.payment_date,
            'invoice': next((inv for inv in invoices if inv.id == payment.invoice_id), None),
            'amount': round(float(payment.amount or 0), 2),
            'reference': payment.reference_no or '-',
            'mode': payment.payment_mode or '-',
            'note': payment_meta['clean_notes'] or '-',
        })

    entries.sort(key=lambda row: (row['date'] or datetime.min, row['kind'] != 'invoice'), reverse=True)

    total_sales = round(sum(float(inv.total or 0) for inv in invoices), 2)
    total_paid = round(sum(float(inv.paid_amount or 0) for inv in invoices), 2)
    total_balance = round(sum(float(inv.balance_amount if inv.balance_amount is not None else inv.total or 0) for inv in invoices), 2)

    communication_logs = (
        ActivityLog.query
        .filter(
            ActivityLog.action.in_(['Customer Reminder Sent', 'Invoice WhatsApp Share Opened']),
            ActivityLog.details.ilike(f'%customer_id={customer.id}%')
        )
        .order_by(ActivityLog.timestamp.desc(), ActivityLog.id.desc())
        .limit(30)
        .all()
    )

    return render_template(
        'customers/ledger.html',
        customer=customer,
        invoices=invoices,
        entries=entries,
        total_sales=total_sales,
        total_paid=total_paid,
        total_balance=total_balance,
        communication_logs=communication_logs,
    )


@customers_bp.route('/<int:customer_id>/send-reminder', methods=['POST'])
@login_required
def send_customer_reminder(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    if not customer.reminder_opt_in:
        flash('This customer has reminders disabled.', 'info')
        return redirect(url_for('customers.customer_ledger', customer_id=customer.id))

    invoice_id = request.form.get('invoice_id', type=int)

    invoice_query = Invoice.query.filter(func.lower(Invoice.customer_name) == customer.name.lower())
    if invoice_id:
        invoice_query = invoice_query.filter(Invoice.id == invoice_id)
    invoice = (
        invoice_query
        .order_by(Invoice.date.desc(), Invoice.id.desc())
        .first()
    )

    if not invoice:
        flash('No invoice found to send reminder.', 'warning')
        return redirect(url_for('customers.customer_ledger', customer_id=customer.id))

    if round(float(invoice.balance_amount if invoice.balance_amount is not None else invoice.total or 0), 2) <= 0:
        flash('Selected invoice has no pending balance.', 'info')
        return redirect(url_for('customers.customer_ledger', customer_id=customer.id))

    reminder_text = _build_reminder_text(customer, invoice)
    phone = _sanitize_phone_for_whatsapp(customer.whatsapp_number or customer.mobile_number)

    log_details = (
        f'customer_id={customer.id}; customer={customer.name}; invoice_id={invoice.id}; '
        f'invoice_no={invoice.invoice_number}; balance={round(float(invoice.balance_amount or 0), 2):.2f}; '
        f'channel={"whatsapp" if phone else "manual"}'
    )
    _add_communication_log('Customer Reminder Sent', log_details)

    if not phone:
        flash('Reminder logged. Add mobile/WhatsApp number to share via WhatsApp.', 'warning')
        return redirect(url_for('customers.customer_ledger', customer_id=customer.id))

    whatsapp_url = f'https://wa.me/{phone}?text={quote(reminder_text)}'
    flash('Reminder logged and WhatsApp message prepared.', 'success')
    return redirect(whatsapp_url)
