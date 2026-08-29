"""Confere a normalizacao da Apify, o storage e o downloader.

Nada de rede: o Actor e o yt-dlp entram como dublê. O que se testa aqui e a
nossa traducao, que e onde os erros de verdade moram.

    .venv\\Scripts\\python.exe tests\\test_coleta.py
"""

import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import config

TEMPORARIA = Path(tempfile.mkdtemp(prefix="teste-coleta-"))
config.DADOS = TEMPORARIA
config.BUSCAS = TEMPORARIA / "buscas"
config.PERFIS = TEMPORARIA / "perfis"
config.ANALISES = TEMPORARIA / "analises"
config.SAIDA = TEMPORARIA / "saida"
config.SESSOES = TEMPORARIA / "sessoes"

import coletor
import storage
from downloader import ResultadoDownload, YtDlpDownloader

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


# Item de perfil no formato documentado do Actor.
PERFIL_CRU = {
    "username": "casa_verde", "fullName": "Casa Verde Apostas",
    "biography": "link na bio", "followersCount": 84000, "followsCount": 12,
    "postsCount": 430, "private": False, "verified": True,
    "externalUrl": "https://casaverde.com", "id": "1122334455",
    "url": "https://www.instagram.com/casa_verde/",
}

REEL_CRU = {
    "shortCode": "C9xYz01", "type": "Video", "productType": "clips",
    "url": "https://www.instagram.com/reel/C9xYz01/",
    "caption": "olha isso #tigrinho #apostas", "hashtags": ["tigrinho", "apostas"],
    "mentions": ["parceiro"], "timestamp": "2026-08-20T15:30:00.000Z",
    "likesCount": 5200, "commentsCount": 310, "videoPlayCount": 190000,
    "videoDuration": 31.4, "videoUrl": "https://cdn.instagram.com/vence.mp4",
    "ownerUsername": "casa_verde", "ownerId": "1122334455",
}

FOTO_CRUA = {
    "shortCode": "C9foto1", "type": "Image",
    "url": "https://www.instagram.com/p/C9foto1/",
    "caption": "so uma foto", "timestamp": 1755700000,
    "likesCount": 12, "commentsCount": 1, "ownerUsername": "casa_verde",
}

print("=== conta do custo ===")
conferir("40 resultados no plano free",
         round(coletor.custo_estimado(40), 4), 0.108)
conferir("1000 resultados no plano free", coletor.custo_estimado(1000), 2.70)
conferir("1240 resultados = a rodada cara que eu avisei",
         round(coletor.custo_estimado(1240), 3), 3.348)
conferir("plano desconhecido cai no padrao, nao estoura",
         coletor.custo_estimado(1000, "inventado"), 2.70)

print("\n=== perfil normalizado ===")
perfil = coletor.normalizar_perfil(PERFIL_CRU, nicho="apostas")
conferir("usuario", perfil["usuario"], "casa_verde")
conferir("seguidores", perfil["seguidores"], 84000)
conferir("profile_id do pipeline", perfil["perfil_id"], "1122334455")
conferir("profile_url do pipeline", perfil["link_perfil"],
         "https://www.instagram.com/casa_verde/")
conferir("nicho carimbado", perfil["nicho"], "apostas")
conferir("verificado vira booleano", perfil["verificado"], True)

print("\n=== o que a rodada REAL do Actor ensinou (28/08/2026) ===")
# externalUrls e PLURAL e LISTA. Antes disso, o link da bio vinha sempre vazio
# e ninguem notaria, porque None e um valor plausivel para esse campo.
conferir("externalUrls como lista de texto",
         coletor.normalizar_perfil(
             {"username": "x", "externalUrls": ["https://site.com"]})["link_externo"],
         "https://site.com")
conferir("externalUrls como lista de objeto",
         coletor.normalizar_perfil(
             {"username": "x",
              "externalUrls": [{"url": "https://obj.com"}]})["link_externo"],
         "https://obj.com")
conferir("lista vazia nao vira string vazia",
         coletor.normalizar_perfil({"username": "x",
                                    "externalUrls": []})["link_externo"], None)
conferir("o nome antigo no singular ainda funciona",
         coletor.normalizar_perfil(
             {"username": "x", "externalUrl": "https://velho.com"})["link_externo"],
         "https://velho.com")

conferir("relatedProfiles vira lista de @",
         coletor.perfis_relacionados(
             {"relatedProfiles": [{"username": "a"}, {"username": "b"},
                                  {"sem": "usuario"}]}),
         ["a", "b"])
conferir("sem relatedProfiles devolve lista vazia",
         coletor.perfis_relacionados({}), [])

print("\n=== o normalizador aguenta nome de campo diferente ===")
conferir("followers em vez de followersCount",
         coletor.normalizar_perfil({"username": "x", "followers": 50})["seguidores"], 50)
conferir("sem url, monta a do perfil",
         coletor.normalizar_perfil({"username": "x"})["link_perfil"],
         "https://www.instagram.com/x/")
conferir("item sem usuario e descartado, nao quebra",
         coletor.normalizar_perfil({"followersCount": 10}), None)

print("\n=== reel normalizado ===")
reel = coletor.normalizar_post(REEL_CRU)
conferir("id e o shortcode", reel["id"], "C9xYz01")
conferir("perfil", reel["perfil"], "casa_verde")
conferir("productType clips vira reel", reel["tipo"], "reel")
conferir("e video", reel["e_video"], True)
conferir("duracao", reel["duracao_segundos"], 31.4)
conferir("visualizacoes vem de videoPlayCount", reel["visualizacoes"], 190000)
conferir("curtidas", reel["curtidas"], 5200)
conferir("hashtags", reel["hashtags"], ["tigrinho", "apostas"])
conferir("mencoes", reel["mencoes"], ["parceiro"])
conferir_que("data_utc em ISO", reel["data_utc"].startswith("2026-08-20T15:30:00"))
conferir_que("dia da semana calculado", reel["dia_da_semana"] in (
    "Thursday", "Wednesday", "Friday"))
conferir_que("hora no formato HH:MM", len(reel["hora"]) == 5 and ":" in reel["hora"])
conferir("video_url guardada (mas vence)", reel["video_url"],
         "https://cdn.instagram.com/vence.mp4")

print("\n=== -1 e 'oculto', nao um numero ===")
# [VERIFICADO 28/08/2026] Na rodada real do nicho 'receitas', dois posts de
# @receitas vieram com likesCount = -1. E o sentinela do Instagram para
# "curtidas ocultas" — nao e uma medicao. Guardado como -1 ele virava
# engajamento NEGATIVO (-0,01%) e derrubava o post no ranking por um motivo
# que nada tem a ver com desempenho. Mesma regra que ja vale para saves:
# None e honesto; numero inventado nao.
oculto = coletor.normalizar_post(dict(REEL_CRU, likesCount=-1))
conferir("likesCount -1 vira None", oculto["curtidas"], None)
conferir("commentsCount -1 vira None",
         coletor.normalizar_post(dict(REEL_CRU, commentsCount=-1))["comentarios"], None)
conferir("visualizacao -1 em todos os nomes vira None",
         coletor.normalizar_post(dict(REEL_CRU, videoPlayCount=-1, videoViewCount=-1,
                                      playCount=-1, viewCount=-1))["visualizacoes"], None)
conferir("zero de verdade continua zero",
         coletor.normalizar_post(dict(REEL_CRU, commentsCount=0))["comentarios"], 0)
conferir("numero normal passa intacto",
         coletor.normalizar_post(dict(REEL_CRU, likesCount=5200))["curtidas"], 5200)
conferir("seguidores -1 vira None",
         coletor.normalizar_perfil({"username": "x", "followersCount": -1})["seguidores"], None)

print("\n=== o post.json sai no formato que a analise ja le ===")
CAMPOS = {"id", "perfil", "link", "tipo", "typename", "e_video",
          "duracao_segundos", "visualizacoes", "legenda", "hashtags",
          "mencoes", "curtidas", "comentarios", "data_utc", "data_local",
          "dia_da_semana", "hora"}
conferir_que("todos os campos que analisar.py espera", CAMPOS <= set(reel))

print("\n=== foto ===")
foto = coletor.normalizar_post(FOTO_CRUA)
conferir("tipo foto", foto["tipo"], "foto")
conferir("nao e video", foto["e_video"], False)
conferir_que("timestamp em epoch tambem funciona", bool(foto["data_utc"]))
conferir("sem hashtag vira lista vazia, nao None", foto["hashtags"], [])
conferir("post sem codigo e descartado",
         coletor.normalizar_post({"caption": "sem id"}), None)

print("\n=== data invalida nao derruba a coleta ===")
quebrado = coletor.normalizar_post({"shortCode": "X", "ownerUsername": "y",
                                    "timestamp": "nao e data"})
conferir("data vira None em vez de estourar", quebrado["data_utc"], None)

print("\n=== Coleta sabe separar video de foto ===")
c = coletor.Coleta(perfis=[perfil], posts=[reel, foto], itens=3, custo_usd=0.0081)
conferir("so um video", len(c.videos), 1)
conferir("o video e o reel", c.videos[0]["id"], "C9xYz01")

print("\n=== coletor sem token recusa na hora ===")
try:
    coletor.ApifyInstagramCollector(token="")
    conferir_que("deveria ter recusado", False)
except coletor.ErroDeColeta as erro:
    conferir_que("mensagem explica onde pegar o token",
                 "console.apify.com" in str(erro))

print("\n=== storage local ===")
guarda = storage.LocalStorage()
conferir("ainda nao tem", guarda.ja_tem("casa_verde", "C9xYz01"), False)

origem = TEMPORARIA / "baixado.mp4"
origem.write_bytes(b"conteudo de video")
destino = guarda.guardar(origem, "casa_verde", "C9xYz01")

conferir_que("guardou no layout que a transcricao procura",
             destino.endswith(str(Path("perfis") / "casa_verde" / "C9xYz01" / "midia.mp4")))
conferir("agora tem", guarda.ja_tem("casa_verde", "C9xYz01"), True)
conferir("o arquivo de origem saiu (move, nao copy)", origem.exists(), False)
conferir("conteudo intacto", Path(destino).read_bytes(), b"conteudo de video")

caminho_json = guarda.guardar_dados(reel, "casa_verde", "C9xYz01")
conferir_que("post.json ao lado da midia",
             Path(caminho_json).name == "post.json"
             and Path(caminho_json).parent == Path(destino).parent)

try:
    guarda.guardar(TEMPORARIA / "nao-existe.mp4", "x", "y")
    conferir_que("guardar arquivo inexistente deveria estourar", False)
except storage.ErroDeStorage:
    conferir_que("guardar arquivo inexistente levanta ErroDeStorage", True)

print("\n=== downloader: achar o arquivo que o yt-dlp escreveu ===")
pasta = TEMPORARIA / "trabalho"
pasta.mkdir()
escrito = pasta / "video.mp4"
escrito.write_bytes(b"x" * 10)

conferir("acha por filepath",
         YtDlpDownloader._arquivo_de({"filepath": str(escrito)}, pasta), escrito)
conferir("acha por requested_downloads",
         YtDlpDownloader._arquivo_de(
             {"requested_downloads": [{"filepath": str(escrito)}]}, pasta), escrito)
conferir("acha varrendo a pasta quando o info nao diz",
         YtDlpDownloader._arquivo_de({}, pasta), escrito)
conferir("playlist: pega a primeira entrada",
         YtDlpDownloader._arquivo_de(
             {"_type": "playlist", "entries": [{"filepath": str(escrito)}]}, pasta),
         escrito)
conferir("pasta vazia devolve None",
         YtDlpDownloader._arquivo_de({}, TEMPORARIA / "vazia" if
                                     (TEMPORARIA / "vazia").mkdir() or True
                                     else pasta), None)

print("\n=== downloader: erro de rede vira resultado, nao excecao ===")
resultado = YtDlpDownloader().baixar("https://www.instagram.com/reel/NAO_EXISTE_xyz/",
                                     TEMPORARIA / "falha")
conferir("sucesso False", resultado.sucesso, False)
conferir_que("com motivo legivel", bool(resultado.erro))
conferir_que("e nao levantou excecao", isinstance(resultado, ResultadoDownload))

print("\n=== limpeza: o que o disco tem, e o que sai dele ===")
import pipeline

# A pasta nao esta vazia: os testes de storage acima ja guardaram midia nela.
# Medir a diferenca, e nao o total, evita um teste que quebra sempre que
# alguem acrescenta um caso la em cima.
ANTES = len(pipeline._midias_no_disco())

# `_midias_no_disco` e `_apagar` sao a metade da limpeza que nao passa pelo
# banco. Testadas aqui porque sao logica de disco pura — e porque errar nelas
# apaga arquivo de verdade.
for perfil, codigo in (("casa_verde", "AAA"), ("casa_verde", "BBB"),
                       ("outro_perfil", "CCC")):
    pasta = config.PERFIS / perfil / codigo
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "midia.mp4").write_bytes(b"x" * 1000)
    (pasta / "post.json").write_text("{}", encoding="utf-8")

achadas = pipeline._midias_no_disco()
conferir("acha uma midia por post", len(achadas) - ANTES, 3)
conferir_que("todas se chamam midia.*",
             all(c.name.startswith("midia.") for c in achadas))
conferir_que("post.json NAO entra na conta",
             all(c.name != "post.json" for c in achadas))

# Uma extensao diferente continua sendo midia: o downloader escolhe o
# container, e nem todo Reels sai em mp4.
(config.PERFIS / "casa_verde" / "AAA" / "midia.webm").write_bytes(b"y" * 10)
conferir("outra extensao tambem conta",
         len(pipeline._midias_no_disco()) - ANTES, 4)

alvo_midia = config.PERFIS / "outro_perfil" / "CCC" / "midia.mp4"
conferir("apagar devolve True", pipeline._apagar(alvo_midia), True)
conferir_que("e o arquivo sumiu", not alvo_midia.exists())
conferir_que("mas a pasta fica: ainda tem o post.json",
             alvo_midia.parent.is_dir())

# Com a pasta vazia, ela tambem sai — senao sobra esqueleto de pasta pelo
# disco inteiro depois de uma limpeza grande.
(alvo_midia.parent / "post.json").unlink()
vazia = config.PERFIS / "outro_perfil" / "VAZIA"
vazia.mkdir(parents=True, exist_ok=True)
(vazia / "midia.mp4").write_bytes(b"z")
conferir("apagar a ultima coisa da pasta", pipeline._apagar(vazia / "midia.mp4"), True)
conferir_que("a pasta vazia some junto", not vazia.exists())

conferir("apagar o que nao existe devolve False, sem estourar",
         pipeline._apagar(config.PERFIS / "nao" / "existe" / "midia.mp4"), False)

shutil.rmtree(TEMPORARIA, ignore_errors=True)

print("\n" + "=" * 52)
if falhas:
    print("%d TESTE(S) FALHARAM:" % len(falhas))
    for falha in falhas:
        print("  - " + falha)
    sys.exit(1)
print("Todos os testes de coleta passaram.")
