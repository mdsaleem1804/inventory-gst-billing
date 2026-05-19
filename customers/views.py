from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from models import db, Customer

customers_bp = Blueprint('customers', __name__, url_prefix='/customers')

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
        name = request.form['name']
        gstin = request.form['gstin']
        address = request.form['address']
        if cid:
            customer = Customer.query.get(cid)
            if customer:
                customer.name = name
                customer.gstin = gstin
                customer.address = address
                db.session.commit()
                flash('Customer updated!', 'success')
        else:
            customer = Customer(name=name, gstin=gstin, address=address)
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
            Customer.gstin.ilike(f'%{search}%')
        )
    customers = query.order_by(Customer.name).all()
    return render_template('customers/crud.html', customers=customers, form_customer=form_customer, search=search)
