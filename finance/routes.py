from flask import Blueprint

finance_bp = Blueprint('finance', __name__, url_prefix='/finance')

from . import views
