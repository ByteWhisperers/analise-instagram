-- =============================================================================
-- 005 — O nicho deixa de ser só um nome
--
-- Até aqui `niches` guardava uma linha com `name` e mais nada: `keywords` ficou
-- em `{}` e `language`, `country` e `description` em NULL desde 28/08 — mesmo
-- com `repos/niches.obter_ou_criar()` aceitando os quatro. É a mesma doença que
-- a T13 curou na seção `busca` do config: estrutura que promete e ninguém
-- preenche.
--
-- O que muda: o nicho passa a carregar o que foi APRENDIDO sobre ele. E o que
-- foi aprendido tem duas naturezas, que ficam separadas de propósito:
--
--   `niches.criteria`  — os números daquele nicho (banda, janela, duração).
--                        JSONB porque o conjunto de critérios ainda vai mudar,
--                        e cada mudança não pode custar uma migration.
--   `niche_terms`      — o vocabulário, UMA LINHA POR TERMO, com a evidência
--                        que o sustenta. Não é um array dentro do nicho porque
--                        termo tem número (em quantos perfis apareceu, em
--                        quantos posts) e tem julgamento (`is_approved`), e
--                        isso é linha, não item de lista.
--
-- POR QUE GUARDAR A EVIDÊNCIA, E NÃO SÓ O RESULTADO: com `profiles_count` e
-- `posts_count` na tabela, mudar o critério de corte é uma consulta. Sem eles,
-- seria mapear de novo — e mapear custa dinheiro. Mesmo princípio do score de
-- oportunidade, que é calculado na leitura e nunca gravado como coluna.
--
-- `niches.keywords` continua existindo e passa a ser preenchida com os termos
-- APROVADOS: é o atalho para quem só quer a lista pronta, sem passar pela
-- evidência.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Os dois CHECK são fechados e recusam tipo novo. Uma rodada de mapeamento não
-- é `profile_discovery`: ela não descobre perfil para coletar, ela descobre
-- VOCABULÁRIO. Contabilizar as duas juntas esconderia quanto custa cada uma.
-- ---------------------------------------------------------------------------
ALTER TABLE collection_jobs DROP CONSTRAINT IF EXISTS collection_jobs_job_type_check;
ALTER TABLE collection_jobs ADD  CONSTRAINT collection_jobs_job_type_check
    CHECK (job_type IN ('profile_discovery', 'content_collection',
                        'comment_collection', 'metric_refresh',
                        'niche_mapping'));

ALTER TABLE data_costs DROP CONSTRAINT IF EXISTS data_costs_operation_check;
ALTER TABLE data_costs ADD  CONSTRAINT data_costs_operation_check
    CHECK (operation IN ('profile_collection', 'content_collection',
                         'comment_collection', 'metric_refresh',
                         'video_download', 'transcription', 'llm_analysis',
                         'embedding', 'storage', 'niche_mapping'));


-- ---------------------------------------------------------------------------
-- Os números daquele nicho. NULL enquanto ninguém mapeou — e NULL aqui é a
-- resposta honesta para "qual a banda de seguidores deste nicho?" antes de
-- qualquer medição. Foi exatamente o erro da T13: a banda 10k–500k foi
-- escolhida por intuição, sem uma distribuição na mão.
-- ---------------------------------------------------------------------------
ALTER TABLE niches ADD COLUMN IF NOT EXISTS criteria JSONB;

COMMENT ON COLUMN niches.criteria IS
    'Criterios quantitativos medidos deste nicho (banda de seguidores, janela, '
    'duracao tipica). Sobrescreve o global do config.local.json. NULL = nunca '
    'foi mapeado, e o global vale.';


-- ---------------------------------------------------------------------------
-- O vocabulário, com a conta que o sustenta.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS niche_terms (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    niche_id       BIGINT      NOT NULL REFERENCES niches(id) ON DELETE CASCADE,

    term           TEXT        NOT NULL,
    kind           TEXT        NOT NULL DEFAULT 'hashtag'
                       CHECK (kind IN ('hashtag', 'termo_da_bio',
                                       'termo_proibido')),

    -- A evidencia. `profiles_count` e o numero que MANDA no ranqueamento:
    -- tag que 5 perfis diferentes usam vale mais que tag que 1 perfil repetiu
    -- 20 vezes. Medido em 30/08/2026: colhendo as hashtags de um perfil real
    -- vieram `publi`, `MercadoLivre`, `PagBank` e `AeC440` — vocabulario de
    -- PUBLICIDADE, que so aparece em um perfil e por isso afunda no ranking.
    profiles_count INTEGER     NOT NULL DEFAULT 0,
    posts_count    INTEGER     NOT NULL DEFAULT 0,

    -- De onde o termo veio: a tag-semente, o perfil relacionado, a bio.
    source         TEXT,

    -- Julgamento humano, separado da medicao — mesma regra de
    -- `profiles.is_approved`: remapear NAO pode apagar o que voce decidiu.
    -- NULL = ainda nao julgado, e e diferente de reprovado.
    is_approved    BOOLEAN,

    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT niche_terms_unico UNIQUE (niche_id, term, kind)
);

CREATE INDEX IF NOT EXISTS niche_terms_nicho_idx ON niche_terms (niche_id);

-- Parcial: a consulta que a busca faz o tempo todo e "quais as tags aprovadas
-- deste nicho". Indexar as reprovadas e as nao julgadas seria pagar por linha
-- que essa pergunta nunca le.
CREATE INDEX IF NOT EXISTS niche_terms_aprovados_idx ON niche_terms (niche_id, term)
    WHERE is_approved IS TRUE;

COMMENT ON TABLE niche_terms IS
    'Vocabulario mapeado de cada nicho, com a evidencia. Guardar '
    'profiles_count/posts_count permite re-ranquear sem remapear — e remapear '
    'custa dinheiro.';

INSERT INTO schema_migrations (version) VALUES ('005_mapeamento')
ON CONFLICT (version) DO NOTHING;

COMMIT;
