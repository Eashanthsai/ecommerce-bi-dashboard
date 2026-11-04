import os

from werkzeug.security import generate_password_hash


os.environ["FLASK_SECRET_KEY"] = "test-suite-secret-key"
os.environ["DASHBOARD_USERNAME"] = "test-admin"
os.environ["DASHBOARD_PASSWORD_HASH"] = generate_password_hash(
    "test-only-password-123"
)
