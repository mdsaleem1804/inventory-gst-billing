from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from models import db, Unit

units_bp = Blueprint('units', __name__, url_prefix='/units')

@units_bp.route('/', methods=['GET', 'POST'])
@login_required
def list_units():
    if request.method == 'POST':
        name = request.form.get('name').strip()
        abbreviation = request.form.get('abbreviation').strip()
        if not name or not abbreviation:
            flash('Name and abbreviation are required.', 'danger')
        elif Unit.query.filter((Unit.name == name) | (Unit.abbreviation == abbreviation)).first():
            flash('Unit name or abbreviation already exists.', 'danger')
        else:
            unit = Unit(name=name, abbreviation=abbreviation)
            db.session.add(unit)
            db.session.commit()
            flash('Unit added successfully.', 'success')
        return redirect(url_for('units.list_units'))
    units = Unit.query.order_by(Unit.name).all()
    return render_template('units/crud.html', units=units)

@units_bp.route('/edit/<int:unit_id>', methods=['GET', 'POST'])
@login_required
def edit_unit(unit_id):
    unit = Unit.query.get_or_404(unit_id)
    if request.method == 'POST':
        name = request.form.get('name').strip()
        abbreviation = request.form.get('abbreviation').strip()
        if not name or not abbreviation:
            flash('Name and abbreviation are required.', 'danger')
        elif Unit.query.filter(((Unit.name == name) | (Unit.abbreviation == abbreviation)) & (Unit.id != unit_id)).first():
            flash('Unit name or abbreviation already exists.', 'danger')
        else:
            unit.name = name
            unit.abbreviation = abbreviation
            db.session.commit()
            flash('Unit updated successfully.', 'success')
            return redirect(url_for('units.list_units'))
    return render_template('units/edit.html', unit=unit)

@units_bp.route('/delete/<int:unit_id>', methods=['POST'])
@login_required
def delete_unit(unit_id):
    unit = Unit.query.get_or_404(unit_id)
    db.session.delete(unit)
    db.session.commit()
    flash('Unit deleted.', 'success')
    return redirect(url_for('units.list_units'))
