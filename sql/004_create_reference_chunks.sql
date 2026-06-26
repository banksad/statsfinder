CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS reference_chunks (
    chunk_id BIGSERIAL PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_title TEXT NOT NULL,
    source_url TEXT,
    page_number INTEGER,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    chunk_text TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS reference_chunks_source_idx
    ON reference_chunks (source_id);

CREATE INDEX IF NOT EXISTS reference_chunks_page_idx
    ON reference_chunks (source_id, page_number);

CREATE TABLE IF NOT EXISTS reference_chunk_embeddings (
    chunk_id BIGINT NOT NULL REFERENCES reference_chunks(chunk_id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    embedding_dim INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    embedding vector(768) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chunk_id, model, embedding_dim)
);
