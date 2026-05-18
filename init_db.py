from app import app
from models import db, User
from werkzeug.security import generate_password_hash

with app.app_context():
    db.create_all()
    # Check if admin user exists
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password_hash=generate_password_hash('admin'))
        db.session.add(admin)
        db.session.commit()
        print('Admin user created: admin/admin')
    else:
        print('Admin user already exists.')
    print('Database initialized.')
