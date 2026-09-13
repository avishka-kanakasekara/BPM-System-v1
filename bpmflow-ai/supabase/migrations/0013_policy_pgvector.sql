-- pgvector support for policy chunk semantic retrieval (Agent 4 G5)

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE public.policy_chunks
    ADD COLUMN IF NOT EXISTS embedding_vector vector(128);

COMMENT ON COLUMN public.policy_chunks.embedding_vector IS
    'Cosine-indexed embedding for tenant policy retrieval; JSONB embedding kept for REST fallback.';

CREATE INDEX IF NOT EXISTS idx_policy_chunks_embedding_vector
    ON public.policy_chunks
    USING ivfflat (embedding_vector vector_cosine_ops)
    WITH (lists = 100);
