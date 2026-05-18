from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required
from werkzeug.security import check_password_hash
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
			return redirect(url_for('dashboard.dashboard'))
		else:
			flash('Invalid username or password', 'danger')
	return render_template('auth/login.html')

@auth_bp.route('/logout')
@login_required
def logout():
	logout_user()
	return redirect(url_for('auth.login'))