"""O pipeline: nicho -> perfis -> conteúdo -> fila -> vídeo no disco.

    python src/pipeline.py descobrir "apostas"
    python src/pipeline.py coletar --nicho apostas
    python src/pipeline.py baixar
    python src/pipeline.py status
    python src/pipeline.py ranking --nicho apostas
    python src/pipeline.py schema "apostas"     <- rodada mínima de conferência

Cada etapa é um comando separado de propósito: coleta e download rodam em
processos diferentes, e é isso que permite parar no meio e continuar depois.

Idempotente em toda etapa. Quem garante isso são as constraints do banco —
`(platform, username)`, `(platform, platform_content_id)` e
`(job_type, entity_type, entity_id)` —, e não uma checagem em Python que dá
para esquecer de escrever.

**Este arquivo não escreve SQL.** Quem fala com o banco é `repos/`.
"""

import argparse
import json
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import coletor as mod_coletor
import console
import config
import db
import desempenho
from downloader import YtDlpDownloader
from repos import (consultas, contents, costs, jobs, media, metrics, niches,
                   profiles)
from storage import LocalStorage

TIPO_DOWNLOAD = "video_download"


def _linha(texto=""):
    print(texto)


def _titulo(texto):
    print("\n" + texto)
    print("-" * len(texto))


# ------------------------------------------------------------ freio de custo


def _confirmar_gasto(estimado, avisar_acima_de, forcar=False):
    """Para e pergunta antes de uma rodada cara.

    Existe porque o botão de custo é silencioso: dobrar os posts por perfil
    dobra a fatura sem nenhum aviso da Apify.
    """
    _linha("Custo estimado desta rodada: US$ %.4f" % estimado)

    if forcar or estimado <= avisar_acima_de:
        return True

    _linha("Isso passa do seu limite de aviso (US$ %.2f)." % avisar_acima_de)
    try:
        resposta = input("Rodar mesmo assim? [s/N] ").strip().lower()
    except (EOFError, OSError):
        _linha("Sem teclado para confirmar. Use --forcar se for proposital.")
        return False

    return resposta in ("s", "sim", "y", "yes")


def _montar_coletor(cfg, guardar_brutos=False):
    apify = config.apify(cfg)
    return mod_coletor.ApifyInstagramCollector(
        token=config.token_apify(cfg),
        actor=apify["actor"],
        plano=apify["plano"],
        teto_usd=apify["teto_usd_por_rodada"],
        guardar_brutos=guardar_brutos)


def _registrar_custo(conexao, operacao, coleta, coleta_id):
    """O custo real da rodada — ou a estimativa, marcada como estimativa."""
    real = coleta.custo_usd is not None
    costs.registrar(
        conexao, operacao, "apify", quantidade=coleta.itens,
        custo_total=coleta.custo_usd if real else costs.custo_apify(coleta.itens),
        coleta_id=coleta_id, estimado=not real)


# -------------------------------------------------------------- 1. descobrir


def descobrir(cfg, nicho, max_perfis=None, forcar=False):
    apify = config.apify(cfg)
    max_perfis = max_perfis or apify["max_perfis"]

    _titulo("1. Descoberta de perfis: %r" % nicho)

    estimado = float(costs.custo_apify(max_perfis, apify["plano"]))
    if not _confirmar_gasto(estimado, apify["avisar_acima_de_usd"], forcar):
        return 1

    coletor = _montar_coletor(cfg)

    with db.conectar(cfg) as cx:
        nicho_id = niches.obter_ou_criar(cx, nicho)
        coleta_id = jobs.abrir_coleta(cx, "profile_discovery", "apify",
                                      ator=coletor.actor, nicho_id=nicho_id)
        cx.commit()

        try:
            coleta = coletor.descobrir_perfis(nicho, max_perfis)
        except mod_coletor.ErroDeColeta as erro:
            jobs.fechar_coleta(cx, coleta_id, status=jobs.FALHA, erro=str(erro))
            cx.commit()
            _linha("FALHOU: %s" % erro)
            return 1

        novos = 0
        for perfil in coleta.perfis:
            perfil_id = profiles.salvar(cx, perfil, fonte="apify",
                                        ator=coletor.actor, run_id=coleta.run_id)
            if profiles.ligar_ao_nicho(cx, perfil_id, nicho_id, "busca"):
                novos += 1
            # A foto de agora. Gravada já na primeira vez, quando ainda não
            # serve de nada — porque crescimento é a diferença entre duas.
            profiles.gravar_snapshot(cx, perfil_id,
                                     seguidores=perfil.get("seguidores"),
                                     seguindo=perfil.get("seguindo"),
                                     conteudos=perfil.get("posts"),
                                     job_id=coleta_id)

        jobs.fechar_coleta(cx, coleta_id, encontrados=coleta.itens,
                           criados=novos,
                           atualizados=len(coleta.perfis) - novos,
                           run_id=coleta.run_id)
        _registrar_custo(cx, "profile_collection", coleta, coleta_id)
        cx.commit()

    _linha("%d perfis (%d novos no nicho). Custo real: US$ %.4f (%d itens)"
           % (len(coleta.perfis), novos, coleta.custo_usd or 0, coleta.itens))
    _linha()
    _linha("Nenhum foi julgado relevante ainda — a busca acha quem tem a")
    _linha("palavra no nome, não quem performa. Confira: pipeline.py status")
    return 0


# ---------------------------------------------------------------- 2. coletar


def coletar(cfg, nicho=None, perfis=None, posts_por_perfil=None,
            limite_perfis=None, forcar=False, so_aprovados=False):
    apify = config.apify(cfg)
    posts_por_perfil = posts_por_perfil or apify["posts_por_perfil"]
    limite_perfis = limite_perfis or apify["max_perfis"]

    _titulo("2. Coleta de conteúdo")

    with db.conectar(cfg) as cx:
        if perfis:
            usuarios = [u.strip() for u in perfis.split(",") if u.strip()]
        elif nicho:
            achado = niches.por_nome(cx, nicho)
            if not achado:
                _linha("Nicho %r não existe. Rode a descoberta antes." % nicho)
                return 1
            usuarios = [linha["username"] for linha in
                        profiles.do_nicho(cx, achado["id"], so_aprovados,
                                          limite_perfis)]
        else:
            _linha("Diga de onde: --nicho <nome> ou --perfis a,b,c")
            return 1

        if not usuarios:
            _linha("Nenhum perfil para coletar. Rode a descoberta antes:")
            _linha('  python src/pipeline.py descobrir "seu nicho"')
            return 1

        _linha("%d perfis, até %d posts cada" % (len(usuarios), posts_por_perfil))

        estimado = float(costs.custo_apify(
            len(usuarios) * posts_por_perfil + len(usuarios), apify["plano"]))
        if not _confirmar_gasto(estimado, apify["avisar_acima_de_usd"], forcar):
            return 1

        coletor = _montar_coletor(cfg)
        coleta_id = jobs.abrir_coleta(cx, "content_collection", "apify",
                                      ator=coletor.actor)
        cx.commit()

        try:
            coleta = coletor.coletar_conteudo(usuarios, posts_por_perfil)
        except mod_coletor.ErroDeColeta as erro:
            jobs.fechar_coleta(cx, coleta_id, status=jobs.FALHA, erro=str(erro))
            cx.commit()
            _linha("FALHOU: %s" % erro)
            return 1

        guarda = LocalStorage()
        na_fila = 0

        for perfil in coleta.perfis:
            perfil_id = profiles.salvar(cx, perfil, fonte="apify",
                                        ator=coletor.actor, run_id=coleta.run_id)
            profiles.gravar_snapshot(cx, perfil_id,
                                     seguidores=perfil.get("seguidores"),
                                     seguindo=perfil.get("seguindo"),
                                     conteudos=perfil.get("posts"),
                                     job_id=coleta_id)

        for post in coleta.posts:
            perfil_id = profiles.id_por_usuario(cx, post["perfil"])
            if perfil_id is None:
                # O Actor devolveu post de um perfil que não veio na lista de
                # perfis. Grava-se o mínimo, para não perder o post.
                perfil_id = profiles.salvar(cx, {"usuario": post["perfil"]},
                                            fonte="apify", ator=coletor.actor)

            conteudo_id = contents.salvar(cx, post, perfil_id)
            metrics.gravar_snapshot(
                cx, conteudo_id, post,
                horas_desde_post=desempenho.horas_desde(post.get("data_utc")),
                job_id=coleta_id)

            # O `post.json` no disco não é redundância: é o que permite
            # conferir a coleta a olho, sem abrir o banco.
            guarda.guardar_dados(post, post["perfil"], post["id"])

            if not post.get("e_video"):
                continue
            if media.tem(cx, conteudo_id, "video"):
                continue
            if jobs.enfileirar(cx, TIPO_DOWNLOAD, conteudo_id):
                na_fila += 1

        jobs.fechar_coleta(cx, coleta_id, encontrados=coleta.itens,
                           criados=len(coleta.posts), run_id=coleta.run_id)
        _registrar_custo(cx, "content_collection", coleta, coleta_id)
        cx.commit()

    _linha("%d posts, %d vídeos. %d novos na fila. Custo real: US$ %.4f"
           % (len(coleta.posts), len(coleta.videos), na_fila,
              coleta.custo_usd or 0))
    _linha("Próximo passo: python src/pipeline.py baixar")
    return 0


# ----------------------------------------------------------------- 3. baixar


def baixar(cfg, limite=None, concorrencia=None, tentar_de_novo=False):
    ajustes = config.download(cfg)
    concorrencia = concorrencia or ajustes["concorrencia"]
    limite = limite or 50

    _titulo("3. Download")

    baixador = YtDlpDownloader(
        timeout=ajustes["timeout_segundos"],
        cookies_do_navegador=ajustes["cookies_do_navegador"])
    guarda = LocalStorage()
    trabalho = Path(tempfile.mkdtemp(prefix="baixando-"))
    ok = falhou = 0

    try:
        with db.conectar(cfg) as cx:
            orfaos = jobs.destravar_orfaos(cx, TIPO_DOWNLOAD)
            if orfaos:
                _linha("%d item(ns) presos em 'running' voltaram para a fila."
                       % orfaos)

            if tentar_de_novo:
                _linha("%d falha(s) reenfileirada(s)."
                       % jobs.reenfileirar_falhas(cx, TIPO_DOWNLOAD))

            cx.commit()

            fila = jobs.proximos(cx, TIPO_DOWNLOAD, limite=limite)
            if not fila:
                _linha("Fila vazia. Nada a baixar.")
                return 0

            dados = contents.dados_para_download(
                cx, [item["entity_id"] for item in fila])

            _linha("%d na fila, %d por vez." % (len(fila), concorrencia))

            # Reserva no fio principal, ANTES de qualquer download: se o
            # processo morrer agora, os itens ficam em 'running' e o
            # `destravar_orfaos` da próxima rodada devolve todos para a fila.
            for item in fila:
                jobs.reservar(cx, item["id"])
            cx.commit()

            def tarefa(item):
                info = dados.get(item["entity_id"]) or {}
                url = info.get("url")
                if not url:
                    return item, info, None
                return item, info, baixador.baixar(
                    url, trabalho / str(item["entity_id"]))

            # Download em fios; **escrita no banco só no fio principal**,
            # porque a conexão não é segura entre threads.
            with ThreadPoolExecutor(max_workers=concorrencia) as piscina:
                for item, info, resultado in piscina.map(tarefa, fila):
                    codigo = info.get("codigo") or item["entity_id"]

                    if resultado is None:
                        jobs.falhar(cx, item["id"], "conteúdo sem link do post")
                        falhou += 1
                        _linha("  FALHOU  %s - sem link" % codigo)
                        continue

                    if not resultado.sucesso:
                        jobs.falhar(cx, item["id"], resultado.erro,
                                    resultado.duracao_ms)
                        falhou += 1
                        _linha("  FALHOU  %s - %s" % (codigo, resultado.erro[:80]))
                        continue

                    try:
                        destino = guarda.guardar(resultado.arquivo,
                                                 info["usuario"], codigo)
                    except Exception as erro:
                        jobs.falhar(cx, item["id"], "storage: %s" % erro)
                        falhou += 1
                        _linha("  FALHOU  %s - não guardei: %s" % (codigo, erro))
                        continue

                    media.registrar(cx, item["entity_id"], "video", destino,
                                    mime="video/mp4", bytes_=resultado.bytes)
                    jobs.concluir(cx, item["id"], resultado.duracao_ms)
                    costs.registrar(cx, "video_download", "yt-dlp", quantidade=1,
                                    custo_total=0, entidade="content",
                                    entidade_id=item["entity_id"],
                                    job_id=item["id"])
                    cx.commit()

                    ok += 1
                    _linha("  ok      %s - %.1f MB em %.1fs"
                           % (codigo, resultado.bytes / 1e6,
                              resultado.duracao_ms / 1000))

            cx.commit()
    finally:
        shutil.rmtree(trabalho, ignore_errors=True)

    _linha()
    _linha("%d baixados, %d falharam." % (ok, falhou))
    if falhou:
        _linha("Para tentar de novo: pipeline.py baixar --tentar-de-novo")
    return 0


# ----------------------------------------------------------------- 4. status


def status(cfg):
    with db.conectar(cfg) as cx:
        _titulo("Cobertura da esteira")
        for chave, valor in consultas.cobertura(cx).items():
            _linha("  %-18s %d" % (chave, valor))

        lista = niches.listar(cx)
        if lista:
            _titulo("Nichos")
            for nicho in lista:
                _linha("  %-20s %d perfis"
                       % (nicho["name"], niches.contar_perfis(cx, nicho["id"])))

        _titulo("Fila de download")
        contagem = jobs.contagem_por_status(cx, TIPO_DOWNLOAD)
        if not contagem:
            _linha("  vazia")
        for estado, quantos in contagem.items():
            _linha("  %-12s %d" % (estado, quantos))

        taxa = jobs.taxa_de_falha(cx, TIPO_DOWNLOAD)
        if taxa is not None:
            _linha("  taxa de falha: %.1f%%" % (100 * taxa))

        _titulo("Custo")
        total = costs.total(cx)
        if not total["operacoes"]:
            _linha("  nada gasto ainda")
        else:
            _linha("  US$ %.4f em %d operações"
                   % (total["total"], total["operacoes"]))
            rotulos = {1: "coleta primária", 2: "processamento",
                       3: "enriquecimento", 4: "IA / análise"}
            for nivel, dados in sorted(total["por_nivel"].items()):
                _linha("    nível %d (%-16s) US$ %.4f"
                       % (nivel, rotulos.get(nivel, "?"), dados["custo"]))

            unidade = costs.por_unidade(cx)
            for rotulo, chave in (("por perfil", "custo_por_perfil"),
                                  ("por conteúdo", "custo_por_conteudo"),
                                  ("por vídeo baixado", "custo_por_video")):
                valor = unidade[chave]
                _linha("  %-20s %s"
                       % (rotulo, "—" if valor is None else "US$ %.4f" % valor))

        disco = media.total_em_disco(cx)
        if disco["arquivos"]:
            _titulo("Disco")
            _linha("  %d arquivos, %.0f MB"
                   % (disco["arquivos"], disco["bytes"] / 1e6))

    return 0


# ---------------------------------------------------------------- 5. ranking


def ranking(cfg, nicho=None, limite=20):
    _titulo("Score de oportunidade")

    with db.conectar(cfg) as cx:
        nicho_id = None
        if nicho:
            achado = niches.por_nome(cx, nicho)
            if not achado:
                _linha("Nicho %r não existe no banco." % nicho)
                return 1
            nicho_id = achado["id"]

        posts = metrics.para_desempenho(cx, nicho_id=nicho_id)

    if len(posts) < 2:
        _linha("Preciso de pelo menos 2 vídeos para comparar. Achei %d."
               % len(posts))
        _linha("O score é relativo ao grupo — com um post só, não há grupo.")
        return 1

    pesos = config.pesos_do_score(cfg)
    seguidores = {p["perfil"]: p["seguidores"] for p in posts}

    _linha("Comparando %d vídeos dentro de: %s"
           % (len(posts), nicho or "tudo que está no banco"))
    _linha("Pesos: %s" % ", ".join("%s %.0f%%" % (n, v * 100)
                                   for n, v in sorted(pesos.items(),
                                                      key=lambda kv: -kv[1])))
    _linha()

    linhas = desempenho.ranquear(posts, pesos=pesos,
                                 seguidores_por_perfil=seguidores)

    print("%-5s %-20s %-6s %s" % ("score", "perfil", "vel%", "legenda"))
    print("-" * 76)
    for linha in linhas[:limite]:
        comp = linha.get("componentes") or {}
        print("%5s %-20s %5s  %s"
              % (linha["score"] if linha["score"] is not None else "-",
                 (linha["perfil"] or "?")[:20],
                 "%.0f" % (100 * comp["velocidade"])
                 if "velocidade" in comp else "-",
                 (linha["legenda"] or "").replace("\n", " ")[:38]))

    campeao = linhas[0]
    sinais = campeao.get("sinais") or {}
    if campeao["score"] is not None:
        _linha()
        _linha("Primeiro colocado: %s" % campeao["id"])
        if sinais.get("engajamento") is not None:
            _linha("  engajamento %.2f%% (base: %s)"
                   % (100 * sinais["engajamento"], sinais["base_do_engajamento"]))
        if sinais.get("velocidade") is not None:
            _linha("  %.0f %s por hora, %.0fh de publicado"
                   % (sinais["velocidade"], sinais["base_da_velocidade"],
                      sinais["horas"] or 0))
    return 0


# ------------------------------------------------- 6. conferência do schema


def schema(cfg, nicho):
    """Rodada mínima que despeja o item cru do Actor.

    Existe porque o mapeamento de campos em `coletor.py` veio da documentação,
    não de uma rodada real. Isto custa centavos e troca hipótese por fato.
    """
    _titulo("Conferência do schema do Actor (rodada mínima)")

    apify = config.apify(cfg)
    _linha("Custo estimado: US$ %.4f" % costs.custo_apify(4, apify["plano"]))

    coletor = _montar_coletor(cfg, guardar_brutos=True)
    try:
        coleta = coletor.descobrir_perfis(nicho, max_perfis=1)
    except mod_coletor.ErroDeColeta as erro:
        _linha("FALHOU: %s" % erro)
        return 1

    destino = config.DADOS / "schema-apify.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8") as aberto:
        json.dump(coleta.brutos, aberto, ensure_ascii=False, indent=2)

    _linha("%d item(ns) crus gravados em %s" % (len(coleta.brutos), destino))
    if coleta.brutos:
        _linha("Campos do primeiro item:")
        for chave in sorted(coleta.brutos[0]):
            _linha("  %s" % chave)

    _linha("Custo real: US$ %.4f" % (coleta.custo_usd or 0))
    return 0


# ---------------------------------------------------------------------- cli


def ler_argumentos(argv=None):
    p = argparse.ArgumentParser(description="Pipeline de coleta do Instagram")
    sub = p.add_subparsers(dest="comando", required=True)

    d = sub.add_parser("descobrir", help="nicho -> perfis")
    d.add_argument("nicho")
    d.add_argument("--max-perfis", type=int)
    d.add_argument("--forcar", action="store_true", help="não perguntar do custo")

    c = sub.add_parser("coletar", help="perfis -> conteúdo + fila")
    c.add_argument("--nicho")
    c.add_argument("--perfis", help="lista separada por vírgula")
    c.add_argument("--posts", type=int, dest="posts_por_perfil")
    c.add_argument("--limite-perfis", type=int)
    c.add_argument("--so-aprovados", action="store_true")
    c.add_argument("--forcar", action="store_true")

    b = sub.add_parser("baixar", help="fila -> vídeo no disco")
    b.add_argument("--limite", type=int)
    b.add_argument("--concorrencia", type=int)
    b.add_argument("--tentar-de-novo", action="store_true")

    sub.add_parser("status", help="onde a esteira está e quanto custou")

    r = sub.add_parser("ranking", help="quem performa acima do grupo")
    r.add_argument("--nicho")
    r.add_argument("--limite", type=int, default=20)

    s = sub.add_parser("schema", help="rodada mínima para conferir o Actor")
    s.add_argument("nicho")

    return p.parse_args(argv)


def main(argv=None):
    console.preparar()
    args = ler_argumentos(argv)

    try:
        cfg = config.carregar()
    except config.ErroDeConfig as erro:
        print("ERRO DE CONFIGURAÇÃO\n\n%s" % erro)
        return 1

    try:
        if args.comando == "descobrir":
            return descobrir(cfg, args.nicho, args.max_perfis, args.forcar)
        if args.comando == "coletar":
            return coletar(cfg, args.nicho, args.perfis, args.posts_por_perfil,
                           args.limite_perfis, args.forcar, args.so_aprovados)
        if args.comando == "baixar":
            return baixar(cfg, args.limite, args.concorrencia,
                          args.tentar_de_novo)
        if args.comando == "status":
            return status(cfg)
        if args.comando == "ranking":
            return ranking(cfg, args.nicho, args.limite)
        if args.comando == "schema":
            return schema(cfg, args.nicho)
    except config.ErroDeConfig as erro:
        print("\n%s" % erro)
        return 1
    except db.ErroDeBanco as erro:
        print("\nERRO DE BANCO\n\n%s" % erro)
        return 1
    except KeyboardInterrupt:
        print("\nInterrompido. O estado ficou no banco — é só rodar de novo.")
        return 130

    return 1


if __name__ == "__main__":
    sys.exit(main())
