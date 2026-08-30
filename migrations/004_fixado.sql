-- =============================================================================
-- 004 — Post fixado deixa de se passar por post recente
--
-- MEDIDO EM 30/08/2026, contra o Actor de verdade. Pedindo os reels de
-- @receitasdepai com `onlyPostsNewerThan: "30 days"` — que o Actor converteu
-- corretamente para 2026-07-31 — vieram quatro itens, e DOIS estavam fora da
-- janela:
--
--     data         isPinned   views
--     2024-10-09   true       6.960.164
--     2026-04-18   true       3.348.237
--     2026-08-28   false        953.973
--     2026-08-25   false        351.405
--
-- Os dois que vazaram são exatamente os dois fixados. A documentação do Actor
-- avisa: "pinned posts may still appear even with this filter set".
--
-- POR QUE MARCAR E NÃO DESCARTAR: o post fixado é a vitrine que o próprio dono
-- escolheu — é ele dizendo qual acha que é o melhor dele. Como dado, vale
-- muito. O que não pode é entrar numa conta de "desempenho dos últimos 30
-- dias" fingindo ter 30 dias, porque um post de 2024 com 6,9M de views
-- distorce qualquer mediana de janela.
--
-- NULL é honesto e é o padrão: nas linhas coletadas antes desta migration não
-- se sabe se o post era fixado. `false` seria afirmar que não era.
-- =============================================================================

BEGIN;

ALTER TABLE contents ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN;

COMMENT ON COLUMN contents.is_pinned IS
    'Post fixado no topo do perfil. Escapa do filtro de data do Actor, entao '
    'nao pode entrar em conta de janela sem ser separado. NULL = nao se sabe.';

-- Parcial: só interessa achar os fixados, que são poucos (no máximo 3 por
-- perfil). Índice sobre a coluna inteira seria pagar por 97% de linhas que
-- ninguém procura por esse critério.
CREATE INDEX IF NOT EXISTS contents_pinned_idx ON contents (profile_id)
    WHERE is_pinned IS TRUE;

-- A view ganha a coluna NO FIM, e não ao lado de `content_type` onde ela faria
-- mais sentido para quem lê: `CREATE OR REPLACE VIEW` só aceita acrescentar
-- coluna no final. Trocar a ordem exigiria DROP, e DROP derrubaria qualquer
-- coisa que dependa da view.
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
    END AS engagement_base,

    c.is_pinned

FROM contents c
JOIN profiles p ON p.id = c.profile_id
LEFT JOIN LATERAL (
    SELECT * FROM content_metric_snapshots m
    WHERE m.content_id = c.id
    ORDER BY m.collected_at DESC
    LIMIT 1
) s ON TRUE;

INSERT INTO schema_migrations (version) VALUES ('004_fixado')
ON CONFLICT (version) DO NOTHING;

COMMIT;
