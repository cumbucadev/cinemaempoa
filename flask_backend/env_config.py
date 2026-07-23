from decouple import config

from flask_backend.utils.enums.environment import EnvironmentEnum

DATABASE_URL = config("DATABASE_URL", default="sqlite:///./development.sqlite")
SESSION_KEY = config("SESSION_KEY", default="dev")
APP_ENVIRONMENT = EnvironmentEnum(
    config("APP_ENVIRONMENT", default=EnvironmentEnum.DEVELOPMENT)
)
ADMIN_PROD_USERNAME = config("ADMIN_PROD_USERNAME", default="cinemaempoa")
ADMIN_PROD_PWD = config("ADMIN_PROD_PWD", default="secret-pwd")
UPLOAD_DIR = config("UPLOAD_DIR", None)
IMGBB_API_KEY = config(
    "IMGBB_API_KEY", default="invalid-key"
)  # api-key from https://api.imgbb.com/
GEMINI_API_KEY = config("GEMINI_API_KEY", None)
TMDB_API_TOKEN = config(
    "TMDB_API_TOKEN", default=None
)  # Read Access Token from https://www.themoviedb.org/settings/api
PAULO_AMORIM_EMAIL_ADDRESS = config("PAULO_AMORIM_EMAIL_ADDRESS", default=None)
PAULO_AMORIM_EMAIL_APP_PASSWORD = config(
    "PAULO_AMORIM_EMAIL_APP_PASSWORD", default=None
)
PAULO_AMORIM_NEWSLETTER_SENDER_EMAIL = config(
    "PAULO_AMORIM_NEWSLETTER_SENDER_EMAIL", default=None
)  # sender address to filter for in the mailbox; fill in once the newsletter is subscribed to
