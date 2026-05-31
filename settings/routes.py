from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app
from flask_login import login_required, current_user
import os
import shutil
from datetime import datetime

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')

BACKUP_FOLDER = 'backups'
DB_FILENAME = 'app.db'


def _require_admin():
    if current_user.role != 'admin':
        flash('Only admin can access backup and restore settings.', 'danger')
        return False
    return True

@settings_bp.route('/backup', methods=['GET', 'POST'])
@login_required
def backup_restore():
    if not _require_admin():
        return redirect(url_for('dashboard.dashboard'))
    if not os.path.exists(BACKUP_FOLDER):
        os.makedirs(BACKUP_FOLDER)
    backup_files = os.listdir(BACKUP_FOLDER)
    backup_files.sort(reverse=True)
    if request.method == 'POST':
        if 'backup' in request.form:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            src = os.path.join(current_app.root_path, DB_FILENAME)
            dst = os.path.join(BACKUP_FOLDER, f"backup_{timestamp}.db")
            shutil.copy2(src, dst)
            flash('Backup created successfully.', 'success')
            return redirect(url_for('settings.backup_restore'))
        elif 'restore' in request.form:
            if not _require_admin():
                return redirect(url_for('dashboard.dashboard'))
            restore_file = request.form.get('restore_file')
            if restore_file and restore_file in backup_files:
                src = os.path.join(BACKUP_FOLDER, restore_file)
                dst = os.path.join(current_app.root_path, DB_FILENAME)
                shutil.copy2(src, dst)
                flash('Database restored successfully. Please restart the app.', 'success')
                return redirect(url_for('settings.backup_restore'))
    return render_template('settings/backup_restore.html', backup_files=backup_files)

@settings_bp.route('/download/<filename>')
@login_required
def download_backup(filename):
    if not _require_admin():
        return redirect(url_for('dashboard.dashboard'))
    backup_path = os.path.join(BACKUP_FOLDER, filename)
    if os.path.exists(backup_path):
        return send_file(backup_path, as_attachment=True)
    flash('File not found.', 'danger')
    return redirect(url_for('settings.backup_restore'))
