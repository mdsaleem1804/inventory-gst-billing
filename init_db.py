from app import app
from models import db, User, Unit, Company
from werkzeug.security import generate_password_hash

with app.app_context():
    db.create_all()
    changed = False

    # Create admin user if not exists
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password_hash=generate_password_hash('admin'), role='admin')
        db.session.add(admin)
        changed = True
        print('Admin user created: admin/admin')
    else:
        print('Admin user already exists.')

    # Ensure one default unit exists
    if not Unit.query.first():
        db.session.add(Unit(name='Nos', abbreviation='NOS'))
        changed = True
        print('Default unit created: Nos (NOS)')

    # Ensure one default company exists
    if not Company.query.first():
        db.session.add(
            Company(
                title='Default Company',
                header='Inventory GST Billing',
                gst_number='UNREGISTERED',
                phone_number='',
                address='',
                logo=None,
            )
        )
        changed = True
        print('Default company created: Default Company')

    if changed:
        db.session.commit()

    print('Database initialized.')
