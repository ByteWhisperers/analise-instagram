"""T4 - Transcricao.

Para cada video ja baixado: extrai o audio com o ffmpeg e transcreve com o
faster-whisper, localmente, de graca.

Cada trecho sai com o segundo em que comeca. E isso que permite a analise da
T5 perguntar "o que foi falado nos primeiros 3 segundos" - o gancho.

E retomavel: video que ja tem transcricao.json e pulado.

Uso:
    python src/transcrever.py
    python src/transcrever.py --perfil algumperfil --limite 1
    python src/transcrever.py --modelo base
"""

import argparse
import json
import sys
import time

import console
import banco
import config
import fala
import midia

# Quem sabe falar com o Whisper e o `fala.py` — o editor de pasta precisa da
# mesma capacidade sem perfil, sem post e sem banco. Aqui ficam so os nomes,
# para o resto do arquivo continuar lendo igual.
carregar_modelo = fala.carregar_modelo
transcrever_arquivo = fala.transcrever_arquivo
montar_transcricao = fala.montar_transcricao

SEGUNDOS_DO_GANCHO = fala.SEGUNDOS_DO_GANCHO


def _achar_video(pasta_post):
    """Devolve o arquivo de video da pasta do post, ou None se for foto."""
    for arquivo in sorted(pasta_post.glob("midia*")):
        if arquivo.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm"):
            return arquivo
    return None


def listar_pendentes(perfil_filtro=None, refazer=False):
    """Posts de video que ainda nao tem transcricao."""
    if not config.PERFIS.is_dir():
        return []

    pendentes = []
    for pasta_perfil in sorted(config.PERFIS.iterdir()):
        if not pasta_perfil.is_dir():
            continue
        if perfil_filtro and pasta_perfil.name != perfil_filtro:
            continue

        for pasta_post in sorted(pasta_perfil.iterdir()):
            if not pasta_post.is_dir():
                continue
            if not (pasta_post / "post.json").exists():
                continue
            if (pasta_post / "transcricao.json").exists() and not refazer:
                continue

            video = _achar_video(pasta_post)
            if video:
                pendentes.append((pasta_perfil.name, pasta_post, video))

    return pendentes


def processar(modelo, pasta_post, video, nome_modelo, idioma, ffmpeg, conexao=None):
    """Extrai o audio, transcreve e grava. Devolve o dicionario ou None."""
    wav = pasta_post / "audio.wav"

    try:
        if not midia.tem_audio(video, ffmpeg):
            print("      video sem trilha de audio - pulando")
            return None
        midia.extrair_audio(video, wav, ffmpeg)
    except midia.ErroDeMidia as erro:
        print("      %s" % erro)
        return None

    inicio = time.monotonic()
    segmentos, palavras, texto, duracao = transcrever_arquivo(modelo, wav, idioma)
    gasto = time.monotonic() - inicio

    transcricao = montar_transcricao(segmentos, palavras, texto, duracao, gasto,
                                     nome_modelo, idioma)

    with (pasta_post / "transcricao.json").open("w", encoding="utf-8") as aberto:
        json.dump(transcricao, aberto, ensure_ascii=False, indent=2)

    if conexao:
        banco.salvar_transcricao(conexao, pasta_post.name, transcricao)

    wav.unlink(missing_ok=True)  # o WAV so serve para transcrever; ocupa espaco a toa
    return transcricao


def ler_argumentos(cfg):
    transcricao = cfg.get("transcricao", {})
    parser = argparse.ArgumentParser(
        description="Transcreve os videos ja baixados, localmente.")
    parser.add_argument("--perfil", help="So os videos deste perfil.")
    parser.add_argument("--limite", type=int,
                        help="Transcreve no maximo N videos e para.")
    parser.add_argument("--modelo", default=transcricao.get("modelo", "small"),
                        choices=["tiny", "base", "small", "medium"])
    parser.add_argument("--tipo-computacao",
                        default=transcricao.get("tipo_computacao", "int8"))
    parser.add_argument("--idioma", default=transcricao.get("idioma", "pt"))
    parser.add_argument("--refazer", action="store_true",
                        help="Transcreve de novo o que ja tem transcricao.")
    return parser.parse_args()


def main():
    console.preparar()
    try:
        cfg = config.carregar()
    except config.ErroDeConfig as erro:
        print("\nERRO DE CONFIGURACAO\n\n%s\n" % erro, file=sys.stderr)
        return 1

    args = ler_argumentos(cfg)

    try:
        ffmpeg = midia.achar_ffmpeg()
    except midia.ErroDeMidia as erro:
        print("\n%s\n" % erro, file=sys.stderr)
        return 1

    pendentes = listar_pendentes(args.perfil, args.refazer)
    if args.limite:
        pendentes = pendentes[:args.limite]

    if not pendentes:
        print("Nenhum video pendente de transcricao.")
        print("Rode antes:  python src/coletar.py --termo \"...\"")
        return 0

    print("%d video(s) para transcrever." % len(pendentes))
    print("Nesta maquina, espere algo entre 3 e 5 minutos por minuto de video.\n")

    modelo = carregar_modelo(args.modelo, args.tipo_computacao)

    feitos = 0
    tempo_total = 0.0
    audio_total = 0.0
    conexao = banco.conectar()

    try:
        for indice, (perfil, pasta_post, video) in enumerate(pendentes, start=1):
            print("(%d/%d) %s / %s" % (indice, len(pendentes), perfil,
                                       pasta_post.name))

            try:
                resultado = processar(modelo, pasta_post, video, args.modelo,
                                      args.idioma, ffmpeg, conexao)
            except (OSError, RuntimeError, ValueError) as erro:
                print("      falhou (%s) - segue para o proximo" % erro)
                continue

            if resultado is None:
                continue

            feitos += 1
            tempo_total += resultado["tempo_de_transcricao_segundos"]
            audio_total += resultado["duracao_audio_segundos"]

            print("      %.0fs de video em %.0fs (%.1fx) | %d trechos | %d palavras"
                  % (resultado["duracao_audio_segundos"],
                     resultado["tempo_de_transcricao_segundos"],
                     resultado["quantas_vezes_a_duracao"] or 0,
                     len(resultado["segmentos"]),
                     len(resultado["palavras"])))
            if resultado["gancho_falado"]:
                print("      gancho: \"%s\"" % resultado["gancho_falado"][:70])
    finally:
        conexao.close()

    print("\n%d video(s) transcrito(s)." % feitos)
    if feitos and audio_total:
        print("Custo real desta maquina: %.1fx a duracao do video "
              "(%.0f min de video em %.0f min)." % (
                  tempo_total / audio_total, audio_total / 60, tempo_total / 60))
    return 0


if __name__ == "__main__":
    sys.exit(main())
