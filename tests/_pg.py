"""Arranjo comum dos testes que precisam de PostgreSQL de verdade.

Cria um banco descartável, aplica as migrations nele e o derruba no fim.
**Nunca encosta no banco real** — o nome é outro, e há uma checagem explícita
para o caso de alguém trocar o nome errado no config.

Se o servidor não estiver de pé, os testes dizem isso com clareza e saem com
código 0 em vez de vermelho: falta de ambiente não é defeito de código.

    from _pg import abrir_banco_de_teste, fechar_banco_de_teste
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import config
import db

SUFIXO = "_teste"


def _cfg_de_teste():
    cfg = config.carregar()
    real = cfg["postgres"]["database"]

    if real.endswith(SUFIXO):
        raise SystemExit(
            "O config aponta para um banco que já termina em '%s'. Não dá "
            "para saber qual é o real. Corrija config.local.json." % SUFIXO)

    cfg = dict(cfg)
    cfg["postgres"] = dict(cfg["postgres"], database=real + SUFIXO)
    return cfg


def abrir_banco_de_teste():
    """Devolve `(cfg, conexao)` num banco limpo, ou encerra explicando.

    O banco é derrubado antes de ser criado: teste que morreu na rodada
    passada não pode deixar sujeira que faça a próxima passar por engano.
    """
    try:
        cfg = _cfg_de_teste()
    except config.ErroDeConfig as erro:
        print("PULADO: %s" % erro)
        raise SystemExit(0)

    alvo = cfg["postgres"]["database"]

    try:
        with db.conectar(cfg, database="postgres", autocommit=True) as adm:
            adm.execute('DROP DATABASE IF EXISTS "%s" WITH (FORCE)' % alvo)
    except db.ErroDeBanco as erro:
        print("PULADO: o PostgreSQL não respondeu.\n")
        print(erro)
        raise SystemExit(0)

    db.migrar(cfg, verboso=False)
    return cfg, db.conectar(cfg)


def fechar_banco_de_teste(cfg, conexao):
    """Fecha e apaga. Roda mesmo se o teste falhou."""
    try:
        conexao.close()
    except Exception:
        pass

    alvo = cfg["postgres"]["database"]
    try:
        with db.conectar(cfg, database="postgres", autocommit=True) as adm:
            adm.execute('DROP DATABASE IF EXISTS "%s" WITH (FORCE)' % alvo)
    except Exception:
        # Não derrubar a suíte por causa da faxina.
        pass


class Placar:
    """Contagem e impressão, no mesmo formato dos testes antigos."""

    def __init__(self):
        self.falhas = []

    def conferir(self, descricao, obtido, esperado):
        if obtido == esperado:
            print("  ok   %s" % descricao)
        else:
            print("  FALHOU  %s\n         esperado: %r\n         obtido:   %r"
                  % (descricao, esperado, obtido))
            self.falhas.append(descricao)

    def conferir_que(self, descricao, condicao):
        if condicao:
            print("  ok   %s" % descricao)
        else:
            print("  FALHOU  %s" % descricao)
            self.falhas.append(descricao)

    def secao(self, titulo):
        print("\n=== %s ===" % titulo)

    def encerrar(self, nome):
        print("\n" + "=" * 52)
        if self.falhas:
            print("%d TESTE(S) FALHARAM:" % len(self.falhas))
            for falha in self.falhas:
                print("  - " + falha)
            sys.exit(1)
        print("Todos os testes de %s passaram." % nome)
