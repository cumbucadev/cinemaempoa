from decouple import config

DATABASE_URL = config("DATABASE_URL", default="sqlite:///./flask_backend.sqlite")
SESSION_KEY = config("SESSION_KEY", default="dev")
