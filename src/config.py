"""Configuração e caminhos do projeto.

Todo caminho do projeto sai daqui. Nenhum outro módulo monta caminho na mão.
"""

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

CONFIG = RAIZ / "config.local.json"
EXEMPLO = RAIZ / "config.local.example.json"

DADOS = RAIZ / "dados"
BUSCAS = DADOS / "buscas"
PERFIS = DADOS / "perfis"
ANALISES = DADOS / "analises"
# Video gravado pelo usuario, entrada do editor em lote (T8). Fica sob `dados/`
# de proposito: e a pasta que o .gitignore ja cobre inteira, e material proprio
# nao pode vazar para o repositorio publico.
GRAVACOES = DADOS / "gravacoes"
SAIDA = RAIZ / "saida"
SESSOES = RAIZ / ".sessoes"

OBRIGATORIAS_DO_POSTGRES = ("host", "port", "database", "user", "password")


class ErroDeConfig(Exception):
    """Configuração ausente ou inválida. Mensagem já pronta para o usuário."""


def carregar():
    """Lê config.local.json, valida o mínimo e devolve o dicionário."""
    if not CONFIG.exists():
        raise ErroDeConfig(
            f"Falta o arquivo {CONFIG.name}.\n"
            f"Copie {EXEMPLO.name} para {CONFIG.name} e preencha o usuário do Instagram.\n"
            f"Pasta: {RAIZ}"
        )

    try:
        # utf-8-sig e nao utf-8: o Bloco de Notas e o PowerShell 5.1 gravam
        # com BOM, e o json.load recusa BOM. `utf-8-sig` le os dois casos.
        with CONFIG.open(encoding="utf-8-sig") as arquivo:
            cfg = json.load(arquivo)
    except json.JSONDecodeError as erro:
        raise ErroDeConfig(f"{CONFIG.name} não é um JSON válido: {erro}") from erro

    _exigir_postgres(cfg)
    return cfg


def _exigir_postgres(cfg):
    """O banco e a unica coisa sem a qual nada roda.

    Ate 29/08/2026 o que se exigia aqui era `instagram.usuario`. Era um portao
    trancado por uma chave que nao existe mais: a ADR 005 tirou a conta do
    Instagram do projeto, e `usuario_instagram()` tinha zero chamadores. O
    efeito pratico era pior que inutil — numa maquina limpa, o projeto e os
    testes recusavam subir enquanto alguem nao inventasse um nome de usuario
    para um campo que nada lia.

    A exigencia certa e a do PostgreSQL, e o texto e o mesmo que
    `db._conexao_do_config()` ja dava — so que agora aparece na hora de
    carregar, e nao na primeira consulta.
    """
    pg = cfg.get("postgres") or {}
    faltando = [c for c in OBRIGATORIAS_DO_POSTGRES if not pg.get(c)]
    if not faltando:
        return

    if not pg:
        raise ErroDeConfig(
            f"Falta a secao `postgres` em {CONFIG.name}.\n\n"
            f"Copie a secao de {EXEMPLO.name} e preencha com os dados do seu\n"
            "servidor. Rode `preparar.py verificar` para conferir o resto.")

    raise ErroDeConfig(
        f"A secao `postgres` de {CONFIG.name} esta incompleta.\n"
        "Falta: %s" % ", ".join(faltando))


# ------------------------------------------------------------------- Apify


def apify(cfg):
    """A secao `apify` do config, com os padroes preenchidos."""
    secao = dict(cfg.get("apify") or {})
    secao.setdefault("actor", "apify/instagram-scraper")
    secao.setdefault("plano", "free")
    secao.setdefault("max_perfis", 40)
    secao.setdefault("posts_por_perfil", 10)
    secao.setdefault("teto_usd_por_rodada", 1.0)
    secao.setdefault("avisar_acima_de_usd", 0.50)
    return secao


def token_apify(cfg):
    """O token. Falta dele e erro com instrucao, nao KeyError."""
    token = (cfg.get("apify") or {}).get("token", "")
    if not token or token.startswith("SEU_TOKEN"):
        raise ErroDeConfig(
            "Falta o token da Apify em %s.\n\n"
            "1. Crie a conta em apify.com (o plano gratis nao pede cartao)\n"
            "2. Copie o token em console.apify.com/account/integrations\n"
            "3. Cole em config.local.json, em apify.token\n\n"
            "O arquivo ja esta no .gitignore. Nunca mande o token por mensagem."
            % CONFIG.name)
    return token


def pesos_do_score(cfg):
    """Os pesos do score de oportunidade.

    Ficam em configuracao de proposito: o score e calculado na leitura, nunca
    gravado como coluna, entao mudar um peso aqui re-ranqueia tudo na hora,
    sem recoletar nada e sem gastar um centavo na Apify.
    """
    import desempenho

    pesos = dict(desempenho.PESOS_PADRAO)
    pesos.update({c: v for c, v in (cfg.get("score") or {}).items()
                  if not c.startswith("_") and isinstance(v, (int, float))})
    return pesos


def download(cfg):
    """A secao `download`, com os padroes preenchidos.

    `concorrencia` nasce em 2 por causa do teto de requisicao anonima do
    yt-dlp, nao por causa da maquina — download e I/O, a maquina aguentaria
    mais. Subir isso so depois de medir.
    """
    secao = dict(cfg.get("download") or {})
    secao.setdefault("concorrencia", 2)
    secao.setdefault("timeout_segundos", 120)
    secao.setdefault("max_tentativas", 3)
    secao.setdefault("cookies_do_navegador", None)
    return secao


def dados(cfg):
    """A secao `dados`: retencao da midia bruta, com os padroes preenchidos.

    Fica em configuracao e nao no codigo porque a resposta certa depende do
    disco de quem roda. Nasce tudo desligado: `pipeline.py limpar` avisa, mas
    so apaga com --aplicar.
    """
    secao = dict(cfg.get("dados") or {})
    secao.setdefault("apagar_midia_apos_transcricao", False)
    secao.setdefault("manter_dias", 30)
    secao.setdefault("avisar_acima_de_gb", 5)
    return secao


def mapeamento(cfg):
    """A secao `mapeamento`: quanto explorar antes de desistir.

    Existe porque mapear e EXPLORATORIO — nao se sabe de antemao quantas
    rodadas um tema exige. "Receitas" satura rapido; um tema ramificado pode
    nao saturar nunca. Por isso sao tres freios, e nao um:

      `teto_usd`   garantia dura, em dinheiro
      `rodadas`    teto de profundidade
      `saturacao`  o freio que economiza: para quando a rodada nova traz menos
                   de 20% de vocabulario inedito

    O `teto_usd` conta pela ESTIMATIVA, nunca pelo custo real. O real so chega
    depois que a rodada terminou, e depois e tarde para nao gastar. Numa sonda
    de 30/08/2026 a Apify devolveu `usage_total_usd = 0.0000` numa rodada que
    trouxe 3 itens — teto que contasse por ai nunca fecharia.
    """
    secao = dict(cfg.get("mapeamento") or {})
    secao.setdefault("teto_usd", 0.30)
    secao.setdefault("rodadas", 3)
    secao.setdefault("saturacao", 0.20)
    secao.setdefault("itens_por_tag", 30)
    secao.setdefault("tags_por_rodada", 2)
    secao.setdefault("perfis_para_expandir", 3)
    # Quantos perfis qualificar no fim, so para MEDIR a distribuicao. O perfil
    # que vem da aba da tag nao traz contagem de seguidores — sem esta etapa a
    # banda sugerida sai de tres perfis quaisquer, que foi o que aconteceu na
    # primeira rodada real de 30/08/2026: "13 a 404 seguidores".
    secao.setdefault("perfis_para_medir", 12)
    # O idioma que se quer mapear. `"qualquer"` desliga o filtro.
    #
    # Existe porque em 30/08/2026 o mapeamento de "desastres e tragedias"
    # voltou inteiro em espanhol e o laco gastou tres rodadas aprofundando num
    # cluster hispano-americano que seria rejeitado no fim.
    secao.setdefault("idioma", "pt")

    teto = secao["teto_usd"]
    if not isinstance(teto, (int, float)) or teto <= 0:
        raise ErroDeConfig(
            "mapeamento.teto_usd tem de ser um numero maior que zero. "
            "Recebi: %r.\nSem teto, um tema ramificado vira torneira aberta."
            % (teto,))

    sat = secao["saturacao"]
    if not isinstance(sat, (int, float)) or not 0 < sat < 1:
        raise ErroDeConfig(
            "mapeamento.saturacao e uma fracao entre 0 e 1 (0.20 = para quando "
            "menos de um quinto do vocabulario for novidade). Recebi: %r"
            % (sat,))

    return secao


def garantir_pastas():
    """Cria as pastas de trabalho se ainda não existirem."""
    for pasta in (BUSCAS, PERFIS, ANALISES, SAIDA, SESSOES):
        pasta.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------- Criterios de coleta (T13)
#
# Ficam aqui, e nao no codigo, porque sao JULGAMENTO e nao regra: quem decide
# se um perfil de 600 mil seguidores interessa e o dono do projeto, e a
# resposta muda por nicho. O padrao e so um ponto de partida defensavel.
#
# Toda variavel destas tem espelho em flag de linha de comando. A precedencia
# e sempre a mesma: `flag > config.local.json > padrao daqui`.


EIXOS_DE_DESCOBERTA = ("nome", "hashtag")

TIPOS_DE_COLETA = ("reels", "posts")


def descoberta(cfg):
    """A secao `descoberta`: como achar perfil, e qual perfil serve.

    `eixos` decide POR ONDE procurar, e a diferenca e grande:

      - `nome`    busca por `searchType: user` — acha quem tem a palavra no
                  nome. Foi o unico eixo ate 30/08/2026, e enviesou o banco:
                  7 dos 9 perfis achados tinham "receitas" no username.
      - `hashtag` abre `instagram.com/explore/tags/<tag>/` — acha quem PUBLICA
                  no assunto, mesmo com nome que nao entrega nada.
                  `searchType: "hashtag"` NAO serve para isso: devolve
                  `no_items`. Medido em 30/08/2026, duas vezes.

    `max_qualificar` existe porque o item da hashtag nao traz contagem de
    seguidores — nem com `addParentData`, conferido. Cada candidato que a
    hashtag levanta custa uma segunda chamada para saber se cabe na banda, e
    sem teto isso vira torneira aberta na fatura.
    """
    secao = dict(cfg.get("descoberta") or {})
    secao.setdefault("eixos", ["nome"])
    secao.setdefault("max_perfis", 40)
    secao.setdefault("seguidores_min", 10000)
    secao.setdefault("seguidores_max", 500000)
    secao.setdefault("somente_publicos", True)
    secao.setdefault("aprovacao_manual", True)
    secao.setdefault("max_qualificar", 20)
    # Quantas tags APROVADAS do nicho a descoberta usa por rodada. Cada tag e
    # uma chamada paga; sem teto, um nicho com 30 tags aprovadas viraria 30
    # chamadas sem ninguem pedir.
    secao.setdefault("max_tags_por_rodada", 3)

    eixos = [str(e).strip().lower() for e in (secao["eixos"] or []) if str(e).strip()]
    desconhecidos = [e for e in eixos if e not in EIXOS_DE_DESCOBERTA]
    if desconhecidos:
        raise ErroDeConfig(
            "Eixo de descoberta desconhecido: %s.\n"
            "Os que existem: %s"
            % (", ".join(desconhecidos), ", ".join(EIXOS_DE_DESCOBERTA)))
    secao["eixos"] = eixos or ["nome"]

    minimo, maximo = secao["seguidores_min"], secao["seguidores_max"]
    if minimo is not None and maximo is not None and minimo > maximo:
        raise ErroDeConfig(
            "descoberta.seguidores_min (%s) e maior que seguidores_max (%s).\n"
            "Assim nenhum perfil passa, e o comando devolveria zero sem dizer "
            "por que." % (minimo, maximo))

    return secao


def coleta(cfg):
    """A secao `coleta`: de que posts vale a pena pagar.

    `janela_dias` vira `onlyPostsNewerThan` na chamada — e o unico filtro que
    o Actor aceita de verdade, ou seja, o unico que economiza dinheiro em vez
    de so economizar disco.

    `incluir_fixados` e separado da janela porque o post fixado ESCAPA dela.
    Medido em 30/08/2026: pedindo 30 dias, 2 dos 4 reels vieram de fora — e
    eram exatamente os dois `isPinned`. Com `true` ele entra marcado e fica
    fora das contas de recencia; com `false` e descartado na entrada, antes de
    virar linha no banco.

    `maturidade_horas` nao filtra a chamada: filtra o JULGAMENTO. Post de duas
    horas ainda nao acumulou views, e compara-lo com um de tres dias em numero
    absoluto e comparar coisas diferentes.
    """
    secao = dict(cfg.get("coleta") or {})
    secao.setdefault("janela_dias", 30)
    secao.setdefault("tipo", "reels")
    secao.setdefault("posts_por_perfil", 10)
    secao.setdefault("maturidade_horas", 48)
    secao.setdefault("incluir_fixados", True)
    secao.setdefault("segundos_entre_requisicoes", 8)
    secao.setdefault("segundos_entre_perfis", 60)

    tipo = str(secao["tipo"]).strip().lower()
    if tipo not in TIPOS_DE_COLETA:
        raise ErroDeConfig(
            "coleta.tipo = %r nao existe. Os que existem: %s.\n"
            "`reels` pede so video ao Actor e por isso e mais barato; `posts` "
            "traz foto e carrossel junto." % (secao["tipo"],
                                              ", ".join(TIPOS_DE_COLETA)))
    secao["tipo"] = tipo

    janela = secao["janela_dias"]
    if janela is not None and (not isinstance(janela, int) or janela < 1):
        raise ErroDeConfig(
            "coleta.janela_dias tem de ser um inteiro de dias (ou null para "
            "nao filtrar por data). Recebi: %r" % (janela,))

    return secao
