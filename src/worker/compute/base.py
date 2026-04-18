"""Abstract ComputeBackend interface.

All execution differences between local (pandas/PostgreSQL) and cloud
(PySpark/Databricks) are encapsulated here. No if-CLOUD checks are
allowed outside BackendFactory.
"""

from abc import ABC, abstractmethod

import pandas as pd


class ComputeBackend(ABC):
    """Execution backend abstraction for local and cloud environments."""

    @abstractmethod
    def read_csv(self, path: str) -> object:
        """Read a CSV file and return a backend-native DataFrame.

        Args:
            path: Absolute or relative path to the CSV file.

        Returns:
            A pandas DataFrame (LocalBackend) or Spark DataFrame (DatabricksBackend).
        """

    @abstractmethod
    def read_sas7bdat(self, path: str) -> object:
        """Read a .sas7bdat binary dataset into a backend-native DataFrame.

        Args:
            path: Absolute path to the .sas7bdat file.

        Returns:
            A pandas DataFrame (LocalBackend) or Spark DataFrame (DatabricksBackend).
        """

    @abstractmethod
    def run_sql(self, query: str, context: dict[str, object]) -> object:
        """Execute a SQL query against registered tables.

        Args:
            query: ANSI SQL query string.
            context: Mapping of table name to DataFrame to register before execution.

        Returns:
            A backend-native DataFrame containing the query result.
        """

    @abstractmethod
    def write_parquet(self, df: object, path: str) -> None:
        """Write a DataFrame to Parquet at the given path.

        Args:
            df: A backend-native DataFrame.
            path: Destination path for the Parquet file.
        """

    @abstractmethod
    def to_pandas(self, df: object) -> pd.DataFrame:
        """Convert a backend-native DataFrame to pandas for reconciliation.

        Args:
            df: A backend-native DataFrame.

        Returns:
            An equivalent pandas DataFrame.
        """
