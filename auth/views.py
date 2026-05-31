from flask import render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from .routes import auth_bp
from models import User

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
	if request.method == 'POST':
		username = request.form['username']
		password = request.form['password']
		user = User.query.filter_by(username=username).first()
		if user and check_password_hash(user.password_hash, password):
			login_user(user)
			# Force password change for insecure default admin credentials.
			if user.username == 'admin' and password == 'admin':
				session['force_password_change'] = True
				flash('Please change the default admin password before continuing.', 'warning')
				return redirect(url_for('auth.change_password'))
			session.pop('force_password_change', None)
			return redirect(url_for('dashboard.dashboard'))
		else:
			flash('Invalid username or password', 'danger')
	return render_template('auth/login.html')


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
	if request.method == 'POST':
		current_password = request.form.get('current_password', '')
		new_password = request.form.get('new_password', '')
		confirm_password = request.form.get('confirm_password', '')

		if not check_password_hash(current_user.password_hash, current_password):
			flash('Current password is incorrect.', 'danger')
			return render_template('auth/change_password.html')
		if len(new_password) < 8:
			flash('New password must be at least 8 characters long.', 'danger')
			return render_template('auth/change_password.html')
		if new_password != confirm_password:
			flash('New password and confirmation do not match.', 'danger')
			return render_template('auth/change_password.html')
		if current_password == new_password:
			flash('New password must be different from current password.', 'danger')
			return render_template('auth/change_password.html')

		current_user.password_hash = generate_password_hash(new_password)
		session.pop('force_password_change', None)
		from models import db
		db.session.commit()
		flash('Password changed successfully.', 'success')
		return redirect(url_for('dashboard.dashboard'))

	return render_template('auth/change_password.html')

@auth_bp.route('/logout')
@login_required
def logout():
	session.pop('force_password_change', None)
	logout_user()
	return redirect(url_for('auth.login'))