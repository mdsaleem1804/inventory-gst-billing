from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from models import db, Company
import os
from werkzeug.utils import secure_filename

company_bp = Blueprint('company', __name__, url_prefix='/company')

@company_bp.route('/')
def index():
    company = Company.query.first()
    # Update company info to match attached invoice image if not already set
    if company:
        updated = False
        if company.title != 'PRINCE AGENCIES':
            company.title = 'PRINCE AGENCIES'
            updated = True
        header_text = 'No. 92, SAMUEL STREET, NAZARETH, TUTICORIN - 628 617'
        if company.header != header_text:
            company.header = header_text
            updated = True
        gst_number = '33CNWPP8106P1Z2'
        if company.gst_number != gst_number:
            company.gst_number = gst_number
            updated = True
        phone_number = '9566720210'
        if company.phone_number != phone_number:
            company.phone_number = phone_number
            updated = True
        address = 'No. 92, SAMUEL STREET, NAZARETH, TUTICORIN - 628 617'
        if company.address != address:
            company.address = address
            updated = True
        if updated:
            db.session.commit()
    return render_template('company/crud.html', company=company)

@company_bp.route('/add', methods=['GET', 'POST'])
def add():
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
def edit(id):
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
def delete(id):
    company = Company.query.get_or_404(id)
    db.session.delete(company)
    db.session.commit()
    flash('Company information deleted.', 'success')
    return redirect(url_for('company.index'))
