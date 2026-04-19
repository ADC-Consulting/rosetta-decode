-- Install extensions required by TensorZero
-- pg_cron: scheduled job cleanup / retention
-- vector: pgvector for DICL (Dynamic In-Context Learning) similarity search
CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS vector;
