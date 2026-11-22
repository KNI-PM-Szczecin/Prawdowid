"""
Trims the scraper's Law table to the acts rag actually imports (app/data/law_acts.json): for every entry the newest
matching act is kept, every other row is deleted. The full Dziennik Ustaw 2025-2026 dump (about 120k article rows,
137M characters) would exceed the free database tier and nothing reads the other acts.

Dry run by default. `--apply` deletes and runs VACUUM so the space is actually released.

    uv run python scripts/trim_law_table.py            # report only
    uv run python scripts/trim_law_table.py --apply    # delete and vacuum
"""

import argparse
import asyncio

import asyncpg

from app import db
from app.config import settings
from app.law_import import ActVersion, act_versions, load_act_specs, newest_version


async def main(apply: bool) -> None:
    await db.connect()
    try:
        rows = await db.fetch_law_acts()
        candidates = act_versions(rows)
        kept: dict[tuple[int, int], ActVersion] = {}
        for spec in load_act_specs():
            version = newest_version(spec, candidates)
            if version is None:
                print(f"no act matches {spec.id}")
                continue
            kept[(version.position, version.year)] = version

        table = db._table(settings.corpus_law_table)
        total_rows = await db.pool().fetchval(f"SELECT COUNT(*) FROM {table}")
        kept_rows = await db.pool().fetchval(
            f"SELECT COUNT(*) FROM {table} WHERE (docid, date / {db.YEAR_DIVISOR}) IN "
            "(SELECT * FROM unnest($1::bigint[], $2::bigint[]))",
            [position for position, _ in kept],
            [year for _, year in kept],
        )
        print(
            f"acts kept: {len(kept)} of {len(rows)}; rows kept: {kept_rows} of {total_rows}; "
            f"rows to delete: {total_rows - kept_rows}"
        )
        for (position, year), version in sorted(kept.items(), key=lambda item: item[1].date):
            print(f"  keep Dz.U. {year} poz. {position}: {' '.join(version.title.split())[:100]}")
        if not apply:
            print("dry run, nothing deleted (use --apply)")
            return

        # The service pool has a short command timeout meant for searches; deleting 100k rows and VACUUM need their own
        # connection without it.
        connection = await asyncpg.connect(settings.postgres_dsn, statement_cache_size=0)
        try:
            deleted = await connection.execute(
                f"DELETE FROM {table} WHERE (docid, date / {db.YEAR_DIVISOR}) NOT IN "
                "(SELECT * FROM unnest($1::bigint[], $2::bigint[])) OR date IS NULL OR docid IS NULL",
                [position for position, _ in kept],
                [year for _, year in kept],
            )
            print(f"deleted: {deleted}")
            try:
                await connection.execute(f"VACUUM (FULL, ANALYZE) {table}")
                print("vacuum done")
            except asyncpg.PostgresError as error:
                print(f"vacuum skipped: {type(error).__name__}: {error}")
        finally:
            await connection.close()
    finally:
        await db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="delete rows and vacuum; without it only a report")
    asyncio.run(main(parser.parse_args().apply))
