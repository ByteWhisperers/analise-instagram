"""Confere o banco e as consultas com dados sinteticos.

Cria um banco descartavel numa pasta temporaria. Nao encosta no banco real.

    .venv\\Scripts\\python.exe tests\\test_banco.py
"""

import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import config

# Aponta o projeto inteiro para uma pasta temporaria ANTES de importar o banco.
TEMPORARIA = Path(tempfile.mkdtemp(prefix="teste-analise-"))
config.DADOS = TEMPORARIA
config.BUSCAS = TEMPORARIA / "buscas"
config.PERFIS = TEMPORARIA / "perfis"
config.ANALISES = TEMPORARIA / "analises"
config.SAIDA = TEMPORARIA / "saida"
config.SESSOES = TEMPORARIA / "sessoes"

import banco
import consultas

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


def perfil(usuario, seguidores):
    return {"usuario": usuario, "nome": usuario.title(), "bio": "bio",
            "seguidores": seguidores, "seguindo": 100, "posts": 500,
            "privado": False, "verificado": False, "link_externo": None}


def post(id_post, usuario, curtidas, comentarios, tags, video=True,
         visualizacoes=None, hora="19:30"):
    return {
        "id": id_post, "perfil": usuario,
        "link": "https://www.instagram.com/p/%s/" % id_post,
        "tipo": "video" if video else "carrossel",
        "typename": "GraphVideo" if video else "GraphSidecar",
        "e_video": video, "duracao_segundos": 30.0 if video else None,
        "visualizacoes": visualizacoes,
        "legenda": "Legenda de teste #%s" % tags[0],
        "hashtags": tags, "mencoes": ["algum_parceiro"],
        "curtidas": curtidas, "comentarios": comentarios,
        "data_utc": "2026-08-20T22:30:00", "data_local": "2026-08-20T19:30:00",
        "dia_da_semana": "Thursday", "hora": hora,
    }


print("=== esquema ===")
conexao = banco.conectar()
conferir_que("banco criado em disco", banco.caminho().exists())
conferir("todas as tabelas vazias no inicio",
         sum(banco.resumo(conexao).values()), 0)

banco.criar_esquema(conexao)
conferir("criar_esquema de novo nao quebra nem duplica",
         sum(banco.resumo(conexao).values()), 0)

print("\n=== gravar perfis e posts ===")
banco.salvar_perfil(conexao, perfil("mestre_odds", 100000))
banco.salvar_perfil(conexao, perfil("banca_verde", 50000))

banco.salvar_post(conexao, post("AAA", "mestre_odds", 5000, 200,
                                ["apostas", "bet", "tigrinho"],
                                visualizacoes=90000))
banco.salvar_post(conexao, post("BBB", "mestre_odds", 1000, 20,
                                ["apostas", "cassino"], visualizacoes=20000))
banco.salvar_post(conexao, post("CCC", "banca_verde", 2500, 300,
                                ["apostas", "bet"], video=False, hora="12:00"))

resumo = banco.resumo(conexao)
conferir("2 perfis gravados", resumo["perfis"], 2)
conferir("3 posts gravados", resumo["posts"], 3)
conferir("7 pares (post, hashtag)", resumo["hashtags"], 7)

print("\n=== gravar de novo nao duplica (retomavel) ===")
banco.salvar_perfil(conexao, perfil("mestre_odds", 101000))
banco.salvar_post(conexao, post("AAA", "mestre_odds", 5500, 210,
                                ["apostas", "bet", "tigrinho"],
                                visualizacoes=95000))
resumo = banco.resumo(conexao)
conferir("continua com 2 perfis", resumo["perfis"], 2)
conferir("continua com 3 posts", resumo["posts"], 3)
conferir("continua com 7 hashtags", resumo["hashtags"], 7)
conferir("seguidores foram atualizados",
         conexao.execute("SELECT seguidores FROM perfis WHERE usuario='mestre_odds'"
                         ).fetchone()[0], 101000)
conferir("curtidas foram atualizadas",
         conexao.execute("SELECT curtidas FROM posts WHERE id='AAA'").fetchone()[0],
         5500)

print("\n=== hashtag que sai da legenda tambem sai do banco ===")
banco.salvar_post(conexao, post("BBB", "mestre_odds", 1000, 20, ["apostas"],
                                visualizacoes=20000))
conferir("post BBB agora tem 1 hashtag",
         conexao.execute("SELECT COUNT(*) FROM hashtags WHERE post_id='BBB'"
                         ).fetchone()[0], 1)

print("\n=== transcricao, trechos e palavras ===")
banco.salvar_transcricao(conexao, "AAA", {
    "texto": "Para com isso agora. Voce esta doando dinheiro no bonus.",
    "gancho_falado": "Para com isso agora.",
    "duracao_audio_segundos": 30.0,
    "tempo_de_transcricao_segundos": 14.7,
    "modelo": "small", "idioma": "pt",
    "segmentos": [
        {"inicio": 0.0, "fim": 2.4, "texto": "Para com isso agora."},
        {"inicio": 2.5, "fim": 8.0, "texto": "Voce esta doando dinheiro no bonus."},
    ],
    "palavras": [
        {"palavra": "Para", "inicio": 0.0, "fim": 0.4},
        {"palavra": "com", "inicio": 0.4, "fim": 0.6},
        {"palavra": "isso", "inicio": 0.6, "fim": 1.0},
        {"palavra": "agora", "inicio": 1.0, "fim": 2.4},
    ],
})
resumo = banco.resumo(conexao)
conferir("1 transcricao", resumo["transcricoes"], 1)
conferir("2 trechos", resumo["segmentos"], 2)
conferir("4 palavras", resumo["palavras"], 4)

banco.salvar_transcricao(conexao, "AAA", {
    "texto": "Texto refeito com outro modelo.", "gancho_falado": "Texto refeito",
    "duracao_audio_segundos": 30.0, "tempo_de_transcricao_segundos": 5.0,
    "modelo": "base", "idioma": "pt",
    "segmentos": [{"inicio": 0.0, "fim": 3.0, "texto": "Texto refeito"}],
    "palavras": [{"palavra": "Texto", "inicio": 0.0, "fim": 0.5}],
})
resumo = banco.resumo(conexao)
conferir("refazer substitui a transcricao", resumo["transcricoes"], 1)
conferir("refazer substitui os trechos", resumo["segmentos"], 1)
conferir("refazer substitui as palavras", resumo["palavras"], 1)

# Volta a transcricao boa para as consultas seguintes.
banco.salvar_transcricao(conexao, "AAA", {
    "texto": "Para com isso agora. Voce esta doando dinheiro no bonus.",
    "gancho_falado": "Para com isso agora.",
    "duracao_audio_segundos": 30.0, "tempo_de_transcricao_segundos": 14.7,
    "modelo": "small", "idioma": "pt",
    "segmentos": [{"inicio": 0.0, "fim": 2.4, "texto": "Para com isso agora."}],
    "palavras": [
        {"palavra": "Para", "inicio": 0.0, "fim": 0.4},
        {"palavra": "com", "inicio": 0.4, "fim": 0.6},
    ],
})

print("\n=== metricas ===")
for id_post, engajamento, cta in [("AAA", 5.71, {"comentar": ["comenta ai"]}),
                                  ("BBB", 1.02, {}),
                                  ("CCC", 5.60, {"salvar": ["salva esse"]})]:
    banco.salvar_metricas(conexao, id_post, {
        "engajamento": {"taxa_percentual": engajamento},
        "ritmo_palavras_por_minuto": 165.0,
        "gancho": {"falado": "Para com isso agora." if id_post == "AAA" else "",
                   "escrito": "Voce esta doando dinheiro"},
        "hashtags": {"quantas": 3},
        "legenda": {"caracteres": 120, "linhas": 3, "emojis": 2},
        "chamadas_para_acao": cta,
    })
conferir("3 metricas gravadas", banco.resumo(conexao)["metricas"], 3)

print("\n=== a pergunta central: hashtag x desempenho ===")
linhas = consultas.hashtags_por_desempenho(conexao, minimo_de_posts=2)
tags = {linha["tag"]: linha for linha in linhas}
conferir_que("'apostas' aparece (esta em 3 posts)", "apostas" in tags)
conferir("'apostas' em 3 posts", tags["apostas"]["posts"], 3)
conferir("'apostas' usada por 2 perfis", tags["apostas"]["perfis_que_usam"], 2)
conferir_que("'bet' aparece (2 posts)", "bet" in tags)
conferir_que("'tigrinho' NAO aparece (so 1 post, e ruido)", "tigrinho" not in tags)
conferir_que("engajamento medio foi calculado",
             tags["apostas"]["media_engajamento"] is not None)
conferir_que("visualizacoes medias vieram junto",
             tags["bet"]["media_visualizacoes"] is not None)

print("\n=== melhores posts (a fila para editar) ===")
melhores = consultas.melhores_posts(conexao, limite=10)
conferir("3 posts na fila", len(melhores), 3)
conferir("o de maior engajamento vem primeiro", melhores[0]["id"], "AAA")
conferir("o pior vem por ultimo", melhores[-1]["id"], "BBB")

so_video = consultas.melhores_posts(conexao, so_video=True)
conferir("filtro de video exclui o carrossel", len(so_video), 2)
conferir_que("o carrossel CCC ficou de fora",
             "CCC" not in [linha["id"] for linha in so_video])

de_um_perfil = consultas.melhores_posts(conexao, usuario="banca_verde")
conferir("filtro por perfil funciona", len(de_um_perfil), 1)

print("\n=== busca por palavra falada (FTS5) ===")
achados = consultas.procurar_no_falado(conexao, "bonus")
conferir("achou o video que fala 'bonus'", len(achados), 1)
conferir("achou o post certo", achados[0]["post_id"], "AAA")
conferir_que("devolveu o trecho com destaque", "[" in (achados[0]["trecho"] or ""))
conferir("palavra que ninguem fala nao acha nada",
         len(consultas.procurar_no_falado(conexao, "jacare")), 0)

print("\n=== as outras perguntas ===")
ranking = consultas.ranking_de_perfis(conexao)
conferir("2 perfis no ranking", len(ranking), 2)
conferir_que("o ranking vem ordenado por engajamento",
             (ranking[0]["media_engajamento"] or 0) >=
             (ranking[1]["media_engajamento"] or 0))

formatos = consultas.formatos_que_rendem(conexao)
conferir("2 formatos (video e carrossel)", len(formatos), 2)

horarios = consultas.horarios_que_rendem(conexao)
conferir("2 faixas de horario", len(horarios), 2)

compartilhadas = consultas.hashtags_compartilhadas(conexao, minimo_de_perfis=2)
nomes = [linha["tag"] for linha in compartilhadas]
conferir_que("'apostas' e usada por mais de um perfil", "apostas" in nomes)

chamadas = consultas.chamadas_que_rendem(conexao)
conferir("dois grupos: com e sem chamada", len(chamadas), 2)

ganchos = consultas.ganchos_dos_melhores(conexao)
conferir("1 gancho falado registrado", len(ganchos), 1)

palavras = consultas.palavras_do_post(conexao, "AAA")
conferir("2 palavras com tempo", len(palavras), 2)
conferir("a primeira palavra e 'Para'", palavras[0]["palavra"], "Para")

print("\n=== cobertura (onde a esteira parou) ===")
mapa = consultas.cobertura(conexao)
conferir("2 videos", mapa["videos"], 2)
conferir("1 transcrito", mapa["transcritos"], 1)
conferir("3 analisados", mapa["analisados"], 3)
conferir("0 editados", mapa["editados"], 0)
conferir("2 posts com visualizacoes", mapa["com_visualizacoes"], 2)

print("\n=== registrar edicao ===")
banco.registrar_edicao(conexao, "entrada.mp4", "saida.mp4", "padrao", post_id="AAA")
conferir("1 edicao no historico", banco.resumo(conexao)["edicoes"], 1)
conferir("cobertura enxerga a edicao", consultas.cobertura(conexao)["editados"], 1)

print("\n=== apagar perfil leva os filhos junto (cascade) ===")
conexao.execute("DELETE FROM perfis WHERE usuario = 'banca_verde'")
conexao.commit()
conferir("posts do perfil apagado sumiram",
         conexao.execute("SELECT COUNT(*) FROM posts WHERE usuario='banca_verde'"
                         ).fetchone()[0], 0)
conferir("hashtags orfas sumiram junto",
         conexao.execute("SELECT COUNT(*) FROM hashtags WHERE post_id='CCC'"
                         ).fetchone()[0], 0)

conexao.close()
shutil.rmtree(TEMPORARIA, ignore_errors=True)

print("\n" + "=" * 52)
if falhas:
    print("%d TESTE(S) FALHARAM:" % len(falhas))
    for falha in falhas:
        print("  - " + falha)
    sys.exit(1)
print("Todos os testes do banco passaram.")
