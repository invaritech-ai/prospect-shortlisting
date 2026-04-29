from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context
from sqlmodel import SQLModel

from app.core.config import settings

# Import models so SQLModel metadata is populated for autogenerate.
from app.models import (  # noqa: F401
    AnalysisJob,
    ClassificationResult,
    Company,
    ContactFetchBatch,
    ContactFetchJob,
    ContactFetchRuntimeControl,
    ContactProviderAttempt,
    ContactRevealAttempt,
    ContactRevealBatch,
    ContactRevealJob,
    ContactVerifyJob,
    CrawlArtifact,
    CrawlJob,
    JobEvent,
    Prompt,
    Run,
    ScrapeJob,
    ScrapePage,
    TitleMatchRule,
    Upload,
)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = SQLModel.metadata

PIPELINE_TABLES = {
    "uploads",
    "companies",
    "crawl_jobs",
    "crawl_artifacts",
    "prompts",
    "runs",
    "analysis_jobs",
    "classification_results",
    "job_events",
    "scrapejob",
    "scrapepage",
    "contact_fetch_batches",
    "contact_fetch_jobs",
    "contact_fetch_runtime_controls",
    "contact_provider_attempts",
    "contact_reveal_batches",
    "contact_reveal_jobs",
    "contact_reveal_attempts",
    "contact_verify_jobs",
    "discovered_contacts",
    "prospect_contacts",
    "prospect_contact_emails",
    "title_match_rules",
}


def include_object(object_, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    if type_ == "table":
        return name in PIPELINE_TABLES
    return True

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
