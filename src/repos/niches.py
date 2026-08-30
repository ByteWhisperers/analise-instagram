"""Nichos monitorados.

Um nicho é o ponto de partida do funil: você informa um, e dele saem perfis,
conteúdos e tudo o mais. É a única entidade que nasce de decisão humana e não
de coleta.
"""

from ._comum import dicts, exigir, id_de

COLUNAS = ("id", "name", "description", "keywords", "language", "country",
           "status", "created_at", "updated_at")


def obter_ou_criar(conexao, nome, descricao=None, palavras_chave=None,
                   idioma=None, pais=None):
    """Devolve o id do nicho, criando se ainda não existir.

    Idempotente pelo nome: rodar a descoberta duas vezes com o mesmo termo
    não cria dois nichos. O `DO UPDATE` existe só para o `RETURNING` sempre
    devolver linha — com `DO NOTHING`, um conflito devolveria vazio.
    """
    exigir(nome, "nome")

    cursor = conexao.execute(
        """
        INSERT INTO niches (name, description, keywords, language, country)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (name) DO UPDATE SET
            description = COALESCE(EXCLUDED.description, niches.description),
            keywords    = CASE WHEN cardinality(EXCLUDED.keywords) > 0
                               THEN EXCLUDED.keywords ELSE niches.keywords END,
            language    = COALESCE(EXCLUDED.language, niches.language),
            country     = COALESCE(EXCLUDED.country, niches.country)
        RETURNING id
        """,
        (nome, descricao, list(palavras_chave or []), idioma, pais))

    return id_de(cursor)


def por_nome(conexao, nome):
    """O nicho inteiro, ou None."""
    cursor = conexao.execute(
        "SELECT %s FROM niches WHERE name = %%s" % ", ".join(COLUNAS), (nome,))
    linhas = dicts(cursor, COLUNAS)
    return linhas[0] if linhas else None


def listar(conexao, status="active"):
    """Os nichos, do mais novo para o mais antigo. `status=None` traz todos."""
    sql = "SELECT %s FROM niches" % ", ".join(COLUNAS)
    parametros = ()

    if status:
        sql += " WHERE status = %s"
        parametros = (status,)

    sql += " ORDER BY created_at DESC"
    return dicts(conexao.execute(sql, parametros), COLUNAS)


def mudar_status(conexao, nicho_id, status):
    """`active`, `paused` ou `archived`. Outro valor o CHECK recusa."""
    conexao.execute("UPDATE niches SET status = %s WHERE id = %s",
                    (status, nicho_id))


def contar_perfis(conexao, nicho_id):
    linha = conexao.execute(
        "SELECT count(*) FROM niche_profiles WHERE niche_id = %s",
        (nicho_id,)).fetchone()
    return linha[0]


# ------------------------------------------------- O nicho mapeado (T14)
#
# Ate 30/08/2026 um nicho era um nome e nada mais: `keywords` ficava em `{}` e
# `language`, `country` e `description` em NULL — mesmo com `obter_ou_criar()`
# aceitando os quatro desde sempre. O mapeamento e quem passa a preencher.


def salvar_criterios(conexao, nicho_id, criterios):
    """Os numeros MEDIDOS daquele nicho. Sobrescrevem o global do config.

    JSONB e nao coluna por criterio porque o conjunto ainda vai mudar, e cada
    criterio novo nao pode custar uma migration.
    """
    import json

    exigir(nicho_id, "nicho_id")
    conexao.execute(
        "UPDATE niches SET criteria = %s::jsonb, updated_at = now() "
        "WHERE id = %s",
        (json.dumps(criterios, ensure_ascii=False) if criterios else None,
         nicho_id))


def criterios(conexao, nicho_id):
    """Os criterios do nicho, ou `{}` se ele nunca foi mapeado.

    `{}` e nao None para quem chama poder fazer `.get()` sem checar antes — e
    a ausencia de criterio proprio significa exatamente "use o global".
    """
    linha = conexao.execute("SELECT criteria FROM niches WHERE id = %s",
                            (nicho_id,)).fetchone()
    return (linha[0] if linha and linha[0] else {})


def salvar_termo(conexao, nicho_id, termo, tipo="hashtag", perfis=0, posts=0,
                 fonte=None, aprovado=None):
    """Um termo do vocabulario, com a evidencia que o sustenta.

    Como em `profiles.salvar()`, **recoletar nao apaga julgamento**: o
    `COALESCE` no `is_approved` faz remapear atualizar os numeros sem desfazer
    o que voce ja decidiu sobre aquele termo.
    """
    exigir(nicho_id, "nicho_id")
    termo = (termo or "").strip().lower()
    exigir(termo, "termo")

    cursor = conexao.execute(
        """
        INSERT INTO niche_terms (niche_id, term, kind, profiles_count,
                                 posts_count, source, is_approved)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (niche_id, term, kind) DO UPDATE SET
            profiles_count = EXCLUDED.profiles_count,
            posts_count    = EXCLUDED.posts_count,
            source         = COALESCE(EXCLUDED.source, niche_terms.source),
            is_approved    = COALESCE(EXCLUDED.is_approved,
                                      niche_terms.is_approved),
            updated_at     = now()
        RETURNING id
        """,
        (nicho_id, termo, tipo, perfis, posts, fonte, aprovado))
    return id_de(cursor)


def termos(conexao, nicho_id, tipo=None, apenas_aprovados=False, limite=200):
    """O vocabulario do nicho, do mais forte para o mais fraco.

    Ordena por perfis distintos primeiro — tag que cinco perfis usam vale mais
    que tag que um perfil repetiu vinte vezes. Foi assim que `publi` e
    `MercadoLivre` ficaram no fim da lista de receitas, sem lista negra.
    """
    sql = ["SELECT term, kind, profiles_count, posts_count, source, "
           "is_approved FROM niche_terms WHERE niche_id = %s"]
    parametros = [nicho_id]

    if tipo:
        sql.append("AND kind = %s")
        parametros.append(tipo)
    if apenas_aprovados:
        sql.append("AND is_approved IS TRUE")

    sql.append("ORDER BY profiles_count DESC, posts_count DESC, term LIMIT %s")
    parametros.append(limite)

    cursor = conexao.execute(" ".join(sql), parametros)
    return dicts(cursor, ("termo", "tipo", "perfis", "posts", "fonte",
                          "aprovado"))


def tags_aprovadas(conexao, nicho_id):
    """So as hashtags aprovadas, como lista de string.

    E o que o eixo de hashtag da busca consome: `"apostas"` nao vive em
    `#apostas`, vive em `#tigrinho` e `#cassino`, e quem sabe disso e o
    mapeamento — nao o nome do nicho.
    """
    return [linha["termo"] for linha in
            termos(conexao, nicho_id, tipo="hashtag", apenas_aprovados=True)]
