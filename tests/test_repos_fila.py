"""Confere a fila, os arquivos e a camada de custo contra PostgreSQL real.

    .venv\\Scripts\\python.exe tests\\test_repos_fila.py
"""

from _pg import Placar, abrir_banco_de_teste, fechar_banco_de_teste

from repos import ErroDeRepositorio, contents, costs, jobs, media, niches, profiles

p = Placar()
cfg, cx = abrir_banco_de_teste()

try:
    nicho = niches.obter_ou_criar(cx, "apostas")
    perfil = profiles.salvar(cx, {"usuario": "casa_verde", "seguidores": 84000})
    profiles.ligar_ao_nicho(cx, perfil, nicho)

    ids = {}
    for codigo in ("A", "B", "C"):
        ids[codigo] = contents.salvar(
            cx, {"id": codigo, "tipo": "reel", "e_video": True,
                 "link": "https://www.instagram.com/reel/%s/" % codigo}, perfil)

    # ------------------------------------------------------- coleta externa
    p.secao("registro da coleta externa")

    coleta = jobs.abrir_coleta(cx, "profile_discovery", "apify",
                               ator="apify/instagram-scraper", run_id="run_x",
                               nicho_id=nicho)
    p.conferir_que("abre com id", isinstance(coleta, int))
    p.conferir("nasce rodando",
               cx.execute("SELECT status FROM collection_jobs WHERE id = %s",
                          (coleta,)).fetchone()[0], "running")

    jobs.fechar_coleta(cx, coleta, encontrados=40, criados=38, atualizados=2)
    linha = cx.execute("SELECT status, items_found, items_created, finished_at "
                       "FROM collection_jobs WHERE id = %s", (coleta,)).fetchone()
    p.conferir("fecha como succeeded", linha[0], "succeeded")
    p.conferir("encontrados", linha[1], 40)
    p.conferir("criados", linha[2], 38)
    p.conferir_que("com hora de fim", linha[3] is not None)

    # ----------------------------------------------------------------- fila
    p.secao("entrar na fila")

    p.conferir("primeiro enfileiramento é novo",
               jobs.enfileirar(cx, "video_download", ids["A"]), True)
    p.conferir("repetir NÃO duplica",
               jobs.enfileirar(cx, "video_download", ids["A"]), False)
    p.conferir("uma linha só",
               cx.execute("SELECT count(*) FROM processing_jobs").fetchone()[0], 1)

    jobs.enfileirar(cx, "video_download", ids["B"])
    jobs.enfileirar(cx, "video_download", ids["C"], prioridade=1)
    p.conferir("o mesmo conteúdo em OUTRO tipo de job é outro job",
               jobs.enfileirar(cx, "transcription", ids["A"]), True)

    fila = jobs.proximos(cx, "video_download")
    p.conferir("só o tipo pedido entra", len(fila), 3)
    p.conferir("prioridade menor vem primeiro",
               fila[0]["entity_id"], ids["C"])

    p.conferir("limite respeitado",
               len(jobs.proximos(cx, "video_download", limite=2)), 2)

    p.secao("reservar conta a tentativa ANTES de tentar")

    job_c = fila[0]["id"]
    jobs.reservar(cx, job_c)
    linha = cx.execute("SELECT status, attempts, started_at FROM processing_jobs "
                       "WHERE id = %s", (job_c,)).fetchone()
    p.conferir("virou running", linha[0], "running")
    p.conferir("tentativa contada na reserva", linha[1], 1)
    p.conferir_que("com hora de início", linha[2] is not None)
    p.conferir("reservado sai da fila",
               len(jobs.proximos(cx, "video_download")), 2)

    p.secao("concluir e falhar")

    jobs.concluir(cx, job_c, duracao_ms=8100)
    linha = cx.execute("SELECT status, duration_ms, error FROM processing_jobs "
                       "WHERE id = %s", (job_c,)).fetchone()
    p.conferir("virou done", linha[0], "done")
    p.conferir("tempo guardado", linha[1], 8100)
    p.conferir_que("sem erro", linha[2] is None)

    p.conferir("job já concluído NÃO volta para a fila",
               jobs.enfileirar(cx, "video_download", ids["C"]), False)
    p.conferir("e continua done",
               cx.execute("SELECT status FROM processing_jobs WHERE id = %s",
                          (job_c,)).fetchone()[0], "done")

    job_a = [j for j in jobs.proximos(cx, "video_download")
             if j["entity_id"] == ids["A"]][0]["id"]
    jobs.reservar(cx, job_a)
    jobs.falhar(cx, job_a, "HTTP 404: post apagado")
    linha = cx.execute("SELECT status, error, attempts FROM processing_jobs "
                       "WHERE id = %s", (job_a,)).fetchone()
    p.conferir("virou failed", linha[0], "failed")
    p.conferir_que("com o motivo", "404" in linha[1])
    p.conferir("tentativas", linha[2], 1)

    p.secao("retry com teto")

    p.conferir("reenfileira quem ainda tem crédito",
               jobs.reenfileirar_falhas(cx, "video_download"), 1)
    p.conferir_que("e voltou mesmo",
                   job_a in [j["id"] for j in jobs.proximos(cx, "video_download")])

    for _ in range(2):
        jobs.reservar(cx, job_a)
        jobs.falhar(cx, job_a, "de novo")
    p.conferir("três tentativas acumuladas",
               cx.execute("SELECT attempts FROM processing_jobs WHERE id = %s",
                          (job_a,)).fetchone()[0], 3)
    p.conferir("com o teto estourado, não reenfileira mais",
               jobs.reenfileirar_falhas(cx, "video_download"), 0)

    p.secao("desligar o PC no meio não perde o item")

    job_b = [j for j in jobs.proximos(cx, "video_download")
             if j["entity_id"] == ids["B"]][0]["id"]
    jobs.reservar(cx, job_b)
    p.conferir("preso em running", len(jobs.proximos(cx, "video_download")), 0)
    p.conferir("destravar devolve 1", jobs.destravar_orfaos(cx, "video_download"), 1)
    p.conferir("e voltou para a fila",
               len(jobs.proximos(cx, "video_download")), 1)

    p.secao("contagem e taxa de falha")

    contagem = jobs.contagem_por_status(cx, "video_download")
    p.conferir("um done", contagem.get("done"), 1)
    p.conferir("um failed", contagem.get("failed"), 1)
    p.conferir("um queued", contagem.get("queued"), 1)
    p.conferir("taxa de falha entre os tentados",
               round(jobs.taxa_de_falha(cx, "video_download"), 3), round(1 / 3, 3))
    p.conferir_que("sem nada tentado, a taxa é None, não zero",
                   jobs.taxa_de_falha(cx, "embedding_generation") is None)

    # ------------------------------------------------------------ arquivos
    p.secao("arquivos")

    p.conferir("ainda não tem vídeo", media.tem(cx, ids["A"]), False)
    asset = media.registrar(cx, ids["A"], "video", "dados/perfis/x/A/midia.mp4",
                            mime="video/mp4", bytes_=1_950_000, duracao=31.4,
                            checksum="abc123")
    p.conferir_que("registrar devolve id", isinstance(asset, int))
    p.conferir("agora tem", media.tem(cx, ids["A"]), True)
    p.conferir("caminho recuperável", media.caminho_do_video(cx, ids["A"]),
               "dados/perfis/x/A/midia.mp4")

    p.conferir("registrar de novo devolve o MESMO id",
               media.registrar(cx, ids["A"], "video", "outro/caminho.mp4"), asset)
    p.conferir("uma linha só",
               cx.execute("SELECT count(*) FROM media_assets").fetchone()[0], 1)
    p.conferir_que("mas o tamanho antigo não foi apagado pelo update parcial",
                   media.de(cx, ids["A"])[0]["file_size"] == 1_950_000)

    media.registrar(cx, ids["A"], "thumbnail", "dados/perfis/x/A/thumb.jpg")
    media.registrar(cx, ids["A"], "transcript", "dados/perfis/x/A/t.json")
    p.conferir("três tipos para o mesmo conteúdo", len(media.de(cx, ids["A"])), 3)
    p.conferir("filtrar por tipo", len(media.de(cx, ids["A"], "video")), 1)

    try:
        media.registrar(cx, ids["B"], "gif", "x")
        p.conferir_que("tipo inválido deveria estourar", False)
    except ErroDeRepositorio:
        p.conferir_que("tipo de arquivo inválido é recusado antes do banco", True)

    total = media.total_em_disco(cx)
    p.conferir("três arquivos", total["arquivos"], 3)
    p.conferir("bytes somados", total["bytes"], 1_950_000)

    # --------------------------------------------------------------- custo
    p.secao("custo")

    p.conferir("estimativa da Apify para 440 itens",
               float(costs.custo_apify(440)), 1.188)
    p.conferir("plano desconhecido cai no free",
               float(costs.custo_apify(1000, "inventado")), 2.70)

    costs.registrar(cx, "profile_collection", "apify", quantidade=40,
                    custo_total=costs.custo_apify(40), coleta_id=coleta)
    costs.registrar(cx, "content_collection", "apify", quantidade=400,
                    custo_total=costs.custo_apify(400), coleta_id=coleta)
    costs.registrar(cx, "video_download", "local", quantidade=1, custo_total=0)
    costs.registrar(cx, "comment_collection", "apify", quantidade=200,
                    custo_total=costs.custo_apify(200))

    t = costs.total(cx)
    p.conferir("quatro operações", t["operacoes"], 4)
    p.conferir("total gasto", round(t["total"], 4), 1.728)
    p.conferir("nível 1 é coleta primária",
               round(t["por_nivel"][1]["custo"], 4), 1.188)
    p.conferir("nível 2 é processamento", t["por_nivel"][2]["custo"], 0.0)
    p.conferir("nível 3 é enriquecimento (comentário é caro)",
               round(t["por_nivel"][3]["custo"], 4), 0.54)

    ops = costs.por_operacao(cx)
    p.conferir("ordenado do mais caro", ops[0]["operacao"], "content_collection")

    try:
        costs.registrar(cx, "operacao_inventada", "apify", 1)
        p.conferir_que("operação sem nível deveria estourar", False)
    except ErroDeRepositorio:
        p.conferir_que("operação sem nível é recusada", True)

    u = costs.por_unidade(cx)
    p.conferir("um perfil", u["perfis"], 1)
    p.conferir("três conteúdos", u["conteudos"], 3)
    p.conferir("um vídeo baixado", u["videos_baixados"], 1)
    p.conferir("custo por perfil", round(u["custo_por_perfil"], 4), 1.728)
    p.conferir("conteúdos por perfil", u["conteudos_por_perfil"], 3.0)

    cx.execute("DELETE FROM media_assets")
    p.conferir_que("sem vídeo baixado, custo por vídeo é None e não zero",
                   costs.por_unidade(cx)["custo_por_video"] is None)

    cx.commit()

finally:
    fechar_banco_de_teste(cfg, cx)

p.encerrar("fila, arquivos e custo")
