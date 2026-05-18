
from flask import Flask
from config import Config

app = Flask(__name__)
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
    app.register_blueprint(auth_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(invoices_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(customers_bp)

register_blueprints(app)

if __name__ == '__main__':
    app.run(debug=True)
