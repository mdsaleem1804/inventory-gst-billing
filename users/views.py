
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, User, ActivityLog
from werkzeug.security import generate_password_hash
from .routes import users_bp

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
        role = request.form['role']
        if uid:
            user = User.query.get(uid)
            if user:
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
