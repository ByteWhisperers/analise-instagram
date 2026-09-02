"""Confere o cache de transcricao.

**Nao carrega o Whisper e nao toca em audio.** O modelo e um dublê. O que se
confere aqui e a decisao de *quando* transcrever — que e o que separa um lote
de 50 videos rodando em minutos de um rodando em uma hora.

Os quatro jeitos de errar:

- **cache que nao e usado.** Transcrever de novo o que ja foi custa ~0,9x a
  duracao do video. Em 50 videos de 1 minuto, e 45 minutos jogados fora so
  para trocar a cor da legenda no template.
- **cache que e usado quando nao devia.** Aproveitar palavras do modelo `base`
  numa rodada que pediu `small` seria mentir sobre qual modelo produziu
  aquilo.
- **modelo carregado a toa.** Carregar o Whisper custa ~11s e ~1 GB nesta
  maquina. Numa pasta toda em cache, esse preco nao pode ser pago.
- **cache corrompido derrubando o lote.** Um JSON truncado por queda de luz
  nao pode ser erro: e so transcrever de novo.

    .venv\\Scripts\\python.exe tests\\test_fala.py
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import fala

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


PASTA = Path(tempfile.mkdtemp(prefix="teste-fala-"))
VIDEO = PASTA / "abertura.mp4"
VIDEO.write_bytes(b"nao e um mp4 de verdade, e ninguem vai abrir")

TRANSCRICAO = {
    "texto": "Adicione ovos a cenouras",
    "palavras": [{"palavra": "Adicione", "inicio": 0.0, "fim": 0.64}],
    "segmentos": [{"inicio": 0.0, "fim": 0.64, "texto": "Adicione"}],
    "modelo": "small",
    "idioma": "pt",
}


print("=== onde o cache mora ===")

conferir("fica ao lado do video, com o mesmo nome",
         fala.caminho_do_cache(VIDEO).name, "abertura.palavras.json")
conferir("na mesma pasta", fala.caminho_do_cache(VIDEO).parent, PASTA)
conferir("aceita caminho em texto",
         fala.caminho_do_cache(str(VIDEO)).name, "abertura.palavras.json")
conferir("a extensao do video nao vaza para o nome do cache",
         fala.caminho_do_cache(PASTA / "a.MOV").name, "a.palavras.json")


print("\n=== ler e gravar ===")

conferir("sem arquivo, nao ha cache", fala.ler_cache(VIDEO), None)

fala.gravar_cache(VIDEO, TRANSCRICAO)
conferir_que("gravou de verdade", fala.caminho_do_cache(VIDEO).is_file())

lido = fala.ler_cache(VIDEO)
conferir_que("e le de volta o que foi gravado",
             lido["palavras"][0]["palavra"] == "Adicione")

com_acento = dict(TRANSCRICAO, palavras=[
    {"palavra": "ação", "inicio": 0.0, "fim": 0.5},
    {"palavra": "coração", "inicio": 0.5, "fim": 1.0},
])
fala.gravar_cache(VIDEO, com_acento)
volta = fala.ler_cache(VIDEO)
conferir("acento sobrevive a ida e volta, porque grava em UTF-8",
         [p["palavra"] for p in volta["palavras"]], ["ação", "coração"])
conferir_que("e nao virou sequencia de escape no arquivo",
             "ação" in fala.caminho_do_cache(VIDEO).read_text(encoding="utf-8"))
fala.gravar_cache(VIDEO, TRANSCRICAO)

conferir_que("o mesmo modelo aceita o cache",
             fala.ler_cache(VIDEO, "small") is not None)
conferir("modelo diferente RECUSA o cache",
         fala.ler_cache(VIDEO, "base"), None)
conferir_que("sem pedir modelo, aceita qualquer um",
             fala.ler_cache(VIDEO, None) is not None)


print("\n=== cache estragado nao e erro: e so transcrever de novo ===")

fala.caminho_do_cache(VIDEO).write_text("{ isto nao fecha", encoding="utf-8")
conferir("JSON truncado devolve None em vez de estourar",
         fala.ler_cache(VIDEO), None)

fala.caminho_do_cache(VIDEO).write_text('{"modelo": "small"}', encoding="utf-8")
conferir("JSON valido mas sem palavras tambem nao serve",
         fala.ler_cache(VIDEO), None)

fala.caminho_do_cache(VIDEO).write_text('{"palavras": "nao e lista"}',
                                        encoding="utf-8")
conferir("palavras que nao e lista nao serve", fala.ler_cache(VIDEO), None)


print("\n=== o modelo so e pedido quando nao ha cache ===")

fala.gravar_cache(VIDEO, TRANSCRICAO)
pedidos = []


def obter_modelo():
    pedidos.append(1)
    return "modelo-falso"


transcricao, do_cache = fala.palavras_de_video(VIDEO, obter_modelo, "small")
conferir_que("com cache, devolve a transcricao guardada",
             transcricao["palavras"][0]["palavra"] == "Adicione")
conferir("e avisa que veio do cache", do_cache, True)
conferir("sem pedir o modelo uma unica vez", pedidos, [])

# Sem cache aproveitavel, o caminho longo tem que ser percorrido inteiro. Os
# tres dubles abaixo substituem o que fala com o mundo — ffprobe, ffmpeg e o
# Whisper — para conferir a ORDEM e a limpeza, sem audio de verdade.
chamadas = []
originais = (fala.midia.tem_audio, fala.midia.extrair_audio,
             fala.transcrever_arquivo)
fala.midia.tem_audio = lambda video, ffmpeg=None: chamadas.append("audio?") or True
fala.midia.extrair_audio = (
    lambda video, destino, ffmpeg=None: chamadas.append("extrai")
    or destino.write_bytes(b"wav de mentira") or destino)
fala.transcrever_arquivo = lambda modelo, wav, idioma: (
    chamadas.append("transcreve:%s" % modelo)
    or ([{"inicio": 0.0, "fim": 1.0, "texto": "oi"}],
        [{"palavra": "oi", "inicio": 0.0, "fim": 1.0}], "oi", 1.0))

pedidos.clear()
try:
    transcricao, do_cache = fala.palavras_de_video(VIDEO, obter_modelo, "base")
finally:
    fala.midia.tem_audio, fala.midia.extrair_audio, fala.transcrever_arquivo = originais

conferir("modelo diferente ignora o cache", do_cache, False)
conferir("e a ordem e: conferir audio, extrair, transcrever",
         chamadas, ["audio?", "extrai", "transcreve:modelo-falso"])
conferir("o modelo foi pedido exatamente uma vez", pedidos, [1])
conferir("e a transcricao nova saiu com as palavras do dublê",
         transcricao["palavras"][0]["palavra"], "oi")
conferir("carimbada com o modelo que a rodada pediu",
         transcricao["modelo"], "base")
conferir_que("o WAV temporario nao ficou para tras",
             not (PASTA / "abertura.audio.wav").exists())
conferir("e o cache foi reescrito com o modelo novo",
         fala.ler_cache(VIDEO)["modelo"], "base")
conferir("agora o cache de 'base' e aceito",
         fala.ler_cache(VIDEO, "base")["palavras"][0]["palavra"], "oi")

fala.gravar_cache(VIDEO, TRANSCRICAO)


print("\n=== video mudo nao e falha: e video sem legenda ===")

original = fala.midia.tem_audio
fala.midia.tem_audio = lambda video, ffmpeg=None: False
pedidos.clear()
try:
    transcricao, do_cache = fala.palavras_de_video(
        VIDEO, obter_modelo, "small", refazer=True)
    conferir("sem trilha de audio, devolve None sem estourar", transcricao, None)
    conferir("e nao veio do cache", do_cache, False)
    conferir("nem carregou o Whisper para descobrir isso", pedidos, [])
finally:
    fala.midia.tem_audio = original


print("\n=== montar_transcricao: o gancho dos 3 primeiros segundos ===")

segmentos = [
    {"inicio": 0.0, "fim": 1.5, "texto": "Adicione ovos"},
    {"inicio": 1.5, "fim": 2.9, "texto": "e veja"},
    {"inicio": 4.0, "fim": 6.0, "texto": "isto ja passou do gancho"},
]
montada = fala.montar_transcricao(segmentos, [], "tudo junto", 6.0, 3.0,
                                  "small", "pt")

conferir("o gancho junta so o que foi dito antes dos 3s",
         montada["gancho_falado"], "Adicione ovos e veja")
conferir("guarda quanto tempo levou", montada["tempo_de_transcricao_segundos"],
         3.0)
conferir("e quantas vezes a duracao do audio",
         montada["quantas_vezes_a_duracao"], 0.5)
conferir("guarda qual modelo produziu", montada["modelo"], "small")
conferir_que("e carimba a hora", "T" in montada["transcrito_em"])

vazia = fala.montar_transcricao([], [], "", 0, 1.0, "small", "pt")
conferir("audio de duracao zero nao divide por zero",
         vazia["quantas_vezes_a_duracao"], None)
conferir("e o gancho fica vazio, nao None", vazia["gancho_falado"], "")


print("\n=== o transcrever.py continua falando pela mesma boca ===")

import transcrever

conferir_que("carregar_modelo e o mesmo objeto",
             transcrever.carregar_modelo is fala.carregar_modelo)
conferir_que("transcrever_arquivo tambem",
             transcrever.transcrever_arquivo is fala.transcrever_arquivo)
conferir_que("montar_transcricao tambem",
             transcrever.montar_transcricao is fala.montar_transcricao)
conferir("e o gancho e o mesmo numero nos dois",
         transcrever.SEGUNDOS_DO_GANCHO, fala.SEGUNDOS_DO_GANCHO)


shutil.rmtree(PASTA, ignore_errors=True)

print("\n" + "=" * 52)
if falhas:
    print("%d TESTE(S) FALHARAM:" % len(falhas))
    for falha in falhas:
        print("  - " + falha)
    sys.exit(1)
print("Todos os testes de fala passaram.")
