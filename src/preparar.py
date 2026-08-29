"""Confere se a máquina está pronta para rodar o projeto.

Substitui o `instalar-postgres.ps1`, apagado na faxina de 28/08. A diferença
importante é de papel: **este script verifica e instrui; não instala.** Instalar
programa é decisão de quem opera a máquina, não do assistente (V1 §14).

O problema que ele resolve é concreto. Até 29/08/2026 um clone novo não subia,
e descobrir por quê exigia ler o código: `config.carregar()` exigia um usuário
do Instagram que nada lê, o `config.local.example.json` não tinha a seção
`postgres`, e não havia caminho documentado para montar o banco. Cada uma
dessas falhas aparecia sozinha, no meio de outra coisa, com mensagem diferente.

Aqui elas aparecem juntas, em ordem, com o conserto ao lado:

    .venv\\Scripts\\python.exe src\\preparar.py verificar

Sai com código 0 se está tudo de pé, 1 se falta alguma coisa — então serve
como portão em script, e não só para leitura humana.

**Sem emoji de propósito.** O console do Windows é cp1252 e engasga com eles;
`[ok]` e `[FALTA]` são os mesmos marcadores que os testes já usam.
"""

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import console
import config
import db

OK = "[ok]   "
FALTA = "[FALTA]"

# As bibliotecas que o projeto importa de verdade, com o motivo de cada uma.
# `pgvector` NAO entra: a ADR do modelo registra que ele nao esta instalado
# nesta fase, e cobrar por ele aqui daria falso alarme.
DEPENDENCIAS = (
    ("apify_client", "descoberta de perfis"),
    ("yt_dlp", "download de vídeo"),
    ("curl_cffi", "impersonação de TLS no download"),
    ("psycopg", "banco"),
    ("faster_whisper", "transcrição"),
)


class Resultado:
    """O que uma checagem devolve: passou, o que dizer, e como consertar."""

    def __init__(self, nome, ok, detalhe="", conserto=""):
        self.nome = nome
        self.ok = ok
        self.detalhe = detalhe
        self.conserto = conserto

    def imprimir(self):
        marca = OK if self.ok else FALTA
        print("%s %s" % (marca, self.nome))
        if self.detalhe:
            print("          %s" % self.detalhe)
        if not self.ok and self.conserto:
            for linha in self.conserto.split("\n"):
                print("          -> %s" % linha)


# ------------------------------------------------------------------ checagens


def checar_python():
    """O `python` do sistema não serve — falta tudo que está no venv."""
    executavel = Path(sys.executable)
    no_venv = ".venv" in executavel.parts
    versao = "%d.%d.%d" % sys.version_info[:3]

    return Resultado(
        "Python do venv",
        no_venv,
        "%s (Python %s)" % (executavel, versao),
        "Rode pelo interpretador do projeto:\n"
        "   .venv\\Scripts\\python.exe src\\preparar.py verificar\n"
        "Se a pasta .venv não existe: python -m venv .venv")


def checar_dependencias(dependencias=DEPENDENCIAS):
    """Importa de verdade. `pip list` mentiria sobre instalação quebrada.

    A lista entra por parâmetro só para o teste conseguir provar o caminho da
    falha sem desinstalar nada de verdade.
    """
    import importlib

    faltando = []
    for modulo, para_que in dependencias:
        try:
            importlib.import_module(modulo)
        except ImportError:
            faltando.append("%s (%s)" % (modulo, para_que))

    return Resultado(
        "Dependências",
        not faltando,
        "%d de %d instaladas" % (len(dependencias) - len(faltando),
                                 len(dependencias)),
        "Falta: %s\n"
        ".venv\\Scripts\\python.exe -m pip install -r requirements.txt"
        % ", ".join(faltando))


def checar_ffmpeg():
    """Sem ffmpeg não há extração de áudio, logo não há transcrição."""
    import midia

    caminho = midia.achar_ffmpeg()
    return Resultado(
        "ffmpeg",
        bool(caminho),
        caminho or "não encontrado no PATH nem na pasta do WinGet",
        "winget install Gyan.FFmpeg\n"
        "Depois feche e abra o terminal: o PATH só recarrega em sessão nova.")


def checar_config():
    """O arquivo existe, é JSON válido e tem o que é obrigatório."""
    if not config.CONFIG.exists():
        return Resultado(
            "config.local.json", False, "não existe",
            "copy %s %s\n"
            "Depois preencha a seção `postgres` e o token da Apify."
            % (config.EXEMPLO.name, config.CONFIG.name))

    try:
        config.carregar()
    except config.ErroDeConfig as erro:
        return Resultado("config.local.json", False,
                         "existe, mas está incompleto",
                         str(erro))

    return Resultado("config.local.json", True, str(config.CONFIG))


def checar_postgres(cfg):
    """O servidor responde? É a falha mais comum depois de reiniciar."""
    try:
        with db.conectar(cfg) as conexao:
            versao = conexao.execute("SELECT version()").fetchone()[0]
    except db.ErroDeBanco as erro:
        return Resultado("PostgreSQL no ar", False, db.descrever(cfg),
                         str(erro))
    except Exception as erro:
        # Banco ainda não criado cai aqui. Não é o mesmo problema.
        return Resultado("PostgreSQL no ar", False, db.descrever(cfg),
                         "O servidor respondeu, mas a conexão falhou: %s\n"
                         "Se o banco ainda não existe: preparar.py criar-banco"
                         % erro)

    return Resultado("PostgreSQL no ar", True, versao.split(" on ")[0])


def checar_migrations(cfg):
    """Esquema aplicado é o que separa 'conecta' de 'funciona'."""
    try:
        with db.conectar(cfg) as conexao:
            aplicadas = set(db.versoes_aplicadas(conexao))
    except Exception as erro:
        return Resultado("Migrations", False, "não consegui conferir",
                         "%s\n-> preparar.py criar-banco" % erro)

    todas = [caminho.stem for caminho in db.arquivos_de_migration()]
    pendentes = [v for v in todas if v not in aplicadas]

    return Resultado(
        "Migrations",
        not pendentes,
        "%d de %d aplicadas" % (len(todas) - len(pendentes), len(todas)),
        "Pendente: %s\n"
        ".venv\\Scripts\\python.exe src\\migrar.py aplicar"
        % ", ".join(pendentes))


def checar_pastas():
    """Estas a gente cria na hora: não faz sentido pedir para o usuário."""
    config.garantir_pastas()
    pastas = (config.BUSCAS, config.PERFIS, config.ANALISES, config.SAIDA)
    return Resultado("Pastas de trabalho", True,
                     "%d prontas em %s" % (len(pastas), config.DADOS.parent))


# -------------------------------------------------------------------- comandos


def verificar(_cfg=None):
    """Roda tudo em ordem e devolve 0 se está pronto, 1 se falta algo.

    A ordem importa: sem venv não há psycopg, sem config não há como saber
    onde o banco mora, sem banco não há migration. Parar na primeira falha
    esconderia as outras — então roda todas, mas só tenta as que dependem do
    config se o config carregou.
    """
    print("Preparo do ambiente")
    print("-" * 19)

    resultados = [checar_python(), checar_dependencias(), checar_ffmpeg(),
                  checar_config()]

    if resultados[-1].ok:
        cfg = config.carregar()
        resultados.append(checar_postgres(cfg))
        if resultados[-1].ok:
            resultados.append(checar_migrations(cfg))
        resultados.append(checar_pastas())

    for resultado in resultados:
        resultado.imprimir()

    faltando = [r for r in resultados if not r.ok]
    print()
    if faltando:
        print("%d de %d checagens falharam. Conserte de cima para baixo: uma"
              % (len(faltando), len(resultados)))
        print("falha costuma explicar as de baixo.")
        return 1

    print("Tudo pronto. %d checagens passaram." % len(resultados))
    print("Próximo passo: pipeline.py descobrir \"<nicho>\"")
    return 0


def criar_banco(cfg):
    """Cria o banco (se faltar) e aplica as migrations. Idempotente."""
    print("Preparo do banco")
    print("-" * 16)

    criou = db.garantir_banco(cfg)
    print("%s banco %s" % (OK, "criado" if criou else "já existia"))

    db.migrar(cfg)
    return 0


def main(argv=None):
    console.preparar()
    p = argparse.ArgumentParser(
        description="Confere se a máquina está pronta para rodar o projeto")
    sub = p.add_subparsers(dest="comando", required=True)
    sub.add_parser("verificar", help="o que está pronto e o que falta")
    sub.add_parser("criar-banco", help="cria o banco e aplica as migrations")
    args = p.parse_args(argv)

    if args.comando == "verificar":
        return verificar()

    try:
        cfg = config.carregar()
    except config.ErroDeConfig as erro:
        print("ERRO DE CONFIGURACAO\n\n%s" % erro)
        return 1

    try:
        return criar_banco(cfg)
    except db.ErroDeBanco as erro:
        print("\nERRO DE BANCO\n\n%s" % erro)
        return 1


if __name__ == "__main__":
    sys.exit(main())
