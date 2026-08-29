"""Confere a retencao de midia contra PostgreSQL real.

O que se testa aqui e a regra que decide o que pode sumir do disco. Errar
para o lado permissivo custa caro de um jeito assimetrico: o mp4 volta com um
download, mas se a transcricao ainda nao existe, apagar o video joga fora a
unica coisa que custou CPU.

Tambem trava a decisao de projeto do comando `limpar`: apagar o arquivo apaga
o registro, e isso **nao** pode devolver o video para a fila de download.

    .venv\\Scripts\\python.exe tests\\test_repos_arquivos.py
"""

from pathlib import Path

from _pg import Placar, abrir_banco_de_teste, fechar_banco_de_teste

from repos import contents, jobs, media, niches, profiles, transcripts

p = Placar()
cfg, cx = abrir_banco_de_teste()

TRANSCRICAO = {
    "texto": "adicionei ovos na cenoura e o resultado e incrivel",
    "trechos": [{"inicio": 0.0, "fim": 2.5,
                 "texto": "adicionei ovos na cenoura"}],
    "palavras": [{"palavra": "adicionei", "inicio": 0.0, "fim": 0.6,
                  "probabilidade": 0.98}],
}

try:
    nicho = niches.obter_ou_criar(cx, "receitas")
    perfil = profiles.salvar(cx, {"usuario": "casa_verde", "seguidores": 84000})
    profiles.ligar_ao_nicho(cx, perfil, nicho)

    ids = {}
    for codigo in ("COM_TRANSCRICAO", "SEM_TRANSCRICAO", "TERCEIRO"):
        ids[codigo] = contents.salvar(
            cx, {"id": codigo, "tipo": "reel", "e_video": True,
                 "link": "https://www.instagram.com/reel/%s/" % codigo}, perfil)

    for codigo, tamanho in (("COM_TRANSCRICAO", 20_000_000),
                            ("SEM_TRANSCRICAO", 30_000_000),
                            ("TERCEIRO", 5_000_000)):
        media.registrar(cx, ids[codigo], "video",
                        r"C:\dados\perfis\casa_verde\%s\midia.mp4" % codigo,
                        bytes_=tamanho)

    # ------------------------------------------------ so o transcrito libera
    p.secao("so libera o que ja virou transcricao")

    liberaveis = media.com_derivado_pronto(cx)
    p.conferir("sem nenhuma transcricao, nada e liberavel", len(liberaveis), 0)

    transcripts.salvar(cx, ids["COM_TRANSCRICAO"], TRANSCRICAO, modelo="base")

    liberaveis = media.com_derivado_pronto(cx)
    p.conferir("com uma transcricao, um liberavel", len(liberaveis), 1)
    p.conferir("e o que tem transcricao",
               liberaveis[0]["platform_content_id"], "COM_TRANSCRICAO")
    p.conferir("com o tamanho junto", liberaveis[0]["file_size"], 20_000_000)
    p.conferir("com o dono junto", liberaveis[0]["username"], "casa_verde")

    p.conferir_que(
        "o que nao tem transcricao NUNCA aparece",
        all(a["platform_content_id"] != "SEM_TRANSCRICAO" for a in liberaveis))

    # `--antes-de` nao pode liberar o que acabou de ser baixado
    p.conferir("baixado agora nao entra em --antes-de 1",
               len(media.com_derivado_pronto(cx, dias=1)), 0)
    p.conferir("nem em --antes-de 30",
               len(media.com_derivado_pronto(cx, dias=30)), 0)
    p.conferir("sem restricao de dias, entra",
               len(media.com_derivado_pronto(cx, dias=None)), 1)

    # -------------------------------------------------- esquecer o registro
    p.secao("apagar o arquivo apaga o registro")

    asset = liberaveis[0]
    p.conferir_que("antes: o banco diz que tem video",
                   media.tem(cx, ids["COM_TRANSCRICAO"], "video"))

    chave = media.esquecer(cx, asset["id"])
    p.conferir_que("esquecer devolve a chave apagada", chave.endswith("midia.mp4"))
    p.conferir("depois: o banco nao diz mais que tem",
               media.tem(cx, ids["COM_TRANSCRICAO"], "video"), False)
    p.conferir("esquecer um id que nao existe devolve None",
               media.esquecer(cx, 999999), None)

    p.conferir_que("a transcricao SOBREVIVE ao apagar o video",
                   transcripts.de(cx, ids["COM_TRANSCRICAO"]) is not None)
    p.conferir_que("o conteudo continua existindo",
                   contents.por_codigo(cx, "COM_TRANSCRICAO") is not None)

    # --------------------------------- e nao devolve o video para a fila
    p.secao("limpar nao devolve o video para a fila")

    # A decisao de projeto: `processing_jobs` guarda que o download ja
    # aconteceu. Apagar o arquivo nao pode desfazer esse fato — senao a
    # proxima rodada de `baixar` re-baixa tudo que foi limpo, e a limpeza
    # vira um moto-continuo caro.
    p.conferir_que("enfileirar diz que entrou agora",
                   jobs.enfileirar(cx, "video_download", ids["TERCEIRO"]))
    job = [j["id"] for j in jobs.proximos(cx, "video_download", limite=50)
           if j["entity_id"] == ids["TERCEIRO"]][0]
    jobs.reservar(cx, job)
    jobs.concluir(cx, job)

    media.esquecer(cx, media.de(cx, ids["TERCEIRO"], "video")[0]["id"])

    pendentes = jobs.proximos(cx, "video_download", limite=50)
    p.conferir("depois de limpar, a fila continua vazia", len(pendentes), 0)
    p.conferir_que(
        "o job continua marcado como done",
        cx.execute("SELECT status FROM processing_jobs WHERE id = %s",
                   (job,)).fetchone()[0] == "done")

    # ------------------------------------------------------ contas de disco
    p.secao("para onde o disco foi")

    total = media.total_em_disco(cx)
    p.conferir("sobrou um arquivo", total["arquivos"], 1)
    p.conferir("com os bytes do que sobrou", total["bytes"], 30_000_000)

    media.registrar(cx, ids["COM_TRANSCRICAO"], "subtitle",
                    r"C:\dados\perfis\casa_verde\COM_TRANSCRICAO\legenda.ass",
                    bytes_=4_000)

    tipos = {linha["tipo"]: linha for linha in media.por_tipo(cx)}
    p.conferir("separa por tipo de arquivo", sorted(tipos), ["subtitle", "video"])
    p.conferir("os bytes de video", tipos["video"]["bytes"], 30_000_000)
    p.conferir("os bytes de legenda", tipos["subtitle"]["bytes"], 4_000)

    pesados = media.por_perfil(cx)
    p.conferir("agrupa por perfil", len(pesados), 1)
    p.conferir("com o nome do dono", pesados[0]["perfil"], "casa_verde")
    p.conferir("somando os dois arquivos dele", pesados[0]["arquivos"], 2)

    # ---------------------------------------------------- reconciliacao
    p.secao("reconciliacao disco x banco")

    chaves = media.chaves_registradas(cx)
    p.conferir("devolve uma chave por registro", len(chaves), 2)
    p.conferir_que("sao caminhos, nao ids",
                   all(str(c).endswith((".mp4", ".ass")) for c in chaves))

    alvo = r"C:\dados\perfis\casa_verde\SEM_TRANSCRICAO\midia.mp4"
    achados = media.registros_da_chave(cx, alvo)
    p.conferir("acha o registro pelo caminho", len(achados), 1)
    p.conferir("com o tipo certo", achados[0]["asset_type"], "video")
    p.conferir("caminho que ninguem registrou devolve vazio",
               len(media.registros_da_chave(cx, r"C:\nao\existe.mp4")), 0)

    # O caso que o `limpar --orfas` conserta: a linha continua la, apontando
    # para um arquivo que ninguem mais tem.
    p.conferir_que("o disco de teste nao tem esses arquivos",
                   not Path(alvo).exists())
    p.conferir_que("logo, a chave registrada e um registro orfao",
                   alvo in [str(c) for c in chaves])

finally:
    fechar_banco_de_teste(cfg, cx)

p.encerrar("retencao de arquivos")
