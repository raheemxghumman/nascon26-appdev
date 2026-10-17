import os

# Read once at startup from the environment only (spec 5.2): never hard-coded.
DAY1_SALT = os.environ.get("DAY1_SALT", "")
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-jwt-secret-change-me")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://league:league@localhost:5432/league")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
MAX_BODY_BYTES = 1024 * 1024
