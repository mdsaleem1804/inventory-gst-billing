import shutil
import os

# Copy app.db to dist folder for executable to use
src = os.path.join(os.path.dirname(__file__), 'app.db')
dst = os.path.join(os.path.dirname(__file__), 'dist', 'app.db')
shutil.copy2(src, dst)
print('Database copied to dist folder.')
