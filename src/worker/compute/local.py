"""LocalBackend — pandas execution backend for CLOUD=false.

SQL queries are executed via an in-memory SQLite connection (stdlib sqlite3)
so that PROC SQL translations run locally without a live PostgreSQL service.
This is intentional for unit and reconciliation tests; production local runs
use the same path since result fidelity is what matters, not the SQL engine.
"""

import sqlite3

import pandas as pd
from src.worker.compute.base import ComputeBackend


class LocalBackend(ComputeBackend):
    """Runs generated pipelines locally using pandas and in-memory SQLite."""

    def read_csv(self, path: str) -> pd.DataFrame:
        """Read a CSV file into a pandas DataFrame.

        Args:
            path: Path to the CSV file.

        Returns:
            pandas DataFrame with all columns loaded.
        """
        return pd.read_csv(path)

    def run_sql(self, query: str, context: dict[str, object]) -> pd.DataFrame:
        """Execute a SQL query against the provided DataFrames via SQLite.

        Each key in *context* is registered as a table name. The query runs
        inside a temporary in-memory SQLite connection; results are returned
        as a pandas DataFrame.

        Args:
            query: ANSI SQL query string.
            context: Mapping of table name to pandas DataFrame.

        Returns:
            Query result as a pandas DataFrame.

        Raises:
            TypeError: If any value in *context* is not a pandas DataFrame.
        """
        conn = sqlite3.connect(":memory:")
        try:
            for table_name, df in context.items():
                if not isinstance(df, pd.DataFrame):
                    raise TypeError(
                        f"context['{table_name}'] must be a pandas DataFrame, got {type(df)}"
                    )
                df.to_sql(table_name, conn, index=False, if_exists="replace")
            return pd.read_sql_query(query, conn)
        finally:
            conn.close()

    def write_parquet(self, df: object, path: str) -> None:
        """Write a pandas DataFrame to a Parquet file.

        Args:
            df: pandas DataFrame to write.
            path: Destination file path (created or overwritten).

        Raises:
            TypeError: If *df* is not a pandas DataFrame.
        """
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"Expected pandas DataFrame, got {type(df)}")
        df.to_parquet(path, index=False)

    def to_pandas(self, df: object) -> pd.DataFrame:
        """Return *df* unchanged — it is already a pandas DataFrame.

        Args:
            df: pandas DataFrame.

        Returns:
            The same DataFrame, cast to pd.DataFrame.

        Raises:
            TypeError: If *df* is not a pandas DataFrame.
        """
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"Expected pandas DataFrame, got {type(df)}")
        return df
