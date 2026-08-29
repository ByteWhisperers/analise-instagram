"""Confere transcrição, análises e as 11 perguntas contra PostgreSQL real.

    .venv\\Scripts\\python.exe tests\\test_repos_consultas.py
"""

from datetime import datetime, timedelta, timezone

from _pg import Placar, abrir_banco_de_teste, fechar_banco_de_teste

from repos import (analyses, consultas, contents, metrics, niches, profiles,
                   transcripts)

p = Placar()
cfg, cx = abrir_banco_de_teste()

AGORA = datetime.now(timezone.utc)


def quando(horas_atras):
    return (AGORA - timedelta(hours=horas_atras)).isoformat()


try:
    apostas = niches.obter_ou_criar(cx, "apostas")
    outro = niches.obter_ou_criar(cx, "culinaria")

    perfis = {}
    for usuario, seguidores in (("casa_verde", 84000), ("tigre_bet", 210000),
                                ("bonus_hoje", 32000)):
        pid = profiles.salvar(cx, {"usuario": usuario, "seguidores": seguidores})
        profiles.ligar_ao_nicho(cx, pid, apostas)
        perfis[usuario] = pid

    fora = profiles.salvar(cx, {"usuario": "chef", "seguidores": 5000})
    profiles.ligar_ao_nicho(cx, fora, outro)

    # (perfil, codigo, horas, views, likes, comments, tags, audio)
    DADOS = [
        ("casa_verde", "cv1", 90,  22000, 700,  40, ["tigrinho", "bet"], "som A"),
        ("casa_verde", "cv2", 140, 18000, 610,  33, ["bet"], "som B"),
        ("tigre_bet",  "tb1", 100, 60000, 1900, 120, ["tigrinho"], "som A"),
        ("tigre_bet",  "tb2", 55,  71000, 2300, 140, ["tigrinho", "bet"], "som A"),
        ("bonus_hoje", "bh1", 120, 6000,  180,  9,  ["bonus"], None),
        ("bonus_hoje", "bh3", 5,   41000, 5200, 890, ["tigrinho"], "som A"),
    ]

    ids = {}
    for usuario, codigo, horas, views, likes, coms, tags, audio in DADOS:
        cid = contents.salvar(cx, {
            "id": codigo, "tipo": "reel", "e_video": True,
            "link": "https://www.instagram.com/reel/%s/" % codigo,
            "legenda": "primeira linha do %s\nsegunda linha" % codigo,
            "hashtags": tags, "data_utc": quando(horas),
            "duracao_segundos": 30.0,
            "audio_id": audio and audio.replace(" ", "_"), "audio_titulo": audio,
        }, perfis[usuario])
        metrics.gravar_snapshot(cx, cid, {"visualizacoes": views,
                                          "curtidas": likes, "comentarios": coms},
                                horas_desde_post=horas)
        ids[codigo] = cid

    fora_id = contents.salvar(cx, {"id": "ch1", "tipo": "reel", "e_video": True,
                                   "legenda": "bolo", "hashtags": ["tigrinho"],
                                   "data_utc": quando(10)}, fora)
    metrics.gravar_snapshot(cx, fora_id, {"visualizacoes": 100, "curtidas": 90,
                                          "comentarios": 50})

    # ------------------------------------------------------------ transcrição
    p.secao("transcrição estruturada")

    TR = {"texto": "olha o bônus que a casa está dando hoje, link na bio",
          "trechos": [{"inicio": 0.0, "fim": 2.4, "texto": "olha o bônus"},
                      {"inicio": 2.4, "fim": 5.0, "texto": "que a casa está dando hoje"},
                      {"inicio": 5.0, "fim": 8.0, "texto": "link na bio"}],
          "palavras": [{"palavra": "olha", "inicio": 0.0, "fim": 0.3,
                        "probabilidade": 0.99},
                       {"palavra": "o", "inicio": 0.3, "fim": 0.4},
                       {"palavra": "bônus", "inicio": 0.4, "fim": 0.9}]}

    tid = transcripts.salvar(cx, ids["bh3"], TR, modelo="small",
                             segundos_de_audio=8.0, tempo_ms=3900)
    p.conferir_que("salvar devolve id", isinstance(tid, int))
    p.conferir("regravar com o mesmo modelo substitui",
               transcripts.salvar(cx, ids["bh3"], TR, modelo="small"), tid)
    p.conferir("uma transcrição só",
               cx.execute("SELECT count(*) FROM transcripts").fetchone()[0], 1)

    outro_modelo = transcripts.salvar(cx, ids["bh3"], TR, modelo="base")
    p.conferir_que("outro modelo é outra linha, para poder comparar",
                   outro_modelo != tid)

    p.conferir("três trechos", len(transcripts.trechos(cx, tid)), 3)
    p.conferir("três palavras com tempo", len(transcripts.palavras(cx, tid)), 3)
    p.conferir("a palavra sai no formato que legenda.py consome",
               transcripts.palavras(cx, tid)[0],
               {"palavra": "olha", "inicio": 0.0, "fim": 0.3,
                "probabilidade": 0.99})
    # A regra: trecho que COMEÇA antes do corte conta inteiro. O trecho 2
    # começa em 2,4s, então entra todo — inclusive o pedaço depois dos 3s.
    # Cortar no meio da frase daria gancho truncado, que é pior de ler.
    p.conferir("gancho falado inclui o trecho que começa antes dos 3s",
               transcripts.gancho_falado(cx, tid),
               "olha o bônus que a casa está dando hoje")
    p.conferir("com corte menor, só o primeiro trecho",
               transcripts.gancho_falado(cx, tid, ate_segundos=2.0),
               "olha o bônus")

    p.conferir("refazer não acumula trechos",
               len(transcripts.trechos(cx, tid)), 3)

    p.secao("busca no que foi falado")

    achados = transcripts.procurar(cx, "bônus")
    p.conferir_que("acha pela palavra falada", len(achados) >= 1)
    p.conferir("e diz de qual post", achados[0]["post"], "bh3")
    p.conferir_que("com trecho destacado", "<b>" in achados[0]["trecho"])

    # O stemmer portugues reduz plural: "casas" e "casa" viram "cas".
    # (Ja "dando" vira "dand" e NAO casa com "dar" -- verificado no banco.)
    p.conferir_que("busca com stemming: 'casas' acha 'casa'",
                   len(transcripts.procurar(cx, "casas")) >= 1)
    p.conferir("termo ausente devolve vazio, não erro",
               transcripts.procurar(cx, "jacaré"), [])
    p.conferir_que("pontuação não estoura a busca",
                   isinstance(transcripts.procurar(cx, "link, na bio!"), list))

    cedo = transcripts.procurar(cx, "bônus", nos_primeiros_segundos=3.0)
    p.conferir_que("acha 'bônus' nos 3 primeiros segundos", len(cedo) == 1)
    p.conferir("mas 'bio' não está no começo",
               transcripts.procurar(cx, "bio", nos_primeiros_segundos=3.0), [])

    # -------------------------------------------------------------- análises
    p.secao("análises versionadas")

    analyses.salvar_do_conteudo(cx, ids["bh3"],
                                {"gancho": "olha o bônus", "ritmo": 168,
                                 "chamadas": ["clicar", "seguir"]})
    analyses.salvar_do_conteudo(cx, ids["cv1"],
                                {"gancho": "x", "chamadas": ["comentar"]})
    analyses.salvar_do_conteudo(cx, ids["tb1"],
                                {"gancho": "y", "chamadas": ["clicar"]})

    p.conferir("campo lido de dentro do JSONB",
               analyses.campo(cx, ids["bh3"], "ritmo"), 168)
    p.conferir("regravar substitui",
               len(analyses.comparar_modelos(cx, ids["bh3"])), 1)

    analyses.salvar_do_conteudo(cx, ids["bh3"], {"gancho": "outra leitura"},
                                modelo="claude-opus-5", versao="v1")
    p.conferir("modelo diferente convive, para poder comparar",
               len(analyses.comparar_modelos(cx, ids["bh3"])), 2)

    faltando = analyses.sem_analise(cx)
    p.conferir_que("lista quem ainda não foi analisado",
                   {l["codigo"] for l in faltando} == {"cv2", "tb2", "bh1", "ch1"})

    # ------------------------------------------------------------- consultas
    p.secao("hashtags por desempenho")

    tags = consultas.hashtags_por_desempenho(cx, nicho_id=apostas)
    nomes = [t["tag"] for t in tags]
    p.conferir_que("tigrinho e bet aparecem", {"tigrinho", "bet"} <= set(nomes))
    p.conferir_que("tag de post único é descartada", "bonus" not in nomes)
    p.conferir_que("ordenado por engajamento",
                   tags[0]["engajamento_medio"] >= tags[-1]["engajamento_medio"])

    todas = consultas.hashtags_por_desempenho(cx, minimo_de_posts=1)
    p.conferir_que("sem filtro de nicho, a tag do outro nicho entra",
                   any(t["tag"] == "tigrinho" and t["posts"] == 5 for t in todas))

    p.secao("melhores posts")

    melhores = consultas.melhores_posts(cx, nicho_id=apostas)
    p.conferir("o bh3 lidera", melhores[0]["post"], "bh3")
    p.conferir("a base do engajamento vem declarada",
               melhores[0]["base"], "views")
    p.conferir("filtrar por perfil",
               {m["perfil"] for m in
                consultas.melhores_posts(cx, usuario="casa_verde")},
               {"casa_verde"})

    p.secao("ranking de perfis")

    ranking = consultas.ranking_de_perfis(cx, nicho_id=apostas)
    p.conferir("três perfis", len(ranking), 3)
    p.conferir("o menor lidera, porque engajamento é razão",
               ranking[0]["perfil"], "bonus_hoje")
    p.conferir_que("perfil de outro nicho fica de fora",
                   "chef" not in [r["perfil"] for r in ranking])

    p.secao("horário, dia e formato")

    horas = consultas.horarios_que_rendem(cx, nicho_id=apostas)
    p.conferir_que("agrupa por hora local", all(0 <= h["hora"] <= 23 for h in horas))
    p.conferir("soma dos posts bate", sum(h["posts"] for h in horas), 6)

    dias = consultas.dias_que_rendem(cx, nicho_id=apostas)
    p.conferir_que("dia da semana com nome", all(d["dia"] for d in dias))

    formatos = consultas.formatos_que_rendem(cx, nicho_id=apostas)
    p.conferir("só reel neste conjunto", [f["tipo"] for f in formatos], ["reel"])
    p.conferir("duração média", formatos[0]["duracao_media"], 30.0)

    p.secao("áudio em alta")

    audios = consultas.audios_em_alta(cx, nicho_id=apostas)
    p.conferir("som A aparece em vários perfis", audios[0]["audio"], "som A")
    p.conferir("três perfis diferentes usam", audios[0]["perfis"], 3)
    p.conferir_que("som usado por um perfil só não entra",
                   "som B" not in [a["audio"] for a in audios])

    p.secao("hashtags compartilhadas")

    compartilhadas = consultas.hashtags_compartilhadas(cx, nicho_id=apostas)
    p.conferir("tigrinho é a mais compartilhada",
               compartilhadas[0]["tag"], "tigrinho")
    p.conferir("por três perfis", compartilhadas[0]["perfis"], 3)
    p.conferir_que("com os nomes de quem usa",
                   "casa_verde" in compartilhadas[0]["quem"])

    p.secao("ganchos")

    ganchos = consultas.ganchos_dos_melhores(cx, limite=3, nicho_id=apostas)
    p.conferir("o melhor primeiro", ganchos[0]["post"], "bh3")
    p.conferir("gancho escrito é só a PRIMEIRA linha da legenda",
               ganchos[0]["gancho_escrito"], "primeira linha do bh3")
    p.conferir("gancho falado vem da transcrição",
               ganchos[0]["gancho_falado"],
               "olha o bônus que a casa está dando hoje")
    p.conferir("post sem transcrição devolve vazio, não quebra",
               ganchos[1]["gancho_falado"], "")

    p.secao("chamadas para ação")

    chamadas = consultas.chamadas_que_rendem(cx, nicho_id=apostas)
    tipos = {c["chamada"] for c in chamadas}
    p.conferir("as três chamadas gravadas aparecem", tipos,
               {"clicar", "seguir", "comentar"})
    p.conferir_que("ordenado por engajamento",
                   chamadas[0]["engajamento_medio"]
                   >= chamadas[-1]["engajamento_medio"])
    p.conferir("modelo sem análise devolve vazio, não zero",
               consultas.chamadas_que_rendem(cx, modelo="inexistente"), [])

    p.secao("crescimento")

    profiles.gravar_snapshot(cx, perfis["casa_verde"], seguidores=80000,
                             medido_em=quando(120))
    profiles.gravar_snapshot(cx, perfis["casa_verde"], seguidores=84000,
                             medido_em=quando(1))
    profiles.gravar_snapshot(cx, perfis["tigre_bet"], seguidores=210000,
                             medido_em=quando(1))

    cresc = consultas.crescimento_dos_perfis(cx, nicho_id=apostas, dias=7)
    p.conferir("só quem tem duas leituras aparece", len(cresc), 1)
    p.conferir("o perfil certo", cresc[0]["perfil"], "casa_verde")
    p.conferir("ganho", cresc[0]["ganho"], 4000)
    p.conferir("percentual", cresc[0]["percentual"], 5.0)

    p.secao("cobertura")

    c = consultas.cobertura(cx)
    p.conferir("nichos", c["nichos"], 2)
    p.conferir("perfis", c["perfis"], 4)
    p.conferir("conteúdos", c["conteudos"], 7)
    p.conferir("transcritos", c["transcritos"], 1)
    p.conferir("analisados", c["analisados"], 3)
    p.conferir("nada baixado", c["baixados"], 0)
    p.conferir("nenhum comentário", c["com_comentarios"], 0)

    p.secao("banco vazio não quebra nenhuma consulta")

    cx.execute("DELETE FROM niches")
    cx.execute("DELETE FROM profiles")
    for nome, chamada in (
            ("hashtags", lambda: consultas.hashtags_por_desempenho(cx)),
            ("melhores", lambda: consultas.melhores_posts(cx)),
            ("ranking", lambda: consultas.ranking_de_perfis(cx)),
            ("horarios", lambda: consultas.horarios_que_rendem(cx)),
            ("dias", lambda: consultas.dias_que_rendem(cx)),
            ("formatos", lambda: consultas.formatos_que_rendem(cx)),
            ("audios", lambda: consultas.audios_em_alta(cx)),
            ("compartilhadas", lambda: consultas.hashtags_compartilhadas(cx)),
            ("ganchos", lambda: consultas.ganchos_dos_melhores(cx)),
            ("chamadas", lambda: consultas.chamadas_que_rendem(cx)),
            ("crescimento", lambda: consultas.crescimento_dos_perfis(cx))):
        p.conferir("%s devolve lista vazia" % nome, chamada(), [])

    p.conferir("cobertura zerada", consultas.cobertura(cx)["perfis"], 0)

    cx.commit()

finally:
    fechar_banco_de_teste(cfg, cx)

p.encerrar("transcrição, análises e consultas")
