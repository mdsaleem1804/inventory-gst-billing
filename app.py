
from flask import Flask
from num2words import num2words as n2w
import re
from config import Config

app = Flask(__name__)
# Indian currency formatting filter
def num2words_filter(value):
    try:
        return n2w(value, to='currency', lang='en_IN').replace('euro', '').replace('cents', '').replace('INR', '').strip()
    except Exception:
        return str(value)
app.jinja_env.filters['num2words'] = num2words_filter
def indian_currency(value):
    try:
        value = float(value)
    except (ValueError, TypeError):
        return value
    # Round to two decimals
    value = round(value + 1e-8, 2)
    s = f"{value:,.2f}"
    # Convert to Indian format
    x = s.split('.')
    int_part = x[0]
    dec_part = x[1] if len(x) > 1 else '00'
    if len(int_part) > 3:
        int_part = re.sub(r'(\d)(?=(\d{2})+(\d{3})$)', r'\1,', int_part)
    return f"{int_part}.{dec_part}"

app.jinja_env.filters['indian_currency'] = indian_currency
app.config.from_object(Config)



from models import db, User
from flask_login import LoginManager
db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'

# Register user loader after login_manager is defined
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Register blueprints
def register_blueprints(app):
    from auth.routes import auth_bp
    from products.routes import products_bp
    from invoices.routes import invoices_bp
    from reports.routes import reports_bp
    from dashboard import dashboard_bp
    from customers.views import customers_bp
    from company.routes import company_bp
    from users.routes import users_bp
    app.register_blueprint(auth_bp)
    print('Registered auth_bp')
    app.register_blueprint(products_bp)
    print('Registered products_bp')
    app.register_blueprint(invoices_bp)
    print('Registered invoices_bp')
    app.register_blueprint(reports_bp)
    print('Registered reports_bp')
    app.register_blueprint(dashboard_bp)
    print('Registered dashboard_bp')
    app.register_blueprint(customers_bp)
    print('Registered customers_bp')
    app.register_blueprint(company_bp)
    print('Registered company_bp')
    app.register_blueprint(users_bp)
    print('Registered users_bp')

register_blueprints(app)

if __name__ == '__main__':
    app.run(debug=True)
