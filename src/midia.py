"""Encontrar o ffmpeg e extrair audio.

Separado da transcricao porque o problema e outro: aqui e so lidar com o
sistema (achar o executavel, rodar o processo). A transcricao nao precisa
saber nada disso.
"""

import os
import shutil
import subprocess
from pathlib import Path

TAXA_DE_AMOSTRAGEM = 16000  # o que o Whisper espera; menos que isso ele reamostra

_PASTA_WINGET = (
    Path(os.environ.get("LOCALAPPDATA", ""))
    / "Microsoft" / "WinGet" / "Packages"
)


class ErroDeMidia(Exception):
    """Falha ao achar o ffmpeg ou ao extrair o audio."""


def achar_ffmpeg():
    """Devolve o caminho do ffmpeg.

    Tenta o PATH primeiro. Se o terminal foi aberto antes da instalacao, o PATH
    ainda esta velho - por isso procura tambem na pasta do WinGet.
    """
    no_path = shutil.which("ffmpeg")
    if no_path:
        return no_path

    if _PASTA_WINGET.is_dir():
        for encontrado in _PASTA_WINGET.glob("*FFmpeg*/**/bin/ffmpeg.exe"):
            return str(encontrado)

    raise ErroDeMidia(
        "Nao achei o ffmpeg.\n"
        "Se ele acabou de ser instalado, feche este terminal e abra outro.\n"
        "Para instalar:  winget install Gyan.FFmpeg"
    )


# ------------------------------------------------------------------ medir
#
# O ffmpeg nao serve so para escrever video: ele LE. Os leitores abaixo
# devolvem texto cru, sem interpretar nada — quem interpreta e `formato.py`,
# que e funcao pura e da para conferir sem ter mp4 na maquina.
#
# Sao DUAS passadas por video, nao quatro: a deteccao de cena precisa da taxa
# de quadros cheia, e o resto cabe junto numa passada a 1 quadro por segundo.


LIMIAR_DE_CENA = 0.3  # acima disto, o quadro mudou o bastante para ser corte


def _rodar(comando, timeout=900):
    """Roda o ffmpeg e devolve (stdout, stderr). Nao levanta por codigo de saida.

    O `volumedetect` e o `cropdetect` escrevem no stderr e ainda assim terminam
    bem; tratar stderr como falha perderia justamente a medida.
    """
    try:
        resultado = subprocess.run(comando, capture_output=True, text=True,
                                   timeout=timeout, errors="replace")
    except subprocess.TimeoutExpired:
        raise ErroDeMidia("O ffmpeg passou de %ds medindo. Arquivo grande "
                          "demais ou travado." % timeout)
    return resultado.stdout or "", resultado.stderr or ""


def ler_cortes(video, ffmpeg=None, limiar=LIMIAR_DE_CENA):
    """Os segundos em que a cena muda. Passada de taxa cheia.

    `scene` compara cada quadro com o anterior e devolve 0 a 1. Acima do
    limiar, houve corte. Nao e perfeito — movimento de camera forte tambem
    pontua — mas e a medida que existe sem modelo nenhum, e serve para
    comparar videos entre si, que e o que interessa.
    """
    executavel = ffmpeg or achar_ffmpeg()
    saida, erro = _rodar([
        executavel, "-hide_banner", "-nostats",
        "-i", str(video),
        "-vf", "select='gt(scene,%s)',metadata=print:file=-" % limiar,
        "-an", "-f", "null", "-",
    ])
    return saida + erro


def ler_imagem(video, ffmpeg=None, por_segundo=1):
    """Brilho, saturacao e tarjas. Passada leve, a 1 quadro por segundo.

    Tres medidas na mesma corrente porque as tres querem os mesmos quadros:
    decodificar o video de novo para cada uma seria pagar tres vezes.
    """
    executavel = ffmpeg or achar_ffmpeg()
    saida, erro = _rodar([
        executavel, "-hide_banner", "-nostats",
        "-i", str(video),
        "-vf", "fps=%d,cropdetect,signalstats,metadata=print:file=-" % por_segundo,
        "-an", "-f", "null", "-",
    ])
    return saida + erro


def ler_audio(video, ffmpeg=None):
    """Volume medio e de pico, em dB. Vazio quando o video e mudo."""
    executavel = ffmpeg or achar_ffmpeg()
    if not tem_audio(video, executavel):
        return ""
    saida, erro = _rodar([
        executavel, "-hide_banner", "-nostats",
        "-i", str(video),
        "-af", "volumedetect", "-vn", "-f", "null", "-",
    ])
    return saida + erro


def ler_ficha(video, ffmpeg=None):
    """Largura, altura, fps e duracao, do ffprobe. Uma linha de texto."""
    probe = _ffprobe(ffmpeg)
    if not probe:
        raise ErroDeMidia("Nao achei o ffprobe ao lado do ffmpeg.")

    resultado = subprocess.run([
        str(probe), "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate:format=duration",
        "-of", "default=nw=1",
        str(video),
    ], capture_output=True, text=True, errors="replace")
    return resultado.stdout or ""


def extrair_audio(video, destino_wav, ffmpeg=None):
    """Video -> WAV 16 kHz mono.

    O arquivo de audio fica muito menor que o video e e o formato que a
    transcricao consome direto, sem reamostragem.
    """
    executavel = ffmpeg or achar_ffmpeg()
    destino_wav.parent.mkdir(parents=True, exist_ok=True)

    comando = [
        executavel,
        "-y",                    # sobrescreve sem perguntar
        "-loglevel", "error",
        "-i", str(video),
        "-vn",                   # descarta o video
        "-ac", "1",              # mono
        "-ar", str(TAXA_DE_AMOSTRAGEM),
        "-c:a", "pcm_s16le",
        str(destino_wav),
    ]

    resultado = subprocess.run(comando, capture_output=True, text=True)

    if resultado.returncode != 0:
        raise ErroDeMidia(
            "O ffmpeg falhou em %s:\n%s" % (video.name, resultado.stderr.strip())
        )

    if not destino_wav.exists() or destino_wav.stat().st_size == 0:
        raise ErroDeMidia("O ffmpeg terminou sem erro, mas o audio saiu vazio: %s"
                          % video.name)

    return destino_wav


def _ffprobe(ffmpeg=None):
    """O ffprobe que mora ao lado do ffmpeg, ou None se nao houver."""
    executavel = ffmpeg or achar_ffmpeg()
    probe = Path(executavel).with_name("ffprobe.exe")
    return probe if probe.exists() else None


def dimensoes(video, ffmpeg=None):
    """`(largura, altura)` do video, em pixels. Levanta se nao der para ler.

    O enquadramento precisa disto para fazer a conta em inteiro em vez de em
    expressao do ffmpeg — ver `enquadrar.py`. Sem isto nao ha como prender o
    corte dentro da imagem.
    """
    probe = _ffprobe(ffmpeg)
    if not probe:
        raise ErroDeMidia(
            "Nao achei o ffprobe ao lado do ffmpeg. Ele vem junto na "
            "instalacao normal:  winget install Gyan.FFmpeg")

    comando = [
        str(probe),
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0:s=x",
        str(video),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    bruto = (resultado.stdout or "").strip().splitlines()

    if resultado.returncode != 0 or not bruto:
        raise ErroDeMidia(
            "Nao consegui ler as dimensoes de %s.\n%s"
            % (Path(video).name, (resultado.stderr or "").strip()[:300]))

    try:
        largura, altura = bruto[0].split("x")[:2]
        return int(largura), int(altura)
    except ValueError:
        raise ErroDeMidia(
            "O ffprobe devolveu algo que nao sao dimensoes para %s: %r"
            % (Path(video).name, bruto[0]))


def tem_audio(video, ffmpeg=None):
    """Diz se o arquivo tem trilha de audio. Video mudo nao vale transcrever."""
    probe = _ffprobe(ffmpeg)
    if not probe:
        return True  # sem ffprobe, deixa a extracao decidir

    comando = [
        str(probe),
        "-loglevel", "error",
        "-select_streams", "a",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0",
        str(video),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    return "audio" in resultado.stdout
