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


def garantir_pastas():
    """Cria as pastas de trabalho se ainda não existirem."""
    for pasta in (BUSCAS, PERFIS, ANALISES, SAIDA, SESSOES):
        pasta.mkdir(parents=True, exist_ok=True)
