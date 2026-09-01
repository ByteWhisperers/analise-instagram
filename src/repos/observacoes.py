"""O que foi observado, sem nunca apagar o que já se tinha observado.

`niche_terms` (migration 005) guarda o vocabulário **julgado** de um nicho:
uma linha por termo, com `is_approved`, sobrescrita a cada remapeamento. Aqui
é o contrário e de propósito: `term_observations` é append-only e não tem
coluna de aprovação.

As duas perguntas que só esta tabela responde:

- **"Esse termo é raro FORA desta tribo?"** — a exclusividade precisa de um
  denominador, e denominador é corpus de fundo. Toda observação de todo nicho
  já mapeado entra nele.
- **"O vocabulário mudou?"** — a linguagem de uma tribo é dinâmica, e é o
  movimento que interessa. Linha sobrescrita não tem passado.

**A fronteira de idioma mora aqui**, como em todo repositório: o Python fala
`"?"` para "não sei" (é o que `lexico.contar` produz), o banco fala `NULL`. A
tradução é nos dois sentidos e não vaza para fora deste módulo.
"""

from ._comum import dicts, exigir

COLUNAS = ("id", "job_id", "niche_id", "term", "kind", "profile_username",
           "content_platform_id", "occurrences", "language", "source",
           "observed_at")

# A mesma lista fechada de `lexico.KINDS` e do CHECK da tabela. Repetida aqui
# porque o repositório é a fronteira: rejeitar antes de ir ao banco dá erro
# nomeado em vez de violação de CHECK crua.
KINDS = ("hashtag", "palavra", "bigrama", "emoji", "mencao")


def _idioma_para_banco(valor):
    """`"?"` e qualquer coisa que não seja pt/es viram NULL.

    NULL é "não sei", e é diferente de "não é português". A distinção é a
    mesma de `idioma.detectar()` e é o que impede o filtro de matar tag
    legítima calado.
    """
    return valor if valor in ("pt", "es") else None


def _agrupar(lista):
    """Observações soltas -> uma linha por (termo, kind, perfil, post).

    `lexico.observacoes()` devolve uma OCORRÊNCIA por vez, porque a frequência
    dentro do post é sinal. Gravar uma linha por ocorrência diria o mesmo
    gastando mais — a contagem vira a coluna `occurrences`.
    """
    agrupado = {}
    for obs in (lista or []):
        chave = (obs["termo"], obs["kind"], obs.get("perfil"),
                 obs.get("post"), _idioma_para_banco(obs.get("idioma")),
                 obs.get("fonte"))
        agrupado[chave] = agrupado.get(chave, 0) + 1
    return agrupado


def gravar(conexao, lista, job_id=None, niche_id=None):
    """Acrescenta observações. Devolve quantas linhas entraram.

    `niche_id=None` é o caso normal de uma rodada seca: o `mapear` grava
    observação mesmo sem `--aplicar`, porque dinheiro gasto vira dado mesmo
    quando o dossiê é descartado. Sem nicho a linha continua servindo de corpus
    de fundo — e o fundo é justamente o que não pertence a tribo nenhuma.
    """
    agrupado = _agrupar(lista)
    if not agrupado:
        return 0

    for (_, kind, _, _, _, _) in agrupado:
        if kind not in KINDS:
            raise ValueError(
                "kind %r não existe. Os válidos são: %s. Tipo novo é "
                "migration, não descuido." % (kind, ", ".join(KINDS)))

    linhas = [(job_id, niche_id, termo, kind, perfil, post, quantas,
               lingua, fonte)
              for (termo, kind, perfil, post, lingua, fonte), quantas
              in agrupado.items()]

    with conexao.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO term_observations
                (job_id, niche_id, term, kind, profile_username,
                 content_platform_id, occurrences, language, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, linhas)
    return len(linhas)


def contagens(conexao, job_id=None, niche_id=None, kinds=None):
    """Reconstrói `{termo: {posts, perfis, idiomas, fonte, kind}}` do banco.

    **É esta função que torna a re-análise gratuita.** Com ela, mudar fórmula,
    limiar ou agrupamento é consulta — não chamada nova ao Actor. Mesmo
    princípio já registrado na 005 ("re-ranquear sem remapear"), agora valendo
    para o grafo e para a assinatura, e não só para o ranking.

    Devolve a MESMA forma que `lexico.contar()` e que `coletor.tags_dos_itens()`
    sempre devolveram, para `mapeador.fundir_contagens` e
    `mapeador.ranquear_termos` continuarem valendo sem tradução no meio.
    """
    onde, parametros = [], []
    if job_id is not None:
        onde.append("job_id = %s")
        parametros.append(job_id)
    if niche_id is not None:
        onde.append("niche_id = %s")
        parametros.append(niche_id)
    if kinds:
        onde.append("kind = ANY(%s)")
        parametros.append(list(kinds))

    sql = """
        SELECT term, kind,
               sum(occurrences)                          AS posts,
               array_agg(DISTINCT profile_username)
                   FILTER (WHERE profile_username IS NOT NULL) AS perfis,
               count(*) FILTER (WHERE language = 'pt')   AS pt,
               count(*) FILTER (WHERE language = 'es')   AS es,
               count(*) FILTER (WHERE language IS NULL)  AS indefinido,
               min(source)                               AS fonte
        FROM term_observations
    """
    if onde:
        sql += " WHERE " + " AND ".join(onde)
    sql += " GROUP BY term, kind"

    achado = {}
    for linha in conexao.execute(sql, tuple(parametros)).fetchall():
        termo, kind, posts, perfis, pt, es, indefinido, fonte = linha
        achado[termo] = {
            "posts": int(posts or 0),
            "perfis": sorted(perfis or []),
            "idiomas": {"pt": int(pt or 0), "es": int(es or 0),
                        "?": int(indefinido or 0)},
            "fonte": fonte,
            "kind": kind,
        }
    return achado


def fundo(conexao, kinds=None, excluir_job_id=None):
    """O corpus de fundo: em quantos perfis distintos cada termo já apareceu.

    É o denominador de `P(termo | fora da tribo)`. Devolve
    `(por_termo, total_de_perfis)` — o total vem junto porque uma contagem sem
    o universo que a produziu é chute com cara de medição, e sem ele não há
    como transformar contagem em probabilidade.

    `excluir_job_id` tira a própria rodada da conta. Sem isso, o termo que só
    esta rodada viu apareceria como "comum no mundo" por causa dela mesma, e a
    exclusividade se mediria contra si própria.
    """
    onde, parametros = ["profile_username IS NOT NULL"], []
    if kinds:
        onde.append("kind = ANY(%s)")
        parametros.append(list(kinds))
    if excluir_job_id is not None:
        onde.append("(job_id IS DISTINCT FROM %s)")
        parametros.append(excluir_job_id)

    filtro = " WHERE " + " AND ".join(onde)

    por_termo = {
        termo: int(quantos)
        for termo, quantos in conexao.execute(
            "SELECT term, count(DISTINCT profile_username) "
            "FROM term_observations" + filtro + " GROUP BY term",
            tuple(parametros)).fetchall()
    }

    linha = conexao.execute(
        "SELECT count(DISTINCT profile_username) "
        "FROM term_observations" + filtro, tuple(parametros)).fetchone()

    return por_termo, int(linha[0] if linha else 0)


def serie(conexao, termo, niche_id=None, kind="hashtag"):
    """O termo ao longo do tempo: por dia, quantos perfis o usaram.

    A pergunta que a 005 não podia responder. Serve para ver a gíria nascendo
    e a tag morrendo — e é por isso que a tabela é append-only.
    """
    exigir(termo, "termo")

    onde = ["term = %s", "kind = %s"]
    parametros = [termo, kind]
    if niche_id is not None:
        onde.append("niche_id = %s")
        parametros.append(niche_id)

    cursor = conexao.execute(
        "SELECT date_trunc('day', observed_at) AS dia, "
        "       count(DISTINCT profile_username) AS perfis, "
        "       sum(occurrences) AS posts "
        "FROM term_observations WHERE " + " AND ".join(onde) +
        " GROUP BY dia ORDER BY dia", tuple(parametros))

    return dicts(cursor, ("dia", "perfis", "posts"))


def perfis_por_termo(conexao, job_id=None, niche_id=None, kinds=None,
                     minimo_de_perfis=1):
    """`{termo: {perfis}}` — a matéria-prima do grafo de co-ocorrência.

    Conjunto e não lista: o peso entre dois termos é Jaccard sobre os perfis
    que usam ambos, e Jaccard é operação de conjunto. Montar aqui poupa a Fase
    2 de reconverter.

    `minimo_de_perfis` corta a cauda de termo visto uma vez só. Numa amostra
    pequena essa cauda é a maior parte das linhas e não sustenta estatística
    nenhuma — mas o padrão é 1 porque quem decide o corte é quem chama, com o
    tamanho da amostra na mão.
    """
    return {linha["termo"]: set(linha["perfis"])
            for linha in _perfis_crus(conexao, job_id, niche_id, kinds)
            if len(linha["perfis"]) >= minimo_de_perfis}


def _perfis_crus(conexao, job_id, niche_id, kinds):
    onde, parametros = ["profile_username IS NOT NULL"], []
    if job_id is not None:
        onde.append("job_id = %s")
        parametros.append(job_id)
    if niche_id is not None:
        onde.append("niche_id = %s")
        parametros.append(niche_id)
    if kinds:
        onde.append("kind = ANY(%s)")
        parametros.append(list(kinds))

    cursor = conexao.execute(
        "SELECT term, array_agg(DISTINCT profile_username) "
        "FROM term_observations WHERE " + " AND ".join(onde) +
        " GROUP BY term", tuple(parametros))
    return dicts(cursor, ("termo", "perfis"))


def apagar_rodada(conexao, job_id):
    """Descarta uma rodada inteira. Devolve quantas linhas saíram.

    Append-only não quer dizer imutável para sempre: uma rodada que se
    descobriu envenenada (a semente errada, o cluster errado) precisa poder
    sair do corpus de fundo, senão ela contamina toda exclusividade calculada
    depois. O que não pode é a rodada NOVA apagar a antiga por descuido — e é
    isso que a ausência de UNIQUE garante.
    """
    exigir(job_id, "job_id")
    cursor = conexao.execute(
        "DELETE FROM term_observations WHERE job_id = %s", (job_id,))
    return cursor.rowcount
