import os
import sys
import logging
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr
# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, send_from_directory
from flask_cors import CORS
from src.models.user import db
from src.routes.user import user_bp
from src.routes.mcp import mcp_bp

# Create a null stream to discard output
class NullIO(StringIO):
    def write(self, *args, **kwargs):
        return
    def flush(self, *args, **kwargs):
        return

# Completely disable all logging
logging.disable(logging.CRITICAL)
for logger_name in ['werkzeug', 'sqlalchemy', 'sqlalchemy.engine', 'flask.app']:
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.disabled = True
    logger.propagate = False

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))
app.config['SECRET_KEY'] = 'asdf#FGSgvasgf$5$WGT'

# Completely disable Flask's internal logging
app.logger.handlers.clear()
app.logger.disabled = True
app.logger.propagate = False

# Enable CORS for all routes
CORS(app)

app.register_blueprint(user_bp, url_prefix='/api')
app.register_blueprint(mcp_bp, url_prefix='/api')

# uncomment if you need to use database
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(os.path.dirname(__file__), 'database', 'app.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
with app.app_context():
    db.create_all()

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_folder_path = app.static_folder
    if static_folder_path is None:
            return "Static folder not configured", 404

    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, 'index.html')
        else:
            return "index.html not found", 404


if __name__ == '__main__':
    # Redirect everything to null
    null_stream = NullIO()
    with redirect_stdout(null_stream), redirect_stderr(null_stream):
        app.run(
            host='0.0.0.0', 
            port=5000, 
            debug=False,          # MUST be False
            use_reloader=False,   # MUST be False
            threaded=True
        )