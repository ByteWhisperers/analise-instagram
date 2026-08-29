"""Repositórios: a única camada que escreve SQL.

Um módulo por agregado. Todos recebem a conexão como primeiro argumento e
nenhum abre conexão por conta própria — quem abre é `db.py`, e quem decide
quando commitar é quem chamou.

    import db
    from repos import niches, profiles

    with db.conectar(cfg) as conexao:
        nicho = niches.obter_ou_criar(conexao, "apostas")
        perfil = profiles.salvar(conexao, dados)
        profiles.ligar_ao_nicho(conexao, perfil, nicho)
        conexao.commit()

O commit fica com quem chamou de propósito: gravar perfil, vínculo e snapshot
é uma operação só do ponto de vista de quem coleta, e três commits separados
deixariam o banco num estado meio pronto se o processo morresse no meio.
"""

from ._comum import ErroDeRepositorio

__all__ = ["ErroDeRepositorio"]
