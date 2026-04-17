"""LocalBackend — pandas + PostgreSQL execution backend.

Method bodies are stubs; full implementations ship with F1/F3.
"""

import pandas as pd
from src.worker.compute.base import ComputeBackend


class LocalBackend(ComputeBackend):
    """Runs generated pipelines locally using pandas and PostgreSQL."""

    def read_csv(self, path: str) -> pd.DataFrame:
        """Read a CSV file into a pandas DataFrame.

        Args:
            path: Path to the CSV file.

        Returns:
            pandas DataFrame.
        """
        raise NotImplementedError("LocalBackend.read_csv — implemented in F1")

    def run_sql(self, query: str, context: dict[str, object]) -> pd.DataFrame:
        """Execute SQL against in-memory pandas DataFrames via DuckDB-in-memory.

        Args:
            query: SQL query string.
            context: Table name → DataFrame mapping.

        Returns:
            Result as a pandas DataFrame.
        """
        raise NotImplementedError("LocalBackend.run_sql — implemented in F1")

    def write_parquet(self, df: object, path: str) -> None:
        """Write a pandas DataFrame to Parquet.

        Args:
            df: pandas DataFrame.
            path: Destination path.
        """
        raise NotImplementedError("LocalBackend.write_parquet — implemented in F1")

    def to_pandas(self, df: object) -> pd.DataFrame:
        """Return df unchanged — it is already a pandas DataFrame.

        Args:
            df: pandas DataFrame.

        Returns:
            The same DataFrame, cast to pd.DataFrame.
        """
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"Expected pandas DataFrame, got {type(df)}")
        return df
