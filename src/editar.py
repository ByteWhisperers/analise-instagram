"""T8 - Edicao em lote.

Pega um video e monta o formato de pagina de meme: fundo branco, video no
centro, headline em cima, @ do perfil, legenda queimada no meio.

Feito para volume: um comando edita 50 videos seguidos. O visual mora em
`templates/*.json`, nunca no codigo.

Uso:
    python src/editar.py --lote --perfis algumperfil --limite 50
    python src/editar.py --video entrada.mp4 --headline "Olha isso"
    python src/editar.py --lote --template meu-estilo
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

import console
import banco
import config
import consultas
import legenda as modulo_legenda
import midia

PASTA_DE_FONTES = Path("C:/Windows/Fonts")


class ErroDeEdicao(Exception):
    """Falha ao montar o video. Mensagem já pronta para o usuário."""


# ------------------------------------------------------------ caminhos


def cor_para_ffmpeg(cor):
    """'#8A8A8A' -> '0x8A8A8A'. O ffmpeg entende os dois, o 0x nunca dá dúvida."""
    if not cor:
        return "white"
    texto = str(cor).strip()
    return "0x" + texto[1:] if texto.startswith("#") else texto


def achar_fonte(nome):
    """Resolve o arquivo da fonte. Aceita nome solto ou caminho completo."""
    if not nome:
        return None

    candidato = Path(nome)
    if candidato.is_file():
        return candidato

    do_windows = PASTA_DE_FONTES / nome
    if do_windows.is_file():
        return do_windows

    raise ErroDeEdicao(
        "Nao achei a fonte '%s'.\n"
        "Use o nome do arquivo como esta em %s (ex.: arial.ttf, arialbd.ttf), "
        "ou o caminho completo." % (nome, PASTA_DE_FONTES))


def carregar_template(nome):
    arquivo = Path(nome)
    if not arquivo.is_file():
        arquivo = config.RAIZ / "templates" / ("%s.json" % nome)
    if not arquivo.is_file():
        raise ErroDeEdicao("Template '%s' nao encontrado em templates/." % nome)

    with arquivo.open(encoding="utf-8") as aberto:
        return json.load(aberto)


# ------------------------------------------------------------ filtros


def _quebrar_linhas(texto, largura):
    return "\n".join(textwrap.wrap(texto, width=largura)) if texto else ""


def _bloco_de_texto(rotulo, conteudo, estilo, pasta_trabalho, entrada, saida):
    """Monta um drawtext lendo tudo de arquivo, por nome curto.

    Dois problemas de Windows resolvidos do mesmo jeito:

    1. Texto com aspas, dois-pontos ou acento quebra o filtro se for inline —
       daí `textfile=`.
    2. Caminho de fonte como `C:/Windows/Fonts/arial.ttf` quebra o filtro no
       dois-pontos, **mesmo escapado**. Escapar não resolve; foi testado.
       A fonte é copiada para a pasta de trabalho e citada pelo nome puro,
       porque o ffmpeg roda com a pasta de trabalho como diretório atual.
    """
    arquivo = pasta_trabalho / ("%s.txt" % rotulo)
    arquivo.write_text(conteudo, encoding="utf-8")

    partes = [
        "textfile=%s.txt" % rotulo,
        "fontsize=%d" % estilo.get("tamanho", 48),
        "fontcolor=%s" % cor_para_ffmpeg(estilo.get("cor", "#000000")),
        "x=(w-text_w)/2",
        "y=%d" % estilo.get("topo", 100),
        "line_spacing=%d" % estilo.get("espaco_entre_linhas", 10),
    ]

    fonte = achar_fonte(estilo.get("fonte"))
    if fonte:
        nome_local = "fonte_%s%s" % (rotulo, fonte.suffix)
        shutil.copyfile(fonte, pasta_trabalho / nome_local)
        partes.append("fontfile=%s" % nome_local)

    return "[%s]drawtext=%s[%s]" % (entrada, ":".join(partes), saida)


def montar_filtros(template, headline, perfil, tem_logo, tem_legenda,
                   pasta_trabalho):
    """A corrente de filtros inteira, em ordem."""
    canvas = template["canvas"]
    area = template["video"]

    largura_video = canvas["largura"] - 2 * area.get("margem_lateral", 60)
    filtros = [
        "color=c=%s:s=%dx%d:r=%d[fundo]" % (
            cor_para_ffmpeg(canvas.get("fundo", "#FFFFFF")),
            canvas["largura"], canvas["altura"], canvas.get("fps", 30)),
        "[0:v]scale=%d:%d:force_original_aspect_ratio=decrease[video]" % (
            largura_video, area.get("altura", 980)),
        "[fundo][video]overlay=(W-w)/2:%d+(%d-h)/2:shortest=1[base]" % (
            area.get("topo", 560), area.get("altura", 980)),
    ]

    atual = "base"

    cabecalho = template.get("headline", {})
    if cabecalho.get("mostrar", True) and headline:
        texto = _quebrar_linhas(headline,
                                cabecalho.get("largura_em_caracteres", 30))
        filtros.append(_bloco_de_texto("headline", texto, cabecalho,
                                       pasta_trabalho, atual, "comheadline"))
        atual = "comheadline"

    dados_perfil = template.get("perfil", {})
    if dados_perfil.get("mostrar", True) and perfil:
        texto = "%s%s" % (dados_perfil.get("prefixo", "@"), perfil)
        filtros.append(_bloco_de_texto("perfil", texto, dados_perfil,
                                       pasta_trabalho, atual, "comperfil"))
        atual = "comperfil"

    if tem_logo:
        dados_logo = template.get("logo", {})
        filtros.append("[1:v]scale=-1:%d[logo]" % dados_logo.get("altura", 90))
        filtros.append("[%s][logo]overlay=(W-w)/2:%d[comlogo]"
                       % (atual, dados_logo.get("topo", 110)))
        atual = "comlogo"

    if tem_legenda:
        filtros.append("[%s]ass=legenda.ass[final]" % atual)
        atual = "final"

    return filtros, atual


# ------------------------------------------------------------ execucao


def editar_video(entrada, saida, template, headline="", perfil="", palavras=None,
                 ffmpeg=None):
    """Edita um video. Devolve quantos segundos levou."""
    entrada = Path(entrada)
    if not entrada.is_file():
        raise ErroDeEdicao("Video de entrada nao existe: %s" % entrada)

    executavel = ffmpeg or midia.achar_ffmpeg()
    pasta_trabalho = Path(tempfile.mkdtemp(prefix="edicao-"))

    try:
        arquivo_legenda = None
        if palavras and template.get("legenda", {}).get("mostrar", True):
            arquivo_legenda = modulo_legenda.gravar(
                palavras, template["legenda"], pasta_trabalho / "legenda.ass")

        caminho_logo = template.get("logo", {}).get("arquivo")
        tem_logo = bool(caminho_logo) and Path(caminho_logo).is_file()

        filtros, ultimo = montar_filtros(template, headline, perfil, tem_logo,
                                         bool(arquivo_legenda), pasta_trabalho)

        comando = [executavel, "-y", "-loglevel", "error", "-i", str(entrada.resolve())]
        if tem_logo:
            comando += ["-i", str(Path(caminho_logo).resolve())]

        saida_config = template.get("saida", {})
        comando += [
            "-filter_complex", ";".join(filtros),
            "-map", "[%s]" % ultimo,
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", saida_config.get("preset", "veryfast"),
            "-crf", str(saida_config.get("qualidade", 23)),
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "%dk" % saida_config.get("audio_kbps", 128),
            "-shortest",
            "-movflags", "+faststart",
            str(Path(saida).resolve()),
        ]

        Path(saida).parent.mkdir(parents=True, exist_ok=True)

        inicio = time.monotonic()
        # cwd na pasta de trabalho: assim os filtros citam "legenda.ass" e
        # "headline.txt" por nome, sem caminho para escapar.
        resultado = subprocess.run(comando, capture_output=True, text=True,
                                   cwd=str(pasta_trabalho))
        gasto = time.monotonic() - inicio

        if resultado.returncode != 0:
            raise ErroDeEdicao("O ffmpeg falhou em %s:\n%s"
                               % (entrada.name, resultado.stderr.strip()[:1500]))

        if not Path(saida).exists() or Path(saida).stat().st_size == 0:
            raise ErroDeEdicao("O ffmpeg terminou sem erro mas nao gerou arquivo.")

        return gasto
    finally:
        shutil.rmtree(pasta_trabalho, ignore_errors=True)


# ------------------------------------------------------------ lote


def _palavras_do_banco(conexao, post_id):
    return [
        {"palavra": linha["palavra"], "inicio": linha["inicio"],
         "fim": linha["fim"]}
        for linha in consultas.palavras_do_post(conexao, post_id)
    ]


def editar_em_lote(conexao, template, alvos, pasta_saida, headline_padrao,
                   ffmpeg, refazer=False):
    """Edita a fila inteira. Um video que falha nao derruba os outros."""
    pasta_saida.mkdir(parents=True, exist_ok=True)
    feitos, pulados, falhados = 0, 0, 0
    tempo_total = 0.0

    for indice, alvo in enumerate(alvos, start=1):
        entrada = alvo.get("caminho_midia")
        post_id = alvo.get("id")
        perfil = alvo.get("usuario", "")

        print("(%d/%d) %s / %s" % (indice, len(alvos), perfil, post_id))

        if not entrada or not Path(entrada).is_file():
            print("      sem arquivo de midia - pulando")
            pulados += 1
            continue

        saida = pasta_saida / ("%s-%s.mp4" % (perfil, post_id))
        if saida.exists() and not refazer:
            print("      ja editado - pulando")
            pulados += 1
            continue

        palavras = _palavras_do_banco(conexao, post_id)
        headline = headline_padrao or (alvo.get("gancho_escrito") or "")

        try:
            gasto = editar_video(entrada, saida, template, headline, perfil,
                                 palavras, ffmpeg)
        except ErroDeEdicao as erro:
            print("      FALHOU: %s" % str(erro)[:300])
            falhados += 1
            continue

        banco.registrar_edicao(conexao, entrada, saida, template.get("nome"),
                               post_id)
        feitos += 1
        tempo_total += gasto
        print("      pronto em %.1fs | %d palavras na legenda" % (gasto,
                                                                  len(palavras)))

    return feitos, pulados, falhados, tempo_total


def ler_argumentos():
    parser = argparse.ArgumentParser(
        description="Edita video no formato de pagina de meme, em lote.")
    parser.add_argument("--template", default="padrao")
    parser.add_argument("--headline", default="",
                        help="Texto de cima. Em lote, vale para todos.")

    parser.add_argument("--video", help="Editar um arquivo avulso.")
    parser.add_argument("--saida", help="Arquivo de saida (com --video).")
    parser.add_argument("--perfil", default="", help="O @ que aparece no video.")

    parser.add_argument("--lote", action="store_true",
                        help="Editar os videos ja coletados.")
    parser.add_argument("--perfis", action="append",
                        help="Restringe o lote a estes perfis. Pode repetir.")
    parser.add_argument("--limite", type=int, default=50)
    parser.add_argument("--refazer", action="store_true")

    args = parser.parse_args()
    if not args.video and not args.lote:
        parser.error("informe --video para um arquivo, ou --lote para a fila")
    return args


def main():
    console.preparar()
    args = ler_argumentos()

    try:
        template = carregar_template(args.template)
        ffmpeg = midia.achar_ffmpeg()
    except (ErroDeEdicao, midia.ErroDeMidia) as erro:
        print("\n%s\n" % erro, file=sys.stderr)
        return 1

    pasta_saida = config.SAIDA / "editados"

    if args.video:
        saida = Path(args.saida) if args.saida else (
            pasta_saida / ("%s-editado.mp4" % Path(args.video).stem))
        try:
            gasto = editar_video(args.video, saida, template, args.headline,
                                 args.perfil, None, ffmpeg)
        except ErroDeEdicao as erro:
            print("\n%s\n" % erro, file=sys.stderr)
            return 1
        print("Pronto em %.1fs: %s" % (gasto, saida))
        return 0

    conexao = banco.conectar()
    try:
        alvos = []
        if args.perfis:
            for usuario in args.perfis:
                alvos.extend(consultas.melhores_posts(
                    conexao, limite=args.limite, usuario=usuario, so_video=True))
        else:
            alvos = consultas.melhores_posts(conexao, limite=args.limite,
                                             so_video=True)

        if not alvos:
            print("Nenhum video coletado para editar.", file=sys.stderr)
            print("Rode antes:  python src/coletar.py --termo \"...\"",
                  file=sys.stderr)
            return 1

        print("%d video(s) na fila, template '%s'.\n"
              % (len(alvos), template.get("nome", args.template)))

        feitos, pulados, falhados, tempo = editar_em_lote(
            conexao, template, alvos, pasta_saida, args.headline, ffmpeg,
            args.refazer)
    finally:
        conexao.close()

    print("\n%d editado(s), %d pulado(s), %d falhou(ram)."
          % (feitos, pulados, falhados))
    if feitos:
        print("Media de %.1fs por video. Total: %.1f minutos."
              % (tempo / feitos, tempo / 60))
    print("Pasta: %s" % pasta_saida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
