CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS series_embeddings (
    series_id BIGINT NOT NULL REFERENCES series_search_documents(series_id) ON DELETE CASCADE,
    embedding_model TEXT NOT NULL,
    embedding_dim INTEGER NOT NULL,
    document_version TEXT NOT NULL,
    document_content_hash TEXT NOT NULL,
    embedding vector(768) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (series_id, embedding_model, embedding_dim)
);

CREATE INDEX IF NOT EXISTS idx_series_embeddings_model_dim
    ON series_embeddings(embedding_model, embedding_dim);

CREATE INDEX IF NOT EXISTS idx_series_embeddings_content_hash
    ON series_embeddings(document_content_hash);
