#!/usr/bin/env python3
r"""Seed all demo jobs into the database.

Runs the three demo seed scripts in sequence:
  1. Customer Revenue Pipeline      (dec0de00-…-001)
  2. Regulatory Exposure Reporting  (dec0de00-…-002)
  3. KYC / AML Client Screening     (dec0de00-…-003)

Usage:
    DATABASE_URL=postgresql+asyncpg://rosetta:rosetta@localhost:5432/rosetta \
        uv run python scripts/seed_all.py
"""

import asyncio

import seed_demo_job  # type: ignore[import-not-found]
import seed_finrep_job  # type: ignore[import-not-found]
import seed_kyc_job  # type: ignore[import-not-found]


async def main() -> None:
    """Seed all three demo jobs in sequence."""
    print("Seeding all demo jobs...\n")
    await seed_demo_job.seed()
    print()
    await seed_finrep_job.seed()
    print()
    await seed_kyc_job.seed()
    print("\nAll demo jobs seeded.")


if __name__ == "__main__":
    asyncio.run(main())
