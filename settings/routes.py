from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app
from flask_login import login_required, current_user
import os
import shutil
from datetime import datetime
from sqlalchemy import func
from models import db, Company, ActivityLog, Customer, ReminderTemplate

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
        db.session.commit()
        flash('Application feature settings updated successfully.', 'success')
        return redirect(url_for('settings.developer_settings'))

    return render_template('settings/developer.html', company=company)


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
