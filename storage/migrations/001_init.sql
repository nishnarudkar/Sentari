-- Postgres bootstrap. SQLAlchemy init_db() creates the tables; this file only
-- enables pgvector for the optional vector-store path.
CREATE EXTENSION IF NOT EXISTS vector;
-- Optional: dedicated embedding column for ANN search
-- ALTER TABLE chunks ADD COLUMN embedding_vec vector(384);
-- CREATE INDEX ON chunks USING ivfflat (embedding_vec vector_cosine_ops);
