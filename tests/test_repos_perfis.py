"""Confere os repositórios de nicho e de perfil contra um PostgreSQL real.

Banco descartável, criado e derrubado aqui. Não encosta no banco real.

    .venv\\Scripts\\python.exe tests\\test_repos_perfis.py
"""

from _pg import Placar, abrir_banco_de_teste, fechar_banco_de_teste

from repos import ErroDeRepositorio, niches, profiles

p = Placar()
cfg, cx = abrir_banco_de_teste()

try:
    # -------------------------------------------------------------- nichos
    p.secao("nichos")

    apostas = niches.obter_ou_criar(cx, "apostas", descricao="casas de aposta",
                                    palavras_chave=["tigrinho", "bet"],
                                    idioma="pt", pais="BR")
    p.conferir_que("criar devolve um id", isinstance(apostas, int))

    de_novo = niches.obter_ou_criar(cx, "apostas")
    p.conferir("criar com o mesmo nome devolve o MESMO id", de_novo, apostas)
    p.conferir("e não cria segunda linha",
               cx.execute("SELECT count(*) FROM niches").fetchone()[0], 1)

    nicho = niches.por_nome(cx, "apostas")
    p.conferir("descrição gravada", nicho["description"], "casas de aposta")
    p.conferir("palavras-chave viram array de verdade",
               nicho["keywords"], ["tigrinho", "bet"])
    p.conferir("status nasce ativo", nicho["status"], "active")

    niches.obter_ou_criar(cx, "apostas")
    p.conferir("recriar sem palavras-chave NÃO apaga as que existiam",
               niches.por_nome(cx, "apostas")["keywords"], ["tigrinho", "bet"])

    cassino = niches.obter_ou_criar(cx, "cassino")
    p.conferir("dois nichos", len(niches.listar(cx)), 2)

    niches.mudar_status(cx, cassino, "archived")
    p.conferir("arquivado sai da lista de ativos", len(niches.listar(cx)), 1)
    p.conferir("mas continua existindo", len(niches.listar(cx, status=None)), 2)

    # Savepoint, e não rollback: erro esperado não pode desfazer o que os
    # testes anteriores já gravaram na mesma transação.
    try:
        with cx.transaction():
            niches.mudar_status(cx, cassino, "inventado")
        p.conferir_que("status inválido deveria ser recusado pelo banco", False)
    except Exception:
        p.conferir_que("o CHECK do banco recusa status inválido", True)

    p.conferir("e o nicho continua existindo depois do erro",
               niches.por_nome(cx, "cassino")["id"], cassino)

    try:
        niches.obter_ou_criar(cx, "")
        p.conferir_que("nome vazio deveria estourar", False)
    except ErroDeRepositorio:
        p.conferir_que("nome vazio levanta ErroDeRepositorio", True)

    # -------------------------------------------------------------- perfis
    p.secao("gravar perfil")

    bruto = {"usuario": "casa_verde", "nome": "Casa Verde", "bio": "link na bio",
             "seguidores": 84000, "seguindo": 12, "posts": 430,
             "verificado": True, "privado": False, "perfil_id": "1122334455",
             "link_perfil": "https://www.instagram.com/casa_verde/",
             "avatar_url": "https://cdn/avatar.jpg",
             "categoria_negocio": "Entretenimento",
             "link_externo": "https://casaverde.com"}

    pid = profiles.salvar(cx, bruto, fonte="apify",
                          ator="apify/instagram-scraper", run_id="run_1",
                          guardar_bruto={"qualquer": "coisa", "n": 1})
    p.conferir_que("salvar devolve id", isinstance(pid, int))

    p.conferir("salvar de novo devolve o MESMO id",
               profiles.salvar(cx, bruto), pid)
    p.conferir("e não duplica",
               cx.execute("SELECT count(*) FROM profiles").fetchone()[0], 1)

    linha = profiles.por_usuario(cx, "casa_verde")
    p.conferir("username", linha["username"], "casa_verde")
    p.conferir("seguidores", linha["followers"], 84000)
    p.conferir("platform_profile_id", linha["platform_profile_id"], "1122334455")
    p.conferir("verificado é True, não 1", linha["is_verified"], True)
    p.conferir("categoria de negócio", linha["category"], "Entretenimento")
    p.conferir("fonte registrada", linha["source"], "apify")
    p.conferir("plataforma padrão", linha["platform"], "instagram")

    p.conferir_que("raw_data guardado como JSONB navegável",
                   cx.execute("SELECT raw_data->>'qualquer' FROM profiles "
                              "WHERE id = %s", (pid,)).fetchone()[0] == "coisa")

    p.secao("recoletar não pode destruir dado")

    profiles.salvar(cx, {"usuario": "casa_verde", "seguidores": 85000})
    linha = profiles.por_usuario(cx, "casa_verde")
    p.conferir("seguidores atualizam", linha["followers"], 85000)
    p.conferir("bio que não veio na rodada NÃO foi apagada",
               linha["bio"], "link na bio")
    p.conferir("nem o avatar", linha["avatar_url"], "https://cdn/avatar.jpg")
    p.conferir("nem o link externo", linha["external_url"], "https://casaverde.com")

    p.secao("classificação sobrevive à recoleta")

    profiles.classificar(cx, pid, categoria="cassino online", relevancia=0.92,
                         aprovado=True)
    linha = profiles.por_usuario(cx, "casa_verde")
    p.conferir("categoria classificada", linha["category"], "cassino online")
    p.conferir("relevância", round(linha["relevance"], 2), 0.92)
    p.conferir("aprovado", linha["is_approved"], True)
    p.conferir_que("com data", linha["classified_at"] is not None)

    profiles.salvar(cx, bruto)
    linha = profiles.por_usuario(cx, "casa_verde")
    p.conferir("recoletar NÃO desfaz a aprovação", linha["is_approved"], True)
    p.conferir("nem a relevância", round(linha["relevance"], 2), 0.92)

    p.secao("um perfil em vários nichos")

    p.conferir("primeiro vínculo é novo",
               profiles.ligar_ao_nicho(cx, pid, apostas, "busca"), True)
    p.conferir("repetir o vínculo não duplica",
               profiles.ligar_ao_nicho(cx, pid, apostas), False)
    p.conferir("o mesmo perfil entra em outro nicho",
               profiles.ligar_ao_nicho(cx, pid, cassino), True)
    p.conferir("dois vínculos, um perfil só",
               cx.execute("SELECT count(*) FROM niche_profiles").fetchone()[0], 2)
    p.conferir("contagem por nicho", niches.contar_perfis(cx, apostas), 1)

    p.secao("None não pode virar False")

    sem_dado = profiles.salvar(cx, {"usuario": "misterioso"})
    linha = profiles.por_usuario(cx, "misterioso")
    p.conferir_que("verificado desconhecido fica NULL, não False",
                   linha["is_verified"] is None)
    p.conferir_que("privado desconhecido fica NULL", linha["is_private"] is None)
    p.conferir_que("seguidores desconhecidos ficam NULL",
                   linha["followers"] is None)

    try:
        profiles.salvar(cx, {"nome": "sem usuario"})
        p.conferir_que("perfil sem usuário deveria estourar", False)
    except ErroDeRepositorio:
        p.conferir_que("perfil sem usuário levanta ErroDeRepositorio", True)

    p.secao("série temporal de seguidores")

    profiles.gravar_snapshot(cx, pid, seguidores=84000, seguindo=12,
                             medido_em="2026-08-20T12:00:00+00:00")
    profiles.gravar_snapshot(cx, pid, seguidores=85400, seguindo=13,
                             medido_em="2026-08-27T12:00:00+00:00")
    p.conferir("duas leituras", len(profiles.historico(cx, pid)), 2)

    profiles.gravar_snapshot(cx, pid, seguidores=99999,
                             medido_em="2026-08-27T12:00:00+00:00")
    hist = profiles.historico(cx, pid)
    p.conferir("mesmo instante substitui, não duplica", len(hist), 2)
    p.conferir("e o valor foi atualizado", hist[-1]["seguidores"], 99999)
    p.conferir_que("em ordem cronológica",
                   hist[0]["medido_em"] < hist[1]["medido_em"])

    import desempenho
    p.conferir("o histórico alimenta desempenho.crescimento() direto",
               desempenho.crescimento(hist)["absoluto"], 15999)

    p.secao("listar perfis do nicho")

    grande = profiles.salvar(cx, {"usuario": "tigre_bet", "seguidores": 210000})
    profiles.ligar_ao_nicho(cx, grande, apostas)
    privado = profiles.salvar(cx, {"usuario": "fechado", "seguidores": 500000,
                                   "privado": True})
    profiles.ligar_ao_nicho(cx, privado, apostas)

    lista = profiles.do_nicho(cx, apostas)
    p.conferir("perfil privado fica de fora",
               [linha["username"] for linha in lista], ["tigre_bet", "casa_verde"])

    p.conferir("filtrar por aprovados",
               [linha["username"] for linha in
                profiles.do_nicho(cx, apostas, apenas_aprovados=True)],
               ["casa_verde"])

    p.secao("apagar o nicho não apaga o perfil")

    cx.execute("DELETE FROM niches WHERE id = %s", (cassino,))
    p.conferir("o vínculo some", niches.contar_perfis(cx, cassino), 0)
    p.conferir_que("mas o perfil continua lá",
                   profiles.por_usuario(cx, "casa_verde") is not None)

    cx.commit()

finally:
    fechar_banco_de_teste(cfg, cx)

p.encerrar("repositórios de perfil")
