"""Confere o corpus append-only contra PostgreSQL real.

Esta tabela existe para responder duas perguntas que a 005 nao podia:

- "Esse termo e raro FORA desta tribo?" — exclusividade precisa de um
  denominador, e denominador e corpus de fundo.
- "O vocabulario mudou?" — linha sobrescrita nao tem passado.

O que se testa aqui, principalmente, e que gravar de novo **acrescenta** em vez
de sobrescrever. Se algum dia alguem puser um UNIQUE nesta tabela para "evitar
duplicata", e este arquivo que tem de gritar.

    .venv\\Scripts\\python.exe tests\\test_repos_observacoes.py
"""

import sys
from pathlib import Path

from _pg import Placar, abrir_banco_de_teste, fechar_banco_de_teste

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import lexico
from repos import jobs, niches, observacoes

p = Placar()
cfg, cx = abrir_banco_de_teste()


def obs(termo, kind="hashtag", perfil="a", post="p1", idioma="pt",
        fonte="#moto"):
    return {"termo": termo, "kind": kind, "perfil": perfil, "post": post,
            "idioma": idioma, "fonte": fonte}


try:
    nicho = niches.obter_ou_criar(cx, "moto")
    rodada1 = jobs.abrir_coleta(cx, "niche_mapping", "apify")
    rodada2 = jobs.abrir_coleta(cx, "niche_mapping", "apify")

    # ------------------------------------------------------------ gravacao
    p.secao("gravar: a ocorrencia vira contagem, nao linha repetida")

    entraram = observacoes.gravar(
        cx, [obs("grau"), obs("grau"), obs("moto")], job_id=rodada1,
        niche_id=nicho)
    p.conferir("duas ocorrencias do mesmo termo no mesmo post viram UMA linha",
               entraram, 2)

    contagem = observacoes.contagens(cx, job_id=rodada1)
    p.conferir("mas a frequencia nao se perde: vira occurrences",
               contagem["grau"]["posts"], 2)
    p.conferir("termo visto uma vez conta um", contagem["moto"]["posts"], 1)
    p.conferir("a fonte fica registrada", contagem["grau"]["fonte"], "#moto")
    p.conferir("o kind fica registrado", contagem["grau"]["kind"], "hashtag")

    p.conferir("lista vazia nao grava nem estoura",
               observacoes.gravar(cx, [], job_id=rodada1), 0)
    p.conferir("None nao estoura", observacoes.gravar(cx, None), 0)

    # `kind` fechado: tipo novo e migration, nao descuido no meio de um laco.
    try:
        observacoes.gravar(cx, [obs("x", kind="inventado")], job_id=rodada1)
        p.conferir_que("kind invalido devia ter sido recusado", False)
    except ValueError as erro:
        p.conferir_que("kind invalido vira erro nomeado, nao CHECK cru",
                       "inventado" in str(erro))

    # ------------------------------------------------------- append-only
    p.secao("append-only: a rodada nova NAO apaga a antiga")

    observacoes.gravar(cx, [obs("grau", perfil="b", post="p2")],
                       job_id=rodada2, niche_id=nicho)

    tudo = observacoes.contagens(cx, niche_id=nicho)
    p.conferir("as duas rodadas somam", tudo["grau"]["posts"], 3)
    p.conferir("e os perfis das duas aparecem",
               tudo["grau"]["perfis"], ["a", "b"])

    so_a_primeira = observacoes.contagens(cx, job_id=rodada1)
    p.conferir("filtrando pela rodada, so o que ela viu",
               so_a_primeira["grau"]["posts"], 2)
    p.conferir("e o perfil da outra rodada nao entra",
               so_a_primeira["grau"]["perfis"], ["a"])

    # ---------------------------------------------------------- os idiomas
    p.secao("idioma: NULL e 'nao sei', e nao 'nao e portugues'")

    rodada3 = jobs.abrir_coleta(cx, "niche_mapping", "apify")
    observacoes.gravar(cx, [obs("misto", perfil="c", post="p3", idioma="es"),
                            obs("misto", perfil="d", post="p4", idioma="?")],
                       job_id=rodada3)
    linha = observacoes.contagens(cx, job_id=rodada3)["misto"]
    p.conferir("o voto espanhol chega inteiro", linha["idiomas"]["es"], 1)
    p.conferir("'?' vira NULL no banco e volta como '?'",
               linha["idiomas"]["?"], 1)
    p.conferir("e ninguem inventou portugues", linha["idiomas"]["pt"], 0)

    # -------------------------------------------------------- corpus de fundo
    p.secao("fundo: o denominador da exclusividade")

    por_termo, universo = observacoes.fundo(cx)
    p.conferir("`grau` foi visto em dois perfis no mundo todo",
               por_termo["grau"], 2)
    p.conferir_que("o universo de perfis vem junto — contagem sem universo "
                   "nao vira probabilidade", universo >= 4)

    sem_a_propria, _ = observacoes.fundo(cx, excluir_job_id=rodada2)
    p.conferir("excluindo a rodada, ela sai da conta do fundo",
               sem_a_propria["grau"], 1)

    # Sem isto, o termo que so esta rodada viu apareceria como "comum no
    # mundo" por causa dela mesma, e a exclusividade se mediria contra si.
    p.conferir_que("e o termo que so aquela rodada viu some do fundo",
                   "grau" in sem_a_propria)

    # ---------------------------------------------------------- serie no tempo
    p.secao("serie: a pergunta que a 005 nao podia responder")

    dias = observacoes.serie(cx, "grau", niche_id=nicho)
    p.conferir("o termo tem historia por dia", len(dias), 1)
    p.conferir("com os dois perfis do dia", dias[0]["perfis"], 2)
    p.conferir("termo que ninguem viu devolve serie vazia",
               observacoes.serie(cx, "inexistente"), [])

    # ------------------------------------------------- materia-prima do grafo
    p.secao("perfis_por_termo: conjuntos, para o Jaccard da Fase 2")

    mapa = observacoes.perfis_por_termo(cx, niche_id=nicho)
    p.conferir_que("devolve conjunto e nao lista",
                   isinstance(mapa["grau"], set))
    p.conferir("com os perfis distintos", mapa["grau"], {"a", "b"})

    cortado = observacoes.perfis_por_termo(cx, niche_id=nicho,
                                           minimo_de_perfis=2)
    p.conferir_que("o corte tira a cauda de termo visto uma vez so",
                   "moto" not in cortado)
    p.conferir_que("e mantem o que tem lastro", "grau" in cortado)

    # ------------------------------------------------------- descarte honesto
    p.secao("apagar_rodada: append-only nao e imutavel para sempre")

    saiu = observacoes.apagar_rodada(cx, rodada2)
    p.conferir("a rodada envenenada sai inteira", saiu, 1)
    depois = observacoes.contagens(cx, niche_id=nicho)
    p.conferir("e o que sobrou e so a outra rodada",
               depois["grau"]["posts"], 2)
    p.conferir("o perfil que so ela tinha sumiu",
               depois["grau"]["perfis"], ["a"])

    # ------------------------------------------------ integracao com o lexico
    p.secao("o que o lexico produz entra sem traducao no meio")

    rodada4 = jobs.abrir_coleta(cx, "niche_mapping", "apify")
    do_lexico = lexico.observacoes(
        texto="dar grau na quebrada 🏍️", hashtags=["#grau"],
        perfil="ze", post="p9", fonte="#moto", voto="pt")
    quantas = observacoes.gravar(cx, do_lexico, job_id=rodada4)
    p.conferir_que("as observacoes do lexico gravam direto", quantas > 0)

    reconstruido = observacoes.contagens(cx, job_id=rodada4)
    p.conferir_que("e voltam com os kinds do lexico",
                   {reconstruido[t]["kind"] for t in reconstruido}
                   <= set(lexico.KINDS))
    p.conferir_que("o emoji sobreviveu a ida e volta do banco",
                   any(v["kind"] == "emoji" for v in reconstruido.values()))
    p.conferir_que("o bigrama tambem", "dar grau" in reconstruido)

    cx.commit()

finally:
    fechar_banco_de_teste(cfg, cx)

p.encerrar("observacoes")
