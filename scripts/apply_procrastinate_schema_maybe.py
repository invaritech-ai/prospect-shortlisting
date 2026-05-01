"""Apply Procrastinate DDL only when the queue tables are missing.

``procrastinate schema --apply`` runs the full bundled ``schema.sql``, which uses
bare ``CREATE TYPE`` / ``CREATE TABLE`` statements. Re-running fails with errors
such as ``type "procrastinate_job_status" already exists`` once the schema is
installed.

Uses the library's ``check_connection`` probe (``procrastinate_jobs`` via
``to_regclass``) so startup stays idempotent.
"""

from __future__ import annotations

import asyncio
import sys


async def _main() -> None:
    from app.queue import app as procrastinate_app

    async with procrastinate_app.open_async():
        installed = await procrastinate_app.check_connection_async()
        if installed:
            print(
                "procrastinate schema already present — skipping apply",
                file=sys.stderr,
            )
            return
        print("Installing procrastinate SQL schema …", file=sys.stderr)
        await procrastinate_app.schema_manager.apply_schema_async()
        print("procrastinate SQL schema OK", file=sys.stderr)


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
