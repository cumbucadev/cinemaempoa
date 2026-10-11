from decouple import config

from flask_backend.utils.enums.environment import EnvironmentEnum

DATABASE_URL = config("DATABASE_URL", default="sqlite:///./development.sqlite")
SESSION_KEY = config("SESSION_KEY", default="dev")
SESSION_LIFETIME_DAYS = config("SESSION_LIFETIME_DAYS", default=365, cast=int)
APP_ENVIRONMENT = EnvironmentEnum(
    config("APP_ENVIRONMENT", default=EnvironmentEnum.DEVELOPMENT)
)
ADMIN_PROD_USERNAME = config("ADMIN_PROD_USERNAME", default="cinemaempoa")
ADMIN_PROD_PWD = config("ADMIN_PROD_PWD", default="secret-pwd")
UPLOAD_DIR = config("UPLOAD_DIR", None)
GRAPH_DB_PATH = config("GRAPH_DB_PATH", default="./flask_backend_graph.sqlite")
IMGBB_API_KEY = config(
    "IMGBB_API_KEY", default="invalid-key"
)  # api-key from https://api.imgbb.com/
GEMINI_API_KEY = config("GEMINI_API_KEY", None)
TMDB_API_TOKEN = config(
    "TMDB_API_TOKEN", default=None
)  # Read Access Token from https://www.themoviedb.org/settings/api
# Static bearer token the Orbit agent sends to the MCP server
# (flask_backend/mcp_server.py), which refuses to start while it is empty.
ORBIT_MCP_TOKEN = config("ORBIT_MCP_TOKEN", default="")
MCP_HOST = config("MCP_HOST", default="127.0.0.1")
MCP_PORT = config("MCP_PORT", default=8001, cast=int)
