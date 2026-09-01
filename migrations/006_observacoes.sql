-- =============================================================================
-- 006 — A observação deixa de ser descartada
--
-- A 005 deu ao nicho o vocabulário que foi APRENDIDO sobre ele, em
-- `niche_terms`. Ela resolveu o resultado, e não a evidência bruta: a chave é
-- `UNIQUE (niche_id, term, kind)`, uma linha por termo, para sempre. Remapear
-- **sobrescreve** `profiles_count`.
--
-- Isso deixa duas perguntas sem resposta possível, e as duas são centrais:
--
--   1. "Esse termo é raro FORA desta tribo?" — a exclusividade
--      `P(termo | tribo) / P(termo | fora)` precisa de um denominador, e
--      denominador é um corpus de fundo. Uma linha por termo por nicho não é
--      corpus: é o resultado já digerido, sem o de onde veio.
--
--   2. "O vocabulário deste nicho mudou?" — a linguagem de uma tribo é
--      dinâmica, e é justamente o movimento dela que interessa. Uma linha que
--      é sobrescrita não tem passado.
--
-- O que muda: nasce `term_observations`, **append-only**. Cada rodada acrescenta
-- o que viu e não apaga o que estava lá. É o corpus de fundo (pergunta 1) e é a
-- série temporal (pergunta 2), com a mesma tabela.
--
-- MEDIÇÃO E JULGAMENTO CONTINUAM SEPARADOS. `niche_terms` fica exatamente como
-- está, na função que a 005 lhe deu: a camada do julgamento humano
-- (`is_approved`). Aqui não há coluna de aprovação de propósito — observação é
-- o que foi visto, não o que foi aceito, e misturar as duas faria remapear
-- apagar decisão sua.
--
-- POR QUE NÃO GUARDAR O ITEM CRU INTEIRO: um JSONB por post daria re-análise
-- ainda mais livre, mas a máquina tem ~900 MB livres na prática e o blob não se
-- paga. A observação tipada é o que todas as fases seguintes consomem; o item
-- cru só serviria para colher um campo que ainda não sabemos que queremos.
-- Se um dia for preciso, a decisão volta à mesa com um custo medido na mão.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Uma linha por (termo, post). `occurrences` guarda quantas vezes o termo
-- apareceu NAQUELE post — repetir a linha três vezes diria o mesmo gastando
-- três vezes mais, e a frequência dentro do post é sinal (quem repete `grau`
-- quatro vezes na legenda está dizendo algo diferente de quem diz uma).
--
-- **Sem UNIQUE, e isso é a decisão.** Chave única aqui recriaria exatamente o
-- problema que esta migration existe para resolver: forçaria o UPDATE e mataria
-- o passado. O que separa uma rodada da outra é `job_id`.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS term_observations (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Qual rodada viu isto. É por aqui que se responde "o que mudou entre a
    -- rodada de agosto e a de outubro", e também o que permite descartar uma
    -- rodada inteira que se descobriu envenenada.
    job_id          BIGINT      REFERENCES collection_jobs(id) ON DELETE SET NULL,

    -- NULL enquanto a rodada é seca. O `mapear` grava observação mesmo sem
    -- `--aplicar`: dinheiro gasto vira dado, mesmo quando o dossiê é
    -- descartado. Sem nicho, a linha ainda serve de corpus de fundo — e o
    -- fundo é justamente o que não pertence a nenhuma tribo em particular.
    niche_id        BIGINT      REFERENCES niches(id) ON DELETE SET NULL,

    term            TEXT        NOT NULL,

    -- Fechado de propósito. Tipo novo é migration, não descuido no meio de um
    -- laço. Espelha `lexico.KINDS`.
    kind            TEXT        NOT NULL
                        CHECK (kind IN ('hashtag', 'palavra', 'bigrama',
                                        'emoji', 'mencao')),

    -- Quem falou e onde. `profile_username` é TEXT e não FK: a observação
    -- nasce antes de o perfil existir em `profiles` (a aba da tag entrega nome,
    -- não cadastro), e exigir a FK obrigaria a gravar perfil que talvez nunca
    -- seja coletado.
    profile_username    TEXT,
    content_platform_id TEXT,

    occurrences     INTEGER     NOT NULL DEFAULT 1 CHECK (occurrences > 0),

    -- 'pt', 'es' ou **NULL para "não sei"**. O terceiro estado é o mesmo de
    -- `idioma.detectar()`: legenda curta muitas vezes não tem sinal nenhum, e
    -- NULL diz isso. 'es' por ausência de sinal português seria mentira.
    language        TEXT        CHECK (language IN ('pt', 'es')),

    -- A porta por onde se chegou: '#desastres', 'relacionados'. É o que
    -- permite perguntar depois se um cluster inteiro veio de uma semente só.
    source          TEXT,

    observed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- O corpus de fundo: "em quantos perfis distintos este termo aparece, no
-- mundo todo que já observamos". É o denominador da exclusividade, e é a
-- consulta mais quente da Fase 3.
CREATE INDEX IF NOT EXISTS term_observations_termo_idx
    ON term_observations (term, kind);

-- A série temporal de um nicho.
CREATE INDEX IF NOT EXISTS term_observations_nicho_idx
    ON term_observations (niche_id, observed_at DESC)
    WHERE niche_id IS NOT NULL;

-- A assinatura de um perfil: tudo que ele falou.
CREATE INDEX IF NOT EXISTS term_observations_perfil_idx
    ON term_observations (profile_username)
    WHERE profile_username IS NOT NULL;

-- O que uma rodada produziu, para conferência e para descarte.
CREATE INDEX IF NOT EXISTS term_observations_job_idx
    ON term_observations (job_id);

COMMENT ON TABLE term_observations IS
    'Append-only: cada rodada acrescenta o que viu e nunca apaga o que estava. '
    'E o corpus de fundo da exclusividade e a serie temporal do vocabulario. '
    'Julgamento humano nao mora aqui — mora em niche_terms.is_approved.';

COMMENT ON COLUMN term_observations.occurrences IS
    'Quantas vezes o termo apareceu NAQUELE post. Frequencia dentro do post e '
    'sinal, e repetir a linha diria o mesmo gastando mais.';

INSERT INTO schema_migrations (version) VALUES ('006_observacoes')
ON CONFLICT (version) DO NOTHING;

COMMIT;
