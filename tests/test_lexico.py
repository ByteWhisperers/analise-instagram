"""Confere o colhedor de lexico. A legenda ja foi paga; isto le o que veio.

O modulo existe porque ate a T15 o mapeamento colhia um campo so — `hashtags`
— e jogava a legenda fora. Tudo que distingue uma tribo da outra estava naquele
texto: giria, emoji, abreviacao, expressao de duas palavras, mencao.

Estes testes cobrem principalmente os tres lugares onde e facil contar a mesma
coisa duas vezes (mencao virando palavra, muralha de hashtag afogando a prosa,
campo do Actor somando com o regex) e o agrupamento de emoji, que e a parte
escrita a mao.

    .venv\\Scripts\\python.exe tests\\test_lexico.py
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import console
console.preparar()

import lexico

falhas = []


def conferir(descricao, obtido, esperado):
    if obtido == esperado:
        print("  ok   %s" % descricao)
    else:
        print("  FALHOU  %s\n         esperado: %r\n         obtido:   %r"
              % (descricao, esperado, obtido))
        falhas.append(descricao)


def conferir_que(descricao, condicao):
    if condicao:
        print("  ok   %s" % descricao)
    else:
        print("  FALHOU  %s" % descricao)
        falhas.append(descricao)


# A legenda que o desenho inteiro tenta enxergar: territorio (`moto`, `grau`)
# misturado com marcador de pertencimento (`quebrada`, `menor`, `caô`).
LEGENDA = ("Hoje foi daquele jeito 🏍️💨 dar grau na quebrada com os menor, "
           "sem caô! Olha https://x.com/a #grau #244 #motoclube @fulano_mt 🇧🇷")


print("=== palavras: o que vale e o que e ligacao ===")

palavras = lexico.palavras_do_texto(LEGENDA)
conferir_que("a giria da tribo sobrevive", "quebrada" in palavras)
conferir_que("palavra com acento mantem o acento", "caô" in palavras)
conferir_que("artigo nao vira vocabulario", "os" not in palavras)
conferir_que("preposicao nao vira vocabulario", "com" not in palavras)
conferir_que("verbo comum SOBREVIVE — `dar grau` e a expressao da tribo",
             "dar" in palavras)

# MINIMO_DE_LETRAS e 2 e nao 3 por causa deste caso.
conferir_que("palavra de duas letras que nao e ligacao entra",
             "fé" in lexico.palavras_do_texto("tudo na fé irmao"))

conferir("texto vazio nao estoura", lexico.palavras_do_texto(""), [])
conferir("None nao estoura", lexico.palavras_do_texto(None), [])

# `[MEDIDO 30/08/2026]` `244` E o nome da tribo. Um regex que so aceitasse
# letra apagaria justamente o termo mais identitario do caso que originou isto.
conferir_que("numero e palavra: `244` e o nome da tribo",
             "244" in lexico.palavras_do_texto("os menor da 244 colou"))


print("\n=== o que NAO pode virar palavra ===")

conferir_que("URL nao vira vocabulario", "https" not in palavras)
conferir_que("dominio da URL nao vira vocabulario", "com" not in palavras)
# A mencao tem `kind` proprio. Sem limpar antes, `@fulano_mt` se partia em
# `fulano` e `mt`, porque sublinhado nao e letra para o regex de palavra.
conferir_que("mencao nao se parte em palavras (fulano)",
             "fulano" not in palavras)
conferir_que("mencao nao se parte em palavras (mt)", "mt" not in palavras)
# Legenda de Instagram termina em muralha de hashtag. Sem tirar, trinta tags
# no fim do post afogariam o vocabulario real da prosa.
conferir_que("texto da hashtag nao vira palavra tambem",
             "motoclube" not in palavras)


print("\n=== bigramas: a expressao, nao a palavra ===")

bigramas = lexico.bigramas_do_texto(LEGENDA)
conferir_que("`dar grau` sobrevive inteiro", "dar grau" in bigramas)
# Montado ANTES de tirar as vazias: tirando primeiro, `sem caô` viraria `caô`
# e a expressao inteira e que e o marcador.
conferir_que("`sem caô` sobrevive, apesar de `sem` ser ligacao",
             "sem caô" in bigramas)
conferir_que("par de duas ligacoes e descartado",
             "de que" not in lexico.bigramas_do_texto("isso de que eu falo"))
conferir("uma palavra so nao forma bigrama",
         lexico.bigramas_do_texto("grau"), [])


print("\n=== emoji: agrupado a mao, sem dependencia nova ===")

conferir("a moto com seletor de variacao e UM emoji",
         lexico.emojis_do_texto("🏍️"), ["🏍️"])
conferir("bandeira e UM emoji, nao dois indicadores regionais",
         lexico.emojis_do_texto("🇧🇷"), ["🇧🇷"])
conferir("familia com ZWJ e UM emoji, nao tres pessoas",
         len(lexico.emojis_do_texto("👨‍👩‍👧")), 1)
conferir("tom de pele nao vira termo proprio",
         len(lexico.emojis_do_texto("👍🏽")), 1)
conferir("dois emojis seguidos sao dois",
         lexico.emojis_do_texto("🏍️💨"), ["🏍️", "💨"])
conferir("texto sem emoji devolve lista vazia",
         lexico.emojis_do_texto("dar grau na quebrada"), [])
conferir_que("letra comum nao e emoji", not lexico.e_emoji("a"))


print("\n=== campo do Actor manda; o regex e plano B ===")

# Somar os dois contaria a mesma tag duas vezes, e a contagem de posts sustenta
# todo o ranqueamento.
com_campo = lexico.observacoes(texto=LEGENDA, hashtags=["#grau"],
                               perfil="ze", post="p1", voto="pt")
conferir("com o campo preenchido, so o campo conta",
         sorted(lexico.contar(com_campo, kinds=("hashtag",))), ["grau"])

sem_campo = lexico.observacoes(texto=LEGENDA, hashtags=[], perfil="ze",
                               post="p1", voto="pt")
conferir("com o campo vazio, a legenda e o plano B",
         sorted(lexico.contar(sem_campo, kinds=("hashtag",))),
         ["244", "grau", "motoclube"])

conferir("a mencao sai da legenda quando nao ha campo",
         sorted(lexico.contar(sem_campo, kinds=("mencao",))), ["fulano_mt"])
conferir("com campo de mencao, o campo manda",
         sorted(lexico.contar(
             lexico.observacoes(texto=LEGENDA, mencoes=["@outro"]),
             kinds=("mencao",))), ["outro"])

conferir("hashtag perde o # e vira chave limpa",
         sorted(lexico.contar(
             lexico.observacoes(hashtags=["#Grau", "GRAU"]),
             kinds=("hashtag",))), ["grau"])
conferir_que("hashtag vazia nao vira termo",
             lexico.contar(lexico.observacoes(hashtags=["", "  ", None]),
                           kinds=("hashtag",)) == {})


print("\n=== contar: a mesma forma de sempre, mais o kind ===")

# `contar` devolve de proposito a MESMA forma que `tags_dos_itens` sempre
# devolveu, para `fundir_contagens` e `ranquear_termos` continuarem valendo.
duas = (lexico.observacoes(texto="dar grau", hashtags=["grau"], perfil="a",
                           post="p1", voto="pt", fonte="#moto")
        + lexico.observacoes(texto="grau demais", hashtags=["grau"],
                             perfil="b", post="p2", voto="es", fonte="#moto"))
contagem = lexico.contar(duas, kinds=("hashtag",))
conferir("dois posts com a mesma tag contam dois",
         contagem["grau"]["posts"], 2)
conferir("e dois perfis distintos",
         sorted(contagem["grau"]["perfis"]), ["a", "b"])
conferir("os votos de idioma sao somados",
         contagem["grau"]["idiomas"], {"pt": 1, "es": 1, "?": 0})
conferir("a fonte fica registrada", contagem["grau"]["fonte"], "#moto")
conferir("o kind fica registrado", contagem["grau"]["kind"], "hashtag")

conferir_que("kinds=None conta tudo",
             len(lexico.contar(duas)) > len(contagem))
conferir("sem observacoes nao estoura", lexico.contar(None), {})
conferir("voto invalido vira '?', nao inventa idioma",
         lexico.contar(lexico.observacoes(hashtags=["x"], voto="fr"),
                       kinds=("hashtag",))["x"]["idiomas"],
         {"pt": 0, "es": 0, "?": 1})

# Perfil None nao pode virar um "perfil" chamado None: o ranqueamento conta
# perfis distintos, e um None na lista viraria um perfil fantasma.
conferir("perfil desconhecido nao entra na lista de perfis",
         lexico.contar(lexico.observacoes(hashtags=["x"], perfil=None),
                       kinds=("hashtag",))["x"]["perfis"], [])

conferir_que("todo kind produzido esta na lista fechada KINDS",
             all(o["kind"] in lexico.KINDS
                 for o in lexico.observacoes(texto=LEGENDA,
                                             hashtags=["grau"],
                                             mencoes=["alguem"])))


print("\n" + "=" * 52)
if falhas:
    print("%d TESTE(S) FALHARAM:" % len(falhas))
    for falha in falhas:
        print("  - " + falha)
    sys.exit(1)
print("Todos os testes de lexico passaram.")
