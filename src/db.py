"""Conexao com o PostgreSQL e execucao das migrations.

Um lugar so abre conexao. Um lugar so aplica migration. Nenhum outro modulo
monta string de conexao nem roda DDL.

As migrations sao arquivos `.sql` numerados em `migrations/`, aplicados em
ordem de nome e registrados em `schema_migrations`. Rodar duas vezes nao
reaplica nada — cada arquivo e envolvido pela propria transacao e termina
inserindo a sua versao.

Por que SQL em arquivo e nao um ORM: o modelo tem CHECK, indice parcial,
indice GIN, trigger e constraint composta. Isso e SQL, e escrever SQL como
SQL e mais honesto do que escrever SQL disfarcado de Python.
"""

import re
from pathlib import Path

import config

RAIZ = Path(__file__).resolve().parent.parent
MIGRATIONS = RAIZ / "migrations"

# Nome de arquivo de migration: 001_qualquer_coisa.sql
PADRAO = re.compile(r"^(\d{3,})_[\w-]+\.sql$")


class ErroDeBanco(Exception):
    """Falha de conexao ou de migration. Mensagem pronta para o usuario."""


def _conexao_do_config(cfg):
    pg = dict(cfg.get("postgres") or {})
    faltando = [c for c in ("host", "port", "database", "user", "password")
                if not pg.get(c)]
    if faltando:
        raise ErroDeBanco(
            "Falta configuracao do PostgreSQL em config.local.json: %s"
            % ", ".join(faltando))
    return pg


def parametros_de_conexao(cfg, database=None):
    """Os parametros separados, do jeito que o psycopg prefere.

    Separados e nao em URL porque senha forte tem `/`, `@`, `:` e `[`, e todos
    eles sao delimitadores de URI. Montar a string na mao e depois escapar e
    uma fonte de bug que nao precisa existir.
    """
    pg = _conexao_do_config(cfg)
    return {
        "host": pg["host"],
        "port": int(pg["port"]),
        "dbname": database or pg["database"],
        "user": pg["user"],
        "password": pg["password"],
    }


def string_de_conexao(cfg, database=None):
    """A URL equivalente, com usuario e senha escapados.

    Nao e usada para conectar — serve para montar comando de `psql` quando
    for preciso depurar. **Nunca imprima**: tem a senha dentro.
    """
    from urllib.parse import quote

    p = parametros_de_conexao(cfg, database)
    return "postgresql://%s:%s@%s:%d/%s" % (
        quote(p["user"], safe=""), quote(p["password"], safe=""),
        p["host"], p["port"], p["dbname"])


def descrever(cfg):
    """A mesma informacao, sem a senha. Esta pode ir para a tela."""
    pg = _conexao_do_config(cfg)
    return "%s@%s:%s/%s" % (pg["user"], pg["host"], pg["port"], pg["database"])


def conectar(cfg, database=None, autocommit=False):
    """Abre conexao. Erro de rede vira mensagem, nao stack trace."""
    import psycopg

    try:
        return psycopg.connect(autocommit=autocommit,
                               **parametros_de_conexao(cfg, database))
    except psycopg.OperationalError as erro:
        # A mensagem do driver pode conter a URL inteira, com senha.
        texto = str(erro).replace(_conexao_do_config(cfg)["password"], "***")
        raise ErroDeBanco(
            "Nao consegui falar com o PostgreSQL em %s.\n\n"
            "Confira se o servico esta rodando:\n"
            "  Get-Service *postgres*\n\n"
            "Detalhe tecnico: %s" % (descrever(cfg), texto)) from erro


def garantir_banco(cfg):
    """Cria o banco da aplicacao se ele ainda nao existir.

    Conecta no `postgres`, que sempre existe, porque `CREATE DATABASE` nao
    pode rodar de dentro do banco que esta sendo criado.
    """
    import psycopg
    from psycopg import sql

    alvo = _conexao_do_config(cfg)["database"]

    with conectar(cfg, database="postgres", autocommit=True) as conexao:
        existe = conexao.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (alvo,)).fetchone()
        if existe:
            return False
        try:
            conexao.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(alvo)))
        except psycopg.errors.DuplicateDatabase:
            return False

    return True


def arquivos_de_migration():
    """Os `.sql` de `migrations/`, em ordem numerica."""
    if not MIGRATIONS.is_dir():
        return []
    achados = [a for a in MIGRATIONS.iterdir() if PADRAO.match(a.name)]
    return sorted(achados, key=lambda a: a.name)


def versoes_aplicadas(conexao):
    """O que ja rodou. Banco novo, sem a tabela ainda, devolve vazio."""
    import psycopg

    try:
        linhas = conexao.execute("SELECT version FROM schema_migrations").fetchall()
    except psycopg.errors.UndefinedTable:
        conexao.rollback()
        return set()
    return {linha[0] for linha in linhas}


def migrar(cfg, verboso=True):
    """Aplica o que faltar. Devolve a lista do que foi aplicado agora."""
    garantir_banco(cfg)
    aplicadas_agora = []

    with conectar(cfg) as conexao:
        ja_feitas = versoes_aplicadas(conexao)

        for arquivo in arquivos_de_migration():
            versao = arquivo.stem
            if versao in ja_feitas:
                if verboso:
                    print("  ja aplicada  %s" % versao)
                continue

            sql_bruto = arquivo.read_text(encoding="utf-8")
            try:
                # O proprio arquivo abre e fecha a transacao.
                conexao.execute(sql_bruto)
                conexao.commit()
            except Exception as erro:
                conexao.rollback()
                raise ErroDeBanco(
                    "A migration %s falhou e foi desfeita inteira.\n\n%s"
                    % (versao, erro)) from erro

            aplicadas_agora.append(versao)
            if verboso:
                print("  APLICADA     %s" % versao)

    return aplicadas_agora


def tabelas(cfg):
    """Os nomes das tabelas do schema publico, em ordem."""
    with conectar(cfg) as conexao:
        linhas = conexao.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
            "ORDER BY table_name").fetchall()
    return [linha[0] for linha in linhas]


def tem_pgvector(cfg):
    """Se a extensao vector esta instalada. Enquanto nao estiver, os
    embeddings ficam em `real[]` e nenhum e gerado."""
    with conectar(cfg) as conexao:
        linha = conexao.execute(
            "SELECT 1 FROM pg_extension WHERE extname = 'vector'").fetchone()
    return bool(linha)


def resumo(cfg):
    """Quantas linhas em cada tabela. Serve de diagnostico rapido."""
    from psycopg import sql

    saida = {}
    with conectar(cfg) as conexao:
        for nome in tabelas(cfg):
            linha = conexao.execute(
                sql.SQL("SELECT count(*) FROM {}").format(
                    sql.Identifier(nome))).fetchone()
            saida[nome] = linha[0]
    return saida
