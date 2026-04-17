# Architecture

## Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (React)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Explanation  │  │ Side-by-Side │  │ Lineage / Graph  │  │
│  │ Assistant UI │  │   Diff View  │  │      Views       │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         └─────────────────┴──────────────────┘             │
│                        REST API (FastAPI)                    │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                       Backend (Python)                       │
│                                                             │
│  ┌──────────────────────┐   ┌──────────────────────────┐   │
│  │   Migration Engine   │   │   Validation Engine      │   │
│  │  ┌────────────────┐  │   │  ┌────────────────────┐  │   │
│  │  │  SAS Parser    │  │   │  │ Schema / Row Check │  │   │
│  │  │  (static src)  │  │   │  │ Aggregate Parity   │  │   │
│  │  ├────────────────┤  │   │  │ Hash Diff          │  │   │
│  │  │  Log Ingestion │  │   │  └────────────────────┘  │   │
│  │  │  (runtime ctx) │  │   └──────────────────────────┘   │
│  │  ├────────────────┤  │                                   │
│  │  │  LLM Client    │  │   ┌──────────────────────────┐   │
│  │  │  (hosted API)  │  │   │     ComputeBackend        │   │
│  │  ├────────────────┤  │   │  ┌──────────┐ ┌────────┐ │   │
│  │  │  Code Generator│  │   │  │  Local   │ │ Spark  │ │   │
│  │  │  + Provenance  │  │   │  │pandas/   │ │Databri-│ │   │
│  │  └────────────────┘  │   │  │DuckDB    │ │cks     │ │   │
│  └──────────────────────┘   │  └──────────┘ └────────┘ │   │
│                             └──────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │  Pydantic AI + Hosted LLM   │
              │  (Claude / OpenAI / etc.)   │
              └─────────────────────────────┘
```

---

## Data Flow — Migration (F1)

```
SAS script(s)
     │
     ▼
SAS Parser ──────────────────────────────► AST / Block List
     │                                           │
     ▼                                           ▼
Log Ingestion (optional)              LLM Client (hosted API)
     │                                     │  prompt = SAS block
     └─────────────────────────────────────┘       + patterns
                                                    + context
                                                         │
                                                         ▼
                                              Generated Python block
                                              + provenance comments
                                                         │
                                                         ▼
                                              Code Generator assembles
                                              full ETL pipeline
                                                         │
                                              ┌──────────┴──────────┐
                                              │   ComputeBackend     │
                                              │  (selected by CLOUD) │
                                              └──────────────────────┘
```

---

## ComputeBackend Interface

All execution is routed through a single abstract interface. No `if CLOUD` checks are allowed outside of the factory that creates the backend.

```python
from abc import ABC, abstractmethod
import pandas as pd

class ComputeBackend(ABC):

    @abstractmethod
    def read_csv(self, path: str) -> object:
        """Return a DataFrame (pandas or Spark) from a CSV path."""

    @abstractmethod
    def run_sql(self, query: str, context: dict[str, object]) -> object:
        """Execute SQL against registered tables and return a DataFrame."""

    @abstractmethod
    def write_parquet(self, df: object, path: str) -> None:
        """Write a DataFrame to Parquet at the given path."""

    @abstractmethod
    def to_pandas(self, df: object) -> pd.DataFrame:
        """Convert backend DataFrame to pandas for reconciliation."""
```

Implementations: `LocalBackend` (pandas + DuckDB), `DatabricksBackend` (PySpark).  
Selected at startup via `BackendFactory.create(cloud: bool)` reading the `CLOUD` env var.

---

## Key Directories (planned)

```
src/
  backend/
    api/          # FastAPI routes
    engine/       # SAS parser, LLM client, code generator
    validation/   # Reconciliation checks
    compute/      # ComputeBackend, LocalBackend, DatabricksBackend
  frontend/
    src/
      pages/      # Explanation UI, diff view, lineage, graph
      components/ # shadcn/ui components
      api/        # API client layer
tests/
  reconciliation/ # pytest reconciliation tests (one per SAS construct)
samples/          # Sample SAS scripts and exported SAS outputs for testing
```

---

## Technology Stack

| Layer | Technology |
|---|---|
| Backend language | Python 3.11+ |
| API framework | FastAPI |
| Local execution | pandas + DuckDB |
| Cloud execution | PySpark (Databricks) |
| LLM integration | Pydantic AI (`pydantic-ai`) — agent framework, tools, structured outputs |
| Frontend | React + Vite + TypeScript |
| UI components | Tailwind CSS + shadcn/ui |
| Formatter/linter | ruff |
| Type checker | mypy |
| Tests | pytest |
| Config | .env (CLOUD flag) |
