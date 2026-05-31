from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from models import db, Company
import os
from werkzeug.utils import secure_filename

company_bp = Blueprint('company', __name__, url_prefix='/company')


def _require_admin():
    if current_user.role != 'admin':
        flash('Only admin can manage company information.', 'danger')
        return False
    return True

@company_bp.route('/')
@login_required
def index():
    if not _require_admin():
        return redirect(url_for('dashboard.dashboard'))
    company = Company.query.first()
    return render_template('company/crud.html', company=company)

@company_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if not _require_admin():
        return redirect(url_for('dashboard.dashboard'))
    # Only allow add if no company exists
    if Company.query.first():
        flash('Company information already exists. You can only edit or delete it.', 'warning')
        return redirect(url_for('company.index'))
    if request.method == 'POST':
        title = request.form['title']
        header = request.form.get('header')
        gst_number = request.form['gst_number']
        phone_number = request.form.get('phone_number')
        address = request.form.get('address')
        logo = None
        if 'logo' in request.files and request.files['logo'].filename:
            file = request.files['logo']
            filename = secure_filename(file.filename)
            logo_path = os.path.join('uploads', filename)
            file.save(os.path.join(current_app.static_folder, 'uploads', filename))
            logo = logo_path
        company = Company(title=title, header=header, gst_number=gst_number, phone_number=phone_number, address=address, logo=logo)
        db.session.add(company)
        db.session.commit()
        flash('Company information added successfully!', 'success')
        return redirect(url_for('company.index'))
    return render_template('company/add.html')

@company_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit(id):
    if not _require_admin():
        return redirect(url_for('dashboard.dashboard'))
    company = Company.query.get_or_404(id)
    if request.method == 'POST':
        company.title = request.form['title']
        company.header = request.form.get('header')
        company.gst_number = request.form['gst_number']
        company.phone_number = request.form.get('phone_number')
        company.address = request.form.get('address')
        if 'logo' in request.files and request.files['logo'].filename:
            file = request.files['logo']
            filename = secure_filename(file.filename)
            logo_path = os.path.join('uploads', filename)
            file.save(os.path.join(current_app.static_folder, 'uploads', filename))
            company.logo = logo_path
        db.session.commit()
        flash('Company information updated successfully!', 'success')
        return redirect(url_for('company.index'))
    return render_template('company/edit.html', company=company)


# Delete company info (for completeness, but only one record allowed)
@company_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete(id):
    if not _require_admin():
        return redirect(url_for('dashboard.dashboard'))
    company = Company.query.get_or_404(id)
    db.session.delete(company)
    db.session.commit()
    flash('Company information deleted.', 'success')
    return redirect(url_for('company.index'))
