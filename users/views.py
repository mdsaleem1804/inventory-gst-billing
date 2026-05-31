
from flask import render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from models import db, User, ActivityLog
from werkzeug.security import generate_password_hash
from sqlalchemy import func
from .routes import users_bp
import io
import csv
import pandas as pd

ALLOWED_ROLES = {'admin', 'approver', 'staff'}


def _build_activity_log_query(action, username, from_date, to_date):
    query = ActivityLog.query
    if action:
        query = query.filter(ActivityLog.action.ilike(f'%{action}%'))
    if username:
        query = query.filter(ActivityLog.username.ilike(f'%{username}%'))
    if from_date:
        query = query.filter(func.date(ActivityLog.timestamp) >= from_date)
    if to_date:
        query = query.filter(func.date(ActivityLog.timestamp) <= to_date)
    return query

@users_bp.route('/', methods=['GET', 'POST'])
@login_required
def crud_users():
    if current_user.role != 'admin':
        flash('Only admin can manage users.', 'danger')
        return redirect(url_for('dashboard.dashboard'))
    edit_id = request.args.get('edit_id', type=int)
    form_user = None
    if request.method == 'POST':
        # Delete
        delete_id = request.form.get('delete_id', type=int)
        if delete_id:
            user = User.query.get(delete_id)
            if user and user.username != 'admin':
                db.session.delete(user)
                db.session.commit()
                db.session.add(ActivityLog(user_id=current_user.id, username=current_user.username, action='Delete User', details=f'User: {user.username}'))
                db.session.commit()
                flash('User deleted!', 'success')
            else:
                flash('Cannot delete this user.', 'danger')
            return redirect(url_for('users.crud_users'))
        # Add or Update
        uid = request.form.get('id', type=int)
        username = request.form['username']
        password = request.form['password']
        role = request.form.get('role', 'staff')
        if role not in ALLOWED_ROLES:
            role = 'staff'
        if uid:
            user = User.query.get(uid)
            if user:
                if user.username == 'admin':
                    role = 'admin'
                user.username = username
                if password:
                    user.password_hash = generate_password_hash(password)
                user.role = role
                db.session.commit()
                db.session.add(ActivityLog(user_id=current_user.id, username=current_user.username, action='Edit User', details=f'User: {user.username}'))
                db.session.commit()
                flash('User updated!', 'success')
        else:
            if User.query.filter_by(username=username).first():
                flash('Username already exists.', 'danger')
            else:
                user = User(username=username, password_hash=generate_password_hash(password), role=role)
                db.session.add(user)
                db.session.commit()
                db.session.add(ActivityLog(user_id=current_user.id, username=current_user.username, action='Add User', details=f'User: {user.username}'))
                db.session.commit()
                flash('User added!', 'success')
        return redirect(url_for('users.crud_users'))
    # GET
    if edit_id:
        form_user = User.query.get(edit_id)
    users = User.query.order_by(User.id).all()
    return render_template('users/crud.html', users=users, form_user=form_user)


@users_bp.route('/activity-logs')
@login_required
def activity_logs():
    if current_user.role != 'admin':
        flash('Only admin can view activity logs.', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    action = request.args.get('action', '').strip()
    username = request.args.get('username', '').strip()
    from_date = request.args.get('from_date', '').strip()
    to_date = request.args.get('to_date', '').strip()

    page = request.args.get('page', 1, type=int)
    per_page = 50
    query = _build_activity_log_query(action, username, from_date, to_date)
    pagination = query.order_by(ActivityLog.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False)
    logs = pagination.items
    return render_template(
        'users/activity_logs.html',
        logs=logs,
        pagination=pagination,
        action=action,
        username=username,
        from_date=from_date,
        to_date=to_date,
    )


@users_bp.route('/activity-logs/export')
@login_required
def export_activity_logs():
    if current_user.role != 'admin':
        flash('Only admin can export activity logs.', 'danger')
        return redirect(url_for('dashboard.dashboard'))

    action = request.args.get('action', '').strip()
    username = request.args.get('username', '').strip()
    from_date = request.args.get('from_date', '').strip()
    to_date = request.args.get('to_date', '').strip()
    export_format = request.args.get('format', 'csv').strip().lower()

    query = _build_activity_log_query(action, username, from_date, to_date)
    logs = query.order_by(ActivityLog.timestamp.desc()).all()
    rows = [
        {
            'ID': log.id,
            'Timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S') if log.timestamp else '',
            'User': log.username or '',
            'Action': log.action,
            'Details': log.details or '',
        }
        for log in logs
    ]

    if export_format == 'excel':
        buffer = io.BytesIO()
        df = pd.DataFrame(rows)
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Activity Logs')
        buffer.seek(0)
        return send_file(
            buffer,
            as_attachment=True,
            download_name='activity_logs.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['ID', 'Timestamp', 'User', 'Action', 'Details'])
    for row in rows:
        writer.writerow([row['ID'], row['Timestamp'], row['User'], row['Action'], row['Details']])

    bytes_buffer = io.BytesIO(buffer.getvalue().encode('utf-8'))
    bytes_buffer.seek(0)
    return send_file(bytes_buffer, as_attachment=True, download_name='activity_logs.csv', mimetype='text/csv')
