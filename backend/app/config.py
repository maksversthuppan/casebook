from datetime import date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Every date in this system is a Kerala calendar date - a hearing is listed on
#: a day, not at an instant. "Today" therefore means today *in court*, which is
#: not the same as the server's local day if the server is ever set to UTC:
#: `date.today()` there rolls over five and a half hours early. See the comment
#: on `Case.filing_date` for the sibling trap on the way into the database.
IST = ZoneInfo("Asia/Kolkata")


def today_in_court() -> date:
    """The calendar date it currently is in Kerala."""
    return datetime.now(IST).date()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://dcms:dcms@localhost:5433/dcms"
    session_secret: str = "dev-only-change-me"
    # A working day. Advocates sign in once in the morning.
    session_max_age: int = 60 * 60 * 12
    debug: bool = True
    # Comma-separated. The frontend origin(s) allowed to make credentialed
    # requests - in the deployed split (Vercel + Render), the browser never
    # calls the backend directly (frontend/next.config.ts proxies /api/*), so
    # this only matters for someone hitting the backend origin straight on.
    allowed_origins: str = "http://localhost:3000"

    @field_validator("database_url", mode="before")
    @classmethod
    def _require_asyncpg_driver(cls, value: str) -> str:
        """Normalize a bare `postgresql://`/`postgres://` URL to asyncpg.

        The app is async-only (`create_async_engine` in `app/db.py`), which
        needs the `+asyncpg` driver in the URL to pick the right SQLAlchemy
        dialect - without it, SQLAlchemy defaults to psycopg2 (never
        installed here; it's sync-only) and fails at engine creation with
        `ModuleNotFoundError: No module named 'psycopg2'`. Whoever pastes a
        connection string in - a Supabase dashboard, a repo secret - has no
        reason to know this SQLAlchemy-specific convention, since it isn't
        part of a standard postgres URI; normalizing here means a plain
        connection string just works instead of failing at engine creation.
        """
        for prefix in ("postgresql://", "postgres://"):
            if value.startswith(prefix):
                return "postgresql+asyncpg://" + value[len(prefix) :]
        return value

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if not settings.debug and settings.session_secret == "dev-only-change-me":
        raise RuntimeError(
            "SESSION_SECRET is still the development default. Generate a real one: "
            'python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    return settings
