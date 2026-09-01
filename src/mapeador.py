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

import assinatura
import config
import grafo
import lexico

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


# ----------------------------------------------------------------- as tribos


# Termo visto num perfil so nao liga ninguem a ninguem: ele nao cria aresta e
# so engrossa o denominador do Jaccard. Numa amostra real a cauda de termo
# unico e a MAIOR parte das linhas, e mante-la faria todo perfil parecer
# distante de todo perfil.
MINIMO_DE_PERFIS_PARA_AGRUPAR = 2

# Perfil sobre o qual quase nada foi observado casa com qualquer um por acaso:
# o Jaccard fica alto porque o denominador e minusculo, nao porque as duas
# contas falem parecido.
#
# `[MEDIDO 31/08/2026]` TRES e nao quatro: com 4, o tema "grau de moto" perdia
# os perfis de legenda curta — e naquele nicho a legenda curta e a regra, nao a
# excecao. O corte tem de tirar quem nao diz nada, nao quem fala pouco.
MINIMO_DE_TERMOS_POR_PERFIL = 3


def secao_de_tribos(colhido, vizinhos_por_no=grafo.VIZINHOS_POR_NO,
                    minimo_de_perfis=MINIMO_DE_PERFIS_PARA_AGRUPAR,
                    minimo_de_termos=MINIMO_DE_TERMOS_POR_PERFIL,
                    minimo_por_tribo=grafo.MINIMO_POR_TRIBO):
    """Observacoes -> as tribos, com assinatura e com a nota de cada perfil.

    O caminho inteiro da Fase 2 e da Fase 3 num lugar so, porque as duas nao
    fazem sentido separadas: o agrupamento e o andaime e a assinatura e o
    produto, e quem le o dossie quer os dois na mesma secao.

    Devolve `None` quando o dado nao sustenta agrupamento — menos de duas
    tribos. Devolver uma tribo unica chamada "o nicho" seria dizer que nao ha
    subdivisao, quando o que houve foi amostra pequena demais para ver.
    """
    contagem = lexico.contar(colhido)
    perfis_por_termo = {
        termo: set(dados["perfis"])
        for termo, dados in contagem.items()
        if len(dados["perfis"]) >= minimo_de_perfis
    }
    if not perfis_por_termo:
        return None

    tribo_do_perfil = grafo.tribos_de_perfis(
        perfis_por_termo, vizinhos_por_no=vizinhos_por_no,
        minimo_de_termos=minimo_de_termos,
        minimo_por_tribo=minimo_por_tribo)
    grupos = grafo.agrupar(tribo_do_perfil)
    if len(grupos) < 2:
        return None

    kinds = {termo: dados["kind"] for termo, dados in contagem.items()}
    modelo = assinatura.modelo(perfis_por_termo, tribo_do_perfil,
                               kind_do_termo=kinds)

    generalidades = {
        termo: grafo.generalidade(
            grafo.espalhamento(perfis, tribo_do_perfil), len(grupos))
        for termo, perfis in perfis_por_termo.items()
    }

    # A matriz termo x tribo: a MESMA palavra com uma nota em cada tribo. E o
    # centro do desenho, e o motivo de nao existir lista de dentro/fora — em
    # `moto`, `torque` vale >5 na oficina e <1 na quebrada, e as duas coisas
    # sao verdade ao mesmo tempo.
    matriz = []
    for termo, perfis in perfis_por_termo.items():
        por_tribo = {t: assinatura.exclusividade(modelo, termo, t)
                     for t in grupos}
        notas = [v for v in por_tribo.values() if v is not None]
        matriz.append({
            "termo": termo,
            "kind": kinds.get(termo),
            "perfis": len(perfis),
            "generalidade": generalidades.get(termo),
            "exclusividade_maxima": max(notas) if notas else None,
            "por_tribo": por_tribo,
        })
    matriz.sort(key=lambda l: (-(l["exclusividade_maxima"] or 0), l["termo"]))

    termos_do_perfil = grafo.inverter(perfis_por_termo)
    return {
        "quantas": len(grupos),
        "_como_ler": (
            "`semantic_core` e o territorio onde a tribo mora; "
            "`identity_markers` e o que a distingue das vizinhas. "
            "`generalidade` vai de 0 (marcador) a 1 (territorio), e "
            "`exclusividade` acima de 1 e desproporcionalmente desta tribo. "
            "Em `matriz`, o mesmo termo tem uma nota POR tribo — de proposito: "
            "uma palavra pode ser marca de uma e territorio de outra."),
        "assinaturas": assinatura.montar_todas(modelo, generalidades),
        "matriz": matriz,
        "perfis": {
            perfil: assinatura.classificar(modelo, termos_do_perfil.get(perfil))
            for perfil in sorted(tribo_do_perfil)
        },
    }


# ------------------------------------------------------- a proxima pergunta


# Quanto da rodada vai para EXPLORAR a fronteira em vez de aprofundar o que ja
# se sabe. Sem essa fatia o laco vira exploracao pura da tribo mais forte, que
# e a versao nova do mesmo defeito guloso que a T15 corrigiu no eixo das
# sementes: aprofundar no cluster que abriu primeiro.
FRACAO_DE_EXPLORACAO = 0.34


def ganho_do_termo(linha):
    """Quanto abrir esta tag promete ensinar sobre a identidade das tribos.

        ganho = exclusividade_maxima x log(1 + perfis)

    **A exclusividade e quem manda, e e a troca central da Fase 4.** O ranking
    por perfis distintos elege o TERRITORIO: `#moto` aparece em todo perfil, e
    abri-la devolve a multidao misturada que ja se tem. A exclusividade elege o
    MARCADOR: `#mandrake` mora numa tribo so, e abri-la traz mais gente dela.

    O `log(1 + perfis)` exige algum lastro sem deixar o volume decidir: satura
    depressa, entao a tag do territorio nao vence por tamanho, e a tag vista uma
    vez so nao vence por acaso.

    **Os pesos sao uma primeira aposta, nao uma medicao.** Nao ha rodada real
    comparando esta ordem com a gulosa ainda. Quando houver, e este numero que
    se mexe primeiro.
    """
    import math

    exclusividade = linha.get("exclusividade_maxima")
    if exclusividade is None:
        return 0.0
    return exclusividade * math.log(1 + (linha.get("perfis") or 0))


def proximos_alvos(contagens, quantos, visitadas=(), tribos=None,
                   idioma_alvo="pt", fracao_de_exploracao=FRACAO_DE_EXPLORACAO):
    """As tags da proxima rodada. `[MEDIDO 30/08/2026]` substitui a escolha gulosa.

    A pergunta deixa de ser "quais as tags mais fortes?" e passa a ser **"qual
    observacao mais reduz minha incerteza sobre a identidade dos clusters?"**.
    Sao respostas diferentes: a tag mais forte e quase sempre a do territorio, e
    o territorio e onde todas as tribos se parecem.

    A rodada e dividida em duas intencoes explicitas:

    - **aprofundar** — maior `ganho_do_termo`: os marcadores, que trazem mais
      gente da tribo que os exibe;
    - **explorar** — maior `generalidade`: os termos que ficam ENTRE as tribos.
      E na fronteira que se descobre se sao mesmo duas comunidades ou uma so
      mal separada, e e a fatia que impede o laco de so aprofundar.

    Sem tribos ainda (as primeiras rodadas, quando a amostra nao sustenta
    agrupamento) cai no comportamento antigo — perfis distintos. Isso e
    proposital: sem cluster nao ha incerteza sobre cluster para reduzir.
    """
    visitadas = set(visitadas or ())
    elegiveis = [
        linha["termo"] for linha in ranquear_termos(contagens)
        if linha["termo"] not in visitadas
        and not e_de_outro_idioma(contagens.get(linha["termo"]), idioma_alvo)
    ]
    if quantos <= 0 or not elegiveis:
        return []
    if not tribos or not tribos.get("matriz"):
        return elegiveis[:quantos]

    permitidos = set(elegiveis)
    candidatos = [linha for linha in tribos["matriz"]
                  if linha["termo"] in permitidos
                  and linha.get("kind") == "hashtag"]
    if not candidatos:
        return elegiveis[:quantos]

    # A fatia de exploracao arredonda para BAIXO, e nunca come a rodada
    # inteira: com `quantos=1` a unica vaga vai para aprofundar, que e a aposta
    # mais segura quando so se pode fazer uma pergunta.
    de_exploracao = min(int(quantos * fracao_de_exploracao), quantos - 1)
    de_aprofundar = quantos - de_exploracao

    escolhidos, ja = [], set()
    for linha in sorted(candidatos, key=lambda l: (-ganho_do_termo(l),
                                                   l["termo"])):
        if len(escolhidos) >= de_aprofundar:
            break
        escolhidos.append(linha["termo"])
        ja.add(linha["termo"])

    for linha in sorted(candidatos, key=lambda l: (-(l["generalidade"] or 0),
                                                   l["termo"])):
        if len(escolhidos) >= quantos:
            break
        if linha["termo"] not in ja:
            escolhidos.append(linha["termo"])
            ja.add(linha["termo"])

    # A cauda que o agrupamento nao alcanca (termo de um perfil so) nao pode
    # deixar a rodada vazia: se sobrou vaga, o ranking antigo a preenche.
    for termo in elegiveis:
        if len(escolhidos) >= quantos:
            break
        if termo not in ja:
            escolhidos.append(termo)
            ja.add(termo)
    return escolhidos


def montar_dossie(tema, contagens, perfis, posts=None, custo_usd=0.0,
                  rodadas=0, parou_por=None, limite_de_tags=40, alvo="pt",
                  tribos=None):
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
        # `None` quando o dado nao sustentou agrupamento. A chave fica na
        # mesma: dossie sem a chave faria quem le achar que esqueceram, e
        # dossie com tribo inventada e pior que dossie sem tribo.
        "tribos": tribos,
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
