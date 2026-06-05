from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from sqlalchemy import func
from urllib.parse import quote
import io
import csv
import re
from datetime import datetime, date
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import pandas as pd
from models import db, Customer, Invoice, Payment, ActivityLog, ReminderTemplate, Company, FollowUpTask, PromiseToPay, User

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


def _build_customer_statement(customer):
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
    credit_limit = round(float(customer.credit_limit or 0), 2)
    credit_utilized = total_balance
    credit_remaining = round(max(credit_limit - credit_utilized, 0.0), 2) if credit_limit > 0 else 0.0
    credit_over_limit = round(max(credit_utilized - credit_limit, 0.0), 2) if credit_limit > 0 else 0.0

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

    follow_up_tasks = (
        FollowUpTask.query
        .filter_by(customer_id=customer.id)
        .order_by(FollowUpTask.status.asc(), FollowUpTask.due_date.asc().nullslast(), FollowUpTask.id.desc())
        .all()
    )

    promise_to_pay = (
        PromiseToPay.query
        .filter_by(customer_id=customer.id)
        .order_by(PromiseToPay.status.asc(), PromiseToPay.promised_date.asc().nullslast(), PromiseToPay.id.desc())
        .all()
    )

    return {
        'customer': customer,
        'invoices': invoices,
        'payments': payments,
        'entries': entries,
        'total_sales': total_sales,
        'total_paid': total_paid,
        'total_balance': total_balance,
        'credit_limit': credit_limit,
        'credit_utilized': credit_utilized,
        'credit_remaining': credit_remaining,
        'credit_over_limit': credit_over_limit,
        'communication_logs': communication_logs,
        'follow_up_tasks': follow_up_tasks,
        'promise_to_pay': promise_to_pay,
    }

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
        credit_limit_raw = (request.form.get('credit_limit') or '').strip()
        try:
            credit_limit = round(float(credit_limit_raw), 2) if credit_limit_raw else 0.0
        except ValueError:
            credit_limit = 0.0
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
                customer.credit_limit = credit_limit
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
                credit_limit=credit_limit,
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
    customer_balances = {}
    for customer in customers:
        statement = _build_customer_statement(customer)
        customer_balances[customer.id] = {
            'balance': statement['total_balance'],
            'credit_limit': statement['credit_limit'],
            'credit_over_limit': statement['credit_over_limit'],
        }
    return render_template('customers/crud.html', customers=customers, form_customer=form_customer, search=search, customer_balances=customer_balances)


@customers_bp.route('/<int:customer_id>/tasks', methods=['POST'])
@login_required
def add_follow_up_task(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    title = (request.form.get('title') or '').strip()
    notes = (request.form.get('notes') or '').strip()
    due_date_str = (request.form.get('due_date') or '').strip()
    invoice_id = request.form.get('invoice_id', type=int)
    assigned_to_user_id = request.form.get('assigned_to_user_id', type=int)

    if not title:
        flash('Task title is required.', 'danger')
        return redirect(url_for('customers.customer_ledger', customer_id=customer.id))

    due_date = None
    if due_date_str:
        try:
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Task due date is invalid.', 'danger')
            return redirect(url_for('customers.customer_ledger', customer_id=customer.id))

    task = FollowUpTask(
        customer_id=customer.id,
        invoice_id=invoice_id,
        title=title,
        notes=notes or None,
        due_date=due_date,
        status='open',
        assigned_to_user_id=assigned_to_user_id or None,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.session.add(task)
    db.session.add(
        ActivityLog(
            user_id=current_user.id,
            username=current_user.username,
            action='Follow-Up Task Created',
            details=f'customer_id={customer.id}; customer={customer.name}; title={title}; due_date={due_date_str or "-"}',
        )
    )
    db.session.commit()
    flash('Follow-up task created.', 'success')
    return redirect(url_for('customers.customer_ledger', customer_id=customer.id))


@customers_bp.route('/<int:customer_id>/tasks/<int:task_id>/complete', methods=['POST'])
@login_required
def complete_follow_up_task(customer_id, task_id):
    customer = Customer.query.get_or_404(customer_id)
    task = FollowUpTask.query.filter_by(id=task_id, customer_id=customer.id).first_or_404()
    task.status = 'done'
    task.completed_at = datetime.utcnow()
    task.updated_by = current_user.id
    db.session.add(
        ActivityLog(
            user_id=current_user.id,
            username=current_user.username,
            action='Follow-Up Task Completed',
            details=f'customer_id={customer.id}; customer={customer.name}; task_id={task.id}; title={task.title}',
        )
    )
    db.session.commit()
    flash('Follow-up task completed.', 'success')
    return redirect(url_for('customers.customer_ledger', customer_id=customer.id))


@customers_bp.route('/<int:customer_id>/tasks/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_follow_up_task(customer_id, task_id):
    customer = Customer.query.get_or_404(customer_id)
    task = FollowUpTask.query.filter_by(id=task_id, customer_id=customer.id).first_or_404()
    task_title = task.title
    db.session.delete(task)
    db.session.add(
        ActivityLog(
            user_id=current_user.id,
            username=current_user.username,
            action='Follow-Up Task Deleted',
            details=f'customer_id={customer.id}; customer={customer.name}; task_id={task_id}; title={task_title}',
        )
    )
    db.session.commit()
    flash('Follow-up task deleted.', 'success')
    return redirect(url_for('customers.customer_ledger', customer_id=customer.id))


@customers_bp.route('/tasks', methods=['GET', 'POST'])
@login_required
def follow_up_tasks_page():
    if request.method == 'POST':
        customer_id = request.form.get('customer_id', type=int)
        customer = Customer.query.get(customer_id) if customer_id else None
        if not customer:
            flash('Customer is required.', 'danger')
            return redirect(url_for('customers.follow_up_tasks_page'))

        title = (request.form.get('title') or '').strip()
        notes = (request.form.get('notes') or '').strip()
        due_date_str = (request.form.get('due_date') or '').strip()
        invoice_id = request.form.get('invoice_id', type=int)
        assigned_to_user_id = request.form.get('assigned_to_user_id', type=int)

        if not title:
            flash('Task title is required.', 'danger')
            return redirect(url_for('customers.follow_up_tasks_page', customer_id=customer.id))

        due_date = None
        if due_date_str:
            try:
                due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash('Task due date is invalid.', 'danger')
                return redirect(url_for('customers.follow_up_tasks_page', customer_id=customer.id))

        task = FollowUpTask(
            customer_id=customer.id,
            invoice_id=invoice_id or None,
            title=title,
            notes=notes or None,
            due_date=due_date,
            status='open',
            assigned_to_user_id=assigned_to_user_id or None,
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        db.session.add(task)
        db.session.add(
            ActivityLog(
                user_id=current_user.id,
                username=current_user.username,
                action='Follow-Up Task Created',
                details=(
                    f'customer_id={customer.id}; customer={customer.name}; title={title}; '
                    f'assigned_to_user_id={assigned_to_user_id or "-"}; due_date={due_date_str or "-"}'
                ),
            )
        )
        db.session.commit()
        flash('Follow-up task created.', 'success')
        return redirect(url_for('customers.follow_up_tasks_page', customer_id=customer.id))

    customer_id = request.args.get('customer_id', type=int)
    status = request.args.get('status', '').strip().lower()
    assignee_id = request.args.get('assignee_id', type=int)
    from_date = request.args.get('from_date', '').strip()
    to_date = request.args.get('to_date', '').strip()
    search = request.args.get('search', '').strip()

    from_date_value = None
    to_date_value = None
    if from_date:
        try:
            from_date_value = datetime.strptime(from_date, '%Y-%m-%d').date()
        except ValueError:
            flash('From date is invalid.', 'danger')
            return redirect(url_for('customers.follow_up_tasks_page'))
    if to_date:
        try:
            to_date_value = datetime.strptime(to_date, '%Y-%m-%d').date()
        except ValueError:
            flash('To date is invalid.', 'danger')
            return redirect(url_for('customers.follow_up_tasks_page'))

    query = FollowUpTask.query.join(Customer, FollowUpTask.customer_id == Customer.id)
    if customer_id:
        query = query.filter(FollowUpTask.customer_id == customer_id)
    if status in {'open', 'done'}:
        query = query.filter(FollowUpTask.status == status)
    if assignee_id:
        query = query.filter(FollowUpTask.assigned_to_user_id == assignee_id)
    if from_date_value:
        query = query.filter(func.coalesce(FollowUpTask.due_date, func.date(FollowUpTask.created_at)) >= from_date_value.strftime('%Y-%m-%d'))
    if to_date_value:
        query = query.filter(func.coalesce(FollowUpTask.due_date, func.date(FollowUpTask.created_at)) <= to_date_value.strftime('%Y-%m-%d'))
    if search:
        query = query.filter(
            FollowUpTask.title.ilike(f'%{search}%') |
            FollowUpTask.notes.ilike(f'%{search}%') |
            Customer.name.ilike(f'%{search}%')
        )

    tasks = query.order_by(FollowUpTask.status.asc(), FollowUpTask.due_date.asc().nullslast(), FollowUpTask.id.desc()).all()
    customers = Customer.query.order_by(Customer.name.asc()).all()
    users = User.query.order_by(User.username.asc()).all()

    return render_template(
        'customers/follow_up_tasks.html',
        tasks=tasks,
        customers=customers,
        users=users,
        customer_id=customer_id,
        status=status,
        assignee_id=assignee_id,
        from_date=from_date,
        to_date=to_date,
        search=search,
        today=date.today(),
    )


@customers_bp.route('/tasks/<int:task_id>/update', methods=['POST'])
@login_required
def update_follow_up_task(task_id):
    task = FollowUpTask.query.get_or_404(task_id)
    assignee_id = request.form.get('assigned_to_user_id', type=int)
    status = (request.form.get('status') or '').strip().lower()
    notes = (request.form.get('notes') or '').strip()
    due_date_str = (request.form.get('due_date') or '').strip()

    if assignee_id is not None:
        task.assigned_to_user_id = assignee_id or None
    if status in {'open', 'done'}:
        task.status = status
        task.completed_at = datetime.utcnow() if status == 'done' else None
    if notes:
        task.notes = notes
    if due_date_str:
        try:
            task.due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Task due date is invalid.', 'danger')
            return redirect(url_for('customers.follow_up_tasks_page'))
    task.updated_by = current_user.id

    db.session.add(
        ActivityLog(
            user_id=current_user.id,
            username=current_user.username,
            action='Follow-Up Task Updated',
            details=(
                f'customer_id={task.customer_id}; task_id={task.id}; title={task.title}; '
                f'assigned_to_user_id={task.assigned_to_user_id or "-"}; status={task.status}'
            ),
        )
    )
    db.session.commit()
    flash('Follow-up task updated.', 'success')
    return redirect(url_for('customers.follow_up_tasks_page', customer_id=task.customer_id))


@customers_bp.route('/<int:customer_id>/promises', methods=['POST'])
@login_required
def add_promise_to_pay(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    invoice_id = request.form.get('invoice_id', type=int)
    promised_amount_raw = (request.form.get('promised_amount') or '').strip()
    promised_date_str = (request.form.get('promised_date') or '').strip()
    note = (request.form.get('note') or '').strip()

    try:
        promised_amount = round(float(promised_amount_raw), 2)
    except ValueError:
        promised_amount = 0.0

    if promised_amount <= 0:
        flash('Promised amount is required.', 'danger')
        return redirect(url_for('customers.customer_ledger', customer_id=customer.id))

    promised_date = None
    if promised_date_str:
        try:
            promised_date = datetime.strptime(promised_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Promised date is invalid.', 'danger')
            return redirect(url_for('customers.customer_ledger', customer_id=customer.id))

    promise = PromiseToPay(
        customer_id=customer.id,
        invoice_id=invoice_id,
        promised_amount=promised_amount,
        promised_date=promised_date,
        note=note or None,
        status='open',
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.session.add(promise)
    db.session.add(
        ActivityLog(
            user_id=current_user.id,
            username=current_user.username,
            action='Promise To Pay Created',
            details=(
                f'customer_id={customer.id}; customer={customer.name}; invoice_id={invoice_id or "-"}; '
                f'amount={promised_amount:.2f}; promised_date={promised_date_str or "-"}'
            ),
        )
    )
    db.session.commit()
    flash('Promise-to-pay recorded.', 'success')
    return redirect(url_for('customers.customer_ledger', customer_id=customer.id))


@customers_bp.route('/<int:customer_id>/promises/<int:promise_id>/close', methods=['POST'])
@login_required
def close_promise_to_pay(customer_id, promise_id):
    customer = Customer.query.get_or_404(customer_id)
    promise = PromiseToPay.query.filter_by(id=promise_id, customer_id=customer.id).first_or_404()
    promise.status = 'closed'
    promise.updated_by = current_user.id
    db.session.add(
        ActivityLog(
            user_id=current_user.id,
            username=current_user.username,
            action='Promise To Pay Closed',
            details=f'customer_id={customer.id}; customer={customer.name}; promise_id={promise.id}; amount={promise.promised_amount:.2f}',
        )
    )
    db.session.commit()
    flash('Promise-to-pay closed.', 'success')
    return redirect(url_for('customers.customer_ledger', customer_id=customer.id))


@customers_bp.route('/<int:customer_id>/ledger')
@login_required
def customer_ledger(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    statement = _build_customer_statement(customer)
    users = User.query.order_by(User.username.asc()).all()

    return render_template(
        'customers/ledger.html',
        **statement,
        users=users,
    )


@customers_bp.route('/<int:customer_id>/statement/export')
@login_required
def export_customer_statement(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    export_format = (request.args.get('format') or 'csv').strip().lower()
    statement = _build_customer_statement(customer)

    rows = []
    running_balance = 0.0
    for entry in reversed(statement['entries']):
        if entry['kind'] == 'invoice':
            running_balance += float(entry['amount'] or 0)
        else:
            running_balance -= float(entry['amount'] or 0)
        rows.append({
            'Date': entry['date'].strftime('%Y-%m-%d') if entry['date'] else '',
            'Type': entry['kind'].title(),
            'Invoice #': entry['invoice'].invoice_number if entry.get('invoice') else '-',
            'Reference': entry.get('reference') or '-',
            'Amount': f"{entry['amount']:.2f}",
            'Running Balance': f"{running_balance:.2f}",
            'Details': entry.get('note') or '-',
        })

    summary_rows = [
        ['Customer', customer.name],
        ['GSTIN', customer.gstin or ''],
        ['Credit Limit', f"{statement['credit_limit']:.2f}"],
        ['Outstanding', f"{statement['total_balance']:.2f}"],
        ['Credit Remaining', f"{statement['credit_remaining']:.2f}"],
        ['Credit Over Limit', f"{statement['credit_over_limit']:.2f}"],
    ]

    if export_format == 'excel':
        buffer = io.BytesIO()
        statement_df = pd.DataFrame(rows)
        summary_df = pd.DataFrame(summary_rows, columns=['Field', 'Value'])
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            summary_df.to_excel(writer, index=False, sheet_name='Summary')
            statement_df.to_excel(writer, index=False, sheet_name='Statement')
        buffer.seek(0)
        _add_communication_log('Customer Statement Exported', f'customer_id={customer.id}; customer={customer.name}; format=excel; rows={len(rows)}')
        return send_file(buffer, as_attachment=True, download_name=f'customer_statement_{customer.id}.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    if export_format == 'pdf':
        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        y = height - 40
        pdf.setFont('Helvetica-Bold', 14)
        pdf.drawString(180, y, 'Customer Statement')
        y -= 20
        pdf.setFont('Helvetica', 10)
        pdf.drawString(40, y, f'Customer: {customer.name}')
        pdf.drawString(320, y, f'Credit Limit: {statement["credit_limit"]:.2f}')
        y -= 15
        pdf.drawString(40, y, f'Outstanding: {statement["total_balance"]:.2f}')
        pdf.drawString(320, y, f'Credit Remaining: {statement["credit_remaining"]:.2f}')
        y -= 25
        pdf.setFont('Helvetica-Bold', 9)
        pdf.drawString(30, y, 'Date')
        pdf.drawString(75, y, 'Type')
        pdf.drawString(125, y, 'Invoice #')
        pdf.drawString(200, y, 'Reference')
        pdf.drawString(280, y, 'Amount')
        pdf.drawString(340, y, 'Running Bal.')
        pdf.drawString(420, y, 'Details')
        y -= 12
        pdf.setFont('Helvetica', 8)
        running_balance = 0.0
        for entry in reversed(statement['entries']):
            if entry['kind'] == 'invoice':
                running_balance += float(entry['amount'] or 0)
            else:
                running_balance -= float(entry['amount'] or 0)
            pdf.drawString(30, y, entry['date'].strftime('%Y-%m-%d') if entry['date'] else '')
            pdf.drawString(75, y, entry['kind'].title())
            pdf.drawString(125, y, entry['invoice'].invoice_number if entry.get('invoice') else '-')
            pdf.drawString(200, y, str(entry.get('reference') or '-'))
            pdf.drawString(280, y, f"{entry['amount']:.2f}")
            pdf.drawString(340, y, f"{running_balance:.2f}")
            pdf.drawString(420, y, (entry.get('note') or '-')[:38])
            y -= 12
            if y < 50:
                pdf.showPage()
                y = height - 40
                pdf.setFont('Helvetica', 8)
        pdf.save()
        buffer.seek(0)
        _add_communication_log('Customer Statement Exported', f'customer_id={customer.id}; customer={customer.name}; format=pdf; rows={len(rows)}')
        return send_file(buffer, as_attachment=True, download_name=f'customer_statement_{customer.id}.pdf', mimetype='application/pdf')

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['Field', 'Value'])
    for field, value in summary_rows:
        writer.writerow([field, value])
    writer.writerow([])
    writer.writerow(['Date', 'Type', 'Invoice #', 'Reference', 'Amount', 'Running Balance', 'Details'])
    for row in rows:
        writer.writerow([row['Date'], row['Type'], row['Invoice #'], row['Reference'], row['Amount'], row['Running Balance'], row['Details']])
    bytes_buffer = io.BytesIO(buffer.getvalue().encode('utf-8'))
    bytes_buffer.seek(0)
    _add_communication_log('Customer Statement Exported', f'customer_id={customer.id}; customer={customer.name}; format=csv; rows={len(rows)}')
    return send_file(bytes_buffer, as_attachment=True, download_name=f'customer_statement_{customer.id}.csv', mimetype='text/csv')


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
