
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from .routes import products_bp
from models import db, Product, ActivityLog

@products_bp.route('/', methods=['GET', 'POST'])
@login_required
def crud_products():
	edit_id = request.args.get('edit_id', type=int)
	form_product = None
	if request.method == 'POST':
		# Delete
		delete_id = request.form.get('delete_id', type=int)
		if delete_id:
			if current_user.role != 'admin':
				flash('Only admin can delete products.', 'danger')
				return redirect(url_for('products.crud_products'))
			product = Product.query.get(delete_id)
			if product:
				db.session.delete(product)
				db.session.commit()
				db.session.add(ActivityLog(user_id=current_user.id, username=current_user.username, action='Delete Product', details=f'Product: {product.name}'))
				db.session.commit()
				flash('Product deleted!', 'success')
			return redirect(url_for('products.crud_products'))
		# Add or Update
		pid = request.form.get('id', type=int)
		name = request.form['name']
		hsn_code = request.form['hsn_code']
		gst_percent = float(request.form['gst_percent'])
		price = float(request.form['price'])
		if pid:
			product = Product.query.get(pid)
			if product:
				product.name = name
				product.hsn_code = hsn_code
				product.gst_percent = gst_percent
				product.price = price
				db.session.commit()
				db.session.add(ActivityLog(user_id=current_user.id, username=current_user.username, action='Edit Product', details=f'Product: {product.name}'))
				db.session.commit()
				flash('Product updated!', 'success')
		else:
			product = Product(name=name, hsn_code=hsn_code, gst_percent=gst_percent, price=price)
			db.session.add(product)
			db.session.commit()
			db.session.add(ActivityLog(user_id=current_user.id, username=current_user.username, action='Add Product', details=f'Product: {product.name}'))
			db.session.commit()
			flash('Product added!', 'success')
		return redirect(url_for('products.crud_products'))
	# GET
	search = request.args.get('search', '')
	if edit_id:
		form_product = Product.query.get(edit_id)
	query = Product.query
	if search:
		query = query.filter(
			Product.name.ilike(f'%{search}%') |
			Product.hsn_code.ilike(f'%{search}%')
		)
	products = query.order_by(Product.id).all()
	return render_template('products/crud.html', products=products, form_product=form_product, search=search)