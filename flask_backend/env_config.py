from decouple import config

DATABASE_URL = config("DATABASE_URL", default="sqlite:///./flask_backend.sqlite")
SESSION_KEY = config("SESSION_KEY", default="dev")
APP_ENVIRONMENT = config("APP_ENVIRONMENT", default="development")
ADMIN_PROD_USERNAME = config("ADMIN_PROD_USERNAME", default="cinemaempoa")
ADMIN_PROD_PWD = config("ADMIN_PROD_PWD", default="secret-pwd")
