from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app
from flask_login import login_required, current_user
import os
import shutil
from datetime import datetime, date, timedelta
from urllib.parse import quote
from sqlalchemy import func
from models import db, Company, ActivityLog, Customer, ReminderTemplate, Invoice, FollowUpTask, PromiseToPay

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')

BACKUP_FOLDER = 'backups'
DB_FILENAME = 'app.db'


def _require_admin():
    if current_user.role != 'admin':
        flash('Only admin can access backup and restore settings.', 'danger')
        return False
    return True


def _get_backup_path(filename):
    if not filename:
        return None
    safe_name = os.path.basename(filename)
    if safe_name != filename:
        return None
    return os.path.join(BACKUP_FOLDER, safe_name)


def _sanitize_phone(raw_value):
    digits = ''.join(ch for ch in str(raw_value or '') if ch.isdigit())
    if not digits:
        return ''
    if len(digits) == 10:
        return f'91{digits}'
    if len(digits) > 10 and digits.startswith('0'):
        return digits.lstrip('0')
    return digits


def _get_customer_by_invoice(invoice):
    customer = Customer.query.filter(func.lower(Customer.name) == (invoice.customer_name or '').lower()).first()
    if customer:
        return customer
    return None


def _get_template_message(template_key, fallback_message):
    template = ReminderTemplate.query.filter_by(template_key=template_key, is_active=True).first()
    if template and template.message:
        return template.message
    return fallback_message


def _render_template(template_text, customer_name, invoice, pending_amount):
    paid_amount = round(float(invoice.paid_amount or 0), 2)
    return template_text.format(
        customer_name=customer_name,
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.date.strftime('%d-%m-%Y') if invoice.date else '-',
        pending_amount=f'{pending_amount:.2f}',
        paid_amount=f'{paid_amount:.2f}',
    )


def _build_reminder_message(reminder_type, customer_name, invoice, pending_amount):
    fallback_map = {
        'due_today': 'Hello {customer_name}, Invoice {invoice_number} dated {invoice_date} is due today. Pending amount: Rs.{pending_amount}. Thank you.',
        'overdue': 'Hello {customer_name}, Invoice {invoice_number} dated {invoice_date} is overdue. Pending amount: Rs.{pending_amount}. Please clear the dues at the earliest.',
    }
    template_text = _get_template_message(reminder_type, fallback_map.get(reminder_type, fallback_map['due_today']))
    return _render_template(template_text, customer_name, invoice, pending_amount)

@settings_bp.route('/backup', methods=['GET', 'POST'])
@login_required
def backup_restore():
    if not _require_admin():
        return redirect(url_for('dashboard.dashboard'))
    if not os.path.exists(BACKUP_FOLDER):
        os.makedirs(BACKUP_FOLDER)
    backup_files = os.listdir(BACKUP_FOLDER)
    backup_files.sort(reverse=True)
    if request.method == 'POST':
        if 'backup' in request.form:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            src = os.path.join(current_app.root_path, DB_FILENAME)
            dst = os.path.join(BACKUP_FOLDER, f"backup_{timestamp}.db")
            shutil.copy2(src, dst)
            flash('Backup created successfully.', 'success')
            return redirect(url_for('settings.backup_restore'))
        elif 'restore' in request.form:
            if not _require_admin():
                return redirect(url_for('dashboard.dashboard'))
            restore_file = request.form.get('restore_file')
            backup_path = _get_backup_path(restore_file)
            if restore_file and restore_file in backup_files and backup_path and os.path.exists(backup_path):
                src = backup_path
                dst = os.path.join(current_app.root_path, DB_FILENAME)
                shutil.copy2(src, dst)
                flash('Database restored successfully. Please restart the app.', 'success')
                return redirect(url_for('settings.backup_restore'))
            flash('Selected backup file was not found.', 'danger')
            return redirect(url_for('settings.backup_restore'))
        elif 'delete' in request.form:
            if not _require_admin():
                return redirect(url_for('dashboard.dashboard'))
            delete_file = request.form.get('delete_file')
            backup_path = _get_backup_path(delete_file)
            if delete_file and delete_file in backup_files and backup_path and os.path.exists(backup_path):
                os.remove(backup_path)
                flash('Backup deleted successfully.', 'success')
                return redirect(url_for('settings.backup_restore'))
            flash('Selected backup file was not found.', 'danger')
            return redirect(url_for('settings.backup_restore'))
    return render_template('settings/backup_restore.html', backup_files=backup_files)

@settings_bp.route('/download/<filename>')
@login_required
def download_backup(filename):
    if not _require_admin():
        return redirect(url_for('dashboard.dashboard'))
    backup_path = _get_backup_path(filename)
    if backup_path and os.path.exists(backup_path):
        return send_file(backup_path, as_attachment=True)
    flash('File not found.', 'danger')
    return redirect(url_for('settings.backup_restore'))


@settings_bp.route('/developer', methods=['GET', 'POST'])
@login_required
def developer_settings():
    if not _require_admin():
        return redirect(url_for('dashboard.dashboard'))

    company = Company.query.first()
    if company is None:
        flash('Create company information before changing application feature settings.', 'warning')
        return redirect(url_for('company.index'))

    if request.method == 'POST':
        company.finance_enabled = request.form.get('finance_enabled') == 'on'
        company.credit_block_on_exceed = request.form.get('credit_block_on_exceed') == 'on'
        db.session.commit()
        flash('Application feature settings updated successfully.', 'success')
        return redirect(url_for('settings.developer_settings'))

    return render_template('settings/developer.html', company=company)


def _reminder_bucket_definitions():
    return [
        {'key': 'due_today', 'label': 'Due Today', 'days': 0},
        {'key': 'overdue_3', 'label': 'Overdue by 3 Days', 'days': 3},
        {'key': 'overdue_7', 'label': 'Overdue by 7 Days', 'days': 7},
        {'key': 'overdue_15', 'label': 'Overdue by 15 Days', 'days': 15},
    ]


def _auto_reminder_query(bucket_days):
    as_of = date.today()
    query = Invoice.query.filter(func.coalesce(Invoice.balance_amount, 0) > 0)
    if bucket_days > 0:
        target_date = as_of - timedelta(days=bucket_days)
        query = query.filter(func.date(Invoice.date) <= target_date)
    else:
        query = query.filter(func.date(Invoice.date) == as_of)
    return query.order_by(Invoice.date.asc(), Invoice.id.asc()).all()


def _existing_reminder_logged(invoice_id, bucket_key):
    today_str = date.today().strftime('%Y-%m-%d')
    return (
        ActivityLog.query.filter(
            ActivityLog.action == 'Customer Reminder Sent',
            ActivityLog.details.ilike(f'%invoice_id={invoice_id}%'),
            func.date(ActivityLog.timestamp) == today_str,
            ActivityLog.details.ilike(f'%bucket={bucket_key}%'),
        ).first()
        is not None
    )


def _run_reminder_scheduler(bucket_key=None):
    buckets = _reminder_bucket_definitions()
    bucket_map = {bucket['key']: bucket for bucket in buckets}
    selected_buckets = [bucket_map[bucket_key]] if bucket_key in bucket_map else buckets
    scheduled_items = []
    reminders_logged = 0
    tasks_created = 0
    promises_created = 0

    for bucket in selected_buckets:
        invoices = _auto_reminder_query(bucket['days'])
        for invoice in invoices:
            customer = _get_customer_by_invoice(invoice)
            if customer and not customer.reminder_opt_in:
                continue
            if _existing_reminder_logged(invoice.id, bucket['key']):
                continue

            pending_amount = round(float(invoice.balance_amount if invoice.balance_amount is not None else invoice.total or 0), 2)
            customer_name = customer.name if customer else invoice.customer_name
            phone = _sanitize_phone((customer.whatsapp_number if customer and customer.whatsapp_number else '') or (customer.mobile_number if customer and customer.mobile_number else ''))
            message = _build_reminder_message('overdue' if bucket['days'] > 0 else 'due_today', customer_name, invoice, pending_amount)

            db.session.add(
                ActivityLog(
                    user_id=current_user.id,
                    username=current_user.username,
                    action='Customer Reminder Sent',
                    details=(
                        f'customer_id={customer.id if customer else "-"}; customer={customer_name}; '
                        f'invoice_id={invoice.id}; invoice_no={invoice.invoice_number}; '
                        f'balance={pending_amount:.2f}; bucket={bucket["key"]}; channel={"whatsapp" if phone else "manual"}; scheduler=1'
                    ),
                )
            )
            reminders_logged += 1

            if bucket['days'] >= 7 and customer:
                open_task = FollowUpTask.query.filter_by(customer_id=customer.id, invoice_id=invoice.id, status='open').first()
                if not open_task:
                    db.session.add(
                        FollowUpTask(
                            customer_id=customer.id,
                            invoice_id=invoice.id,
                            title=f'Follow up on {invoice.invoice_number}',
                            notes='Auto-created by reminder scheduler for overdue invoice.',
                            due_date=date.today() + timedelta(days=1),
                            status='open',
                            created_by=current_user.id,
                            updated_by=current_user.id,
                        )
                    )
                    tasks_created += 1

            scheduled_items.append({
                'invoice_number': invoice.invoice_number,
                'customer_name': customer_name,
                'pending_amount': pending_amount,
                'phone': phone,
                'message': message,
                'bucket': bucket['label'],
            })

    db.session.commit()
    return {
        'total': len(scheduled_items),
        'reminders_logged': reminders_logged,
        'tasks_created': tasks_created,
        'promises_created': promises_created,
        'items': scheduled_items,
    }


@settings_bp.route('/communication-logs')
@login_required
def communication_logs():
    if not _require_admin():
        return redirect(url_for('dashboard.dashboard'))

    customer_id = request.args.get('customer_id', type=int)
    from_date = request.args.get('from_date', '').strip()
    to_date = request.args.get('to_date', '').strip()
    action = request.args.get('action', '').strip()
    page = request.args.get('page', 1, type=int)

    query = ActivityLog.query.filter(
        ActivityLog.action.in_(['Customer Reminder Sent', 'Invoice WhatsApp Share Opened'])
    )
    if customer_id:
        query = query.filter(ActivityLog.details.ilike(f'%customer_id={customer_id}%'))
    if action:
        query = query.filter(ActivityLog.action.ilike(f'%{action}%'))
    if from_date:
        query = query.filter(func.date(ActivityLog.timestamp) >= from_date)
    if to_date:
        query = query.filter(func.date(ActivityLog.timestamp) <= to_date)

    pagination = query.order_by(ActivityLog.timestamp.desc(), ActivityLog.id.desc()).paginate(
        page=page,
        per_page=50,
        error_out=False,
    )

    customers = Customer.query.order_by(Customer.name.asc()).all()
    return render_template(
        'settings/communication_logs.html',
        logs=pagination.items,
        pagination=pagination,
        customers=customers,
        customer_id=customer_id,
        from_date=from_date,
        to_date=to_date,
        action=action,
    )


@settings_bp.route('/automated-reminders', methods=['GET', 'POST'])
@login_required
def automated_reminders():
    if not _require_admin():
        return redirect(url_for('dashboard.dashboard'))
    buckets = _reminder_bucket_definitions()
    scheduled_summary = None

    if request.method == 'POST':
        if request.form.get('action') == 'schedule':
            scheduled_summary = _run_reminder_scheduler(request.form.get('bucket', '').strip() or None)
            flash(f'Scheduler processed {scheduled_summary["total"]} reminder item(s).', 'success')
            return render_template(
                'settings/automated_reminders.html',
                buckets=buckets,
                selected_bucket=request.form.get('bucket', 'due_today').strip() or 'due_today',
                prepared=[],
                scheduled_summary=scheduled_summary,
            )

        selected_bucket = request.form.get('bucket', 'due_today').strip()
        bucket_map = {bucket['key']: bucket for bucket in buckets}
        bucket = bucket_map.get(selected_bucket, bucket_map['due_today'])
        as_of = date.today()
        if bucket['days'] > 0:
            target_date = as_of - timedelta(days=bucket['days'])
            reminder_type = 'overdue'
        else:
            target_date = as_of
            reminder_type = 'due_today'

        eligible_invoices = (
            Invoice.query
            .filter(func.coalesce(Invoice.balance_amount, 0) > 0)
            .filter(func.date(Invoice.date) <= target_date if bucket['days'] > 0 else func.date(Invoice.date) == target_date)
            .order_by(Invoice.date.asc(), Invoice.id.asc())
            .all()
        )

        prepared = []
        logged = 0
        for invoice in eligible_invoices:
            pending_amount = round(float(invoice.balance_amount if invoice.balance_amount is not None else invoice.total or 0), 2)
            customer = _get_customer_by_invoice(invoice)
            if customer and not customer.reminder_opt_in:
                continue

            customer_name = customer.name if customer else invoice.customer_name
            phone = _sanitize_phone((customer.whatsapp_number if customer and customer.whatsapp_number else '') or (customer.mobile_number if customer and customer.mobile_number else ''))
            message = _build_reminder_message(reminder_type, customer_name, invoice, pending_amount)

            db.session.add(
                ActivityLog(
                    user_id=current_user.id,
                    username=current_user.username,
                    action='Customer Reminder Sent',
                    details=(
                        f'customer_id={customer.id if customer else "-"}; customer={customer_name}; '
                        f'invoice_id={invoice.id}; invoice_no={invoice.invoice_number}; '
                        f'balance={pending_amount:.2f}; bucket={bucket["key"]}; channel={"whatsapp" if phone else "manual"}'
                    ),
                )
            )
            prepared.append({
                'invoice_number': invoice.invoice_number,
                'customer_name': customer_name,
                'pending_amount': pending_amount,
                'phone': phone,
                'message': message,
                'whatsapp_url': f'https://wa.me/{phone}?text={quote(message)}' if phone else '',
            })
            logged += 1

        db.session.commit()
        flash(f'Prepared {logged} reminder(s) for {bucket["label"]}.', 'success')
        return render_template(
            'settings/automated_reminders.html',
            buckets=buckets,
            selected_bucket=bucket['key'],
            prepared=prepared,
            scheduled_summary=None,
        )

    return render_template(
        'settings/automated_reminders.html',
        buckets=buckets,
        selected_bucket='due_today',
        prepared=[],
        scheduled_summary=None,
    )


@settings_bp.route('/reminder-templates', methods=['GET', 'POST'])
@login_required
def reminder_templates():
    if not _require_admin():
        return redirect(url_for('dashboard.dashboard'))

    if request.method == 'POST':
        templates = ReminderTemplate.query.order_by(ReminderTemplate.template_key.asc()).all()
        for template in templates:
            title = (request.form.get(f'title_{template.template_key}') or '').strip()
            message = (request.form.get(f'message_{template.template_key}') or '').strip()
            is_active = request.form.get(f'is_active_{template.template_key}') == 'on'
            if not title or not message:
                flash(f'Title and message are required for {template.template_key}.', 'danger')
                return redirect(url_for('settings.reminder_templates'))
            template.title = title
            template.message = message
            template.is_active = is_active

        db.session.add(
            ActivityLog(
                user_id=current_user.id,
                username=current_user.username,
                action='Reminder Templates Updated',
                details='Reminder templates updated from application settings.',
            )
        )
        db.session.commit()
        flash('Reminder templates updated successfully.', 'success')
        return redirect(url_for('settings.reminder_templates'))

    templates = ReminderTemplate.query.order_by(ReminderTemplate.template_key.asc()).all()
    return render_template('settings/reminder_templates.html', templates=templates)
