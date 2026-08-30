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
import mapeador
import db
import desempenho
from downloader import YtDlpDownloader
from repos import (consultas, contents, costs, jobs, media, metrics, niches,
                   profiles)
from storage import LocalStorage

TIPO_DOWNLOAD = "video_download"


def _linha(texto=""):
    print(texto)


def _tamanho(bytes_):
    """Bytes em unidade que uma pessoa lê sem contar zeros."""
    if not bytes_:
        return "0 MB"
    if bytes_ >= 1e9:
        return "%.2f GB" % (bytes_ / 1e9)
    if bytes_ >= 1e6:
        return "%.0f MB" % (bytes_ / 1e6)
    return "%.0f KB" % (bytes_ / 1e3)


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



# --------------------------------------------------------------- 0. mapear


def mapear(cfg, tema, teto_usd=None, rodadas=None, saturacao=None,
           itens_por_tag=None, aplicar=False, idioma_alvo=None):
    """Tema em portugues comum -> vocabulario, perfis-semente e numeros.

    A fase que faltava. Ate a T13 o sistema so sabia buscar: voce ja sabia o
    termo, pedia, recebia. Com "desastres e tragedias" isso quebra na primeira
    linha, porque `#desastres` provavelmente nao e onde esse conteudo vive — o
    input que o comando exige e justamente o output que ainda nao se tem.

    **Seco por padrao**, como o `limpar`: sem `--aplicar` nao escreve nem um
    nicho, nem um termo, nem um perfil. O que ele grava sempre e o JOB e o
    CUSTO — dinheiro gasto se registra mesmo quando o resultado e descartado,
    senao a conta do mes nao fecha.
    """
    if aplicar:
        return _mapear_aplicar(cfg, tema)

    apify = config.apify(cfg)
    mapa = config.mapeamento(cfg)

    teto_usd = teto_usd or mapa["teto_usd"]
    rodadas = rodadas or mapa["rodadas"]
    saturacao = saturacao or mapa["saturacao"]
    itens_por_tag = itens_por_tag or mapa["itens_por_tag"]
    idioma_alvo = idioma_alvo or mapa["idioma"]

    sementes = mapeador.sementes_do_tema(tema)
    if not sementes:
        _linha("Tema vazio. Diga do que voce quer perfis.")
        return 1

    _titulo("0. Mapeamento do tema: %r" % tema)
    _mostrar_criterios([
        ("sementes", ", ".join("#" + t for t in sementes)),
        ("teto", "US$ %.2f" % teto_usd),
        ("rodadas", rodadas),
        ("satura em", "%d%% de novidade" % (saturacao * 100)),
        ("itens por tag", itens_por_tag),
        ("idioma", "%s (descarta o que for provado de outro)" % idioma_alvo
                   if idioma_alvo != "qualquer" else "qualquer"),
    ])

    coletor = _montar_coletor(cfg)
    por_rodada = float(costs.custo_apify(itens_por_tag, apify["plano"]))

    contagens, perfis, posts = {}, {}, []
    visitadas, expandidos = set(), set()
    # O teto conta pela ESTIMATIVA e nao pelo custo real: o real so chega
    # depois da rodada, e depois e tarde para nao gastar. Numa sonda de
    # 30/08/2026 a Apify devolveu US$ 0.0000 numa rodada com 3 itens — teto que
    # contasse por ali nunca fecharia.
    estimado = real = 0.0
    parou_por = "rodadas"

    with db.conectar(cfg) as cx:
        coleta_id = jobs.abrir_coleta(cx, "niche_mapping", "apify",
                                      ator=coletor.actor)
        cx.commit()

        def _cabe(reserva=0.0):
            """Cabe mais uma chamada, guardando `reserva` para depois?

            A exploracao roda com uma chamada de reserva no bolso, para a
            MEDICAO do fim nunca ficar sem orcamento. Na rodada de 30/08/2026
            ela ficou: o laco gastou US$ 0,324 de 0,35 explorando, e a banda
            sugerida saiu de 6 perfis que por acaso tinham numero. Explorar
            mais um pouco vale menos que saber de quem se esta falando.
            """
            return estimado + por_rodada + reserva <= teto_usd + 1e-9

        for rodada in range(1, rodadas + 1):
            if rodada == 1:
                # TODAS as sementes, e nao so a primeira que render.
                #
                # `[MEDIDO 30/08/2026]` A versao anterior parava na primeira
                # porta que abria. `#desastres` rendeu, entao `#tragedias`
                # nunca foi tentada — e `#desastres` e tag hispanofona. A porta
                # que abriu primeiro decidiu o idioma, o pais e o assunto de
                # todo o mapeamento. Uma palavra a mais custa uma chamada; o
                # cluster errado custa a rodada inteira.
                alvos = list(sementes)
            else:
                # PARTE B do filtro, e e aqui que ele economiza dinheiro: tag
                # provada de outro idioma nao vira alvo da rodada seguinte.
                # Descartar so no fim seria pagar para aprofundar no cluster
                # que seria rejeitado depois.
                alvos = [linha["termo"] for linha
                         in mapeador.ranquear_termos(contagens)
                         if linha["termo"] not in visitadas
                         and not mapeador.e_de_outro_idioma(
                             contagens.get(linha["termo"]), idioma_alvo)
                         ][:mapa["tags_por_rodada"]]

            if not alvos and rodada > 1:
                parou_por = "acabaram as tags novas"
                break

            _linha("Rodada %d: %s" % (rodada, ", ".join("#" + t for t in alvos)))
            antes = set(contagens)

            for tag in alvos:
                if not _cabe(reserva=por_rodada):
                    parou_por = "teto"
                    break
                try:
                    coleta = coletor.mapear_tag(tag, itens_por_tag)
                except mod_coletor.ErroDeColeta as erro:
                    _linha("  #%s falhou: %s" % (tag, erro))
                    visitadas.add(tag)
                    continue

                visitadas.add(tag)
                estimado += por_rodada
                real += coleta.custo_usd or 0
                contagens = mapeador.fundir_contagens(
                    contagens,
                    mod_coletor.tags_dos_itens(coleta.brutos, fonte="#" + tag))
                for perfil in coleta.perfis:
                    perfis.setdefault(perfil["usuario"], {}).update(perfil)
                posts.extend(coleta.posts)
                _linha("  #%-24s %2d itens, %3d termos no total"
                       % (tag, coleta.itens, len(contagens)))

            # Eixo 2: parte de um perfil que ja apareceu, e nao de uma palavra.
            # `[MEDIDO 30/08/2026]` @receitasdepai devolveu 15 relacionados.
            # PARTE D: quem aparece em mais tags fortes, e nao quem chegou
            # primeiro. A aba da tag vem por recencia, entao ordem de chegada
            # significava "quem postou por ultimo".
            nucleo = [linha["usuario"] for linha
                      in mapeador.ranquear_perfis(contagens)
                      if linha["usuario"] in perfis]
            candidatos = ([u for u in nucleo if u not in expandidos]
                          + [u for u in perfis
                             if u not in expandidos and u not in nucleo])
            if parou_por != "teto" and candidatos and _cabe(reserva=por_rodada):
                alvos_perfis = candidatos[:mapa["perfis_para_expandir"]]
                try:
                    relacoes, coleta = coletor.relacionados_de(alvos_perfis)
                except mod_coletor.ErroDeColeta as erro:
                    _linha("  relacionados falharam: %s" % erro)
                    relacoes, coleta = {}, mod_coletor.Coleta()

                expandidos.update(alvos_perfis)
                estimado += por_rodada
                real += coleta.custo_usd or 0
                contagens = mapeador.fundir_contagens(
                    contagens,
                    mod_coletor.tags_dos_itens(coleta.brutos,
                                               fonte="relacionados"))
                for perfil in coleta.perfis:
                    perfis.setdefault(perfil["usuario"], {}).update(perfil)
                # PARTE C: os `latestPosts` do item de perfil vem datados, e
                # `_montar()` ja os normalizou. Antes eram jogados fora aqui, e
                # por isso `ritmo_dias_entre_posts` saia None num dossie que
                # tinha 12 posts datados por perfil ja pagos.
                posts.extend(coleta.posts)

                novos = 0
                for dono, parecidos in relacoes.items():
                    for parecido in parecidos:
                        if parecido not in perfis:
                            # Vem SEM contagem de seguidores — conferido. Fica
                            # indeterminado ate alguem qualificar.
                            perfis[parecido] = {"usuario": parecido,
                                                "fonte": "relacionado de @%s"
                                                         % dono}
                            novos += 1
                _linha("  relacionados de %d perfil(is): %d nomes novos"
                       % (len(alvos_perfis), novos))

            if parou_por == "teto":
                break
            if mapeador.saturou(antes, set(contagens), saturacao):
                parou_por = "saturacao"
                break

        # MEDIR, que e diferente de descobrir. O perfil que veio da aba da tag
        # nao traz contagem de seguidores — conferido em 30/08/2026, nem com
        # `addParentData`. Sem esta chamada a "banda sugerida" sai de qualquer
        # punhado de perfis que por acaso tinha numero, e uma banda medida
        # sobre tres contas de 100 seguidores nao serve para nada.
        # Mede primeiro quem e nucleo do nicho: a banda tem de descrever quem
        # faz o assunto, nao quem passou pela tag.
        nucleo = [linha["usuario"] for linha
                  in mapeador.ranquear_perfis(contagens)]
        sem_numero = ([u for u in nucleo
                       if perfis.get(u, {}).get("seguidores") is None]
                      + [u for u, p in perfis.items()
                         if p.get("seguidores") is None and u not in nucleo])
        if sem_numero and _cabe():   # aqui sem reserva: esta E a reserva
            fila = sem_numero[:mapa["perfis_para_medir"]]
            _linha("Medindo %d perfil(is) para a distribuicao..." % len(fila))
            try:
                medidos = coletor.qualificar(fila)
            except mod_coletor.ErroDeColeta as erro:
                _linha("  a medicao falhou: %s" % erro)
                medidos = mod_coletor.Coleta()
            estimado += por_rodada
            real += medidos.custo_usd or 0
            for perfil in medidos.perfis:
                perfis.setdefault(perfil["usuario"], {}).update(perfil)
            posts.extend(medidos.posts)   # PARTE C, o outro lugar
            com_numero = sum(1 for p in perfis.values()
                             if p.get("seguidores") is not None)
            _linha("  %d perfil(is) com contagem de seguidores" % com_numero)

        jobs.fechar_coleta(cx, coleta_id, encontrados=len(contagens),
                           criados=0, atualizados=0)
        _registrar_custo(cx, "niche_mapping",
                         mod_coletor.Coleta(itens=len(contagens),
                                            custo_usd=real), coleta_id)
        cx.commit()

    dossie = mapeador.montar_dossie(tema, contagens, list(perfis.values()),
                                    posts, custo_usd=real,
                                    rodadas=rodada, parou_por=parou_por,
                                    alvo=idioma_alvo)
    destino = mapeador.gravar_dossie(dossie)

    _linha()
    _linha("Parou por: %s. %d termos, %d perfis."
           % (parou_por, len(contagens), len(perfis)))
    _linha("Custo estimado US$ %.4f (teto US$ %.2f) | real US$ %.4f"
           % (estimado, teto_usd, real))
    _linha()
    _linha("As 10 mais fortes (por PERFIS distintos, nao por frequencia):")
    for linha in dossie["tags"][:10]:
        _linha("  #%-26s %2d perfis  %3d posts  [%s]"
               % (linha["termo"], linha["perfis"], linha["posts"],
                  linha["idioma"]))

    fora = dossie["descartados_por_idioma"]
    if fora:
        _linha()
        _linha("%d descartada(s) por idioma (as 5 primeiras). Nao sumiram: "
               "estao no dossie." % len(fora))
        for linha in fora[:5]:
            _linha("  #%-26s %2d perfis  [%s]" % (linha["termo"],
                                                  linha["perfis"],
                                                  linha["idioma"]))
    banda = dossie["numeros"]["banda_sugerida"]
    _linha()
    ritmo = dossie["numeros"]["ritmo_dias_entre_posts"]
    _linha()
    _linha("Ritmo: %s" % ("%.1f dias entre posts" % ritmo if ritmo
                          else "nao deu para medir"))
    _linha("Banda sugerida: %s a %s seguidores"
           % (banda["seguidores_min"], banda["seguidores_max"]))
    _linha("  (%s)" % banda["por_que"])
    _linha()
    _linha("Nada foi gravado no banco. Abra o dossie, marque \"entra\": true")
    _linha("no que presta, e rode:")
    _linha('  python src/pipeline.py mapear "%s" --aplicar' % tema)
    _linha("Dossie: %s" % destino)
    return 0


def _mapear_aplicar(cfg, tema):
    """Le o dossie editado e grava so o que voce marcou.

    Os REPROVADOS tambem entram em `niche_terms`, com `is_approved = false`.
    Parece contradizer "grava so o aprovado", mas nao: reprovado gravado nao
    vira criterio de busca nenhum — ele so impede que o proximo mapeamento
    volte a te oferecer a mesma tag de propaganda para julgar de novo.
    """
    try:
        dossie = mapeador.ler_dossie(tema)
    except mapeador.ErroDeMapeamento as erro:
        _linha(str(erro))
        return 1

    tags = dossie.get("tags") or []
    perfis = dossie.get("perfis") or []
    tags_sim = mapeador.aprovados(dossie, "tags")
    perfis_sim = mapeador.aprovados(dossie, "perfis")

    _titulo("0. Aplicar o mapeamento: %r" % tema)

    if not tags_sim and not perfis_sim:
        _linha("Nenhum item marcado com \"entra\": true no dossie.")
        _linha("Abra %s e marque o que presta." % mapeador.caminho_do_dossie(tema))
        return 1

    with db.conectar(cfg) as cx:
        nicho_id = niches.obter_ou_criar(
            cx, tema, palavras_chave=[t["termo"] for t in tags_sim],
            idioma=dossie.get("idioma_alvo"))

        for linha in tags:
            niches.salvar_termo(cx, nicho_id, linha["termo"],
                                perfis=linha.get("perfis", 0),
                                posts=linha.get("posts", 0),
                                fonte=linha.get("fonte"),
                                aprovado=bool(linha.get("entra")))

        banda = (dossie.get("numeros") or {}).get("banda_sugerida") or {}
        criterios = {c: banda.get(c) for c in ("seguidores_min",
                                               "seguidores_max")
                     if banda.get(c) is not None}
        if criterios:
            criterios["origem"] = "mapeamento de %s" % dossie.get("gerado_em")
            niches.salvar_criterios(cx, nicho_id, criterios)

        aprovados_perfis = 0
        for linha in perfis_sim:
            usuario = linha.get("usuario")
            if not usuario:
                continue
            perfil_id = profiles.salvar(cx, {"usuario": usuario,
                                             "seguidores": linha.get("seguidores")},
                                        fonte="mapeamento")
            profiles.ligar_ao_nicho(cx, perfil_id, nicho_id, "mapeamento")
            profiles.classificar(cx, perfil_id, aprovado=True)
            aprovados_perfis += 1

        cx.commit()

    _linha("%d tag(s) aprovada(s), %d reprovada(s) e registradas como tal."
           % (len(tags_sim), len(tags) - len(tags_sim)))
    _linha("%d perfil(is) aprovado(s) e ligado(s) ao nicho." % aprovados_perfis)
    if criterios:
        _linha("Banda do nicho: %s a %s seguidores — passa a valer sobre o "
               "config." % (criterios.get("seguidores_min"),
                            criterios.get("seguidores_max")))
    _linha()
    _linha("Agora a busca usa o vocabulario aprovado:")
    _linha('  python src/pipeline.py descobrir "%s" --eixos hashtag' % tema)
    return 0


def _do_nicho(cfg, nicho):
    """O que o MAPEAMENTO aprendeu sobre este nicho: criterios e tags.

    Devolve `({}, [])` quando o nicho nao existe ou nunca foi mapeado — e a
    resposta honesta para "quais os criterios proprios deste nicho?" antes de
    alguem ter medido. O global do config assume, como sempre assumiu.

    Isto fecha a precedencia em quatro niveis:

        flag  >  nicho (banco)  >  global (config)  >  padrao (codigo)

    O nicho fica no meio de proposito: ele foi MEDIDO, entao vale mais que o
    palpite global; mas a flag continua ganhando, porque quem esta no terminal
    sabe o que quer daquela rodada.
    """
    if not nicho:
        return {}, []

    with db.conectar(cfg) as cx:
        achado = niches.por_nome(cx, nicho)
        if not achado:
            return {}, []
        return (niches.criterios(cx, achado["id"]),
                niches.tags_aprovadas(cx, achado["id"]))


def _faixa(texto):
    """"10000-500000" -> (10000, 500000). "-500000" e "10000-" tambem valem.

    Existe para a banda caber numa flag so. Duas flags separadas convidam ao
    erro de passar so uma e achar que passou as duas.
    """
    if not texto:
        return None, None
    partes = str(texto).split("-")
    if len(partes) != 2:
        raise ValueError(
            "Faixa em formato errado: %r. Use MIN-MAX, por exemplo "
            "10000-500000 (qualquer um dos lados pode ficar vazio)." % texto)
    minimo = int(partes[0]) if partes[0].strip() else None
    maximo = int(partes[1]) if partes[1].strip() else None
    return minimo, maximo


def _mostrar_criterios(criterios):
    """Imprime o que ESTA valendo nesta rodada.

    Nao e enfeite. Estas variaveis vem de tres lugares — flag, config e padrao
    do codigo — e ate 30/08/2026 o `config.local.json` tinha uma secao `busca`
    com `min_seguidores` que NINGUEM lia. A config prometia um filtro que nao
    acontecia, e nada na tela denunciava. Agora denuncia.
    """
    _linha("Critérios desta rodada:")
    for rotulo, valor in criterios:
        _linha("  %-18s %s" % (rotulo, valor))
    _linha()


def descobrir(cfg, nicho, max_perfis=None, forcar=False, eixos=None,
              seguidores=None, max_qualificar=None):
    apify = config.apify(cfg)
    criterios = config.descoberta(cfg)
    do_nicho, tags_do_nicho = _do_nicho(cfg, nicho)

    # A precedencia, no unico lugar onde ela existe: a flag ganha da config, a
    # config ganha do padrao. `or` resolve porque nenhum destes tem zero como
    # valor legitimo — descobrir 0 perfis nao e pedido de ninguem.
    max_perfis = max_perfis or criterios["max_perfis"] or apify["max_perfis"]
    eixos = eixos or criterios["eixos"]
    max_qualificar = max_qualificar or criterios["max_qualificar"]

    if seguidores:
        minimo, maximo = _faixa(seguidores)
    else:
        # O nicho mapeado ganha do global: a banda dele saiu de percentis
        # medidos, e a global saiu de intuicao.
        minimo = do_nicho.get("seguidores_min", criterios["seguidores_min"])
        maximo = do_nicho.get("seguidores_max", criterios["seguidores_max"])

    _titulo("1. Descoberta de perfis: %r" % nicho)
    # O eixo de hashtag deixa de adivinhar a tag pelo nome do nicho. "apostas"
    # nao vive em #apostas; vive em #tigrinho e #cassino, e quem sabe disso e o
    # mapeamento.
    alvos_de_tag = tags_do_nicho[:criterios["max_tags_por_rodada"]] or [nicho]

    _mostrar_criterios([
        ("eixos", ", ".join(eixos)),
        ("tags do nicho", ", ".join("#" + t for t in alvos_de_tag)
                          if tags_do_nicho else
                          "nenhuma mapeada — usando o nome do nicho"),
        ("banda vem de", "nicho mapeado" if do_nicho else "config global"),
        ("seguidores", "%s a %s"
                       % (minimo if minimo is not None else "sem minimo",
                          maximo if maximo is not None else "sem maximo")),
        ("so publicos", "sim" if criterios["somente_publicos"] else "nao"),
        ("teto de perfis", max_perfis),
        ("qualificar ate", max_qualificar),
    ])

    chamadas = sum(len(alvos_de_tag) if e == "hashtag" else 1 for e in eixos)
    estimado = float(costs.custo_apify(max_perfis * chamadas, apify["plano"]))
    if not _confirmar_gasto(estimado, apify["avisar_acima_de_usd"], forcar):
        return 1

    coletor = _montar_coletor(cfg)

    with db.conectar(cfg) as cx:
        nicho_id = niches.obter_ou_criar(cx, nicho)
        coleta_id = jobs.abrir_coleta(cx, "profile_discovery", "apify",
                                      ator=coletor.actor, nicho_id=nicho_id)
        cx.commit()

        achados, custo, itens, run_id = [], 0.0, 0, None
        vistos = set()

        for eixo in eixos:
            # Um eixo pode render varias chamadas: com vocabulario mapeado, a
            # hashtag roda uma vez por tag aprovada.
            alvos = alvos_de_tag if eixo == "hashtag" else [nicho]
            _linha("Eixo %r (%d chamada(s))..." % (eixo, len(alvos)))

            for alvo in alvos:
                try:
                    coleta = coletor.descobrir_perfis(alvo, max_perfis,
                                                      eixo=eixo)
                except mod_coletor.ErroDeColeta as erro:
                    jobs.fechar_coleta(cx, coleta_id, status=jobs.FALHA,
                                       erro=str(erro))
                    cx.commit()
                    _linha("FALHOU no eixo %r (%r): %s" % (eixo, alvo, erro))
                    return 1

                custo += coleta.custo_usd or 0
                itens += coleta.itens
                run_id = coleta.run_id or run_id
                for perfil in coleta.perfis:
                    if perfil.get("usuario") in vistos:
                        continue
                    vistos.add(perfil.get("usuario"))
                    perfil.setdefault("nicho", nicho)
                    achados.append(perfil)
                _linha("  %-24s %d perfis, %d itens"
                       % (alvo, len(coleta.perfis), coleta.itens))

        # Quem veio da hashtag nao tem contagem de seguidores — o item da tag
        # nao traz, conferido em 30/08/2026, nem com `addParentData`. Sem esta
        # etapa todo candidato de hashtag ficaria indeterminado, e a banda nao
        # decidiria nada.
        indefinidos = [
            p["usuario"] for p in achados
            if mod_coletor.na_banda(p, minimo, maximo,
                                    criterios["somente_publicos"]) is None]

        if indefinidos:
            fila = indefinidos[:max_qualificar]
            _linha()
            _linha("%d candidato(s) sem contagem de seguidores. Qualificando "
                   "%d (teto)." % (len(indefinidos), len(fila)))
            try:
                extra = coletor.qualificar(fila)
            except mod_coletor.ErroDeColeta as erro:
                _linha("A qualificacao falhou: %s" % erro)
                extra = mod_coletor.Coleta()
            custo += extra.custo_usd or 0
            itens += extra.itens
            por_usuario = {p.get("usuario"): p for p in extra.perfis}
            achados = [dict(p, **por_usuario.get(p.get("usuario"), {}))
                       for p in achados]

        novos, fora, ja_tinha, gravados = 0, 0, 0, 0
        for perfil in achados:
            usuario = perfil.get("usuario")
            existente = profiles.id_por_usuario(cx, usuario) if usuario else None

            if existente is None:
                veredito = mod_coletor.na_banda(perfil, minimo, maximo,
                                                criterios["somente_publicos"])
                if veredito is not True:
                    # Indeterminado tambem fica de fora: perfil novo sem numero
                    # nenhum e linha que ninguem sabe julgar, e o banco ja tem
                    # uma dessas — `premiere`, criada sem nicho em 28/08.
                    fora += 1
                    continue
            else:
                # Perfil que JA ESTA no banco nao passa pela banda. Decisao do
                # usuario em 30/08/2026: a banda vale para descoberta nova; os
                # 9 que ja estavam ficam, mesmo os 6 que ela reprovaria.
                ja_tinha += 1

            perfil_id = profiles.salvar(cx, perfil, fonte="apify",
                                        ator=coletor.actor, run_id=run_id)
            gravados += 1
            if profiles.ligar_ao_nicho(cx, perfil_id, nicho_id, "busca"):
                novos += 1
            # A foto de agora. Gravada já na primeira vez, quando ainda não
            # serve de nada — porque crescimento é a diferença entre duas.
            profiles.gravar_snapshot(cx, perfil_id,
                                     seguidores=perfil.get("seguidores"),
                                     seguindo=perfil.get("seguindo"),
                                     conteudos=perfil.get("posts"),
                                     job_id=coleta_id)

        jobs.fechar_coleta(cx, coleta_id, encontrados=itens, criados=novos,
                           atualizados=max(gravados - novos, 0), run_id=run_id)
        _registrar_custo(cx, "profile_collection",
                         mod_coletor.Coleta(itens=itens, custo_usd=custo,
                                            run_id=run_id), coleta_id)
        cx.commit()

    _linha()
    _linha("%d achados: %d gravados (%d novos no nicho, %d ja existiam), "
           "%d fora da banda."
           % (len(achados), gravados, novos, ja_tinha, fora))
    _linha("Custo real: US$ %.4f (%d itens)" % (custo, itens))
    _linha()
    _linha("Nenhum foi julgado relevante ainda — a banda diz que o perfil TEM")
    _linha("o tamanho certo, nao que ele presta. Confira: pipeline.py status")
    return 0


# ---------------------------------------------------------------- 2. coletar


def coletar(cfg, nicho=None, perfis=None, posts_por_perfil=None,
            limite_perfis=None, forcar=False, so_aprovados=False,
            janela_dias=None, tipo=None, sem_fixados=False):
    apify = config.apify(cfg)
    criterios = config.coleta(cfg)
    do_nicho, _ = _do_nicho(cfg, nicho)

    posts_por_perfil = (posts_por_perfil or criterios["posts_por_perfil"]
                        or apify["posts_por_perfil"])
    limite_perfis = limite_perfis or apify["max_perfis"]
    tipo = tipo or do_nicho.get("tipo") or criterios["tipo"]
    if janela_dias is None:
        janela_dias = do_nicho.get("janela_dias", criterios["janela_dias"])
    incluir_fixados = criterios["incluir_fixados"] and not sem_fixados

    _titulo("2. Coleta de conteúdo")
    _mostrar_criterios([
        ("janela", "%d dias" % janela_dias if janela_dias else "sem filtro de data"),
        ("tipo", tipo),
        ("posts por perfil", posts_por_perfil),
        ("fixados", "entram marcados" if incluir_fixados else "descartados"),
    ])

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
            coleta = coletor.coletar_conteudo(
                usuarios, posts_por_perfil,
                janela_dias=janela_dias, tipo=tipo)
        except mod_coletor.ErroDeColeta as erro:
            jobs.fechar_coleta(cx, coleta_id, status=jobs.FALHA, erro=str(erro))
            cx.commit()
            _linha("FALHOU: %s" % erro)
            return 1

        guarda = LocalStorage()
        na_fila, fixados, descartados = 0, 0, 0

        for perfil in coleta.perfis:
            perfil_id = profiles.salvar(cx, perfil, fonte="apify",
                                        ator=coletor.actor, run_id=coleta.run_id)
            profiles.gravar_snapshot(cx, perfil_id,
                                     seguidores=perfil.get("seguidores"),
                                     seguindo=perfil.get("seguindo"),
                                     conteudos=perfil.get("posts"),
                                     job_id=coleta_id)

        for post in coleta.posts:
            # `[MEDIDO 30/08/2026]` O fixado passa por cima do filtro de data
            # do Actor: pedindo 30 dias vieram dois posts de fora, e eram
            # exatamente os dois `isPinned` — um de 2024, com 6,9M de views.
            # Deixar isso entrar sem marca envenena qualquer media de janela.
            if post.get("fixado"):
                fixados += 1
                if not incluir_fixados:
                    descartados += 1
                    continue

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
    if fixados:
        _linha("%d fixado(s): %s. Post fixado escapa da janela de data — fica"
               % (fixados, "%d descartado(s)" % descartados if descartados
                  else "gravados e marcados"))
        _linha("marcado para não entrar em conta de recência como se fosse novo.")
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
            _linha("  %d arquivos, %s no total"
                   % (disco["arquivos"], _tamanho(disco["bytes"])))

            for linha in media.por_tipo(cx):
                _linha("    %-10s %3d arquivos  %s"
                       % (linha["tipo"], linha["arquivos"],
                          _tamanho(linha["bytes"])))

            pesados = media.por_perfil(cx, limite=5)
            if len(pesados) > 1:
                _linha("  quem mais ocupa:")
                for linha in pesados:
                    _linha("    %-22s %3d  %s"
                           % (linha["perfil"], linha["arquivos"],
                              _tamanho(linha["bytes"])))

            liberavel = media.com_derivado_pronto(cx)
            bytes_liberaveis = sum(a["file_size"] or 0 for a in liberavel)
            _linha("  liberável agora: %s (%d vídeo(s) já transcrito(s))"
                   % (_tamanho(bytes_liberaveis), len(liberavel)))
            if liberavel:
                _linha("  -> pipeline.py limpar --transcritos")

            teto = config.dados(cfg)["avisar_acima_de_gb"]
            if teto and disco["bytes"] > teto * 1e9:
                _linha()
                _linha("  AVISO: passou de %g GB (o limite do seu config)."
                       % teto)

    return 0


# ----------------------------------------------------------------- 5. limpar


def _midias_no_disco():
    """Todo `midia.*` que existe em dados/perfis, olhando o disco de verdade."""
    if not config.PERFIS.is_dir():
        return []
    return sorted(caminho for caminho in config.PERFIS.glob("*/*/midia.*")
                  if caminho.is_file())


def _descompasso(cx):
    """Onde o disco e o banco discordam.

    Dois erros diferentes, com causas diferentes:

    - **registro sem arquivo**: alguém apagou o mp4 por fora. `media.tem()`
      continua dizendo que existe, e a transcrição vai falhar lá na frente,
      longe da causa.
    - **arquivo sem registro**: byte ocupando disco que nenhuma consulta
      alcança. Foi o caso de `dados/perfis/premiere/` em 28/08 — um post de
      colaboração cujo dono nunca foi descoberto.
    """
    registradas = {Path(chave) for chave in media.chaves_registradas(cx)}
    no_disco = set(_midias_no_disco())

    return {
        "registro_sem_arquivo": sorted(registradas - no_disco),
        "arquivo_sem_registro": sorted(no_disco - registradas),
    }


def _apagar(caminho):
    """Apaga o arquivo e a pasta do post, se ela ficar vazia."""
    caminho = Path(caminho)
    try:
        caminho.unlink()
    except FileNotFoundError:
        return False
    except OSError as erro:
        _linha("    nao consegui apagar %s: %s" % (caminho.name, erro))
        return False

    pasta = caminho.parent
    try:
        if pasta.is_dir() and not any(pasta.iterdir()):
            pasta.rmdir()
    except OSError:
        pass
    return True


def limpar(cfg, transcritos=False, orfas=False, antes_de=None, aplicar=False):
    """O que dá para liberar do disco — e, só com --aplicar, libera.

    Seco por padrão, pela mesma disciplina do freio de custo da Apify: mostra
    a conta antes de cobrar. A diferença é que aqui a conta é irreversível — o
    mp4 volta por download, mas o download custa tempo e a Apify custa dinheiro.

    Sem nenhum alvo escolhido, relata os dois e não apaga nada.
    """
    so_relatorio = not (transcritos or orfas)
    _titulo("Limpeza de disco")

    with db.conectar(cfg) as cx:
        disco = media.total_em_disco(cx)
        _linha("  hoje: %d arquivos, %s"
               % (disco["arquivos"], _tamanho(disco["bytes"])))

        liberaveis = media.com_derivado_pronto(cx, dias=antes_de)
        bytes_liberaveis = sum(a["file_size"] or 0 for a in liberaveis)

        _titulo("Vídeos já transcritos")
        if antes_de:
            _linha("  (só os baixados há mais de %d dias)" % antes_de)
        if not liberaveis:
            _linha("  nenhum. Só some do disco o que já virou transcrição —")
            _linha("  o mp4 é re-baixável, a transcrição não.")
        else:
            for arquivo in liberaveis[:20]:
                _linha("    %-22s %-13s %s"
                       % (arquivo["username"], arquivo["platform_content_id"],
                          _tamanho(arquivo["file_size"] or 0)))
            if len(liberaveis) > 20:
                _linha("    ... e mais %d" % (len(liberaveis) - 20))
            _linha("  total: %d vídeo(s), %s"
                   % (len(liberaveis), _tamanho(bytes_liberaveis)))

        fora = _descompasso(cx)

        _titulo("Descompasso entre disco e banco")
        sem_arquivo = fora["registro_sem_arquivo"]
        sem_registro = fora["arquivo_sem_registro"]

        if not sem_arquivo and not sem_registro:
            _linha("  nenhum. Disco e banco contam a mesma história.")
        if sem_arquivo:
            _linha("  %d registro(s) apontando para arquivo que sumiu:"
                   % len(sem_arquivo))
            for caminho in sem_arquivo[:10]:
                _linha("    %s" % caminho)
        if sem_registro:
            ocupado = sum(c.stat().st_size for c in sem_registro)
            _linha("  %d arquivo(s) que nenhuma consulta alcança (%s):"
                   % (len(sem_registro), _tamanho(ocupado)))
            for caminho in sem_registro[:10]:
                _linha("    %s" % caminho.relative_to(config.PERFIS))

        if so_relatorio:
            _linha()
            _linha("Nada foi apagado. Escolha o alvo para agir:")
            _linha("  pipeline.py limpar --transcritos --aplicar")
            _linha("  pipeline.py limpar --orfas --aplicar")
            return 0

        if not aplicar:
            _linha()
            _linha("Nada foi apagado — faltou --aplicar.")
            return 0

        # --------------------------------------------------------- aplicando
        _titulo("Apagando")
        apagados, liberado = 0, 0

        if transcritos:
            for arquivo in liberaveis:
                if _apagar(arquivo["storage_key"]):
                    media.esquecer(cx, arquivo["id"])
                    apagados += 1
                    liberado += arquivo["file_size"] or 0

        if orfas:
            for caminho in sem_registro:
                tamanho = caminho.stat().st_size
                if _apagar(caminho):
                    apagados += 1
                    liberado += tamanho
            for caminho in sem_arquivo:
                for asset in media.registros_da_chave(cx, str(caminho)):
                    media.esquecer(cx, asset["id"])
                    _linha("    registro órfão removido: %s" % caminho.name)

        cx.commit()
        _linha("  %d arquivo(s) apagado(s), %s liberado(s)"
               % (apagados, _tamanho(liberado)))

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

    m = sub.add_parser("mapear", help="tema -> vocabulário, perfis e números")
    m.add_argument("tema")
    m.add_argument("--teto-usd", type=float, dest="teto_usd",
                   help="freio duro, em dólar. Conta pela estimativa")
    m.add_argument("--rodadas", type=int, help="profundidade da exploração")
    m.add_argument("--saturacao", type=float,
                   help="para quando a novidade cair abaixo disto (0.20)")
    m.add_argument("--itens-por-tag", type=int, dest="itens_por_tag")
    m.add_argument("--idioma", dest="idioma_alvo",
                   help="descarta o que for provado de outro idioma. "
                        "'qualquer' desliga (padrão: pt)")
    m.add_argument("--aplicar", action="store_true",
                   help="grava no banco o que você marcou no dossiê")

    # As flags de critério são o espelho da seção do `config.local.json`.
    # Espelho, e não substituto: a flag serve para experimentar uma rodada sem
    # editar arquivo; o que vale por padrão continua sendo o que está no
    # config. Ordem: flag > config > padrão do código.
    d = sub.add_parser("descobrir", help="nicho -> perfis")
    d.add_argument("nicho")
    d.add_argument("--max-perfis", type=int)
    d.add_argument("--eixos", help="nome, hashtag, ou 'nome,hashtag'")
    d.add_argument("--seguidores", metavar="MIN-MAX",
                   help="banda de seguidores, ex.: 10000-500000")
    d.add_argument("--max-qualificar", type=int, dest="max_qualificar",
                   help="teto de candidatos de hashtag a qualificar (cada um "
                        "custa uma chamada)")
    d.add_argument("--forcar", action="store_true", help="não perguntar do custo")

    c = sub.add_parser("coletar", help="perfis -> conteúdo + fila")
    c.add_argument("--nicho")
    c.add_argument("--perfis", help="lista separada por vírgula")
    c.add_argument("--posts", type=int, dest="posts_por_perfil")
    c.add_argument("--limite-perfis", type=int)
    c.add_argument("--so-aprovados", action="store_true")
    c.add_argument("--janela-dias", type=int, dest="janela_dias",
                   help="só posts dos últimos N dias (0 = sem filtro de data)")
    c.add_argument("--tipo", choices=("reels", "posts"),
                   help="reels pede só vídeo, e por isso sai mais barato")
    c.add_argument("--sem-fixados", action="store_true", dest="sem_fixados",
                   help="descartar post fixado em vez de gravá-lo marcado")
    c.add_argument("--forcar", action="store_true")

    lp = sub.add_parser("limpar", help="o que dá para liberar do disco")
    lp.add_argument("--transcritos", action="store_true",
                    help="mídia cujo conteúdo já tem transcrição")
    lp.add_argument("--orfas", action="store_true",
                    help="descompasso entre disco e banco")
    lp.add_argument("--antes-de", type=int, dest="antes_de", metavar="DIAS",
                    help="só o que foi baixado há mais de N dias")
    lp.add_argument("--aplicar", action="store_true",
                    help="apagar de verdade. Sem isto, só relata.")

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
        if args.comando == "mapear":
            return mapear(cfg, args.tema, args.teto_usd, args.rodadas,
                          args.saturacao, args.itens_por_tag, args.aplicar,
                          args.idioma_alvo)
        if args.comando == "descobrir":
            eixos = [e.strip().lower() for e in (args.eixos or "").split(",")
                     if e.strip()]
            return descobrir(cfg, args.nicho, args.max_perfis, args.forcar,
                             eixos=eixos or None, seguidores=args.seguidores,
                             max_qualificar=args.max_qualificar)
        if args.comando == "coletar":
            # `--janela-dias 0` é o jeito de dizer "sem filtro de data" na
            # linha de comando. `None` ali significaria "não passei a flag", e
            # aí o config voltaria a mandar — que é o contrário do pedido.
            janela = None if args.janela_dias is None else (args.janela_dias or None)
            return coletar(cfg, args.nicho, args.perfis, args.posts_por_perfil,
                           args.limite_perfis, args.forcar, args.so_aprovados,
                           janela_dias=janela, tipo=args.tipo,
                           sem_fixados=args.sem_fixados)
        if args.comando == "baixar":
            return baixar(cfg, args.limite, args.concorrencia,
                          args.tentar_de_novo)
        if args.comando == "status":
            return status(cfg)
        if args.comando == "ranking":
            return ranking(cfg, args.nicho, args.limite)
        if args.comando == "limpar":
            return limpar(cfg, args.transcritos, args.orfas, args.antes_de,
                          args.aplicar)
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
