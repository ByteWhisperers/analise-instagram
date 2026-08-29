"""Confere os repositórios de conteúdo e de métricas contra PostgreSQL real.

    .venv\\Scripts\\python.exe tests\\test_repos_conteudo.py
"""

from _pg import Placar, abrir_banco_de_teste, fechar_banco_de_teste

from repos import ErroDeRepositorio, contents, metrics, niches, profiles

p = Placar()
cfg, cx = abrir_banco_de_teste()

REEL = {
    "id": "C9xYz01", "perfil": "casa_verde", "tipo": "reel", "e_video": True,
    "link": "https://www.instagram.com/reel/C9xYz01/",
    "legenda": "olha isso #Tigrinho #APOSTAS @parceiro",
    "hashtags": ["Tigrinho", "#APOSTAS", "tigrinho"],
    "mencoes": ["@Parceiro"],
    "data_utc": "2026-08-20T15:30:00+00:00",
    "duracao_segundos": 31.4, "visualizacoes": 190000, "curtidas": 5200,
    "comentarios": 310, "thumbnail_url": "https://cdn/t.jpg",
    "video_url": "https://cdn/vence.mp4",
    "audio_id": "998877", "audio_titulo": "som original",
    "audio_autor": "casa_verde", "audio_original": True,
    "local_nome": "São Paulo", "local_id": "42",
}

try:
    nicho = niches.obter_ou_criar(cx, "apostas")
    perfil = profiles.salvar(cx, {"usuario": "casa_verde", "seguidores": 84000})
    profiles.ligar_ao_nicho(cx, perfil, nicho)

    p.secao("gravar conteúdo")

    cid = contents.salvar(cx, REEL, perfil, guardar_bruto={"cru": True})
    p.conferir_que("salvar devolve id", isinstance(cid, int))
    p.conferir("salvar de novo devolve o MESMO id",
               contents.salvar(cx, REEL, perfil), cid)
    p.conferir("e não duplica",
               cx.execute("SELECT count(*) FROM contents").fetchone()[0], 1)

    linha = contents.por_codigo(cx, "C9xYz01")
    p.conferir("shortcode é a chave natural",
               linha["platform_content_id"], "C9xYz01")
    p.conferir("tipo reel traduzido para o CHECK", linha["content_type"], "reel")
    p.conferir("duração", round(linha["duration_seconds"], 1), 31.4)
    p.conferir("áudio", linha["audio_title"], "som original")
    p.conferir("áudio original é True", linha["is_original_audio"], True)
    p.conferir("local", linha["location_name"], "São Paulo")
    p.conferir("URL do CDN guardada à parte",
               linha["source_video_url"], "https://cdn/vence.mp4")
    p.conferir_que("published_at virou timestamp de verdade",
                   linha["published_at"].year == 2026)

    p.secao("hashtags normalizadas")

    tags = contents.hashtags_de(cx, cid)
    p.conferir("minúsculas, sem '#', sem repetida", tags, ["apostas", "tigrinho"])
    p.conferir("menção sem '@' e minúscula",
               contents.mencoes_de(cx, cid), ["parceiro"])

    p.secao("legenda editada tira a hashtag do banco")

    editado = dict(REEL, hashtags=["tigrinho"], mencoes=[])
    contents.salvar(cx, editado, perfil)
    p.conferir("hashtag removida sai", contents.hashtags_de(cx, cid), ["tigrinho"])
    p.conferir("menção removida sai", contents.mencoes_de(cx, cid), [])

    contents.salvar(cx, {k: v for k, v in REEL.items()
                         if k not in ("hashtags", "mencoes")}, perfil)
    p.conferir("mas campo AUSENTE não apaga (None != lista vazia)",
               contents.hashtags_de(cx, cid), ["tigrinho"])

    p.secao("tipos e obrigatórios")

    foto = contents.salvar(cx, {"id": "F1", "tipo": "foto", "e_video": False}, perfil)
    p.conferir("foto vira image",
               contents.por_codigo(cx, "F1")["content_type"], "image")
    carrossel = contents.salvar(cx, {"id": "C1", "tipo": "carrossel"}, perfil)
    p.conferir("carrossel vira carousel",
               contents.por_codigo(cx, "C1")["content_type"], "carousel")
    contents.salvar(cx, {"id": "X1", "tipo": "coisa estranha"}, perfil)
    p.conferir("tipo desconhecido vira other, não estoura",
               contents.por_codigo(cx, "X1")["content_type"], "other")

    for faltando, dados in (("id", {"tipo": "reel"}),
                            ("perfil_id", {"id": "Z1"})):
        try:
            contents.salvar(cx, dados, None if faltando == "perfil_id" else perfil)
            p.conferir_que("faltar %s deveria estourar" % faltando, False)
        except ErroDeRepositorio:
            p.conferir_que("faltar %s levanta ErroDeRepositorio" % faltando, True)

    p.secao("série de métricas")

    metrics.gravar_snapshot(cx, cid, {"visualizacoes": 30000, "curtidas": 900,
                                      "comentarios": 60},
                            horas_desde_post=3.0,
                            medido_em="2026-08-20T18:30:00+00:00")
    metrics.gravar_snapshot(cx, cid, {"visualizacoes": 190000, "curtidas": 5200,
                                      "comentarios": 310},
                            horas_desde_post=27.0,
                            medido_em="2026-08-21T18:30:00+00:00")

    hist = metrics.historico(cx, cid)
    p.conferir("duas leituras", len(hist), 2)
    p.conferir("em ordem cronológica",
               [linha["visualizacoes"] for linha in hist], [30000, 190000])
    p.conferir("a hora da medição ficou junto do número",
               [linha["horas"] for linha in hist], [3.0, 27.0])
    p.conferir("a última é a última", metrics.ultima(cx, cid)["visualizacoes"],
               190000)

    metrics.gravar_snapshot(cx, cid, {"visualizacoes": 999},
                            medido_em="2026-08-21T18:30:00+00:00")
    p.conferir("mesmo instante substitui, não duplica",
               len(metrics.historico(cx, cid)), 2)

    p.conferir_que("shares e saves ficam NULL, não 0",
                   hist[0]["compartilhamentos"] is None
                   and hist[0]["salvamentos"] is None)

    p.secao("o formato que desempenho.py consome")

    metrics.gravar_snapshot(cx, cid, {"visualizacoes": 190000, "curtidas": 5200,
                                      "comentarios": 310},
                            medido_em="2026-08-22T18:30:00+00:00")

    outro = contents.salvar(cx, dict(REEL, id="C9xYz02",
                                     data_utc="2026-08-21T10:00:00+00:00"), perfil)
    metrics.gravar_snapshot(cx, outro, {"visualizacoes": 12000, "curtidas": 300,
                                        "comentarios": 15})

    posts = metrics.para_desempenho(cx, nicho_id=nicho)
    p.conferir("só vídeos entram", len(posts), 2)
    p.conferir_que("com as chaves em português que desempenho.py espera",
                   {"id", "perfil", "seguidores", "data_utc", "visualizacoes",
                    "curtidas", "comentarios"} <= set(posts[0]))
    p.conferir("traz o snapshot MAIS RECENTE de cada conteúdo",
               sorted(linha["visualizacoes"] for linha in posts), [12000, 190000])
    p.conferir("seguidores do dono vêm junto", posts[0]["seguidores"], 84000)

    import desempenho
    ranking = desempenho.ranquear(posts,
                                  seguidores_por_perfil={"casa_verde": 84000})
    p.conferir_que("o ranking roda direto sobre a saída do repositório",
                   ranking[0]["score"] is not None)

    p.secao("cobertura")

    c = metrics.cobertura(cx)
    p.conferir("nichos", c["nichos"], 1)
    p.conferir("perfis", c["perfis"], 1)
    p.conferir("conteúdos", c["conteudos"], 5)
    # 5 conteúdos, mas só 2 são vídeo: F1 é foto, C1 é carrossel e X1 é 'other'.
    p.conferir("vídeos", c["videos"], 2)
    p.conferir("com métrica", c["com_metrica"], 2)
    p.conferir("nenhum baixado ainda", c["baixados"], 0)

    p.secao("apagar o perfil leva tudo junto")

    cx.execute("DELETE FROM profiles WHERE id = %s", (perfil,))
    p.conferir("conteúdos somem",
               cx.execute("SELECT count(*) FROM contents").fetchone()[0], 0)
    p.conferir("hashtags órfãs somem",
               cx.execute("SELECT count(*) FROM content_hashtags").fetchone()[0], 0)
    p.conferir("métricas órfãs somem",
               cx.execute("SELECT count(*) FROM content_metric_snapshots"
                          ).fetchone()[0], 0)

    cx.commit()

finally:
    fechar_banco_de_teste(cfg, cx)

p.encerrar("repositórios de conteúdo")
