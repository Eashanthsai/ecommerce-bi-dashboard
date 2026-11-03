import os
import secrets


os.environ.setdefault("FLASK_SECRET_KEY", secrets.token_hex(32))
