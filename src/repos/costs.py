"""Observabilidade econômica: quanto cada coisa custou, de verdade.

A regra do funil é *"quanto mais caro for adquirir um dado, maior o sinal
necessário para justificá-lo"*. Isso só é aplicável se o custo for medido —
caso contrário é boa intenção.

`cost_level` é a camada do funil, e é `CHECK`ada pelo banco:

    1  coleta primária      (descobrir perfil, listar conteúdo)
    2  processamento        (baixar vídeo, transcrever)
    3  enriquecimento       (comentários)
    4  IA / análise profunda (LLM, embedding)

O nível existe para responder a pergunta que decide o orçamento: *quanto do
mês foi gasto em coleta barata e quanto foi em enriquecimento caro?*
"""

from decimal import Decimal

from ._comum import exigir, id_de

# Preços publicados pela Apify em 26/08/2026, por 1.000 resultados.
PRECO_APIFY_POR_MIL = {"free": Decimal("2.70"), "starter": Decimal("2.30"),
                       "scale": Decimal("1.90"), "business": Decimal("1.50")}

NIVEL = {
    "profile_collection": 1, "content_collection": 1, "metric_refresh": 1,
    # Mapear e coleta primaria como as outras: gasta na Apify e traz dado cru.
    # O CHECK do banco foi aberto na migration 005; sem esta linha aqui, o
    # comando roda, gasta, e estoura na hora de registrar o que gastou.
    "niche_mapping": 1,
    "video_download": 2, "transcription": 2,
    "comment_collection": 3,
    "llm_analysis": 4, "embedding": 4,
    "storage": 2,
}


def custo_apify(itens, plano="free"):
    """Quanto N resultados devem custar. Estimativa, não fato."""
    preco = PRECO_APIFY_POR_MIL.get(plano, PRECO_APIFY_POR_MIL["free"])
    return (Decimal(itens) * preco / Decimal(1000)).quantize(Decimal("0.00000001"))


def registrar(conexao, operacao, provedor, quantidade, custo_total=None,
              custo_unitario=None, entidade=None, entidade_id=None,
              coleta_id=None, job_id=None, moeda="USD", estimado=False,
              nivel=None):
    """Uma linha por operação que consumiu recurso externo. Devolve o id."""
    exigir(operacao, "operacao")
    exigir(provedor, "provedor")

    if nivel is None:
        nivel = NIVEL.get(operacao)
    if nivel is None:
        from ._comum import ErroDeRepositorio
        raise ErroDeRepositorio(
            "Operação '%s' não tem nível de custo definido. Acrescente em "
            "costs.NIVEL ou passe `nivel=` explicitamente." % operacao)

    if custo_total is None and custo_unitario is not None:
        custo_total = Decimal(str(custo_unitario)) * Decimal(str(quantidade))

    cursor = conexao.execute(
        """
        INSERT INTO data_costs (
            collection_job_id, processing_job_id, entity_type, entity_id,
            operation, provider, quantity, unit_cost, total_cost, currency,
            cost_level, is_estimate)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (coleta_id, job_id, entidade, entidade_id, operacao, provedor,
         quantidade, custo_unitario, custo_total, moeda, nivel, estimado))

    return id_de(cursor)


def total(conexao, desde=None, apenas_reais=False):
    """Quanto já foi gasto, no total e por nível do funil."""
    condicoes, parametros = [], []

    if desde:
        condicoes.append("created_at >= %s")
        parametros.append(desde)
    if apenas_reais:
        condicoes.append("is_estimate = FALSE")

    onde = (" WHERE " + " AND ".join(condicoes)) if condicoes else ""

    geral = conexao.execute(
        "SELECT COALESCE(sum(total_cost), 0), count(*) FROM data_costs" + onde,
        parametros).fetchone()

    por_nivel = {
        linha[0]: {"custo": float(linha[1]), "operacoes": linha[2]}
        for linha in conexao.execute(
            "SELECT cost_level, COALESCE(sum(total_cost), 0), count(*) "
            "FROM data_costs" + onde + " GROUP BY cost_level ORDER BY cost_level",
            parametros)
    }

    return {"total": float(geral[0]), "operacoes": geral[1],
            "por_nivel": por_nivel}


def por_operacao(conexao):
    """O gasto quebrado por tipo de operação, do mais caro para o mais barato."""
    return [
        {"operacao": linha[0], "nivel": linha[1], "custo": float(linha[2]),
         "quantidade": float(linha[3]), "vezes": linha[4]}
        for linha in conexao.execute(
            "SELECT operation, cost_level, COALESCE(sum(total_cost), 0), "
            "       COALESCE(sum(quantity), 0), count(*) "
            "FROM data_costs GROUP BY operation, cost_level "
            "ORDER BY sum(total_cost) DESC NULLS LAST")
    ]


def por_unidade(conexao):
    """As médias que decidem se vale trocar a Apify por infra própria.

    São exatamente as métricas do §10 do pipeline. Devolvem None quando ainda
    não há dado — o que é a resposta honesta, e não zero.
    """
    perfis, conteudos, videos = conexao.execute(
        "SELECT (SELECT count(*) FROM profiles), "
        "       (SELECT count(*) FROM contents), "
        "       (SELECT count(*) FROM media_assets WHERE asset_type = 'video')"
    ).fetchone()

    gasto = float(conexao.execute(
        "SELECT COALESCE(sum(total_cost), 0) FROM data_costs").fetchone()[0])

    def dividir(por):
        return None if not por else round(gasto / por, 6)

    return {
        "gasto_total": round(gasto, 6),
        "perfis": perfis,
        "conteudos": conteudos,
        "videos_baixados": videos,
        "custo_por_perfil": dividir(perfis),
        "custo_por_conteudo": dividir(conteudos),
        "custo_por_video": dividir(videos),
        "conteudos_por_perfil": None if not perfis else round(conteudos / perfis, 2),
    }
