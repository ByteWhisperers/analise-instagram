"""As contas de desempenho: engajamento, velocidade e score de oportunidade.

So funcao pura. Entra numero, sai numero. Nao le arquivo, nao acessa rede, nao
toca no banco — e o que permite conferir cada conta isoladamente, no mesmo
espirito de `metricas.py`.

------------------------------------------------------------------------------
Duas decisoes de metodo que mudam o resultado, declaradas aqui em vez de
escondidas no codigo:

**1. Nada e comparado em valor absoluto.** Cada sinal vira *percentil dentro do
grupo* antes de entrar no score. A pergunta que interessa nao e "qual video tem
mais views", e sim "qual conteudo esta performando anormalmente bem dentro
daquele nicho" — e essa segunda so existe com referencia a um grupo.

**2. Mediana, nao media.** Views de Reels sao uma distribuicao de cauda longa:
um viral sozinho puxa a media e faz todo o resto parecer fraco. A mediana
aguenta o viral sem se deformar, e por isso ela e a referencia aqui.
------------------------------------------------------------------------------
"""

from datetime import datetime, timezone

# Os pesos do score. **Nao sao para ficar fixos** — moram no config e podem ser
# mudados sem recoletar nada, porque o score e calculado na leitura, nunca
# gravado como coluna.
PESOS_PADRAO = {
    "velocidade": 0.30,
    "engajamento": 0.25,
    "comentario": 0.20,
    "visualizacao": 0.15,
    "recencia": 0.10,
}

# Meia-vida da recencia: um post de 48h vale metade de um recem-publicado.
MEIA_VIDA_HORAS = 48.0


# ------------------------------------------------------------ fundamentos


def mediana(valores):
    """A mediana, ignorando ausentes. None se nao sobrar nada."""
    limpos = sorted(v for v in valores if v is not None)
    if not limpos:
        return None

    meio = len(limpos) // 2
    if len(limpos) % 2:
        return float(limpos[meio])
    return (limpos[meio - 1] + limpos[meio]) / 2.0


def percentil_no_grupo(valor, grupo):
    """Que fracao do grupo este valor supera. 0.0 a 1.0.

    Empate conta meio ponto, para que um grupo todo igual devolva 0.5 em vez
    de 1.0 — se ninguem se destaca, ninguem e excepcional.
    """
    if valor is None:
        return None

    limpos = [v for v in grupo if v is not None]
    if not limpos:
        return None
    if len(limpos) == 1:
        return 0.5

    abaixo = sum(1 for v in limpos if v < valor)
    iguais = sum(1 for v in limpos if v == valor)
    return (abaixo + iguais / 2.0) / len(limpos)


def razao_para_mediana(valor, grupo):
    """Quantas vezes a mediana do grupo. 2.0 = o dobro do post tipico.

    E o numero que se le em voz alta: "este reel fez 3,4x a mediana do perfil".
    """
    if valor is None:
        return None

    centro = mediana(grupo)
    if not centro:
        return None
    return valor / centro


def horas_desde(publicado_em, agora=None):
    """Horas entre a publicacao e agora. None se a data nao servir."""
    if not publicado_em:
        return None

    if isinstance(publicado_em, datetime):
        momento = publicado_em
    else:
        try:
            momento = datetime.fromisoformat(
                str(publicado_em).replace("Z", "+00:00"))
        except ValueError:
            return None

    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)

    referencia = agora or datetime.now(timezone.utc)
    if referencia.tzinfo is None:
        referencia = referencia.replace(tzinfo=timezone.utc)

    horas = (referencia - momento).total_seconds() / 3600.0
    return horas if horas >= 0 else 0.0


def por_hora(valor, horas, minimo_de_horas=1.0):
    """Velocidade. O piso de 1h evita que um post de 3 minutos vire foguete.

    Sem o piso, um reel com 200 views publicado ha 2 minutos daria 6.000
    views/hora e dominaria qualquer ranking. O piso e conservador de proposito.
    """
    if valor is None or horas is None:
        return None
    return valor / max(horas, minimo_de_horas)


# ---------------------------------------------------------- engajamento


def taxa_de_engajamento(curtidas, comentarios, visualizacoes=None,
                        seguidores=None, compartilhamentos=None,
                        salvamentos=None):
    """Engajamento, e **sobre qual base ele foi calculado**.

    Devolve `(taxa, base)`. A base importa: 4% sobre views e 4% sobre
    seguidores nao sao a mesma coisa, e comparar os dois lado a lado seria
    erro. Quem usa isto tem obrigacao de olhar a base.

    `compartilhamentos` e `salvamentos` entram **se existirem**. O Instagram
    nao publica nenhum dos dois; se um dia o Actor devolver, a conta melhora
    sozinha sem mudar chamada.
    """
    if curtidas is None and comentarios is None:
        return None, None

    interacoes = (curtidas or 0) + (comentarios or 0)
    if compartilhamentos is not None:
        interacoes += compartilhamentos
    if salvamentos is not None:
        interacoes += salvamentos

    if visualizacoes:
        return interacoes / visualizacoes, "visualizacoes"

    # O Instagram vem removendo a contagem publica de views. Quando ela nao
    # vem, seguidores e a unica base que sempre existe.
    if seguidores:
        return interacoes / seguidores, "seguidores"

    return None, None


def sinais_do_post(post, agora=None, seguidores=None):
    """Os cinco sinais crus de um post, antes de virarem percentil.

    Cru de proposito: percentil so existe contra um grupo, e o grupo e escolha
    de quem pergunta (o perfil, o nicho, a semana).
    """
    horas = horas_desde(post.get("data_utc"), agora)
    visualizacoes = post.get("visualizacoes")
    curtidas = post.get("curtidas")
    comentarios = post.get("comentarios")

    taxa, base = taxa_de_engajamento(
        curtidas, comentarios, visualizacoes, seguidores,
        post.get("compartilhamentos"), post.get("salvamentos"))

    # Comentario custa mais esforco que curtida, entao ele e sinal proprio e
    # nao so mais uma parcela do engajamento.
    if visualizacoes:
        taxa_comentario = (comentarios or 0) / visualizacoes
    elif curtidas:
        taxa_comentario = (comentarios or 0) / curtidas
    else:
        taxa_comentario = None

    # Velocidade tambem precisa de base alternativa, e pelo mesmo motivo do
    # engajamento: o Instagram vem escondendo a contagem de views. Se ela
    # sumir e a velocidade dependesse so dela, o score perderia 45% do peso
    # (velocidade + visualizacao) exatamente quando mais precisa funcionar.
    if visualizacoes:
        velocidade, base_velocidade = por_hora(visualizacoes, horas), "visualizacoes"
    else:
        velocidade = por_hora(curtidas, horas)
        base_velocidade = "curtidas" if velocidade is not None else None

    return {
        "horas": horas,
        "velocidade": velocidade,
        "base_da_velocidade": base_velocidade,
        "velocidade_curtidas": por_hora(curtidas, horas),
        "velocidade_comentarios": por_hora(comentarios, horas),
        "engajamento": taxa,
        "base_do_engajamento": base,
        "comentario": taxa_comentario,
        "visualizacao": visualizacoes,
        "recencia": recencia(horas),
    }


def recencia(horas):
    """1.0 recem-publicado, 0.5 com 48h, caindo suave. Nunca negativo."""
    if horas is None:
        return None
    return 0.5 ** (horas / MEIA_VIDA_HORAS)


# ------------------------------------------------- score de oportunidade


def score_de_oportunidade(post, grupo, pesos=None, agora=None,
                          seguidores=None, seguidores_do_grupo=None):
    """0 a 100. Quanto este post destoa dos pares dele, para cima.

    `grupo` sao os outros posts da comparacao — do mesmo perfil, ou do mesmo
    nicho. O score **so faz sentido dentro do grupo que voce escolheu**, e
    trocar o grupo troca o numero. Isso e a definicao, nao um defeito.

    Devolve o total, cada componente em percentil, e os sinais crus — para a
    resposta ser auditavel em vez de um numero magico.
    """
    pesos = pesos or PESOS_PADRAO

    meus = sinais_do_post(post, agora, seguidores)
    dos_outros = [
        sinais_do_post(outro, agora,
                       (seguidores_do_grupo or {}).get(outro.get("perfil")))
        for outro in grupo
        if outro.get("id") != post.get("id")
    ]

    componentes, usados = {}, {}

    for nome in ("velocidade", "engajamento", "comentario", "visualizacao",
                 "recencia"):
        meu_valor = meus.get(nome)
        do_grupo = [s.get(nome) for s in dos_outros]

        # Sem grupo para comparar, o percentil seria invencao. Recencia e a
        # excecao: ela ja nasce numa escala absoluta de 0 a 1.
        if nome == "recencia":
            posicao = meu_valor
        else:
            posicao = percentil_no_grupo(meu_valor, do_grupo)

        if posicao is None:
            continue

        componentes[nome] = posicao
        usados[nome] = pesos.get(nome, 0.0)

    if not componentes:
        return {"score": None, "componentes": {}, "sinais": meus,
                "motivo": "sem dado suficiente para comparar"}

    # Os pesos sao renormalizados sobre o que existe. Se `visualizacoes` nao
    # veio, o score nao e punido em 15% — ele se redistribui entre os sinais
    # que sobraram. Dado ausente nao pode virar nota baixa.
    total_dos_pesos = sum(usados.values()) or 1.0
    score = sum(componentes[n] * usados[n] for n in componentes) / total_dos_pesos

    return {
        "score": round(100.0 * score, 1),
        "componentes": {n: round(v, 3) for n, v in componentes.items()},
        "pesos_usados": usados,
        "sinais": meus,
        "tamanho_do_grupo": len(dos_outros),
    }


def ranquear(posts, pesos=None, agora=None, seguidores_por_perfil=None):
    """Todos os posts pontuados uns contra os outros, do melhor para o pior."""
    seguidores_por_perfil = seguidores_por_perfil or {}
    saida = []

    for post in posts:
        resultado = score_de_oportunidade(
            post, posts, pesos, agora,
            seguidores=seguidores_por_perfil.get(post.get("perfil")),
            seguidores_do_grupo=seguidores_por_perfil)
        saida.append({
            "id": post.get("id"),
            "perfil": post.get("perfil"),
            "legenda": (post.get("legenda") or "")[:70],
            **resultado,
        })

    return sorted(saida, key=lambda linha: linha["score"] or -1, reverse=True)


def crescimento(historico):
    """Crescimento de seguidores entre a leitura mais velha e a mais nova.

    `historico` sao linhas de `perfis_historico`, cada uma com `medido_em` e
    `seguidores`. **Com uma leitura so, devolve None** — e a resposta honesta:
    crescimento e diferenca, e diferenca precisa de dois pontos.
    """
    pontos = sorted(
        ((linha["medido_em"], linha["seguidores"]) for linha in historico
         if linha.get("seguidores") is not None),
        key=lambda p: p[0])

    if len(pontos) < 2:
        return {"absoluto": None, "percentual": None, "por_dia": None,
                "leituras": len(pontos),
                "motivo": "sao necessarias pelo menos duas leituras"}

    (data_velha, antes), (data_nova, agora_) = pontos[0], pontos[-1]
    dias = max(horas_desde(data_velha, _como_data(data_nova)) or 0, 0) / 24.0

    return {
        "absoluto": agora_ - antes,
        "percentual": None if not antes else 100.0 * (agora_ - antes) / antes,
        "por_dia": None if dias < 0.5 else (agora_ - antes) / dias,
        "leituras": len(pontos),
        "dias": round(dias, 2),
    }


def _como_data(texto):
    try:
        momento = datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
    except ValueError:
        return None
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)
