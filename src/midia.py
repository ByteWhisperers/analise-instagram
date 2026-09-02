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
