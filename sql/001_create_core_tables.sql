CREATE TABLE IF NOT EXISTS datasets (
    dataset_id TEXT PRIMARY KEY,
    title TEXT,
    source_url TEXT NOT NULL,
    documentation_url TEXT,
    metadata_url TEXT,
    structure_ref TEXT,
    raw_file_path TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS series (
    series_id BIGSERIAL PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
    series_key TEXT NOT NULL,
    dimension_values JSONB NOT NULL,
    dimension_labels JSONB,
    search_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (dataset_id, series_key)
);

CREATE TABLE IF NOT EXISTS observations (
    observation_id BIGSERIAL PRIMARY KEY,
    series_id BIGINT NOT NULL REFERENCES series(series_id),
    time_period TEXT NOT NULL,
    obs_value NUMERIC,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (series_id, time_period)
);

CREATE TABLE IF NOT EXISTS codelists (
    codelist_pk BIGSERIAL PRIMARY KEY,
    agency_id TEXT,
    codelist_id TEXT NOT NULL,
    version TEXT,
    urn TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (agency_id, codelist_id, version)
);

CREATE TABLE IF NOT EXISTS codelist_items (
    codelist_item_id BIGSERIAL PRIMARY KEY,
    codelist_pk BIGINT NOT NULL REFERENCES codelists(codelist_pk),
    code_id TEXT NOT NULL,
    name TEXT,
    description TEXT,
    urn TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (codelist_pk, code_id)
);

CREATE INDEX IF NOT EXISTS idx_series_dataset_id
    ON series(dataset_id);

CREATE INDEX IF NOT EXISTS idx_observations_series_id
    ON observations(series_id);

CREATE INDEX IF NOT EXISTS idx_observations_time_period
    ON observations(time_period);

CREATE INDEX IF NOT EXISTS idx_codelist_items_code_id
    ON codelist_items(code_id);

CREATE INDEX IF NOT EXISTS idx_series_dimension_values_gin
    ON series USING GIN (dimension_values);

CREATE INDEX IF NOT EXISTS idx_series_dimension_labels_gin
    ON series USING GIN (dimension_labels);
