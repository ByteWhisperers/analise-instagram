"""T8 - Edicao em lote.

Pega um video e monta o formato de pagina de meme: fundo branco, video no
centro, headline em cima, @ do perfil, legenda queimada no meio.

Feito para volume: um comando edita 50 videos seguidos. O visual mora em
`templates/*.json`, nunca no codigo.

Tres modos, com publicos diferentes:

    --pasta   material proprio, uma pasta de mp4 + um roteiro de headlines.
              **Nao toca no banco.** E o caminho do molde, e o modo principal.
    --video   um arquivo avulso, para conferir template rapido.
    --lote    os videos coletados, lendo do banco. **Quebrado desde a migracao
              para o PostgreSQL** — ver a nota em `editar_em_lote`.

Uso:
    python src/editar.py --pasta
    python src/editar.py --pasta dados/gravacoes --template meu-estilo
    python src/editar.py --video entrada.mp4 --headline "Olha isso"
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from datetime import datetime
from pathlib import Path

import console
import banco
import config
import consultas
import fala
import legenda as modulo_legenda
import midia
import roteiro as modulo_roteiro

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

    # Contorno. So entra quando o template pede, e o padrao e zero — assim o
    # `meme-branco`, que tem texto preto sobre fundo branco, continua saindo
    # identico ao que sempre saiu. Existe para o caso oposto: quando o video
    # ocupa a tela toda, o texto cai POR CIMA da imagem e sem contorno some no
    # primeiro quadro claro. Mesmas chaves que o bloco `legenda` ja usa.
    contorno = estilo.get("contorno", 0)
    if contorno:
        partes.append("borderw=%d" % contorno)
        partes.append("bordercolor=%s"
                      % cor_para_ffmpeg(estilo.get("cor_contorno", "#000000")))

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
    """Edita a fila inteira. Um video que falha nao derruba os outros.

    ATENCAO — DIVIDA DA T11. Este caminho fala com o SQLite (`banco`,
    `consultas`), e `dados/analise.db` deixou de existir na migracao para o
    PostgreSQL. **Nao roda.** Ficou de pe, e nao foi apagado, porque a porta da
    Fase 3 e trabalho da T11 e nao deste. Quem edita hoje e `editar_pasta`.
    """
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


# ------------------------------------------------------------ modo pasta


NOME_PADRAO_DO_ROTEIRO = "roteiro.txt"


def listar_videos(pasta):
    """Os videos da pasta, em ordem. Nao entra em subpasta de proposito.

    Uma pasta so, plana, e o que uma pessoa consegue conferir antes de mandar
    editar 50 arquivos. Recursao aqui so serviria para editar por engano.
    """
    pasta = Path(pasta)
    if not pasta.is_dir():
        raise ErroDeEdicao(
            "A pasta '%s' nao existe.\n"
            "Crie ela e jogue seus videos dentro." % pasta)

    return sorted((arquivo for arquivo in pasta.iterdir()
                   if arquivo.is_file() and modulo_roteiro.e_video(arquivo.name)),
                  key=lambda caminho: caminho.name.lower())


def ler_roteiro(pasta, caminho=None):
    """Le o arquivo de headlines. Sem roteiro nao e erro — e lote sem headline."""
    arquivo = Path(caminho) if caminho else Path(pasta) / NOME_PADRAO_DO_ROTEIRO
    if not arquivo.is_file():
        if caminho:
            raise ErroDeEdicao("Roteiro '%s' nao encontrado." % arquivo)
        return [], []
    return modulo_roteiro.ler(arquivo.read_text(encoding="utf-8"))


def _modelo_sob_demanda(nome, tipo_computacao):
    """So carrega o Whisper se algum video realmente precisar dele.

    Carregar o modelo custa alguns segundos e ~1 GB de memoria. Numa pasta em
    que tudo ja esta no cache, esse preco nao deve ser pago.
    """
    guardado = {}

    def obter():
        if "modelo" not in guardado:
            guardado["modelo"] = fala.carregar_modelo(nome, tipo_computacao)
        return guardado["modelo"]

    return obter


def editar_pasta(pasta, template, pasta_saida, pares, ffmpeg=None,
                 obter_modelo=None, nome_modelo="small", idioma="pt",
                 perfil="", refazer=False, refazer_transcricao=False):
    """Edita a pasta inteira. Devolve a lista de resultados, um por video.

    Um video que falha **nao derruba o lote** — em 50 arquivos, um mp4 truncado
    nao pode custar as outras 49 edicoes. A falha entra no relatorio com o
    motivo.

    Sem `obter_modelo`, sai sem legenda: e o modo de conferir o template rapido,
    sem pagar transcricao.
    """
    pasta_saida.mkdir(parents=True, exist_ok=True)
    resultados = []

    videos = listar_videos(pasta)
    for indice, video in enumerate(videos, start=1):
        headline = pares.get(video.name, "")
        registro = {"arquivo": video.name, "headline": headline}
        print("(%d/%d) %s" % (indice, len(videos), video.name))

        saida = pasta_saida / ("%s.mp4" % video.stem)
        if saida.exists() and not refazer:
            print("      ja editado - pulando (use --refazer para refazer)")
            registro["situacao"] = "pulado"
            resultados.append(registro)
            continue

        palavras = []
        if obter_modelo:
            try:
                transcricao, do_cache = fala.palavras_de_video(
                    video, obter_modelo, nome_modelo, idioma, ffmpeg,
                    refazer=refazer_transcricao)
            except midia.ErroDeMidia as erro:
                print("      sem audio aproveitavel: %s" % str(erro)[:200])
                transcricao, do_cache = None, False

            if transcricao is None:
                print("      video sem trilha de audio - segue sem legenda")
            else:
                palavras = transcricao.get("palavras") or []
                registro["transcricao_do_cache"] = do_cache
                registro["segundos_de_audio"] = transcricao.get(
                    "duracao_audio_segundos")
                print("      %d palavras %s"
                      % (len(palavras),
                         "(do cache)" if do_cache else
                         "em %.0fs de transcricao"
                         % (transcricao.get("tempo_de_transcricao_segundos") or 0)))

        try:
            gasto = editar_video(video, saida, template, headline, perfil,
                                 palavras, ffmpeg)
        except (ErroDeEdicao, midia.ErroDeMidia) as erro:
            print("      FALHOU: %s" % str(erro)[:300])
            registro["situacao"] = "falhou"
            registro["erro"] = str(erro)[:500]
            resultados.append(registro)
            continue

        registro["situacao"] = "editado"
        registro["saida"] = str(saida)
        registro["segundos_de_edicao"] = round(gasto, 1)
        registro["palavras_na_legenda"] = len(palavras)
        resultados.append(registro)
        print("      pronto em %.1fs -> %s" % (gasto, saida.name))

    return resultados


def gravar_relatorio(resultados, template, pasta_saida):
    """O tempo por video, em arquivo. E o criterio 4 da T8.

    Vai para um JSON e nao para o banco porque video proprio nao tem
    `content_id` — as tabelas `media_assets` e `processing_jobs` sao chaveadas
    por post do Instagram, e forcar um vinculo ali torceria o schema.
    """
    editados = [r for r in resultados if r.get("situacao") == "editado"]
    tempo = sum(r.get("segundos_de_edicao") or 0 for r in editados)

    relatorio = {
        "template": template.get("nome"),
        "feito_em": datetime.now().isoformat(timespec="seconds"),
        "editados": len(editados),
        "pulados": len([r for r in resultados if r.get("situacao") == "pulado"]),
        "falhados": len([r for r in resultados if r.get("situacao") == "falhou"]),
        "segundos_totais": round(tempo, 1),
        "segundos_por_video": round(tempo / len(editados), 1) if editados else None,
        "videos": resultados,
    }

    destino = pasta_saida / "relatorio.json"
    with destino.open("w", encoding="utf-8") as aberto:
        json.dump(relatorio, aberto, ensure_ascii=False, indent=2)
    return relatorio, destino


def ler_argumentos():
    parser = argparse.ArgumentParser(
        description="Edita video no formato de pagina de meme, em lote.")
    parser.add_argument("--template", default="padrao")
    parser.add_argument("--headline", default="",
                        help="Texto de cima. Em lote, vale para todos.")

    parser.add_argument("--video", help="Editar um arquivo avulso.")
    parser.add_argument("--saida", help="Arquivo de saida (com --video).")
    parser.add_argument("--perfil", default="", help="O @ que aparece no video.")

    parser.add_argument("--pasta", nargs="?", const=str(config.GRAVACOES),
                        help="Editar uma pasta de videos seus. Sem valor, usa "
                             "dados/gravacoes.")
    parser.add_argument("--roteiro",
                        help="Lista de headlines. Padrao: roteiro.txt dentro "
                             "da pasta.")
    parser.add_argument("--sem-legenda", action="store_true", dest="sem_legenda",
                        help="Nao transcreve. Sai so com headline e @.")
    parser.add_argument("--modelo", default="small",
                        choices=["tiny", "base", "small", "medium"],
                        help="Modelo do Whisper para a legenda.")
    parser.add_argument("--tipo-computacao", default="int8",
                        dest="tipo_computacao")
    parser.add_argument("--idioma", default="pt")
    parser.add_argument("--refazer-transcricao", action="store_true",
                        dest="refazer_transcricao",
                        help="Ignora o cache de palavras e transcreve de novo.")

    parser.add_argument("--lote", action="store_true",
                        help="Editar os videos coletados (QUEBRADO - ver T11).")
    parser.add_argument("--perfis", action="append",
                        help="Restringe o lote a estes perfis. Pode repetir.")
    parser.add_argument("--limite", type=int, default=50)
    parser.add_argument("--refazer", action="store_true")

    args = parser.parse_args()
    if not args.video and not args.lote and args.pasta is None:
        parser.error("informe --pasta para uma pasta sua, --video para um "
                     "arquivo, ou --lote para a fila do banco")
    return args


def rodar_pasta(args, template, ffmpeg):
    """O modo pasta, de ponta a ponta. Devolve o codigo de saida do processo."""
    pasta = Path(args.pasta)
    pasta_saida = config.SAIDA / "editados"

    videos = listar_videos(pasta)
    if not videos:
        print("Nenhum video em %s." % pasta, file=sys.stderr)
        print("Aceito: %s" % ", ".join(modulo_roteiro.EXTENSOES_DE_VIDEO),
              file=sys.stderr)
        return 1

    entradas, problemas = ler_roteiro(pasta, args.roteiro)
    pares, sem_headline, sem_video = modulo_roteiro.parear(
        [video.name for video in videos], entradas)

    # As reclamacoes vem ANTES de editar. Descobrir que a headline nao pareou
    # depois de 40 minutos de ffmpeg seria descobrir tarde demais.
    reclamacoes = modulo_roteiro.resumir_problemas(problemas, sem_video)
    if reclamacoes:
        print("Problemas no roteiro:")
        for linha in reclamacoes:
            print(linha)
        print()

    if sem_headline:
        print("%d video(s) sem headline no roteiro: %s"
              % (len(sem_headline), ", ".join(sem_headline[:5])
                 + (" ..." if len(sem_headline) > 5 else "")))
        if args.headline:
            print("      vao usar o --headline passado na linha de comando")
        print()

    # `--headline` e o texto de quem nao esta no roteiro, nao um substituto dele
    for nome in sem_headline:
        if args.headline:
            pares[nome] = args.headline

    obter_modelo = None
    if not args.sem_legenda:
        obter_modelo = _modelo_sob_demanda(args.modelo, args.tipo_computacao)

    print("%d video(s) em %s, template '%s'%s.\n"
          % (len(videos), pasta, template.get("nome", args.template),
             ", sem legenda" if args.sem_legenda else ""))

    resultados = editar_pasta(
        pasta, template, pasta_saida, pares, ffmpeg, obter_modelo,
        args.modelo, args.idioma, args.perfil, args.refazer,
        args.refazer_transcricao)

    relatorio, caminho = gravar_relatorio(resultados, template, pasta_saida)

    print("\n%d editado(s), %d pulado(s), %d falhou(ram)."
          % (relatorio["editados"], relatorio["pulados"],
             relatorio["falhados"]))
    if relatorio["segundos_por_video"]:
        print("Media de %.1fs por video. Total: %.1f minutos."
              % (relatorio["segundos_por_video"],
                 relatorio["segundos_totais"] / 60))
    print("Pasta: %s" % pasta_saida)
    print("Relatorio: %s" % caminho)
    return 0 if not relatorio["falhados"] else 1


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

    if args.pasta is not None:
        try:
            return rodar_pasta(args, template, ffmpeg)
        except (ErroDeEdicao, midia.ErroDeMidia) as erro:
            print("\n%s\n" % erro, file=sys.stderr)
            return 1

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
