"""Confere o editor: a corrente de filtros, a varredura da pasta e o relatorio.

**Nao chama o ffmpeg.** O que se confere aqui e a *montagem da string* que vai
para ele — que e onde os erros ficam escondidos, porque uma corrente de filtros
errada nao da erro de sintaxe em Python: da um vídeo torto 50 segundos depois.

Os tres jeitos de errar que estas conferencias cobrem:

- **a ordem da corrente.** Cada filtro consome o rotulo que o anterior
  produziu. Trocar a ordem ou pular um rotulo quebra o `-map` do fim.
- **o caminho de fonte no Windows.** `C:/Windows/Fonts/arial.ttf` quebra o
  filtro no dois-pontos, mesmo escapado. Por isso a fonte e copiada para a
  pasta de trabalho e citada pelo nome puro — se alguem "consertar" isso
  voltando ao caminho completo, estas conferencias caem.
- **o pareamento da pasta.** Video sem headline, headline sem video, e o
  arquivo de cache que nao pode ser confundido com video.

    .venv\\Scripts\\python.exe tests\\test_editar.py
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import editar

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


TEMPLATE = {
    "nome": "de-teste",
    "canvas": {"largura": 1080, "altura": 1920, "fundo": "#FFFFFF", "fps": 30},
    "video": {"topo": 560, "altura": 980, "margem_lateral": 60},
    "headline": {"mostrar": True, "fonte": "arialbd.ttf", "tamanho": 62,
                 "cor": "#111111", "topo": 250, "largura_em_caracteres": 30,
                 "espaco_entre_linhas": 2},
    "perfil": {"mostrar": True, "prefixo": "@", "fonte": "arial.ttf",
               "tamanho": 38, "cor": "#8A8A8A", "topo": 1620},
    "logo": {"arquivo": None, "altura": 90, "topo": 110},
    "legenda": {"mostrar": True},
    "saida": {"preset": "veryfast", "qualidade": 23, "audio_kbps": 128},
}

TRABALHO = Path(tempfile.mkdtemp(prefix="teste-editar-"))


print("=== a cor para o ffmpeg ===")

conferir("hexadecimal do CSS vira 0x", editar.cor_para_ffmpeg("#8A8A8A"),
         "0x8A8A8A")
conferir("ja com 0x fica como esta", editar.cor_para_ffmpeg("0xFF0000"),
         "0xFF0000")
conferir("nome de cor passa direto", editar.cor_para_ffmpeg("black"), "black")
conferir("espaco em volta nao atrapalha", editar.cor_para_ffmpeg("  #FFF  "),
         "0xFFF")
conferir("cor ausente cai em branco", editar.cor_para_ffmpeg(None), "white")
conferir("string vazia tambem", editar.cor_para_ffmpeg(""), "white")


print("\n=== quebrar a headline em linhas ===")

conferir("texto curto nao quebra",
         editar._quebrar_linhas("Olha isso", 30), "Olha isso")
conferir_que("texto longo quebra na largura pedida",
             "\n" in editar._quebrar_linhas(
                 "Ninguem te contou isso e voce precisa saber agora mesmo", 20))
conferir_que("e nenhuma linha passa da largura",
             all(len(l) <= 20 for l in editar._quebrar_linhas(
                 "Ninguem te contou isso e voce precisa saber agora", 20)
                 .splitlines()))
conferir("texto vazio vira vazio", editar._quebrar_linhas("", 30), "")
conferir("None vira vazio", editar._quebrar_linhas(None, 30), "")


print("\n=== carregar template ===")

carregado = editar.carregar_template("padrao")
conferir("acha pelo nome curto dentro de templates/",
         carregado.get("nome"), "meme-branco")
conferir_que("e o padrao do projeto tem canvas 1080x1920",
             carregado["canvas"]["largura"] == 1080
             and carregado["canvas"]["altura"] == 1920)

conferir_que("acha tambem por caminho completo",
             editar.carregar_template(
                 str(RAIZ / "templates" / "padrao.json")).get("nome")
             == "meme-branco")

try:
    editar.carregar_template("nao-existe-isso")
    conferir_que("template inexistente reclama", False)
except editar.ErroDeEdicao as erro:
    conferir_que("template inexistente reclama", True)
    conferir_que("dizendo onde procurou", "templates/" in str(erro))


print("\n=== a fonte: o dois-pontos do Windows ===")

conferir("sem fonte pedida, sem fonte devolvida", editar.achar_fonte(None), None)
conferir("string vazia idem", editar.achar_fonte(""), None)

achada = editar.achar_fonte("arial.ttf")
conferir_que("acha a fonte pelo nome, na pasta do Windows",
             achada is not None and achada.is_file())

try:
    editar.achar_fonte("fonte-que-nao-existe-999.ttf")
    conferir_que("fonte inexistente reclama", False)
except editar.ErroDeEdicao as erro:
    conferir_que("fonte inexistente reclama", True)
    conferir_que("ensinando onde olhar", "arial.ttf" in str(erro))


print("\n=== a corrente de filtros, na ordem ===")

filtros, ultimo = editar.montar_filtros(TEMPLATE, "Olha isso", "alguem",
                                        False, False, TRABALHO)

conferir_que("comeca criando o fundo do tamanho do canvas",
             filtros[0].startswith("color=c=0xFFFFFF:s=1080x1920:r=30[fundo]"))
conferir_que("depois encaixa o video sem distorcer",
             "force_original_aspect_ratio=decrease" in filtros[1])
conferir_que("na largura do canvas menos as duas margens",
             "scale=960:980" in filtros[1])
conferir_que("e sobrepoe centralizado na area do template",
             "[fundo][video]overlay=(W-w)/2:560+(980-h)/2" in filtros[2])
conferir_que("com shortest, para o fundo infinito nao esticar o video",
             "shortest=1" in filtros[2])

conferir("com headline e perfil, sao cinco filtros", len(filtros), 5)
conferir("e o ultimo rotulo e o do perfil", ultimo, "comperfil")

conferir_que("cada filtro consome o rotulo que o anterior produziu",
             "[base]drawtext=" in filtros[3]
             and "[comheadline]" in filtros[3]
             and "[comheadline]drawtext=" in filtros[4]
             and "[comperfil]" in filtros[4])


print("\n=== o texto vai por arquivo, nunca inline ===")

conferir_que("a headline foi citada por nome curto",
             "textfile=headline.txt" in filtros[3])
conferir_que("e o arquivo existe mesmo na pasta de trabalho",
             (TRABALHO / "headline.txt").is_file())
conferir("com o texto que foi pedido",
         (TRABALHO / "headline.txt").read_text(encoding="utf-8"), "Olha isso")

conferir_que("o perfil ganhou o @ do template",
             (TRABALHO / "perfil.txt").read_text(encoding="utf-8") == "@alguem")

conferir_que("a fonte foi copiada e citada pelo nome puro",
             "fontfile=fonte_headline.ttf" in filtros[3])
conferir_que("e o arquivo de fonte esta la",
             (TRABALHO / "fonte_headline.ttf").is_file())
conferir_que("nenhum caminho com dois-pontos entrou na corrente",
             not any("C:" in f or "c:" in f for f in filtros))

conferir_que("o tamanho e a cor do template chegaram",
             "fontsize=62" in filtros[3] and "fontcolor=0x111111" in filtros[3])
conferir_que("e a posicao vertical tambem", "y=250" in filtros[3])
conferir_que("o x centraliza pela largura do texto",
             "x=(w-text_w)/2" in filtros[3])


print("\n=== o contorno: so quando o template pede ===")

conferir_que("o meme-branco nao pede contorno, entao nao ha borderw",
             "borderw" not in filtros[3])

com_contorno = dict(TEMPLATE, headline=dict(
    TEMPLATE["headline"], contorno=5, cor_contorno="#000000"))
filtros_c, _ = editar.montar_filtros(com_contorno, "Texto", "alguem", False,
                                     False, TRABALHO)
conferir_que("com contorno no template, o borderw aparece",
             "borderw=5" in filtros_c[3])
conferir_que("com a cor pedida, convertida para o ffmpeg",
             "bordercolor=0x000000" in filtros_c[3])
conferir_que("e o perfil, que nao pediu, continua sem",
             "borderw" not in filtros_c[4])

contorno_zero = dict(TEMPLATE, headline=dict(TEMPLATE["headline"], contorno=0))
filtros_z, _ = editar.montar_filtros(contorno_zero, "Texto", "", False, False,
                                     TRABALHO)
conferir_que("contorno zero e o mesmo que nao pedir",
             "borderw" not in filtros_z[3])

conferir_que("o template vertical do projeto pede contorno na headline",
             editar.carregar_template("vertical")["headline"]["contorno"] > 0)
conferir_que("e enche o canvas, que e a razao de ele existir",
             editar.carregar_template("vertical")["video"]["altura"] == 1920)


print("\n=== o que o template manda esconder, some da corrente ===")

filtros, ultimo = editar.montar_filtros(TEMPLATE, "", "", False, False, TRABALHO)
conferir("sem headline e sem perfil, so os tres filtros de base", len(filtros), 3)
conferir("e o ultimo rotulo volta a ser base", ultimo, "base")

sem_headline = dict(TEMPLATE, headline=dict(TEMPLATE["headline"], mostrar=False))
filtros, ultimo = editar.montar_filtros(sem_headline, "Texto", "alguem", False,
                                        False, TRABALHO)
conferir("mostrar=false ignora a headline mesmo havendo texto", ultimo,
         "comperfil")
conferir("e ela nao entra na corrente", len(filtros), 4)

sem_perfil = dict(TEMPLATE, perfil=dict(TEMPLATE["perfil"], mostrar=False))
_, ultimo = editar.montar_filtros(sem_perfil, "Texto", "alguem", False, False,
                                  TRABALHO)
conferir("mostrar=false no perfil idem", ultimo, "comheadline")


print("\n=== logo e legenda entram no fim, nesta ordem ===")

filtros, ultimo = editar.montar_filtros(TEMPLATE, "Texto", "alguem", True,
                                        True, TRABALHO)
conferir("com logo e legenda, oito filtros", len(filtros), 8)
conferir("e o ultimo rotulo e o final", ultimo, "final")
conferir_que("o logo vem da segunda entrada do ffmpeg",
             "[1:v]scale=-1:90[logo]" in filtros[5])
conferir_que("sobreposto centralizado na altura do template",
             "overlay=(W-w)/2:110[comlogo]" in filtros[6])
conferir_que("a legenda e o ultimo, por cima de tudo",
             filtros[7] == "[comlogo]ass=legenda.ass[final]")

filtros, ultimo = editar.montar_filtros(TEMPLATE, "", "", False, True, TRABALHO)
conferir_que("sem headline, a legenda ainda acha o rotulo certo",
             filtros[-1] == "[base]ass=legenda.ass[final]")
conferir_que("a legenda e citada por nome curto, nunca por caminho",
             "ass=legenda.ass" in filtros[-1] and "/" not in filtros[-1])


print("\n=== varrer a pasta ===")

PASTA = Path(tempfile.mkdtemp(prefix="teste-pasta-"))
for nome in ("b.mp4", "A.MOV", "c.webm", "notas.txt", "b.palavras.json",
             "logo.png"):
    (PASTA / nome).write_text("x", encoding="utf-8")
(PASTA / "subpasta").mkdir()
(PASTA / "subpasta" / "escondido.mp4").write_text("x", encoding="utf-8")

videos = editar.listar_videos(PASTA)
conferir("so os tres videos entram", [v.name for v in videos],
         ["A.MOV", "b.mp4", "c.webm"])
conferir_que("o cache de palavras nao e confundido com video",
             not any("palavras" in v.name for v in videos))
conferir_que("nem o png, nem o txt",
             not any(v.suffix in (".png", ".txt") for v in videos))
conferir_que("subpasta nao e varrida: editar por engano seria pior",
             not any("escondido" in v.name for v in videos))

try:
    editar.listar_videos(PASTA / "nao-existe")
    conferir_que("pasta inexistente reclama", False)
except editar.ErroDeEdicao as erro:
    conferir_que("pasta inexistente reclama", True)
    conferir_que("com instrucao do que fazer", "Crie ela" in str(erro))


print("\n=== ler o roteiro da pasta ===")

conferir("pasta sem roteiro.txt nao e erro: e lote sem headline",
         editar.ler_roteiro(PASTA), ([], []))

(PASTA / "roteiro.txt").write_text("b.mp4 | Texto do b\n", encoding="utf-8")
entradas, problemas = editar.ler_roteiro(PASTA)
conferir("o roteiro padrao e lido pelo nome convencionado", len(entradas), 1)
conferir("sem reclamacao quando esta certo", problemas, [])

(PASTA / "outro.txt").write_text("A.MOV | Texto do A\n", encoding="utf-8")
entradas, _ = editar.ler_roteiro(PASTA, PASTA / "outro.txt")
conferir("roteiro apontado a mao vence o padrao", entradas[0][0], "A.MOV")

try:
    editar.ler_roteiro(PASTA, PASTA / "inexistente.txt")
    conferir_que("roteiro apontado que nao existe reclama", False)
except editar.ErroDeEdicao:
    conferir_que("roteiro apontado que nao existe reclama", True)


print("\n=== o relatorio: e ele que cumpre o criterio 4 da T8 ===")

SAIDA = Path(tempfile.mkdtemp(prefix="teste-saida-"))
resultados = [
    {"arquivo": "a.mp4", "situacao": "editado", "segundos_de_edicao": 40.0},
    {"arquivo": "b.mp4", "situacao": "editado", "segundos_de_edicao": 60.0},
    {"arquivo": "c.mp4", "situacao": "pulado"},
    {"arquivo": "d.mp4", "situacao": "falhou", "erro": "mp4 truncado"},
]
relatorio, caminho = editar.gravar_relatorio(resultados, TEMPLATE, SAIDA)

conferir("conta os editados", relatorio["editados"], 2)
conferir("os pulados", relatorio["pulados"], 1)
conferir("e os que falharam", relatorio["falhados"], 1)
conferir("soma o tempo so dos editados", relatorio["segundos_totais"], 100.0)
conferir("e a media divide pelos editados, nao pelo total",
         relatorio["segundos_por_video"], 50.0)
conferir("guarda qual template produziu isto", relatorio["template"], "de-teste")
conferir_que("e a lista completa, com o motivo da falha",
             relatorio["videos"][3]["erro"] == "mp4 truncado")

conferir_que("o arquivo foi gravado", caminho.is_file())
lido = json.loads(caminho.read_text(encoding="utf-8"))
conferir("e le de volta igual", lido["segundos_por_video"], 50.0)

vazio, _ = editar.gravar_relatorio([], TEMPLATE, SAIDA)
conferir("lote sem nada editado nao divide por zero",
         vazio["segundos_por_video"], None)


print("\n=== o modelo do Whisper so carrega se precisar ===")

chamadas = []


def _fingir(nome, tipo):
    chamadas.append((nome, tipo))
    return "modelo-%s" % nome


original = editar.fala.carregar_modelo
editar.fala.carregar_modelo = _fingir
try:
    obter = editar._modelo_sob_demanda("base", "int8")
    conferir("criar o carregador nao carrega nada ainda", chamadas, [])
    conferir("o primeiro uso carrega", obter(), "modelo-base")
    conferir("com o modelo e o tipo pedidos", chamadas, [("base", "int8")])
    obter()
    obter()
    conferir("e os usos seguintes reaproveitam", len(chamadas), 1)
finally:
    editar.fala.carregar_modelo = original


shutil.rmtree(TRABALHO, ignore_errors=True)
shutil.rmtree(PASTA, ignore_errors=True)
shutil.rmtree(SAIDA, ignore_errors=True)

print("\n" + "=" * 52)
if falhas:
    print("%d TESTE(S) FALHARAM:" % len(falhas))
    for falha in falhas:
        print("  - " + falha)
    sys.exit(1)
print("Todos os testes do editor passaram.")
