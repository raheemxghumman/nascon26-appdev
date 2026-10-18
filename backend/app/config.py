import os

# Read once at startup from the environment only (spec 5.2): never hard-coded.
DAY1_SALT = os.environ.get("DAY1_SALT", "")
DAY2_SALT = os.environ.get("DAY2_SALT", "")
MEDIA_API = os.environ.get("MEDIA_API", "http://media:9997")
PUBLIC_BASE = os.environ.get("PUBLIC_BASE", "http://localhost:8080").rstrip("/")
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-jwt-secret-change-me")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://league:league@localhost:5432/league")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
MAX_BODY_BYTES = 1024 * 1024
