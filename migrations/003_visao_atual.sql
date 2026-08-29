-- =============================================================================
-- 003 — A visão "estado atual de cada conteúdo"
--
-- Seis das consultas do projeto precisam da mesma coisa: o conteúdo, o dono e
-- a LEITURA MAIS RECENTE das métricas dele. Escrever esse `DISTINCT ON` seis
-- vezes seria seis lugares para errar quando a regra mudar.
--
-- A view não guarda nada: é a consulta com nome. Métrica derivada continua
-- sendo calculada na leitura, como combinado — o que muda é só não repetir o
-- SQL.
--
-- SOBRE O ENGAJAMENTO: a base fica declarada numa coluna ao lado.
-- 4% sobre views e 4% sobre seguidores não são a mesma coisa, e comparar os
-- dois lado a lado sem saber qual é qual seria erro. Quando o Instagram não
-- publica as views — e ele vem escondendo —, a conta cai para seguidores e
-- `engagement_base` diz isso em voz alta.
-- =============================================================================

BEGIN;

CREATE OR REPLACE VIEW v_content_current AS
SELECT
    c.id                    AS content_id,
    c.platform_content_id   AS code,
    c.content_url,
    c.content_type,
    c.caption,
    c.published_at,
    c.duration_seconds,
    c.audio_id,
    c.audio_title,
    c.location_name,

    p.id                    AS profile_id,
    p.username,
    p.followers,
    p.is_approved,

    s.collected_at          AS measured_at,
    s.hours_since_published,
    s.views,
    s.likes,
    s.comments_count,
    s.shares,
    s.saves,

    -- Horas desde a publicação ATÉ AGORA (não até a medição). É o que a
    -- velocidade de leitura usa.
    EXTRACT(EPOCH FROM (now() - c.published_at)) / 3600.0 AS hours_old,

    CASE
        WHEN COALESCE(s.views, 0) > 0
            THEN (COALESCE(s.likes, 0) + COALESCE(s.comments_count, 0))::numeric
                 / s.views
        WHEN COALESCE(p.followers, 0) > 0
            THEN (COALESCE(s.likes, 0) + COALESCE(s.comments_count, 0))::numeric
                 / p.followers
    END AS engagement,

    CASE
        WHEN COALESCE(s.views, 0) > 0     THEN 'views'
        WHEN COALESCE(p.followers, 0) > 0 THEN 'followers'
    END AS engagement_base

FROM contents c
JOIN profiles p ON p.id = c.profile_id
LEFT JOIN LATERAL (
    -- A leitura mais recente daquele conteúdo. `LATERAL` em vez de
    -- `DISTINCT ON` na consulta inteira porque assim o índice
    -- (content_id, collected_at DESC) é usado uma vez por linha.
    SELECT * FROM content_metric_snapshots m
    WHERE m.content_id = c.id
    ORDER BY m.collected_at DESC
    LIMIT 1
) s ON TRUE;


INSERT INTO schema_migrations (version) VALUES ('003_visao_atual')
ON CONFLICT (version) DO NOTHING;

COMMIT;
