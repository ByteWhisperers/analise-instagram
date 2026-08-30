"""A decisao do mapeamento: ranquear, saturar, medir e montar o dossie.

Separado do `pipeline.py` pelo mesmo motivo que `metricas.py` e
`desempenho.py`: aqui e **decisao**, nao orquestracao. Quase tudo e funcao
pura, testavel sem rede, sem banco e sem gastar um centavo.

**Por que existe:** ate a T13 o sistema tinha um regime so — voce ja sabia o
termo, pedia, recebia. Isso assume que o vocabulario do assunto e conhecido, e
com "receitas" foi verdade por acidente. Com "desastres e tragedias" o input
que o sistema exige e justamente o output que ainda nao se tem.

**A inversao que este modulo faz:** os numeros do nicho (banda de seguidores,
duracao, ritmo) deixam de ser pergunta ANTES da coleta e passam a ser resultado
DELA. Na T13 a banda 10k-500k foi escolhida por intuicao, sem ninguem ter
medido nada — para um tema novo, ninguem sabe a banda certa de antemao.
"""

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

import config

# Onde os dossies moram. Nao vai para o `storage.py` porque o `Storage` daquele
# modulo e moldado inteiro em torno de `(usuario, post_id)` — um dossie nao e
# post de ninguem, e enfia-lo naquela interface distorceria as duas coisas.
PASTA = "mapeamentos"

# Quanto de vocabulario inedito uma rodada precisa trazer para valer a proxima.
# 0.20 = se menos de um quinto do que veio e novidade, o assunto ja se repetiu
# o bastante e continuar so gasta.
LIMIAR_DE_SATURACAO = 0.20


# ------------------------------------------------------------- ranqueamento


# Palavras que ligam frase e nao nomeiam assunto. Sem esta lista, o tema
# "desastres E tragedias" vira a tag `#desastresetragedias`.
LIGACOES = frozenset((
    "e", "ou", "de", "da", "do", "das", "dos", "para", "por", "com", "sem",
    "em", "no", "na", "nos", "nas", "o", "a", "os", "as", "um", "uma", "que",
))


def sementes_do_tema(tema):
    """Tema em portugues comum -> as tags por onde COMECAR a procurar.

    `[MEDIDO 30/08/2026]` Esta funcao nasceu de uma falha real: a primeira
    versao do mapeamento usava so a concatenacao do tema, pediu
    `#desastresetragedias` e recebeu **1 item e zero termos**. Ninguem escreve
    assim. O tema em portugues nao e uma hashtag — e essa e a premissa inteira
    do mapeamento.

    Devolve as candidatas em ordem de aposta:

      1. o tema colado inteiro, que funciona quando o tema JA e uma palavra
         ("receitas") ou uma expressao usada como tag ("cirurgiaplastica")
      2. cada palavra significativa sozinha, que e o resgate quando a 1 falha

    Quem chama tenta uma de cada vez e para na primeira que render — as rodadas
    seguintes alargam o vocabulario a partir dela, entao nao ha por que pagar
    por todas as portas de entrada quando uma ja abriu.
    """
    from coletor import tag_do_termo

    inteiro = tag_do_termo(tema)
    palavras = [p for p in str(tema or "").split()
                if tag_do_termo(p) and tag_do_termo(p) not in LIGACOES]

    sementes = [inteiro] if inteiro else []
    for palavra in palavras:
        tag = tag_do_termo(palavra)
        if tag and tag not in sementes:
            sementes.append(tag)
    return sementes


def fundir_contagens(acumulado, novo):
    """Junta o vocabulario de duas rodadas, sem perder a evidencia.

    Devolve um dicionario novo: nenhuma das entradas e alterada. Somar posts e
    trivial; o cuidado esta em `perfis`, que e uniao de conjunto e nao soma —
    o mesmo perfil aparecendo em duas rodadas continua sendo um perfil.
    """
    def _zerado(fonte=None):
        return {"posts": 0, "perfis": [], "idiomas": {"pt": 0, "es": 0, "?": 0},
                "fonte": fonte}

    saida = {}
    for tag, dados in (acumulado or {}).items():
        linha = _zerado(dados.get("fonte"))
        linha["posts"] = dados["posts"]
        linha["perfis"] = list(dados["perfis"])
        linha["idiomas"].update(dados.get("idiomas") or {})
        saida[tag] = linha

    for tag, dados in (novo or {}).items():
        linha = saida.setdefault(tag, _zerado(dados.get("fonte")))
        linha["posts"] += dados["posts"]
        for lingua, votos in (dados.get("idiomas") or {}).items():
            linha["idiomas"][lingua] = linha["idiomas"].get(lingua, 0) + votos
        for perfil in dados["perfis"]:
            if perfil not in linha["perfis"]:
                linha["perfis"].append(perfil)
    return saida


def idioma_da_tag(dados):
    """O idioma que a maioria dos posts daquela tag falava.

    `None` quando ninguem opinou ou quando deu empate — e `None` aqui NAO
    autoriza descarte. Foi a mitigacao combinada em 30/08/2026: descarta-se o
    que foi positivamente detectado como outro idioma, nunca o que nao se sabe.
    Descartar o desconhecido mataria calado a tag do post sem legenda.
    """
    votos = (dados or {}).get("idiomas") or {}
    pt, es = votos.get("pt", 0), votos.get("es", 0)
    if pt == es:
        return None
    return "pt" if pt > es else "es"


def e_de_outro_idioma(dados, alvo):
    """Esta tag foi PROVADA de outro idioma que nao o alvo?

    `alvo = "qualquer"` desliga o filtro inteiro.
    """
    if not alvo or alvo == "qualquer":
        return False
    achado = idioma_da_tag(dados)
    return achado is not None and achado != alvo


def ranquear_perfis(contagens, top_de_tags=10, limite=None):
    """Quem e NUCLEO do nicho, e nao quem passou por ali.

    Pontua o perfil por em quantas das tags mais fortes ele aparece. A
    informacao ja esta toda em `contagens` — cada tag guarda a lista de perfis
    que a usaram —, entao isto nao custa uma chamada sequer.

    `[MEDIDO 30/08/2026]` Existe porque a versao anterior escolhia por ordem de
    chegada (`candidatos[:3]`, `sem_numero[:12]`), e a aba da tag vem ordenada
    por RECENCIA. A amostra puxava para conta recem-postada e pequena: a
    mediana medida deu 1.435 seguidores.
    """
    ranking = ranquear_termos(contagens, limite=top_de_tags)
    fortes = {linha["termo"] for linha in ranking}

    por_perfil = {}
    for tag, dados in (contagens or {}).items():
        for usuario in dados["perfis"]:
            linha = por_perfil.setdefault(usuario, {"usuario": usuario,
                                                    "tags_fortes": 0,
                                                    "tags": 0})
            linha["tags"] += 1
            if tag in fortes:
                linha["tags_fortes"] += 1

    ordenado = sorted(por_perfil.values(),
                      key=lambda l: (-l["tags_fortes"], -l["tags"],
                                     l["usuario"]))
    return ordenado[:limite] if limite else ordenado


def ranquear_termos(contagens, minimo_de_perfis=1, limite=None):
    """O vocabulario em ordem de forca.

    **Perfis distintos primeiro, posts como desempate.** Esta ordem e a decisao
    mais importante do modulo, e ela e empirica:

    `[MEDIDO 30/08/2026]` colhendo as hashtags reais de @receitasdepai vieram
    `publi`, `MercadoLivre`, `PagBank`, `AeC440` e `CasaDecorMercadoLivre` —
    vocabulario de PUBLICIDADE, no meio das de receita. Tag de patrocinio
    aparece muito, mas dentro de um perfil so. Tag do nicho aparece em varios
    perfis diferentes. Ranquear por frequencia elegeria a propaganda; ranquear
    por perfis distintos a afunda sozinha, sem lista negra e sem LLM.
    """
    linhas = [
        {"termo": tag,
         "perfis": len(dados["perfis"]),
         "posts": dados["posts"],
         "quem": sorted(dados["perfis"])[:5],
         "idioma": idioma_da_tag(dados) or "?",
         "votos": dict(dados.get("idiomas") or {}),
         "fonte": dados.get("fonte")}
        for tag, dados in (contagens or {}).items()
        if len(dados["perfis"]) >= minimo_de_perfis
    ]
    linhas.sort(key=lambda l: (-l["perfis"], -l["posts"], l["termo"]))
    return linhas[:limite] if limite else linhas


def saturou(antes, depois, limiar=LIMIAR_DE_SATURACAO):
    """A rodada nova trouxe pouca novidade? Entao pare.

    `antes` e `depois` sao os conjuntos de termos conhecidos, um antes e outro
    depois da rodada. A conta e a fracao de termos ineditos sobre o total novo.

    Sem vocabulario nenhum antes, nao ha como falar em saturacao: a primeira
    rodada e sempre 100% novidade, e devolver True ali mataria o laco antes de
    ele comecar.
    """
    antes, depois = set(antes or []), set(depois or [])
    if not depois:
        return True
    if not antes:
        return False

    ineditos = depois - antes
    return (len(ineditos) / len(depois)) < limiar


# ------------------------------------------------------- os numeros do nicho


def percentil(valores, p):
    """O percentil p (0 a 100) por posicao, sem interpolar.

    Sem interpolacao de proposito: interpolar inventa um valor de seguidores
    que nenhum perfil tem. Para sugerir uma banda, e melhor apontar um perfil
    que existe.
    """
    numeros = sorted(v for v in (valores or []) if v is not None)
    if not numeros:
        return None
    if len(numeros) == 1:
        return numeros[0]

    posicao = int(round((p / 100.0) * (len(numeros) - 1)))
    return numeros[max(0, min(posicao, len(numeros) - 1))]


def numeros_do_nicho(perfis, posts=None):
    """A distribuicao real do nicho, e a banda que ela sugere.

    Devolve sempre a CONTA junto do numero — quantos perfis entraram, os
    percentis, quantos videos tinham duracao. Numero sem a conta que o produziu
    e chute com cara de medicao, e foi assim que a banda 10k-500k nasceu.

    A banda sugerida e p25-p75, e nao p10-p90: os extremos sao justamente quem
    distorce. Os percentis largos vao junto para voce ver a forma da
    distribuicao e discordar com base.
    """
    seguidores = [p.get("seguidores") for p in (perfis or [])
                  if p.get("seguidores") is not None]
    duracoes = [c.get("duracao_segundos") for c in (posts or [])
                if c.get("duracao_segundos")]

    numeros = {
        "perfis_medidos": len(seguidores),
        "posts_medidos": len(posts or []),
        "seguidores_p10": percentil(seguidores, 10),
        "seguidores_p25": percentil(seguidores, 25),
        "seguidores_p50": percentil(seguidores, 50),
        "seguidores_p75": percentil(seguidores, 75),
        "seguidores_p90": percentil(seguidores, 90),
        "duracao_medidos": len(duracoes),
        "duracao_p25": percentil(duracoes, 25),
        "duracao_p50": percentil(duracoes, 50),
        "duracao_p75": percentil(duracoes, 75),
        "ritmo_dias_entre_posts": _ritmo(posts),
    }

    numeros["banda_sugerida"] = {
        "seguidores_min": numeros["seguidores_p25"],
        "seguidores_max": numeros["seguidores_p75"],
        # A frase que justifica o par. Sem ela, daqui a um mes ninguem lembra
        # de onde saiu o numero — que e exatamente o problema do 10k-500k.
        "por_que": ("p25 a p75 de %d perfis medidos (mediana %s)"
                    % (len(seguidores), numeros["seguidores_p50"])
                    if seguidores else
                    "nenhum perfil com contagem de seguidores foi medido"),
    }
    return numeros


def _ritmo(posts):
    """Mediana de dias entre posts, por perfil, depois entre perfis.

    Duas medianas e nao uma media: perfil que posta cinco vezes num dia e some
    por um mes arrastaria qualquer media. Perfil com menos de dois posts nao
    tem intervalo — devolve None em vez de fingir.
    """
    por_perfil = {}
    for post in (posts or []):
        data = post.get("data_utc")
        dono = post.get("perfil")
        if not data or not dono:
            continue
        try:
            quando = datetime.fromisoformat(str(data).replace("Z", "+00:00"))
        except ValueError:
            continue
        if quando.tzinfo is None:
            quando = quando.replace(tzinfo=timezone.utc)
        por_perfil.setdefault(dono, []).append(quando)

    medianas = []
    for datas in por_perfil.values():
        if len(datas) < 2:
            continue
        datas.sort()
        intervalos = [(b - a).total_seconds() / 86400.0
                      for a, b in zip(datas, datas[1:])]
        medianas.append(statistics.median(intervalos))

    if not medianas:
        return None
    return round(statistics.median(medianas), 2)


# -------------------------------------------------------------- o dossie


def montar_dossie(tema, contagens, perfis, posts=None, custo_usd=0.0,
                  rodadas=0, parou_por=None, limite_de_tags=40, alvo="pt"):
    """O que o mapeamento aprendeu, pronto para voce marcar o que presta.

    Tudo nasce com `"entra": false`. Nada entra sozinho — decisao do usuario em
    30/08/2026, e a razao e simples: nenhum LLM participa deste projeto, e
    dizer se `#caso` e tragedia ou novela e semantica. A maquina traz os
    numeros; quem le portugues e voce.
    """
    todas = ranquear_termos(contagens)

    # O descartado NAO some. Vai para uma secao propria, com o idioma detectado
    # e os votos que o sustentam. O detector e heuristico e vai errar; erro que
    # some do arquivo e erro que ninguem conserta.
    tags, descartadas = [], []
    for linha in todas:
        alvo_lista = descartadas if e_de_outro_idioma(
            contagens.get(linha["termo"]), alvo) else tags
        alvo_lista.append(linha)

    tags = tags[:limite_de_tags]
    numeros = numeros_do_nicho(perfis, posts)

    return {
        "tema": tema,
        "tag_semente": None,
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "rodadas": rodadas,
        "parou_por": parou_por,
        "custo_usd": round(custo_usd or 0.0, 4),
        "_como_aprovar": ("Marque \"entra\": true no que presta e rode "
                          "`pipeline.py mapear aplicar \"%s\"`. O que ficar "
                          "false nao vai para o banco." % tema),
        "idioma_alvo": alvo,
        "numeros": numeros,
        "tags": [dict(linha, entra=False) for linha in tags],
        "_sobre_os_descartados": (
            "Detectados em outro idioma que nao %r. Ficam aqui em vez de "
            "sumir: o detector e heuristico, e se ele errou basta mover a "
            "linha para `tags` e marcar entra=true." % alvo),
        "descartados_por_idioma": [dict(linha, entra=False)
                                   for linha in descartadas[:limite_de_tags]],
        "perfis": [
            {"usuario": p.get("usuario"),
             "seguidores": p.get("seguidores"),
             "privado": p.get("privado"),
             "entra": False}
            for p in sorted(perfis or [],
                            key=lambda x: -(x.get("seguidores") or 0))
        ],
    }


def caminho_do_dossie(tema):
    """dados/mapeamentos/<tema>.json"""
    from coletor import tag_do_termo

    nome = tag_do_termo(tema) or "sem-nome"
    return Path(config.DADOS) / PASTA / ("%s.json" % nome)


def gravar_dossie(dossie):
    destino = caminho_do_dossie(dossie["tema"])
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8") as arquivo:
        json.dump(dossie, arquivo, ensure_ascii=False, indent=2)
    return destino


def ler_dossie(tema):
    """Le o dossie editado. Erro com instrucao, nunca FileNotFoundError cru."""
    caminho = caminho_do_dossie(tema)
    if not caminho.exists():
        raise ErroDeMapeamento(
            "Nao ha dossie para %r.\
"
            "Mapeie antes:\
"
            '  python src/pipeline.py mapear "%s"' % (tema, tema))

    with caminho.open(encoding="utf-8-sig") as arquivo:
        return json.load(arquivo)


def aprovados(dossie, chave="tags"):
    """So o que voce marcou. `entra` ausente conta como false."""
    return [item for item in (dossie.get(chave) or []) if item.get("entra")]


class ErroDeMapeamento(Exception):
    """Falha no mapeamento. Mensagem ja pronta para o usuario."""
