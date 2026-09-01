"""Nicho -> perfis -> conteudo. A descoberta, e so ela.

Uma interface e uma implementacao em cima da Apify.

**Por que Apify e nao raspagem propria:** o `InstagramUserIE` do yt-dlp esta
marcado `_WORKING = False` no codigo-fonte dele — listar os posts de um perfil
e justamente o que ele nao faz. E raspar por conta propria custa conta, cookie,
IP e bloqueio, que foi onde este projeto travou. A Apify assume esse risco.

**Divisao de trabalho:** aqui so se descobre e se normaliza. Baixar video e do
`downloader.py`; guardar arquivo e do `storage.py`; gravar e do `banco.py`.

------------------------------------------------------------------------------
`[VERIFICADO 28/08/2026]` O mapeamento foi conferido contra uma rodada real do
`apify/instagram-scraper` (run y7QKvQUMo73pGrPFD). Tres coisas so apareceram ai:

  1. `externalUrls` e PLURAL e e LISTA, nao `externalUrl` string.
  2. Os posts vem ANINHADOS em `latestPosts` dentro do item de perfil, nao
     como itens soltos no dataset.
  3. `resultsLimit` tem minimo 1 -- nao existe "so o perfil, nenhum post".

Campos confirmados no item de perfil: biography, businessCategoryName,
externalUrls, facebookPage, fbid, followersCount, followsCount, fullName,
highlightReelCount, id, igtvVideoCount, inputUrl, isBusinessAccount,
joinedRecently, latestIgtvVideos, latestPosts, postsCount, private,
profilePicUrl, profilePicUrlHD, relatedProfiles, searchSource, searchTerm,
url, username, verified.

O mapeamento do POST ainda nao foi verificado: o unico perfil que a busca
devolveu nao tinha nenhum. `_primeiro()` continua aceitando varios nomes por
esse motivo.
------------------------------------------------------------------------------
"""

import time
from datetime import datetime, timezone

import idioma
import lexico

ACTOR_PADRAO = "apify/instagram-scraper"

# Precos publicados pela Apify em 26/08/2026, por 1.000 resultados.
# 1 resultado = 1 item cobrado (um post, um perfil, um comentario).
PRECO_POR_MIL = {"free": 2.70, "starter": 2.30, "scale": 1.90, "business": 1.50}
PLANO_PADRAO = "free"

DIAS = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday",
        4: "Friday", 5: "Saturday", 6: "Sunday"}


class ErroDeColeta(Exception):
    """Falha na descoberta. Mensagem ja pronta para o usuario."""


def custo_estimado(itens, plano=PLANO_PADRAO):
    """Quanto uma rodada de N resultados deve custar, em dolar."""
    return itens * PRECO_POR_MIL.get(plano, PRECO_POR_MIL[PLANO_PADRAO]) / 1000.0


def _primeiro(dicionario, *chaves, padrao=None):
    """O primeiro nome de campo que existir e nao for vazio.

    Existe porque o schema do Actor ainda nao foi verificado contra uma rodada
    real: aceitar `followersCount` e `followers` custa nada e evita quebrar
    tudo por causa de um nome.
    """
    for chave in chaves:
        valor = dicionario.get(chave)
        if valor not in (None, "", [], {}):
            return valor
    return padrao


def _contagem(valor):
    """Contagem oculta vem como -1, nao como ausencia.

    `[VERIFICADO 28/08/2026]` Na rodada real do nicho 'receitas', dois posts
    de @receitas vieram com `likesCount: -1`. Nao sao "menos um like": e o
    sentinela do Instagram para quem escondeu as curtidas. Guardado cru, ele
    produzia engajamento NEGATIVO e derrubava o post no ranking por um motivo
    que nada tem a ver com desempenho.

    Mesma regra que ja valia para `salvamentos`: None diz "nao sabemos", que
    e a verdade. Zero diria "ninguem curtiu", que e mentira.
    """
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return valor
    return None if valor < 0 else valor


def _caminho(dicionario, *chaves):
    """Desce por um campo aninhado sem estourar se o caminho nao existir."""
    atual = dicionario
    for chave in chaves:
        if not isinstance(atual, dict):
            return None
        atual = atual.get(chave)
    return atual if atual not in ("", [], {}) else None


def _data_em_partes(bruto):
    """ISO ou epoch -> (utc, local, dia da semana, hora).

    O resto do projeto ja espera esses quatro campos separados; `metricas.py`
    calcula faixa de horario em cima deles.
    """
    if bruto in (None, ""):
        return None, None, None, None

    momento = None
    if isinstance(bruto, (int, float)):
        momento = datetime.fromtimestamp(bruto, tz=timezone.utc)
    else:
        try:
            momento = datetime.fromisoformat(str(bruto).replace("Z", "+00:00"))
        except ValueError:
            return None, None, None, None

    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)

    local = momento.astimezone()
    return (momento.isoformat(), local.isoformat(),
            DIAS[local.weekday()], local.strftime("%H:%M"))


def _primeiro_link(bruto):
    """O link da bio.

    `[VERIFICADO 28/08/2026]` O Actor devolve `externalUrls` no PLURAL e como
    LISTA, nao `externalUrl` como string. Descoberto na rodada de conferencia;
    antes disso o campo vinha sempre vazio e ninguem notaria.
    """
    lista = bruto.get("externalUrls")
    if isinstance(lista, list) and lista:
        primeiro = lista[0]
        if isinstance(primeiro, dict):
            return primeiro.get("url") or primeiro.get("link")
        return primeiro
    return _primeiro(bruto, "externalUrl", "website")


def _booleano_ou_none(valor):
    """True/False quando a fonte disse; None quando ela nao trouxe o campo.

    Existe para nao transformar ausencia em negacao. `bool(None)` daria False,
    que e uma AFIRMACAO — e afirmar sem base e o que faz um relatorio mentir.

    Tem um gemeo em `repos/_comum.booleano`, e a repeticao e de proposito:
    `coletor.py` nao importa da camada de repositorio. Tres linhas duplicadas
    custam menos que um modulo de coleta acoplado ao banco.
    """
    if valor is None:
        return None
    return bool(valor)


def normalizar_perfil(bruto, nicho=None):
    """Item cru do Actor -> o dicionario que `banco.salvar_perfil` aceita."""
    usuario = _primeiro(bruto, "username", "ownerUsername", "userName")
    if not usuario:
        return None

    return {
        "usuario": usuario,
        "nome": _primeiro(bruto, "fullName", "full_name", "name"),
        "bio": _primeiro(bruto, "biography", "bio"),
        "seguidores": _contagem(_primeiro(bruto, "followersCount", "followers",
                                          padrao=0)),
        "seguindo": _contagem(_primeiro(bruto, "followsCount", "followingCount",
                                        "follows")),
        "posts": _contagem(_primeiro(bruto, "postsCount", "mediaCount", "posts")),
        "privado": bool(_primeiro(bruto, "private", "isPrivate", padrao=False)),
        "verificado": bool(_primeiro(bruto, "verified", "isVerified", padrao=False)),
        "link_externo": _primeiro_link(bruto),
        "perfil_id": str(_primeiro(bruto, "id", "ownerId", "pk", padrao="")) or None,
        "link_perfil": _primeiro(bruto, "url", "profileUrl")
                       or "https://www.instagram.com/%s/" % usuario,
        "nicho": nicho,
        "avatar_url": _primeiro(bruto, "profilePicUrl", "profilePicUrlHD"),
        "categoria_negocio": _primeiro(bruto, "businessCategoryName", "category"),
        "lido_em": datetime.now().isoformat(timespec="seconds"),
    }


def normalizar_post(bruto, usuario_padrao=None):
    """Item cru do Actor -> o mesmo `post.json` que a analise ja le.

    O formato nao e escolha nova: e exatamente o que `analisar.py`,
    `metricas.py` e `transcrever.py` ja consomem. Mudar aqui quebraria a
    etapa que ja esta pronta e testada.
    """
    post_id = _primeiro(bruto, "shortCode", "shortcode", "code", "id")
    if not post_id:
        return None

    tipo_bruto = str(_primeiro(bruto, "type", "mediaType", padrao="")).lower()
    produto = str(_primeiro(bruto, "productType", padrao="")).lower()

    e_video = bool(_primeiro(bruto, "isVideo", padrao=False)) \
        or tipo_bruto == "video" or produto in ("clips", "igtv")

    if produto == "clips":
        tipo = "reel"
    elif tipo_bruto in ("sidecar", "carousel"):
        tipo = "carrossel"
    elif e_video:
        tipo = "video"
    else:
        tipo = "foto"

    utc, local, dia, hora = _data_em_partes(
        _primeiro(bruto, "timestamp", "takenAt", "taken_at"))

    usuario = _primeiro(bruto, "ownerUsername", "username") or usuario_padrao

    return {
        "id": post_id,
        "perfil": usuario,
        "link": _primeiro(bruto, "url", "postUrl")
                or "https://www.instagram.com/p/%s/" % post_id,
        "tipo": tipo,
        "typename": _primeiro(bruto, "type", "__typename"),
        "e_video": e_video,

        # `[MEDIDO 30/08/2026]` O post fixado ESCAPA do `onlyPostsNewerThan`:
        # pedindo 30 dias vieram 2 posts de fora da janela, e eram exatamente
        # os 2 com `isPinned`. Sem este campo, um post de 2024 com 6,9M de
        # views entra numa media de "ultimos 30 dias" e a arruina.
        # None e nao False quando a fonte nao diz: nao saber e diferente de
        # saber que nao.
        "fixado": _booleano_ou_none(_primeiro(bruto, "isPinned", "is_pinned")),
        "duracao_segundos": _primeiro(bruto, "videoDuration", "duration"),
        "visualizacoes": _contagem(_primeiro(bruto, "videoPlayCount",
                                             "videoViewCount", "playCount",
                                             "viewCount")),
        "legenda": _primeiro(bruto, "caption", "text", padrao="") or "",
        "hashtags": list(_primeiro(bruto, "hashtags", padrao=[]) or []),
        "mencoes": list(_primeiro(bruto, "mentions", padrao=[]) or []),
        "curtidas": _contagem(_primeiro(bruto, "likesCount", "likes")),
        "comentarios": _contagem(_primeiro(bruto, "commentsCount", "comments")),
        "data_utc": utc,
        "data_local": local,
        "dia_da_semana": dia,
        "hora": hora,
        # URL do CDN. VENCE — guardada por conveniencia, nunca como fonte
        # primaria do download. Quem baixa e o yt-dlp, pelo `link`.
        "video_url": _primeiro(bruto, "videoUrl", "video_url"),
        "thumbnail_url": _primeiro(bruto, "displayUrl", "thumbnailUrl"),

        # O audio e sinal forte de tendencia: um som que aparece em varios
        # perfis do mesmo nicho na mesma semana costuma anteceder o pico.
        "audio_id": str(_caminho(bruto, "musicInfo", "audio_id")
                        or _primeiro(bruto, "musicId", padrao="") or "") or None,
        "audio_titulo": _caminho(bruto, "musicInfo", "song_name")
                        or _caminho(bruto, "musicInfo", "title"),
        "audio_autor": _caminho(bruto, "musicInfo", "artist_name"),
        "audio_original": _caminho(bruto, "musicInfo", "uses_original_audio"),

        "local_nome": _primeiro(bruto, "locationName"),
        "local_id": _primeiro(bruto, "locationId"),

        # O Instagram NAO publica compartilhamento nem salvamento — so o dono
        # da conta ve, no Insights. Ficam None ate que o Actor prove o
        # contrario. None e honesto; zero seria afirmar que ninguem salvou.
        "compartilhamentos": _contagem(_primeiro(bruto, "sharesCount",
                                                "reshareCount")),
        "salvamentos": _contagem(_primeiro(bruto, "savesCount", "savedCount")),

        "baixado_em": datetime.now().isoformat(timespec="seconds"),
    }


def _aninhados(bruto):
    """Os posts que vem dentro do item de perfil."""
    saida = []
    for chave in ("latestPosts", "latestIgtvVideos", "posts", "topPosts"):
        valor = bruto.get(chave)
        if isinstance(valor, list):
            saida.extend(item for item in valor if isinstance(item, dict))
    return saida


def perfis_relacionados(bruto):
    """`relatedProfiles`: quem o Instagram considera parecido.

    Fonte de descoberta melhor que a busca por termo, porque parte de um
    perfil que ja se sabe relevante em vez de uma palavra no nome. Nao entra
    no fluxo automaticamente — quem decide ampliar a lista e o usuario.
    """
    lista = bruto.get("relatedProfiles")
    if not isinstance(lista, list):
        return []
    return [item.get("username") for item in lista
            if isinstance(item, dict) and item.get("username")]


# ------------------------------------------------ Criterios, em funcao pura
#
# Tudo aqui decide SEM rede: da para testar de graca, e o teste nao depende de
# a Apify estar de pe nem de gastar dolar.


def tag_do_termo(nicho):
    """"Receitas de Bolo" -> "receitasdebolo". "Receitas Faceis" com acento
    continua com acento.

    Hashtag do Instagram nao tem espaco nem pontuacao, mas **tem acento**:
    `#receitasfaceis` e `#receitasfáceis` sao DUAS tags diferentes, com feeds
    diferentes. A primeira versao disto derrubava o acento com NFKD, e nesse
    caso o mapeamento pediria uma tag e receberia outra.

    `[MEDIDO 30/08/2026]` `receitasfáceis` veio acentuada nas hashtags reais de
    @receitasdepai. Nao e hipotese.

    Sublinhado sobrevive porque o Instagram aceita (`#comida_boa`). O resto da
    pontuacao cai.

    A funcao e IDEMPOTENTE de proposito: passar uma tag ja valida por aqui nao
    a estraga. E o que permite usar a mesma funcao para derivar tag de um tema
    escrito em portugues comum e para conferir uma tag que veio do mapeamento.
    """
    import unicodedata

    # NFC e nao NFKD: compoe o acento num caractere so, que e como o Instagram
    # escreve. NFKD decompoe em letra + acento solto, e ai `isalnum()` deixaria
    # a letra e jogaria o acento fora — exatamente o bug que isto conserta.
    texto = unicodedata.normalize("NFC", str(nicho or "")).lower()
    return "".join(c for c in texto if c.isalnum() or c == "_")


def url_da_tag(nicho):
    """A URL da aba da hashtag.

    `[MEDIDO 30/08/2026]` E por AQUI que a descoberta por hashtag funciona.
    `searchType: "hashtag"` foi tentado duas vezes e devolveu
    `no_items — Empty or private data` nas duas.
    """
    from urllib.parse import quote

    # `quote` porque a tag pode ter acento, e acento cru no caminho da URL e
    # aposta na boa vontade de quem le do outro lado.
    return "https://www.instagram.com/explore/tags/%s/" % quote(tag_do_termo(nicho))


def na_banda(perfil, minimo=None, maximo=None, somente_publicos=True):
    """O perfil cabe nos criterios? True, False, ou **None para "nao da para
    saber"**.

    O terceiro estado nao e frescura: o item que vem da hashtag NAO traz
    contagem de seguidores — conferido, nem com `addParentData`. Devolver
    False ali seria reprovar por falta de informacao, e o candidato mais
    interessante do nicho morreria caladinho. Devolver None manda ele para a
    qualificacao, que custa uma chamada e responde de verdade.
    """
    if somente_publicos and perfil.get("privado") is True:
        return False

    seguidores = perfil.get("seguidores")
    if seguidores is None:
        return None

    if minimo is not None and seguidores < minimo:
        return False
    if maximo is not None and seguidores > maximo:
        return False
    return True


def observacoes_dos_itens(itens, fonte=None):
    """Itens crus -> a lista de observacoes que eles produziram.

    **Este e o unico lugar que sabe onde os campos moram dentro do item do
    Actor.** O `lexico.py` recebe texto, hashtags e mencoes ja extraidos e nao
    conhece schema nenhum — mesma divisao que existe entre `idioma.py`, que le
    texto, e quem vai buscar o texto.

    `[MEDIDO 30/08/2026]` Ate a T15 daqui saia so o campo `hashtags`, e a
    legenda era lida uma vez para votar idioma e jogada fora. Giria, emoji,
    abreviacao, bigrama e mencao — tudo que distingue uma tribo da outra —
    estavam naquele texto descartado. A legenda ja foi paga: le-la de novo
    custa CPU, nao centavo.
    """
    achadas = []

    def _colher(bruto, dono):
        texto = _primeiro(bruto, "caption", "text", padrao="")
        # Uma deteccao por post, reaproveitada por todos os termos dele: a
        # legenda e a mesma, e detectar dez vezes o mesmo texto seria so gastar
        # CPU para chegar na mesma resposta.
        voto = idioma.detectar(texto)
        achadas.extend(lexico.observacoes(
            texto=texto,
            hashtags=bruto.get("hashtags"),
            mencoes=bruto.get("mentions"),
            perfil=dono,
            post=_primeiro(bruto, "id", "shortCode", "shortcode"),
            fonte=fonte,
            voto="?" if voto is None else voto,
        ))

    for bruto in itens or []:
        if not isinstance(bruto, dict) or bruto.get("error"):
            continue
        dono = _primeiro(bruto, "ownerUsername", "username")
        _colher(bruto, dono)
        # Item de perfil (`resultsType: details`) traz os posts recentes
        # aninhados, e as hashtags deles junto. Sem desaninhar aqui, mapear por
        # perfil relacionado nao renderia vocabulario nenhum.
        for aninhado in _aninhados(bruto):
            _colher(aninhado, _primeiro(aninhado, "ownerUsername") or dono)

    return achadas


def tags_dos_itens(itens, fonte=None):
    """Itens crus -> o vocabulario de HASHTAG que eles carregam.

    Devolve `{tag: {"posts": n, "perfis": [usuarios], "idiomas": {...},
    "fonte": ...}}`.

    Os votos de idioma vem da LEGENDA do post em que a tag apareceu, e nao da
    tag em si: `#seguridad` e espanhola pelo texto ao redor, nao por si mesma
    — `#nepal` e `#brasil` nao teriam idioma nenhum se olhassemos so a palavra.

    **O numero que importa e `perfis`, nao `posts`.** Medido em 30/08/2026:
    colhendo as hashtags de @receitasdepai vieram `publi`, `MercadoLivre`,
    `PagBank` e `AeC440` — vocabulario de PUBLICIDADE, nao de receita. Tag de
    patrocinio aparece MUITO, mas num perfil so; tag do nicho aparece em varios
    perfis. Contar posts elegeria a propaganda.

    Continua existindo com o mesmo nome e a mesma forma depois da T16 porque
    meia duzia de chamadores so querem hashtag. Quem quer a legenda inteira
    chama `observacoes_dos_itens()` e filtra por `kind`.
    """
    return lexico.contar(observacoes_dos_itens(itens, fonte=fonte),
                         kinds=("hashtag",))


def donos_dos_posts(itens):
    """Itens da aba da tag -> candidatos, sem repetir.

    E o que a hashtag entrega de util: uma lista de NOMES. Seguidores, bio e
    o resto vem depois, e so para quem sobreviver ao teto.
    """
    vistos, candidatos = set(), []
    for bruto in itens or []:
        if not isinstance(bruto, dict) or bruto.get("error"):
            continue
        usuario = _primeiro(bruto, "ownerUsername", "username")
        if not usuario or usuario in vistos:
            continue
        vistos.add(usuario)
        candidatos.append({
            "usuario": usuario,
            "nome": _primeiro(bruto, "ownerFullName", "fullName"),
            "perfil_id": str(_primeiro(bruto, "ownerId", padrao="")) or None,
        })
    return candidatos


class Coleta:
    """O que uma rodada devolveu, junto com o que ela custou."""

    def __init__(self, perfis=None, posts=None, itens=0, custo_usd=None,
                 run_id=None, duracao_ms=0, brutos=None):
        self.perfis = perfis or []
        self.posts = posts or []
        self.itens = itens
        self.custo_usd = custo_usd
        self.run_id = run_id
        self.duracao_ms = duracao_ms
        self.brutos = brutos or []

    @property
    def videos(self):
        return [post for post in self.posts if post.get("e_video")]

    def __repr__(self):
        return "<Coleta %d perfis, %d posts (%d video), %d itens, US$ %s>" % (
            len(self.perfis), len(self.posts), len(self.videos), self.itens,
            "?" if self.custo_usd is None else "%.4f" % self.custo_usd)


class InstagramCollector:
    """O contrato. O pipeline nao sabe qual coletor esta rodando."""

    nome = "abstrato"

    def descobrir_perfis(self, nicho, max_perfis, eixo="nome"):
        raise NotImplementedError

    def qualificar(self, usuarios):
        raise NotImplementedError

    def coletar_conteudo(self, usuarios, max_posts, janela_dias=None,
                         tipo="posts"):
        raise NotImplementedError


class ApifyInstagramCollector(InstagramCollector):
    """Roda um Actor da Apify pela API oficial.

    Pela **API** e nao pelo MCP de proposito: o MCP so funciona com um
    assistente aberto na frente. Um pipeline precisa rodar sozinho.
    """

    def __init__(self, token, actor=ACTOR_PADRAO, plano=PLANO_PADRAO,
                 teto_usd=None, guardar_brutos=False):
        if not token:
            raise ErroDeColeta(
                "Falta o token da Apify.\n"
                "Pegue em console.apify.com/account/integrations e coloque em "
                "config.local.json, em apify.token. O arquivo ja esta no "
                ".gitignore — nunca mande o token por mensagem.")
        self._token = token
        self.actor = actor
        self.plano = plano
        self.teto_usd = teto_usd
        self.guardar_brutos = guardar_brutos
        self.nome = "apify:%s" % actor

    def _cliente(self):
        from apify_client import ApifyClient
        return ApifyClient(self._token)

    def _rodar(self, entrada, max_itens):
        """Chama o Actor e devolve (itens crus, run). Nunca sem teto."""
        from apify_client.errors import ApifyApiError

        cliente = self._cliente()
        comeco = time.monotonic()

        try:
            run = cliente.actor(self.actor).call(
                run_input=entrada,
                max_items=max_itens,
                # Teto de gasto do lado da Apify. Se o Actor tentar passar
                # disso, ele para — e nao a fatura.
                max_total_charge_usd=self.teto_usd,
            )
        except ApifyApiError as erro:
            raise ErroDeColeta("A Apify recusou a chamada: %s" % erro) from erro

        if run is None:
            raise ErroDeColeta("O Actor nao devolveu execucao (run vazio).")

        if run.status != "SUCCEEDED":
            raise ErroDeColeta(
                "O Actor terminou em %s. Mensagem: %s"
                % (run.status, run.status_message or "(sem mensagem)"))

        itens = list(cliente.dataset(run.default_dataset_id).iterate_items())
        return itens, run, int((time.monotonic() - comeco) * 1000)

    def _montar(self, itens, run, duracao_ms, nicho=None, usuario_padrao=None):
        perfis, posts = [], []

        for bruto in itens:
            if not isinstance(bruto, dict):
                continue

            # Um item e perfil quando traz contagem de seguidores; e post
            # quando traz codigo de post. Alguns itens trazem os dois — o
            # Actor devolve o dono junto do post — e ai valem como os dois.
            if _primeiro(bruto, "followersCount", "followers") is not None:
                perfil = normalizar_perfil(bruto, nicho)
                if perfil:
                    perfis.append(perfil)

            if _primeiro(bruto, "shortCode", "shortcode", "code"):
                post = normalizar_post(bruto, usuario_padrao)
                if post and post.get("perfil"):
                    posts.append(post)

            # `[VERIFICADO 28/08/2026]` Com `resultsType: details`, os posts
            # NAO vem como itens soltos: vem aninhados no perfil, em
            # `latestPosts`. Sem desaninhar aqui, a coleta traria zero posts
            # e ninguem entenderia por que.
            dono = _primeiro(bruto, "username", "ownerUsername")
            for aninhado in _aninhados(bruto):
                post = normalizar_post(aninhado, dono or usuario_padrao)
                if post and post.get("perfil"):
                    posts.append(post)

        custo = run.usage_total_usd
        if custo is None:
            custo = custo_estimado(len(itens), self.plano)

        return Coleta(perfis=perfis, posts=posts, itens=len(itens),
                      custo_usd=custo, run_id=run.id, duracao_ms=duracao_ms,
                      brutos=itens if self.guardar_brutos else [])

    def descobrir_perfis(self, nicho, max_perfis=40, eixo="nome"):
        """Termo -> perfis candidatos, por um dos dois eixos.

        Sem promessa de relevancia em nenhum dos dois: quem julga e o usuario,
        e a filtragem e etapa a parte.
        """
        if eixo == "hashtag":
            return self._descobrir_por_hashtag(nicho, max_perfis)
        if eixo != "nome":
            raise ErroDeColeta(
                "Eixo de descoberta %r nao existe. Ha `nome` e `hashtag`."
                % (eixo,))

        entrada = {
            "search": nicho,
            "searchType": "user",
            "searchLimit": max_perfis,
            "resultsType": "details",
            # `[VERIFICADO 28/08/2026]` O Actor recusa `resultsLimit: 0` com
            # "Field input.resultsLimit must be >= 1". Não dá para pedir
            # "só o perfil, nenhum post" — o mínimo é 1 post por perfil.
            "resultsLimit": 1,
        }
        itens, run, duracao = self._rodar(entrada, max_perfis)
        return self._montar(itens, run, duracao, nicho=nicho)

    def _descobrir_por_hashtag(self, nicho, max_perfis):
        """Quem PUBLICA no assunto, e nao quem tem a palavra no nome.

        `[MEDIDO 30/08/2026]` Este eixo existe porque o outro enviesa: dos 9
        perfis que a busca por nome achou, 7 tinham "receitas" no username. Uma
        sonda na aba da tag devolveu `mf.meatfreaks` e `leonardoriverob` — dois
        que a busca por nome nunca acharia.

        Duas coisas a saber antes de confiar no resultado:

          1. A aba da tag ordena por RECENCIA, nao por desempenho. Vem post de
             conta minuscula junto, e isso e esperado.
          2. O item NAO traz contagem de seguidores. Por isso o retorno aqui e
             candidato, nao perfil pronto: quem preenche e `qualificar()`.
        """
        entrada = {
            "directUrls": [url_da_tag(nicho)],
            "resultsType": "posts",
            "resultsLimit": max_perfis,
            "addParentData": True,
        }
        itens, run, duracao = self._rodar(entrada, max_perfis)

        coleta = self._montar(itens, run, duracao, nicho=nicho)
        conhecidos = {p.get("usuario") for p in coleta.perfis}
        for candidato in donos_dos_posts(itens):
            if candidato["usuario"] in conhecidos:
                continue
            coleta.perfis.append({
                "usuario": candidato["usuario"],
                "nome": candidato["nome"],
                "perfil_id": candidato["perfil_id"],
                "nicho": nicho,
                "link_perfil": "https://www.instagram.com/%s/"
                               % candidato["usuario"],
                "lido_em": datetime.now().isoformat(timespec="seconds"),
            })
        return coleta

    def mapear_tag(self, tag, limite=30):
        """Uma rodada de tag feita para MAPEAR: os itens crus vem junto.

        Diferente de `descobrir_perfis(eixo="hashtag")`, que so quer os donos.
        Aqui os itens sao o produto: e deles que sai o vocabulario, pelo campo
        `hashtags` que ja vem pago dentro de cada um.
        """
        entrada = {
            "directUrls": [url_da_tag(tag)],
            "resultsType": "posts",
            "resultsLimit": limite,
            "addParentData": True,
        }
        itens, run, duracao = self._rodar(entrada, limite)
        coleta = self._montar(itens, run, duracao)
        for candidato in donos_dos_posts(itens):
            coleta.perfis.append({
                "usuario": candidato["usuario"],
                "nome": candidato["nome"],
                "perfil_id": candidato["perfil_id"],
                "link_perfil": "https://www.instagram.com/%s/"
                               % candidato["usuario"],
                "lido_em": datetime.now().isoformat(timespec="seconds"),
            })
        # O mapeamento precisa dos itens crus mesmo quando o coletor nao foi
        # montado para guarda-los: sem eles nao ha hashtag para colher.
        coleta.brutos = itens
        return coleta

    def relacionados_de(self, usuarios):
        """Perfil -> quem o Instagram considera parecido.

        `[MEDIDO 30/08/2026]` @receitasdepai devolveu **15 relacionados**. A
        unica evidencia anterior era uma lista vazia, mas vinha de uma conta
        com 12 seguidores e 0 posts — conta vazia nao tem parecido.

        Parte de um perfil que ja se sabe relevante, e nao de uma palavra num
        nome: e o eixo que acha `@gordicesdateka` sem que ninguem soubesse que
        ele existia.

        Devolve `(relacoes, coleta)` em vez de so a Coleta porque as duas
        coisas interessam e sao diferentes: o mapa de quem puxa quem, e os
        perfis-semente ja com os detalhes que a chamada trouxe.

        **O relacionado vem SEM contagem de seguidores** — conferido: so
        username, full_name, is_private, is_verified e id. Quem responde se ele
        cabe na banda e `qualificar()`, exatamente como no eixo da hashtag.
        """
        usuarios = [u for u in (usuarios or []) if u]
        if not usuarios:
            return {}, Coleta()

        entrada = {
            "directUrls": ["https://www.instagram.com/%s/" % u
                           for u in usuarios],
            "resultsType": "details",
            "resultsLimit": 1,
        }
        itens, run, duracao = self._rodar(entrada, len(usuarios) * 2)
        coleta = self._montar(itens, run, duracao)
        coleta.brutos = itens

        relacoes = {}
        for bruto in itens:
            if not isinstance(bruto, dict) or bruto.get("error"):
                continue
            dono = _primeiro(bruto, "username", "ownerUsername")
            if dono:
                relacoes[dono] = perfis_relacionados(bruto)
        return relacoes, coleta

    def qualificar(self, usuarios):
        """Nomes -> perfis com seguidores, bio e privacidade.

        A segunda chamada que a hashtag obriga. Quem chama poe o teto: sem
        teto, uma tag movimentada vira fatura.
        """
        usuarios = [u for u in (usuarios or []) if u]
        if not usuarios:
            return Coleta()

        entrada = {
            "directUrls": ["https://www.instagram.com/%s/" % u
                           for u in usuarios],
            "resultsType": "details",
            "resultsLimit": 1,
        }
        itens, run, duracao = self._rodar(entrada, len(usuarios) * 2)
        coleta = self._montar(itens, run, duracao)
        # Os itens crus vem junto, como em `mapear_tag` e `relacionados_de`.
        # O `details` traz `latestPosts` aninhados e datados — sao os mesmos
        # posts que ja alimentam o ritmo, e a legenda deles ja foi paga. Sem
        # esta linha, o lexico da medicao seria jogado fora.
        coleta.brutos = itens
        return coleta

    def coletar_conteudo(self, usuarios, max_posts=10, janela_dias=None,
                         tipo="posts"):
        """Perfis -> posts, com metadado. Nao baixa midia.

        `tipo="reels"` pede so video ao Actor. Numa sonda de 30/08/2026 os 4
        itens vieram `Video`/`clips` — deixa de pagar por foto e carrossel que
        seriam descartados na hora do download.
        """
        if isinstance(usuarios, str):
            usuarios = [usuarios]
        usuarios = list(usuarios)
        if not usuarios:
            return Coleta()

        entrada = {
            "directUrls": ["https://www.instagram.com/%s/" % u for u in usuarios],
            "resultsType": "reels" if tipo == "reels" else "posts",
            "resultsLimit": max_posts,
            "addParentData": True,
        }

        # O UNICO filtro que a Apify aceita na entrada, e por isso o unico que
        # economiza dinheiro em vez de so economizar disco. Os outros sete
        # campos de entrada do Actor sao quantidade e destino, nao criterio.
        #
        # `[MEDIDO 30/08/2026]` Ele nao e garantia: post fixado passa por cima.
        # Quem separa o fixado depois e o campo `fixado` do post.
        if janela_dias:
            entrada["onlyPostsNewerThan"] = "%d days" % int(janela_dias)
        teto = max_posts * len(usuarios) + len(usuarios)
        itens, run, duracao = self._rodar(entrada, teto)
        return self._montar(itens, run, duracao,
                            usuario_padrao=usuarios[0] if len(usuarios) == 1 else None)
