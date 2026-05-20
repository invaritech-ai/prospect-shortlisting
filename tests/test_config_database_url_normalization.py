from app.core.config import Settings


def test_normalizes_postgres_scheme_to_sqlalchemy_driver_url() -> None:
    settings = Settings(_env_file=None, DATABASE_URL="postgres://user:pass@db:5432/prospect")
    assert settings.database_url == "postgresql+psycopg://user:pass@db:5432/prospect"


def test_normalizes_plain_postgresql_scheme_to_psycopg_driver() -> None:
    settings = Settings(_env_file=None, DATABASE_URL="postgresql://user:pass@db:5432/prospect")
    assert settings.database_url == "postgresql+psycopg://user:pass@db:5432/prospect"


def test_normalizes_postgresql_psycopg2_scheme_to_psycopg_driver() -> None:
    settings = Settings(_env_file=None, DATABASE_URL="postgresql+psycopg2://user:pass@db:5432/prospect")
    assert settings.database_url == "postgresql+psycopg://user:pass@db:5432/prospect"


def test_normalizes_postgres_psycopg_scheme_to_postgresql_psycopg() -> None:
    settings = Settings(_env_file=None, DATABASE_URL="postgres+psycopg://user:pass@db:5432/prospect")
    assert settings.database_url == "postgresql+psycopg://user:pass@db:5432/prospect"


def test_leaves_sqlite_url_unchanged() -> None:
    settings = Settings(_env_file=None, DATABASE_URL="sqlite:///data/scrape_service.db")
    assert settings.database_url == "sqlite:///data/scrape_service.db"
