"""Video -> palavras com o segundo de cada uma. Local, de graca, com cache.

**Por que existe separado:** ate 01/09/2026 o Whisper so era chamado de dentro
do `transcrever.py`, que varre `dados/perfis/` e grava no banco. O editor de
pasta precisa da mesma capacidade sem nada disso — sem perfil, sem post, sem
banco. Entao a parte que sabe falar com o Whisper mora aqui, e o
`transcrever.py` passou a importar daqui em vez de ter copia propria.

`word_timestamps=True` custa pouco a mais e entrega o segundo de CADA palavra.
E o que permite a legenda acender palavra por palavra. Sem isso, so daria para
acender frase inteira.

**O cache e o que torna o lote suportavel.** Transcrever custa de 3 a 5 vezes a
duracao do video nesta maquina. Trocar a cor da legenda no template e rodar de
novo nao pode pagar esse preco duas vezes — entao o resultado fica em
`<video>.palavras.json`, ao lado do video, e a segunda rodada le do disco.
"""

import json
import time
from datetime import datetime
from pathlib import Path

import midia

SEGUNDOS_DO_GANCHO = 3.0
SUFIXO_DO_CACHE = ".palavras.json"


def carregar_modelo(nome, tipo_computacao):
    """Carrega o modelo uma vez so. No primeiro uso ele baixa (~500 MB no small)."""
    from faster_whisper import WhisperModel  # import tardio: e pesado

    print("Carregando o modelo '%s' (%s). No primeiro uso ele baixa sozinho."
          % (nome, tipo_computacao))
    inicio = time.monotonic()
    modelo = WhisperModel(nome, device="cpu", compute_type=tipo_computacao)
    print("Modelo pronto em %.1fs.\n" % (time.monotonic() - inicio))
    return modelo


def transcrever_arquivo(modelo, wav, idioma):
    """Devolve (segmentos, palavras, texto_completo, duracao_do_audio)."""
    segmentos_brutos, info = modelo.transcribe(
        str(wav),
        language=idioma,
        beam_size=1,          # maquina fraca: beam maior custa caro e ganha pouco
        vad_filter=True,      # corta silencio; acelera bastante
        vad_parameters={"min_silence_duration_ms": 500},
        word_timestamps=True,
    )

    segmentos = []
    palavras = []
    for segmento in segmentos_brutos:  # e um gerador: aqui e onde o trabalho acontece
        texto = segmento.text.strip()
        if not texto:
            continue

        segmentos.append({
            "inicio": round(segmento.start, 2),
            "fim": round(segmento.end, 2),
            "texto": texto,
        })

        for palavra in (segmento.words or []):
            limpa = palavra.word.strip()
            if limpa:
                palavras.append({
                    "palavra": limpa,
                    "inicio": round(palavra.start, 2),
                    "fim": round(palavra.end, 2),
                })

    texto_completo = " ".join(s["texto"] for s in segmentos)
    return segmentos, palavras, texto_completo, info.duration


def montar_transcricao(segmentos, palavras, texto, duracao, gasto, nome_modelo,
                       idioma):
    """O dicionario que vai para o disco e para o banco. Um formato so."""
    gancho = " ".join(s["texto"] for s in segmentos
                      if s["inicio"] < SEGUNDOS_DO_GANCHO)

    return {
        "texto": texto,
        "gancho_falado": gancho,
        "segmentos": segmentos,
        "palavras": palavras,
        "duracao_audio_segundos": round(duracao, 2),
        "tempo_de_transcricao_segundos": round(gasto, 1),
        "quantas_vezes_a_duracao": round(gasto / duracao, 1) if duracao else None,
        "modelo": nome_modelo,
        "idioma": idioma,
        "transcrito_em": datetime.now().isoformat(timespec="seconds"),
    }


# ------------------------------------------------------------------- cache


def caminho_do_cache(video):
    """`abertura.mp4` -> `abertura.palavras.json`, na mesma pasta."""
    video = Path(video)
    return video.with_name(video.stem + SUFIXO_DO_CACHE)


def ler_cache(video, modelo=None):
    """A transcricao ja feita, ou None.

    Com `modelo`, so aceita o cache se veio do mesmo modelo. Trocar `base` por
    `small` e pedir outra leitura do audio — reaproveitar seria mentir sobre
    qual modelo produziu aquelas palavras.
    """
    arquivo = caminho_do_cache(video)
    if not arquivo.is_file():
        return None

    try:
        with arquivo.open(encoding="utf-8") as aberto:
            guardado = json.load(aberto)
    except (OSError, ValueError):
        return None  # cache corrompido nao e erro: e so transcrever de novo

    if modelo and guardado.get("modelo") != modelo:
        return None
    if not isinstance(guardado.get("palavras"), list):
        return None
    return guardado


def gravar_cache(video, transcricao):
    arquivo = caminho_do_cache(video)
    with arquivo.open("w", encoding="utf-8") as aberto:
        json.dump(transcricao, aberto, ensure_ascii=False, indent=2)
    return arquivo


# ------------------------------------------------------------------ uso


def palavras_de_video(video, obter_modelo, nome_modelo, idioma="pt", ffmpeg=None,
                      refazer=False, pasta_temporaria=None):
    """Video -> transcricao completa. Le do cache quando pode.

    Devolve `(transcricao, veio_do_cache)`. Transcricao `None` quando o video
    nao tem trilha de audio — que nao e erro: e video mudo, e ele deve ser
    editado assim mesmo, sem legenda.

    `obter_modelo` e uma **funcao** que devolve o modelo, nao o modelo. A
    diferenca importa: numa pasta em que tudo ja esta no cache, carregar o
    Whisper custaria 11s e ~1 GB de memoria para nao ser usado uma vez. Aqui
    ele so e pedido depois de o cache falhar.
    """
    video = Path(video)

    if not refazer:
        guardado = ler_cache(video, nome_modelo)
        if guardado:
            return guardado, True

    if not midia.tem_audio(video, ffmpeg):
        return None, False

    modelo = obter_modelo()

    destino = Path(pasta_temporaria or video.parent) / (video.stem + ".audio.wav")
    midia.extrair_audio(video, destino, ffmpeg)

    try:
        inicio = time.monotonic()
        segmentos, palavras, texto, duracao = transcrever_arquivo(
            modelo, destino, idioma)
        gasto = time.monotonic() - inicio
    finally:
        # o WAV so serve para transcrever, e um Reel de 1 min ocupa ~2 MB
        destino.unlink(missing_ok=True)

    transcricao = montar_transcricao(segmentos, palavras, texto, duracao, gasto,
                                     nome_modelo, idioma)
    gravar_cache(video, transcricao)
    return transcricao, False
