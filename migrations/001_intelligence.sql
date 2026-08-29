-- =============================================================================
-- 001 — Intelligence Pipeline: modelo de dados
--
-- Implementa a arquitetura de 12 entidades, com tres desvios do spec original,
-- todos decididos pelo dono do projeto:
--
--   1. `niche_profiles` no lugar de `profiles.niche_id` — um perfil de aposta
--      esta em "apostas" E "cassino" E "tigrinho" ao mesmo tempo. Com uma
--      chave estrangeira simples seria preciso escolher um ou duplicar o perfil.
--
--   2. `embeddings.embedding` nasce como `real[]`, nao `vector(N)`. O pgvector
--      no Windows exige compilar com MSVC, e nesta fase nenhum embedding sera
--      gerado (a analise por IA entra so como tabela, sem chamar modelo).
--      Quando a extensao entrar: `ALTER TABLE embeddings
--      ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector`.
--
--   3. `content_hashtags` e `content_mentions` acrescentadas. Cairiam em
--      `raw_data`, mas o proprio spec manda nao depender de JSONB para consulta
--      importante — e "quais temas estao emergindo" e consulta importante.
--
-- Convencao de nomes em ingles, como no spec. O codigo Python do projeto
-- continua em portugues; a fronteira e a camada de repositorio.
--
-- REGRA QUE ATRAVESSA TUDO: metrica indisponivel e NULL, nunca 0. `0 curtidas`
-- afirma que ninguem curtiu; `NULL` admite que a plataforma nao conta em
-- publico. Confundir os dois envenena toda media calculada depois.
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- `updated_at` mantido pelo banco, e nao pela aplicacao: assim vale tambem
-- para quem mexer por fora, num cliente SQL.
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ============================================================ 1. NICHES

CREATE TABLE IF NOT EXISTS niches (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT        NOT NULL UNIQUE,
    description TEXT,
    keywords    TEXT[]      NOT NULL DEFAULT '{}',
    language    TEXT,
    country     TEXT,
    status      TEXT        NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'paused', 'archived')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- =========================================================== 2. PROFILES

CREATE TABLE IF NOT EXISTS profiles (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    platform            TEXT        NOT NULL DEFAULT 'instagram',
    platform_profile_id TEXT,
    username            TEXT        NOT NULL,
    profile_url         TEXT,
    display_name        TEXT,
    bio                 TEXT,

    -- Valor corrente, para consulta rapida. O historico mora em
    -- `profile_snapshots` — crescimento e diferenca, e diferenca precisa de
    -- duas linhas, nunca de uma coluna que se sobrescreve.
    followers           BIGINT,
    following           BIGINT,
    content_count       BIGINT,

    is_verified         BOOLEAN,
    is_private          BOOLEAN,
    category            TEXT,          -- so conta comercial costuma ter
    avatar_url          TEXT,
    external_url        TEXT,
    language            TEXT,          -- inferido, nao vem da fonte

    -- Julgamento humano. Fica separado da coleta: recoletar o perfil nao pode
    -- apagar o que voce decidiu sobre ele.
    is_approved         BOOLEAN,
    relevance           REAL,
    classified_at       TIMESTAMPTZ,

    source              TEXT,
    source_actor        TEXT,
    source_run_id       TEXT,

    raw_data            JSONB,

    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT profiles_platform_username_key UNIQUE (platform, username)
);

-- Chave natural da plataforma, quando ela vier. Parcial porque
-- `platform_profile_id` pode faltar, e NULL nao pode colidir com NULL.
CREATE UNIQUE INDEX IF NOT EXISTS profiles_platform_id_key
    ON profiles (platform, platform_profile_id)
    WHERE platform_profile_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS profiles_followers_idx ON profiles (followers DESC);


-- Muitos para muitos, de proposito (desvio 1 do cabecalho).
CREATE TABLE IF NOT EXISTS niche_profiles (
    niche_id    BIGINT NOT NULL REFERENCES niches(id)   ON DELETE CASCADE,
    profile_id  BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    source      TEXT,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (niche_id, profile_id)
);


-- Serie temporal do perfil. Sem ela, followers_growth_7d e impossivel.
CREATE TABLE IF NOT EXISTS profile_snapshots (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    profile_id    BIGINT      NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    collected_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    followers     BIGINT,
    following     BIGINT,
    content_count BIGINT,
    job_id        BIGINT,
    CONSTRAINT profile_snapshots_unique UNIQUE (profile_id, collected_at)
);

CREATE INDEX IF NOT EXISTS profile_snapshots_idx
    ON profile_snapshots (profile_id, collected_at DESC);


-- =========================================================== 3. CONTENTS

CREATE TABLE IF NOT EXISTS contents (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    profile_id          BIGINT      NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    platform            TEXT        NOT NULL DEFAULT 'instagram',
    platform_content_id TEXT        NOT NULL,
    content_url         TEXT,
    content_type        TEXT        CHECK (content_type IN
                            ('reel', 'video', 'carousel', 'image', 'story', 'other')),
    caption             TEXT,
    published_at        TIMESTAMPTZ,
    duration_seconds    REAL,
    thumbnail_url       TEXT,

    -- URL do CDN. VENCE. Guardada por conveniencia, nunca como fonte primaria
    -- do download: quem baixa e o yt-dlp, resolvendo `content_url` na hora.
    source_video_url    TEXT,

    language            TEXT,          -- inferido da legenda, nao vem da fonte

    audio_id            TEXT,
    audio_title         TEXT,
    audio_author        TEXT,
    is_original_audio   BOOLEAN,
    location_id         TEXT,
    location_name       TEXT,

    -- O JSON cru da fonte, intacto. E o que permite reprocessar de graca
    -- quando o mapeamento de campos estiver errado — em vez de pagar a
    -- coleta de novo.
    raw_data            JSONB,

    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT contents_platform_id_key UNIQUE (platform, platform_content_id)
);

CREATE INDEX IF NOT EXISTS contents_profile_idx   ON contents (profile_id);
CREATE INDEX IF NOT EXISTS contents_published_idx ON contents (published_at DESC);
CREATE INDEX IF NOT EXISTS contents_audio_idx     ON contents (audio_id)
    WHERE audio_id IS NOT NULL;


-- Desvio 3: hashtag e mencao em tabela propria, nao so dentro do raw_data.
CREATE TABLE IF NOT EXISTS content_hashtags (
    content_id BIGINT NOT NULL REFERENCES contents(id) ON DELETE CASCADE,
    tag        TEXT   NOT NULL,
    PRIMARY KEY (content_id, tag)
);

CREATE INDEX IF NOT EXISTS content_hashtags_tag_idx ON content_hashtags (tag);

CREATE TABLE IF NOT EXISTS content_mentions (
    content_id BIGINT NOT NULL REFERENCES contents(id) ON DELETE CASCADE,
    username   TEXT   NOT NULL,
    PRIMARY KEY (content_id, username)
);


-- ========================================= 4. CONTENT METRIC SNAPSHOTS

-- A tabela mais importante do sistema. Nunca depender do valor corrente:
-- velocidade e aceleracao sao diferenca entre duas leituras.
CREATE TABLE IF NOT EXISTS content_metric_snapshots (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    content_id     BIGINT      NOT NULL REFERENCES contents(id) ON DELETE CASCADE,
    collected_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Horas desde a publicacao NO MOMENTO DA LEITURA. Guardado, e nao
    -- recalculado depois, porque velocidade e uma foto: recalcular amanha
    -- com o mesmo numero de views daria outra resposta.
    hours_since_published REAL,

    views          BIGINT,     -- o Instagram vem removendo a contagem publica
    likes          BIGINT,
    comments_count BIGINT,
    shares         BIGINT,     -- NAO e publico. Fica NULL ate prova em contrario.
    saves          BIGINT,     -- idem
    plays          BIGINT,

    job_id         BIGINT,
    CONSTRAINT content_metric_snapshots_unique UNIQUE (content_id, collected_at)
);

CREATE INDEX IF NOT EXISTS content_metric_snapshots_idx
    ON content_metric_snapshots (content_id, collected_at DESC);


-- =========================================================== 5. COMMENTS

-- Camada de enriquecimento CARA: na Apify, 1 comentario = 1 resultado cobrado.
-- 20 comentarios em 100 posts = 2.000 resultados = US$ 5,40 = o credito
-- gratuito de um mes inteiro. A coleta e disparada por regra de selecao,
-- nunca automaticamente para todo conteudo.
CREATE TABLE IF NOT EXISTS comments (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    content_id          BIGINT      NOT NULL REFERENCES contents(id) ON DELETE CASCADE,
    platform_comment_id TEXT,
    parent_comment_id   BIGINT      REFERENCES comments(id) ON DELETE CASCADE,
    username            TEXT,
    comment_text        TEXT,
    likes               BIGINT,
    reply_count         BIGINT,     -- aninhamento e recurso de plano pago na Apify
    published_at        TIMESTAMPTZ,
    collected_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_data            JSONB
);

CREATE UNIQUE INDEX IF NOT EXISTS comments_platform_id_key
    ON comments (content_id, platform_comment_id)
    WHERE platform_comment_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS comments_content_idx ON comments (content_id);


-- ======================================================= 6. MEDIA ASSETS

-- Arquivo grande NUNCA entra no banco. Aqui ficam so metadado e referencia.
CREATE TABLE IF NOT EXISTS media_assets (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    content_id       BIGINT      NOT NULL REFERENCES contents(id) ON DELETE CASCADE,
    asset_type       TEXT        NOT NULL CHECK (asset_type IN
                        ('video', 'thumbnail', 'audio', 'transcript', 'subtitle', 'edit')),
    storage_provider TEXT        NOT NULL DEFAULT 'local'
                        CHECK (storage_provider IN ('local', 's3', 'r2', 'gcs')),
    storage_key      TEXT        NOT NULL,
    storage_url      TEXT,
    mime_type        TEXT,
    file_size        BIGINT,
    duration_seconds REAL,
    checksum         TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Um conteudo tem no maximo um asset de cada tipo por provedor. E o que
    -- torna o download idempotente sem consultar o disco.
    CONSTRAINT media_assets_unique UNIQUE (content_id, asset_type, storage_provider)
);

CREATE INDEX IF NOT EXISTS media_assets_content_idx ON media_assets (content_id);


-- ================================================== 7. ANALYSES (IA)

-- `analysis_version` e `model` existem para permitir reprocessar quando o
-- prompt ou o modelo mudarem — sem isso, nao ha como saber qual analise veio
-- de qual regra.
CREATE TABLE IF NOT EXISTS content_analyses (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    content_id       BIGINT      NOT NULL REFERENCES contents(id) ON DELETE CASCADE,
    analysis_version TEXT        NOT NULL,
    model            TEXT        NOT NULL,
    analysis         JSONB       NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT content_analyses_unique UNIQUE (content_id, analysis_version, model)
);

CREATE INDEX IF NOT EXISTS content_analyses_gin ON content_analyses USING gin (analysis);

CREATE TABLE IF NOT EXISTS comment_analyses (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    content_id       BIGINT      NOT NULL REFERENCES contents(id) ON DELETE CASCADE,
    analysis_version TEXT        NOT NULL,
    model            TEXT        NOT NULL,
    analysis         JSONB       NOT NULL,
    comments_sampled INTEGER,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT comment_analyses_unique UNIQUE (content_id, analysis_version, model)
);

CREATE INDEX IF NOT EXISTS comment_analyses_gin ON comment_analyses USING gin (analysis);


-- ========================================================= 8. EMBEDDINGS

-- Desvio 2: `real[]` agora, `vector(N)` quando o pgvector entrar. A troca e
-- um ALTER, e ate la nenhum embedding sera gerado.
CREATE TABLE IF NOT EXISTS embeddings (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_type  TEXT        NOT NULL CHECK (entity_type IN
                    ('caption', 'transcript', 'comments', 'content_analysis')),
    entity_id    BIGINT      NOT NULL,
    content_text TEXT,
    embedding    REAL[],
    dimensions   INTEGER,
    model        TEXT        NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT embeddings_unique UNIQUE (entity_type, entity_id, model)
);


-- =================================================== 9. COLLECTION JOBS

CREATE TABLE IF NOT EXISTS collection_jobs (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_type      TEXT        NOT NULL CHECK (job_type IN
                     ('profile_discovery', 'content_collection',
                      'comment_collection', 'metric_refresh')),
    source        TEXT        NOT NULL,
    source_actor  TEXT,
    raw_run_id    TEXT,
    niche_id      BIGINT      REFERENCES niches(id)   ON DELETE SET NULL,
    profile_id    BIGINT      REFERENCES profiles(id) ON DELETE SET NULL,
    status        TEXT        NOT NULL DEFAULT 'running'
                     CHECK (status IN ('running', 'succeeded', 'failed', 'aborted')),
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    items_found   INTEGER     NOT NULL DEFAULT 0,
    items_created INTEGER     NOT NULL DEFAULT 0,
    items_updated INTEGER     NOT NULL DEFAULT 0,
    error         TEXT
);

CREATE INDEX IF NOT EXISTS collection_jobs_started_idx ON collection_jobs (started_at DESC);


-- =================================================== 10. PROCESSING JOBS

-- Uma mecanica para todas as etapas caras. Substitui a ideia de uma tabela de
-- fila por etapa: download, transcricao, analise e embedding sao o mesmo
-- problema com `job_type` diferente.
--
-- ESTA TABELA E A FILA. Nao ha broker: `status='queued'` e quem espera vez.
CREATE TABLE IF NOT EXISTS processing_jobs (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_type     TEXT        NOT NULL CHECK (job_type IN
                    ('video_download', 'transcription', 'video_analysis',
                     'comment_analysis', 'embedding_generation', 'video_edit')),
    entity_type  TEXT        NOT NULL DEFAULT 'content',
    entity_id    BIGINT      NOT NULL,
    status       TEXT        NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued', 'running', 'done', 'failed', 'skipped')),
    priority     INTEGER     NOT NULL DEFAULT 100,
    attempts     INTEGER     NOT NULL DEFAULT 0,
    max_attempts INTEGER     NOT NULL DEFAULT 3,
    started_at   TIMESTAMPTZ,
    finished_at  TIMESTAMPTZ,
    duration_ms  BIGINT,
    error        TEXT,
    payload      JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Idempotencia da fila: um job por (tipo, entidade). Rodar o pipeline
    -- duas vezes nao enfileira o mesmo download duas vezes.
    CONSTRAINT processing_jobs_unique UNIQUE (job_type, entity_type, entity_id)
);

-- O indice que a fila usa em toda leitura: menor prioridade primeiro, mais
-- antigo antes. Parcial, porque so `queued` interessa para desempilhar.
CREATE INDEX IF NOT EXISTS processing_jobs_queue_idx
    ON processing_jobs (job_type, priority, created_at)
    WHERE status = 'queued';


-- ======================================================= 11. DATA COSTS

-- Observabilidade economica. Cada operacao que consome recurso externo deixa
-- registro — e o que torna o funil do §18 mensuravel em vez de intencao.
CREATE TABLE IF NOT EXISTS data_costs (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    collection_job_id BIGINT  REFERENCES collection_jobs(id) ON DELETE SET NULL,
    processing_job_id BIGINT  REFERENCES processing_jobs(id) ON DELETE SET NULL,
    entity_type   TEXT,
    entity_id     BIGINT,
    operation     TEXT        NOT NULL CHECK (operation IN
                     ('profile_collection', 'content_collection',
                      'comment_collection', 'metric_refresh', 'video_download',
                      'transcription', 'llm_analysis', 'embedding', 'storage')),
    provider      TEXT        NOT NULL,
    resource_type TEXT,
    quantity      NUMERIC(18, 4) NOT NULL DEFAULT 0,
    unit_cost     NUMERIC(18, 8),
    total_cost    NUMERIC(18, 8),
    currency      TEXT        NOT NULL DEFAULT 'USD',

    -- 1 coleta primaria · 2 processamento derivado · 3 enriquecimento
    -- 4 IA / analise profunda
    cost_level    SMALLINT    NOT NULL CHECK (cost_level BETWEEN 1 AND 4),

    is_estimate   BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS data_costs_level_idx   ON data_costs (cost_level, created_at DESC);
CREATE INDEX IF NOT EXISTS data_costs_created_idx ON data_costs (created_at DESC);


-- ============================================================== TRIGGERS

DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['niches', 'profiles', 'contents', 'processing_jobs']
    LOOP
        EXECUTE format(
            'DROP TRIGGER IF EXISTS %I_touch ON %I; '
            'CREATE TRIGGER %I_touch BEFORE UPDATE ON %I '
            'FOR EACH ROW EXECUTE FUNCTION touch_updated_at()',
            t, t, t, t);
    END LOOP;
END $$;


INSERT INTO schema_migrations (version) VALUES ('001_intelligence')
ON CONFLICT (version) DO NOTHING;

COMMIT;
