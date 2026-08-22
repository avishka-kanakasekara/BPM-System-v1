-- Enable the pgvector extension in the agent2_db database.
-- This runs automatically on first container start via docker-entrypoint-initdb.d.
CREATE EXTENSION IF NOT EXISTS vector;
