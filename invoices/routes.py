from flask import Blueprint

invoices_bp = Blueprint('invoices', __name__, url_prefix='/invoices')

from . import views
