"""Perfis públicos, o vínculo com nichos e a série temporal de seguidores.

Traduz o dicionário em português que `coletor.py` produz para as colunas em
inglês do banco. Nenhum outro módulo faz essa tradução.

Três coisas que esta camada garante, e que valem mais que o resto do arquivo:

1. **Recoletar não apaga julgamento.** `salvar()` nunca toca em `is_approved`,
   `relevance` nem `classified_at` — quem mexe neles é `classificar()`.
2. **Recoletar não apaga dado que sumiu.** Todo campo entra por `COALESCE`:
   se a fonte não trouxe a bio nesta rodada, a bio anterior fica.
3. **Seguidores viram história.** `gravar_snapshot()` é o que torna
   crescimento calculável; a coluna `followers` é só o valor de agora.
"""

import json

from ._comum import booleano, dicts, exigir, id_de

PLATAFORMA_PADRAO = "instagram"

COLUNAS = ("id", "platform", "platform_profile_id", "username", "profile_url",
           "display_name", "bio", "followers", "following", "content_count",
           "is_verified", "is_private", "category", "avatar_url",
           "external_url", "language", "is_approved", "relevance",
           "classified_at", "source", "source_actor", "source_run_id",
           "first_seen_at", "last_seen_at")


def salvar(conexao, perfil, plataforma=PLATAFORMA_PADRAO, fonte=None,
           ator=None, run_id=None, guardar_bruto=None):
    """Insere ou atualiza pelo par (plataforma, usuário). Devolve o id.

    `guardar_bruto` é o JSON cru da fonte. Guardá-lo é o que permite
    reprocessar de graça quando o mapeamento de campos estiver errado — em
    vez de pagar a coleta de novo.
    """
    usuario = exigir(perfil.get("usuario"), "usuario")

    cursor = conexao.execute(
        """
        INSERT INTO profiles (
            platform, platform_profile_id, username, profile_url,
            display_name, bio, followers, following, content_count,
            is_verified, is_private, category, avatar_url, external_url,
            source, source_actor, source_run_id, raw_data, last_seen_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, now())
        ON CONFLICT (platform, username) DO UPDATE SET
            platform_profile_id = COALESCE(EXCLUDED.platform_profile_id,
                                           profiles.platform_profile_id),
            profile_url   = COALESCE(EXCLUDED.profile_url,   profiles.profile_url),
            display_name  = COALESCE(EXCLUDED.display_name,  profiles.display_name),
            bio           = COALESCE(EXCLUDED.bio,           profiles.bio),
            followers     = COALESCE(EXCLUDED.followers,     profiles.followers),
            following     = COALESCE(EXCLUDED.following,     profiles.following),
            content_count = COALESCE(EXCLUDED.content_count, profiles.content_count),
            is_verified   = COALESCE(EXCLUDED.is_verified,   profiles.is_verified),
            is_private    = COALESCE(EXCLUDED.is_private,    profiles.is_private),
            category      = COALESCE(EXCLUDED.category,      profiles.category),
            avatar_url    = COALESCE(EXCLUDED.avatar_url,    profiles.avatar_url),
            external_url  = COALESCE(EXCLUDED.external_url,  profiles.external_url),
            source        = COALESCE(EXCLUDED.source,        profiles.source),
            source_actor  = COALESCE(EXCLUDED.source_actor,  profiles.source_actor),
            source_run_id = COALESCE(EXCLUDED.source_run_id, profiles.source_run_id),
            raw_data      = COALESCE(EXCLUDED.raw_data,      profiles.raw_data),
            last_seen_at  = now()
        RETURNING id
        """,
        (plataforma,
         perfil.get("perfil_id"),
         usuario,
         perfil.get("link_perfil"),
         perfil.get("nome"),
         perfil.get("bio"),
         perfil.get("seguidores"),
         perfil.get("seguindo"),
         perfil.get("posts"),
         booleano(perfil.get("verificado")),
         booleano(perfil.get("privado")),
         perfil.get("categoria_negocio"),
         perfil.get("avatar_url"),
         perfil.get("link_externo"),
         fonte, ator, run_id,
         json.dumps(guardar_bruto, ensure_ascii=False) if guardar_bruto else None))

    return id_de(cursor)


def ligar_ao_nicho(conexao, perfil_id, nicho_id, origem=None):
    """Muitos para muitos: um perfil pode servir a vários nichos.

    Devolve True se o vínculo nasceu agora, False se já existia.
    """
    cursor = conexao.execute(
        """
        INSERT INTO niche_profiles (niche_id, profile_id, source)
        VALUES (%s, %s, %s)
        ON CONFLICT (niche_id, profile_id) DO NOTHING
        """,
        (nicho_id, perfil_id, origem))
    return cursor.rowcount == 1


def classificar(conexao, perfil_id, categoria=None, relevancia=None,
                aprovado=None):
    """O julgamento humano, gravado com data.

    Separado de `salvar()` de propósito: coletar de novo não pode desfazer
    o que você decidiu sobre o perfil.
    """
    conexao.execute(
        """
        UPDATE profiles SET
            category      = COALESCE(%s, category),
            relevance     = COALESCE(%s, relevance),
            is_approved   = COALESCE(%s, is_approved),
            classified_at = now()
        WHERE id = %s
        """,
        (categoria, relevancia, booleano(aprovado), perfil_id))


def gravar_snapshot(conexao, perfil_id, seguidores=None, seguindo=None,
                    conteudos=None, job_id=None, medido_em=None):
    """Uma foto dos números do perfil.

    **Sem isto, crescimento é impossível:** a coluna `followers` guarda o
    agora e é sobrescrita a cada coleta; crescimento é a diferença entre
    duas leituras, e diferença precisa de duas linhas.

    Duas leituras no mesmo instante não viram duas linhas.
    """
    conexao.execute(
        """
        INSERT INTO profile_snapshots
            (profile_id, collected_at, followers, following, content_count, job_id)
        VALUES (%s, COALESCE(%s, now()), %s, %s, %s, %s)
        ON CONFLICT (profile_id, collected_at) DO UPDATE SET
            followers     = EXCLUDED.followers,
            following     = EXCLUDED.following,
            content_count = EXCLUDED.content_count
        """,
        (perfil_id, medido_em, seguidores, seguindo, conteudos, job_id))


def historico(conexao, perfil_id):
    """As leituras do perfil, da mais velha para a mais nova.

    A saída alimenta `desempenho.crescimento()` direto — por isso as chaves
    são `medido_em` e `seguidores`, e não os nomes das colunas.
    """
    cursor = conexao.execute(
        """
        SELECT collected_at, followers, following, content_count
        FROM profile_snapshots WHERE profile_id = %s ORDER BY collected_at
        """,
        (perfil_id,))
    return [{"medido_em": linha[0].isoformat(), "seguidores": linha[1],
             "seguindo": linha[2], "conteudos": linha[3]}
            for linha in cursor.fetchall()]


def por_usuario(conexao, usuario, plataforma=PLATAFORMA_PADRAO):
    cursor = conexao.execute(
        "SELECT %s FROM profiles WHERE platform = %%s AND username = %%s"
        % ", ".join(COLUNAS), (plataforma, usuario))
    linhas = dicts(cursor, COLUNAS)
    return linhas[0] if linhas else None


def id_por_usuario(conexao, usuario, plataforma=PLATAFORMA_PADRAO):
    linha = conexao.execute(
        "SELECT id FROM profiles WHERE platform = %s AND username = %s",
        (plataforma, usuario)).fetchone()
    return linha[0] if linha else None


def do_nicho(conexao, nicho_id, apenas_aprovados=False, limite=100):
    """Os perfis de um nicho, do maior para o menor."""
    sql = ("SELECT p.%s FROM profiles p "
           "JOIN niche_profiles np ON np.profile_id = p.id "
           "WHERE np.niche_id = %%s" % ", p.".join(COLUNAS))

    if apenas_aprovados:
        sql += " AND p.is_approved IS TRUE"

    sql += " AND p.is_private IS NOT TRUE ORDER BY p.followers DESC NULLS LAST LIMIT %s"

    return dicts(conexao.execute(sql, (nicho_id, limite)), COLUNAS)
