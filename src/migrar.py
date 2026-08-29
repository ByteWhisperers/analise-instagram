"""Gerencia o esquema do PostgreSQL.

    python src/migrar.py aplicar    # cria o banco e aplica o que faltar
    python src/migrar.py status     # o que ja rodou e o que falta
    python src/migrar.py resumo     # quantas linhas em cada tabela

Separado do `pipeline.py` de proposito: mexer em esquema e uma
responsabilidade diferente de rodar a esteira, e misturar as duas faria um
comando de coleta capaz de alterar tabela sem querer.
"""

import argparse
import sys

import console
import config
import db


def aplicar(cfg):
    print("Banco: %s" % db.descrever(cfg))

    if db.garantir_banco(cfg):
        print("Banco de dados criado.")

    print("\nMigrations:")
    aplicadas = db.migrar(cfg)

    if not aplicadas:
        print("\nNada a fazer — o esquema ja estava em dia.")
    else:
        print("\n%d migration(s) aplicada(s)." % len(aplicadas))

    tabelas = db.tabelas(cfg)
    print("%d tabelas no banco." % len(tabelas))

    if not db.tem_pgvector(cfg):
        print()
        print("pgvector NAO esta instalado — esperado por enquanto.")
        print("Os embeddings ficam em REAL[] e nenhum sera gerado nesta fase.")
        print("Quando a extensao entrar, a troca e uma migration:")
        print("  ALTER TABLE embeddings")
        print("    ALTER COLUMN embedding TYPE vector(1536)")
        print("    USING embedding::vector;")

    return 0


def status(cfg):
    print("Banco: %s" % db.descrever(cfg))

    arquivos = db.arquivos_de_migration()
    if not arquivos:
        print("Nenhum arquivo em migrations/.")
        return 1

    with db.conectar(cfg) as conexao:
        feitas = db.versoes_aplicadas(conexao)

    print()
    pendentes = 0
    for arquivo in arquivos:
        versao = arquivo.stem
        if versao in feitas:
            print("  [x] %s" % versao)
        else:
            print("  [ ] %s   PENDENTE" % versao)
            pendentes += 1

    print()
    print("%d aplicada(s), %d pendente(s)." % (len(feitas), pendentes))
    print("pgvector: %s" % ("instalado" if db.tem_pgvector(cfg) else "ausente"))
    return 0


def resumo(cfg):
    print("Banco: %s\n" % db.descrever(cfg))

    contagens = db.resumo(cfg)
    if not contagens:
        print("Nenhuma tabela. Rode: python src/migrar.py aplicar")
        return 1

    largura = max(len(nome) for nome in contagens)
    total = 0
    for nome, quantas in contagens.items():
        print("  %-*s %8d" % (largura, nome, quantas))
        total += quantas

    print("\n%d tabelas, %d linhas no total." % (len(contagens), total))
    return 0


def main(argv=None):
    console.preparar()
    p = argparse.ArgumentParser(description="Esquema do PostgreSQL")
    sub = p.add_subparsers(dest="comando", required=True)
    sub.add_parser("aplicar", help="cria o banco e aplica as migrations")
    sub.add_parser("status", help="o que ja rodou e o que falta")
    sub.add_parser("resumo", help="quantas linhas em cada tabela")
    args = p.parse_args(argv)

    try:
        cfg = config.carregar()
    except config.ErroDeConfig as erro:
        print("ERRO DE CONFIGURACAO\n\n%s" % erro)
        return 1

    try:
        return {"aplicar": aplicar, "status": status,
                "resumo": resumo}[args.comando](cfg)
    except db.ErroDeBanco as erro:
        print("\nERRO DE BANCO\n\n%s" % erro)
        return 1


if __name__ == "__main__":
    sys.exit(main())
