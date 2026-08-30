"""Confere a decisao do mapeamento: ranquear, saturar, medir, montar dossie.

Nada de rede, nada de banco, nada de dolar. Tudo aqui e funcao pura — que e
justamente por que `mapeador.py` existe separado do `pipeline.py`.

    .venv\\Scripts\\python.exe tests\\test_mapeador.py
"""

import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import config

TEMPORARIA = Path(tempfile.mkdtemp(prefix="teste-mapeador-"))
config.DADOS = TEMPORARIA

import mapeador

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


print("=== as sementes: o tema em portugues NAO e uma hashtag ===")

# `[MEDIDO 30/08/2026]` A primeira versao do mapeamento pediu
# `#desastresetragedias` e recebeu 1 item e ZERO termos. Ninguem escreve assim.
conferir("a ligacao 'e' nao entra nas palavras soltas",
         mapeador.sementes_do_tema("desastres e tragedias"),
         ["desastresetragedias", "desastres", "tragedias"])
conferir("tema de uma palavra tem uma semente so",
         mapeador.sementes_do_tema("receitas"), ["receitas"])
conferir("preposicao tambem e ligacao",
         mapeador.sementes_do_tema("bolo de chocolate"),
         ["bolodechocolate", "bolo", "chocolate"])
conferir("a concatenacao vem PRIMEIRO: as vezes ela e a tag certa",
         mapeador.sementes_do_tema("cirurgia plastica")[0], "cirurgiaplastica")
conferir("palavra repetida nao vira duas sementes",
         mapeador.sementes_do_tema("carro carro"), ["carrocarro", "carro"])
conferir("tema vazio nao tem semente", mapeador.sementes_do_tema("   "), [])
conferir("tema so de ligacoes ainda devolve a concatenacao",
         mapeador.sementes_do_tema("de e da"), ["deeda"])


print("=== fundir o vocabulario de duas rodadas ===")

RODADA_1 = {"receitas": {"posts": 3, "perfis": ["a", "b"], "fonte": "#receitas"},
            "publi": {"posts": 9, "perfis": ["a"], "fonte": "#receitas"}}
RODADA_2 = {"receitas": {"posts": 2, "perfis": ["b", "c"], "fonte": "relacionados"},
            "bolo": {"posts": 1, "perfis": ["c"], "fonte": "relacionados"}}

fundido = mapeador.fundir_contagens(RODADA_1, RODADA_2)
conferir("posts somam entre rodadas", fundido["receitas"]["posts"], 5)
conferir("perfil repetido nao conta duas vezes",
         sorted(fundido["receitas"]["perfis"]), ["a", "b", "c"])
conferir("tag que so a segunda rodada viu entra", fundido["bolo"]["posts"], 1)
conferir("fundir nao altera a entrada", RODADA_1["receitas"]["posts"], 3)
conferir("fundir com vazio devolve copia",
         mapeador.fundir_contagens({}, RODADA_2)["bolo"]["posts"], 1)
conferir("fundir dois vazios nao estoura", mapeador.fundir_contagens(None, None), {})


print("\n=== ranquear: perfis distintos mandam, nao frequencia ===")

# `[MEDIDO 30/08/2026]` As hashtags reais de @receitasdepai trouxeram `publi`,
# `MercadoLivre`, `PagBank` e `AeC440` — propaganda, nao receita. Elas aparecem
# MUITO, mas num perfil so. Este e o teste que garante que elas afundam.
COM_PROPAGANDA = {
    "receitas": {"posts": 4, "perfis": ["a", "b", "c", "d"], "fonte": "#x"},
    "publi": {"posts": 40, "perfis": ["a"], "fonte": "#x"},
    "mercadolivre": {"posts": 25, "perfis": ["a"], "fonte": "#x"},
    "sobremesa": {"posts": 3, "perfis": ["b", "c"], "fonte": "#x"},
}
ranking = mapeador.ranquear_termos(COM_PROPAGANDA)

conferir("a tag do nicho vence a propaganda que aparece 10x mais",
         ranking[0]["termo"], "receitas")
conferir("segunda e a que dois perfis usam", ranking[1]["termo"], "sobremesa")
conferir_que("a tag de propaganda afunda, mesmo com 40 posts",
             [l["termo"] for l in ranking].index("publi") >= 2)
conferir("entre duas de um perfil so, mais posts desempata",
         [l["termo"] for l in ranking][2], "publi")
conferir("o ranking carrega a evidencia junto",
         (ranking[0]["perfis"], ranking[0]["posts"]), (4, 4))
conferir("e diz quem usa", ranking[0]["quem"], ["a", "b", "c", "d"])

conferir("corte por minimo de perfis descarta o que so um perfil usa",
         [l["termo"] for l in
          mapeador.ranquear_termos(COM_PROPAGANDA, minimo_de_perfis=2)],
         ["receitas", "sobremesa"])
conferir("limite corta a lista", len(mapeador.ranquear_termos(COM_PROPAGANDA,
                                                              limite=2)), 2)
conferir("ranquear vazio devolve vazio", mapeador.ranquear_termos({}), [])


print("\n=== saturacao: quando parar de gastar ===")

conferir("primeira rodada nunca satura — nao ha 'antes'",
         mapeador.saturou(set(), {"a", "b", "c"}), False)
conferir("rodada que nao trouxe nada satura",
         mapeador.saturou({"a"}, set()), True)
conferir("tudo novo nao satura",
         mapeador.saturou({"a"}, {"x", "y", "z"}), False)
conferir("1 inedito em 10 satura (10% < 20%)",
         mapeador.saturou(set("abcdefghi"), set("abcdefghij")), True)
conferir("3 ineditos em 10 nao satura (30% > 20%)",
         mapeador.saturou(set("abcdefg"), set("abcdefghij")), False)
conferir("o limiar e ajustavel",
         mapeador.saturou(set("abcdefg"), set("abcdefghij"), limiar=0.50), True)


print("\n=== percentil: sem interpolar, para apontar perfil que existe ===")

VALORES = [11895, 26846, 107713, 172465, 956725, 1461456, 3139033]
conferir("p0 e o menor", mapeador.percentil(VALORES, 0), 11895)
conferir("p100 e o maior", mapeador.percentil(VALORES, 100), 3139033)
conferir("p50 e a mediana", mapeador.percentil(VALORES, 50), 172465)
conferir_que("o percentil e um valor que EXISTE na lista",
             mapeador.percentil(VALORES, 25) in VALORES)
conferir("lista vazia devolve None", mapeador.percentil([], 50), None)
conferir("None no meio nao entra na conta",
         mapeador.percentil([None, 10, None, 20, 30], 50), 20)
conferir("um valor so devolve ele mesmo", mapeador.percentil([42], 90), 42)


print("\n=== os numeros do nicho, e a banda que eles sugerem ===")

PERFIS = [{"seguidores": n} for n in VALORES]
POSTS = [
    {"perfil": "a", "duracao_segundos": 41, "data_utc": "2026-08-20T12:00:00+00:00"},
    {"perfil": "a", "duracao_segundos": 57, "data_utc": "2026-08-22T12:00:00+00:00"},
    {"perfil": "a", "duracao_segundos": 71, "data_utc": "2026-08-24T12:00:00+00:00"},
    {"perfil": "b", "duracao_segundos": 131, "data_utc": "2026-08-01T12:00:00+00:00"},
    {"perfil": "b", "duracao_segundos": 87, "data_utc": "2026-08-11T12:00:00+00:00"},
]

numeros = mapeador.numeros_do_nicho(PERFIS, POSTS)
conferir("conta quantos perfis entraram na medicao",
         numeros["perfis_medidos"], 7)
conferir("mediana de seguidores", numeros["seguidores_p50"], 172465)
conferir("a banda sugerida e p25-p75, nao os extremos",
         (numeros["banda_sugerida"]["seguidores_min"],
          numeros["banda_sugerida"]["seguidores_max"]),
         (numeros["seguidores_p25"], numeros["seguidores_p75"]))
conferir_que("a banda vem com a conta que a justifica",
             "7 perfis medidos" in numeros["banda_sugerida"]["por_que"])
conferir("duracao mediana dos videos", numeros["duracao_p50"], 71)
conferir("ritmo: 2 dias em um perfil, 10 no outro -> mediana 6",
         numeros["ritmo_dias_entre_posts"], 6.0)

vazio = mapeador.numeros_do_nicho([], [])
conferir("sem perfil medido, a banda nao inventa numero",
         (vazio["banda_sugerida"]["seguidores_min"],
          vazio["banda_sugerida"]["seguidores_max"]), (None, None))
conferir_que("e diz em portugues que nao mediu nada",
             "nenhum perfil" in vazio["banda_sugerida"]["por_que"])
conferir("sem post, o ritmo e None e nao zero",
         vazio["ritmo_dias_entre_posts"], None)
conferir("perfil com um post so nao tem intervalo",
         mapeador.numeros_do_nicho(
             PERFIS, [{"perfil": "a", "data_utc": "2026-08-20T12:00:00+00:00"}]
         )["ritmo_dias_entre_posts"], None)
conferir("data ilegivel e ignorada em vez de estourar",
         mapeador.numeros_do_nicho(
             PERFIS, [{"perfil": "a", "data_utc": "ontem"},
                      {"perfil": "a", "data_utc": "anteontem"}]
         )["ritmo_dias_entre_posts"], None)


print("\n=== o dossie: nada entra sozinho ===")

dossie = mapeador.montar_dossie("Desastres e Tragedias", COM_PROPAGANDA,
                                [{"usuario": "a", "seguidores": 50000},
                                 {"usuario": "b", "seguidores": 900000}],
                                POSTS, custo_usd=0.0123, rodadas=2,
                                parou_por="saturacao")

conferir("o tema fica no dossie", dossie["tema"], "Desastres e Tragedias")
conferir("registra por que parou", dossie["parou_por"], "saturacao")
conferir("registra o custo", dossie["custo_usd"], 0.0123)
conferir_que("TODA tag nasce com entra=false",
             all(t["entra"] is False for t in dossie["tags"]))
conferir_que("TODO perfil nasce com entra=false",
             all(p["entra"] is False for p in dossie["perfis"]))
conferir("as tags vem ranqueadas", dossie["tags"][0]["termo"], "receitas")
conferir("os perfis vem do maior para o menor",
         [p["usuario"] for p in dossie["perfis"]], ["b", "a"])
conferir_que("o dossie explica como aprovar",
             "entra" in dossie["_como_aprovar"]
             and "--aplicar" in dossie["_como_aprovar"]
             or "aplicar" in dossie["_como_aprovar"])

conferir("sem nada marcado, nada e aprovado",
         mapeador.aprovados(dossie, "tags"), [])

dossie["tags"][0]["entra"] = True
dossie["tags"][2]["entra"] = True
conferir("aprovados devolve so o que foi marcado",
         [t["termo"] for t in mapeador.aprovados(dossie, "tags")],
         [dossie["tags"][0]["termo"], dossie["tags"][2]["termo"]])


print("\n=== o dossie no disco ===")

destino = mapeador.gravar_dossie(dossie)
conferir_que("grava em dados/mapeamentos/", destino.parent.name == "mapeamentos")
conferir("o nome do arquivo e a tag do tema", destino.name,
         "desastresetragedias.json")

lido = mapeador.ler_dossie("Desastres e Tragedias")
conferir("le de volta o que gravou", lido["tema"], dossie["tema"])
conferir("e preserva a aprovacao",
         len(mapeador.aprovados(lido, "tags")), 2)
conferir_que("acha o dossie mesmo escrevendo o tema diferente",
             mapeador.ler_dossie("DESASTRES E TRAGEDIAS")["tema"]
             == dossie["tema"])

try:
    mapeador.ler_dossie("um tema que ninguem mapeou")
    conferir_que("ler dossie inexistente devia estourar", False)
except mapeador.ErroDeMapeamento as erro:
    conferir_que("dossie inexistente explica como criar",
                 "mapear" in str(erro))

print("\n=== T15: o idioma da tag, e o que se faz com ele ===")

ESPANHOLA = {"posts": 9, "perfis": ["a", "b"],
             "idiomas": {"pt": 0, "es": 7, "?": 2}, "fonte": "#x"}
PORTUGUESA = {"posts": 5, "perfis": ["c"],
              "idiomas": {"pt": 4, "es": 1, "?": 0}, "fonte": "#x"}
MUDA = {"posts": 6, "perfis": ["d"],
        "idiomas": {"pt": 0, "es": 0, "?": 6}, "fonte": "#x"}
EMPATE = {"posts": 4, "perfis": ["e"],
          "idiomas": {"pt": 2, "es": 2, "?": 0}, "fonte": "#x"}

conferir("maioria espanhola", mapeador.idioma_da_tag(ESPANHOLA), "es")
conferir("maioria portuguesa", mapeador.idioma_da_tag(PORTUGUESA), "pt")
conferir("so mudos nao elegem", mapeador.idioma_da_tag(MUDA), None)
conferir("empate nao elege", mapeador.idioma_da_tag(EMPATE), None)

conferir("espanhola e descartada quando o alvo e pt",
         mapeador.e_de_outro_idioma(ESPANHOLA, "pt"), True)
conferir("portuguesa fica", mapeador.e_de_outro_idioma(PORTUGUESA, "pt"), False)

# A mitigacao combinada: descarta-se o que foi PROVADO de outro idioma, nunca o
# que nao se sabe. Descartar o desconhecido mataria calado a tag do post sem
# legenda — e o pedido foi descartar o que nao e portugues, nao o que nao se
# sabe se e.
conferir("a tag MUDA nao e descartada: nao saber nao e saber que nao",
         mapeador.e_de_outro_idioma(MUDA, "pt"), False)
conferir("nem a empatada", mapeador.e_de_outro_idioma(EMPATE, "pt"), False)
conferir("com alvo 'qualquer' nada e descartado",
         mapeador.e_de_outro_idioma(ESPANHOLA, "qualquer"), False)
conferir("sem alvo nenhum, nada e descartado",
         mapeador.e_de_outro_idioma(ESPANHOLA, None), False)

conferir("fundir soma os votos de idioma",
         mapeador.fundir_contagens({"t": ESPANHOLA}, {"t": PORTUGUESA})
         ["t"]["idiomas"],
         {"pt": 4, "es": 8, "?": 2})
conferir("fundir com quem nao tem idiomas nao estoura",
         mapeador.fundir_contagens(
             {"t": {"posts": 1, "perfis": ["z"], "fonte": None}},
             {})["t"]["idiomas"], {"pt": 0, "es": 0, "?": 0})

ranking = mapeador.ranquear_termos({"es_tag": ESPANHOLA, "pt_tag": PORTUGUESA,
                                    "muda": MUDA})
conferir("o ranking carrega o idioma detectado",
         {l["termo"]: l["idioma"] for l in ranking},
         {"es_tag": "es", "pt_tag": "pt", "muda": "?"})


print("\n=== T15: quem e nucleo do nicho, e nao quem passou por ali ===")

# `a` aparece em tres tags, `d` numa so. Antes a escolha era por ordem de
# chegada, e a aba da tag vem por recencia — media-se quem tinha postado por
# ultimo.
TEIA = {
    "forte1": {"posts": 9, "perfis": ["a", "b", "c"], "idiomas": {}, "fonte": None},
    "forte2": {"posts": 8, "perfis": ["a", "b"], "idiomas": {}, "fonte": None},
    "forte3": {"posts": 7, "perfis": ["a"], "idiomas": {}, "fonte": None},
    "fraca": {"posts": 1, "perfis": ["d"], "idiomas": {}, "fonte": None},
}
nucleo = mapeador.ranquear_perfis(TEIA)
conferir("quem aparece em mais tags fortes vem primeiro",
         [l["usuario"] for l in nucleo], ["a", "b", "c", "d"])
conferir("e conta em quantas", nucleo[0]["tags_fortes"], 3)
conferir("o limite corta", len(mapeador.ranquear_perfis(TEIA, limite=2)), 2)
conferir("sem contagens, ninguem", mapeador.ranquear_perfis({}), [])


print("\n=== T15: o descartado nao some do dossie ===")

COM_ESPANHOL = {"emergencias": ESPANHOLA, "receita": PORTUGUESA,
                "nepal": MUDA}
dossie_pt = mapeador.montar_dossie("tema", COM_ESPANHOL, [], [], alvo="pt")

# `nepal` vem antes de `receita` porque empatam em perfis (1) e desempatam
# por posts (6 contra 5) — a ordem e a do ranqueamento, nao a do alfabeto.
conferir("a espanhola sai da lista principal",
         [t["termo"] for t in dossie_pt["tags"]], ["nepal", "receita"])
conferir("mas aparece na secao de descartados",
         [t["termo"] for t in dossie_pt["descartados_por_idioma"]],
         ["emergencias"])
conferir_que("com o idioma que a condenou",
             dossie_pt["descartados_por_idioma"][0]["idioma"] == "es")
conferir_que("e com os votos, para voce conferir o veredito",
             dossie_pt["descartados_por_idioma"][0]["votos"]["es"] == 7)
conferir_que("o dossie explica que da para repescar",
             "mover a linha" in dossie_pt["_sobre_os_descartados"])
conferir("o alvo fica registrado", dossie_pt["idioma_alvo"], "pt")
conferir_que("descartado tambem nasce entra=false",
             all(t["entra"] is False
                 for t in dossie_pt["descartados_por_idioma"]))

dossie_qualquer = mapeador.montar_dossie("tema", COM_ESPANHOL, [], [],
                                         alvo="qualquer")
conferir("com alvo 'qualquer' nada e descartado",
         len(dossie_qualquer["descartados_por_idioma"]), 0)
conferir("e as tres ficam na lista principal",
         len(dossie_qualquer["tags"]), 3)

shutil.rmtree(TEMPORARIA, ignore_errors=True)

print("\n" + "=" * 52)
if falhas:
    print("%d TESTE(S) FALHARAM:" % len(falhas))
    for falha in falhas:
        print("  - " + falha)
    sys.exit(1)
print("Todos os testes do mapeador passaram.")
