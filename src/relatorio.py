"""T6 - Relatorio.

Le as analises e monta uma pagina HTML unica, que abre com duplo clique.
Sem servidor, sem internet, sem biblioteca: o CSS vai embutido no arquivo.

Uso:
    python src/relatorio.py
    python src/relatorio.py --saida saida/apostas.html
"""

import argparse
import json
import sys
from datetime import datetime
from html import escape

import console
import config

CSS = "relatorio.css"
QUANTOS_POSTS_NA_TABELA = 12
QUANTAS_HASHTAGS = 12


def _ler_json(caminho):
    with caminho.open(encoding="utf-8") as aberto:
        return json.load(aberto)


def carregar_analises():
    if not config.ANALISES.is_dir():
        return [], None

    analises = []
    comparativo = None
    for arquivo in sorted(config.ANALISES.glob("*.json")):
        if arquivo.name == "_comparativo.json":
            comparativo = _ler_json(arquivo)
        else:
            analises.append(_ler_json(arquivo))

    return analises, comparativo


def _numero(valor, sufixo="", vazio="--"):
    if valor is None:
        return vazio
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    if isinstance(valor, int):
        return "{:,}".format(valor).replace(",", ".") + sufixo
    return "%s%s" % (valor, sufixo)


def bloco_numero(valor, rotulo, destaque=False):
    classe = "numero destaque" if destaque else "numero"
    return ('<div class="%s"><span class="valor">%s</span>'
            '<span class="rotulo">%s</span></div>'
            % (classe, escape(str(valor)), escape(rotulo)))


def bloco_etiquetas(contagem, quantas, classe="etiqueta"):
    if not contagem:
        return '<p class="vazio">nada registrado</p>'

    itens = []
    for chave, quantidade in list(contagem.items())[:quantas]:
        itens.append('<li class="%s">%s <span class="contagem">%d</span></li>'
                     % (classe, escape(str(chave)), quantidade))
    return '<ul class="etiquetas">%s</ul>' % "".join(itens)


def bloco_gancho(post):
    falado = post["gancho"]["falado"]
    escrito = post["gancho"]["escrito"]
    if not falado and not escrito:
        return '<p class="vazio">sem gancho identificado</p>'

    partes = ['<div class="gancho">']
    if falado:
        partes.append('<p class="falado">%s</p>' % escape(falado))
    if escrito:
        partes.append('<p class="escrito">Na legenda: %s</p>' % escape(escrito))
    partes.append("</div>")
    return "".join(partes)


def bloco_linha_do_tempo(post, titulo="Como o video se organiza no tempo"):
    blocos = post.get("estrutura_no_tempo") or []
    if not blocos:
        return ""

    itens = []
    for bloco in blocos:
        itens.append('<li><span class="segundo">%.1fs</span><span>%s</span></li>'
                     % (bloco["segundo"], escape(bloco["texto"])))
    return '<h4>%s</h4><ul class="tempo">%s</ul>' % (escape(titulo), "".join(itens))


def melhor_post_com_tempo(posts):
    """O video mais engajado que tem transcricao.

    O post campeao do perfil pode ser um carrossel, que nao tem fala nenhuma.
    Se a linha do tempo dependesse so dele, a estrutura do video - que e uma das
    coisas que este relatorio existe para mostrar - sumiria da pagina.
    """
    com_tempo = [p for p in posts if p.get("estrutura_no_tempo")]
    if not com_tempo:
        return None
    return max(com_tempo, key=lambda p: p["engajamento"]["taxa_percentual"] or 0)


def _chamadas_em_texto(chamadas):
    if not chamadas:
        return '<span class="vazio">nenhuma</span>'
    return " ".join('<span class="etiqueta laranja">%s</span>' % escape(tipo)
                    for tipo in chamadas)


def tabela_de_posts(posts):
    if not posts:
        return '<p class="vazio">nenhum post analisado</p>'

    ordenados = sorted(
        posts,
        key=lambda p: p["engajamento"]["taxa_percentual"] or 0,
        reverse=True)[:QUANTOS_POSTS_NA_TABELA]

    linhas = []
    for post in ordenados:
        gancho = post["gancho"]["falado"] or post["gancho"]["escrito"] or ""
        linhas.append(
            "<tr>"
            '<td><a href="%s" target="_blank" rel="noreferrer">%s</a></td>'
            '<td>%s</td>'
            '<td class="numerico">%s</td>'
            '<td class="numerico">%s</td>'
            '<td class="numerico">%s</td>'
            '<td class="numerico">%s</td>'
            '<td class="numerico">%s</td>'
            '<td>%s</td>'
            '<td>%s</td>'
            "</tr>" % (
                escape(post["link"]), escape(post["id"]),
                escape(post["tipo"]),
                _numero(post.get("duracao_segundos"), "s"),
                _numero(post["engajamento"]["curtidas"]),
                _numero(post["engajamento"]["comentarios"]),
                _numero(post["engajamento"]["taxa_percentual"], "%"),
                _numero(post["hashtags"]["quantas"]),
                _chamadas_em_texto(post["chamadas_para_acao"]),
                escape(gancho[:90]),
            ))

    return (
        '<div class="rolagem"><table>'
        "<thead><tr>"
        "<th>Post</th><th>Formato</th><th>Duracao</th><th>Curtidas</th>"
        "<th>Comentarios</th><th>Engajamento</th><th>Hashtags</th>"
        "<th>Chamada</th><th>Gancho</th>"
        "</tr></thead><tbody>%s</tbody></table></div>" % "".join(linhas))


def secao_perfil(analise):
    perfil = analise["perfil"]
    resumo = analise["resumo"]

    numeros = "".join([
        bloco_numero(_numero(resumo.get("media_taxa_engajamento"), "%"),
                     "engajamento medio", destaque=True),
        bloco_numero(_numero(resumo.get("media_curtidas")), "curtidas por post"),
        bloco_numero(_numero(resumo.get("media_comentarios")), "comentarios por post"),
        bloco_numero(_numero(resumo.get("media_duracao_segundos"), "s"),
                     "duracao media"),
        bloco_numero(_numero(resumo.get("media_ritmo_palavras_por_minuto")),
                     "palavras por minuto"),
        bloco_numero(_numero(resumo.get("media_hashtags")), "hashtags por post"),
        bloco_numero(_numero(resumo.get("media_caracteres_legenda")),
                     "letras na legenda"),
        bloco_numero(_numero(resumo.get("posts_com_chamada_percentual"), "%"),
                     "posts com chamada"),
    ])

    melhores = resumo.get("melhores_posts") or []
    campeao_no_html = None
    destaque = ""
    if melhores:
        campeao = melhores[0]
        campeao_no_html = next(
            (p for p in analise["posts"] if p["id"] == campeao["id"]), None)
        if campeao_no_html:
            destaque = ("<h4>O post que mais engajou (%s%%)</h4>%s"
                        % (campeao["taxa"], bloco_gancho(campeao_no_html)))

    com_tempo = melhor_post_com_tempo(analise["posts"])
    if com_tempo:
        mesmo_post = campeao_no_html and com_tempo["id"] == campeao_no_html["id"]
        titulo = ("Como esse video se organiza no tempo" if mesmo_post
                  else "O video mais engajado, segundo a segundo (%s%%)"
                       % com_tempo["engajamento"]["taxa_percentual"])
        destaque += bloco_linha_do_tempo(com_tempo, titulo)

    return (
        '<div class="cartao">'
        '<div class="cartao-topo">'
        "<h3>@%s</h3>"
        '<span class="seguidores">%s seguidores &middot; %s posts analisados</span>'
        "</div>"
        '<div class="numeros">%s</div>'
        "%s"
        "<h4>Hashtags que mais usa</h4>%s"
        "<h4>Quando publica</h4>%s"
        "<h4>Todos os posts, do que mais engajou para o que menos</h4>%s"
        "</div>" % (
            escape(perfil["usuario"]),
            _numero(perfil.get("seguidores")),
            _numero(resumo.get("posts_analisados")),
            numeros,
            destaque,
            bloco_etiquetas(resumo.get("hashtags_mais_usadas"), QUANTAS_HASHTAGS,
                            "etiqueta roxa"),
            bloco_etiquetas(resumo.get("horarios_que_publica"), 8, "etiqueta verde"),
            tabela_de_posts(analise["posts"]),
        ))


def secao_comparativo(comparativo):
    if not comparativo:
        return ""

    ranking = comparativo.get("ranking_por_engajamento") or []
    linhas = []
    for posicao, item in enumerate(ranking, start=1):
        linhas.append(
            "<tr>"
            '<td><span class="posicao">%d</span></td>'
            "<td>@%s</td>"
            '<td class="numerico">%s</td>'
            '<td class="numerico">%s</td>'
            '<td class="numerico">%s</td>'
            "</tr>" % (
                posicao,
                escape(item["usuario"]),
                _numero(item.get("seguidores")),
                _numero(item.get("media_taxa_engajamento"), "%"),
                _numero(item.get("posts_analisados")),
            ))

    comuns = comparativo.get("hashtags_em_comum") or {}
    itens_comuns = "".join(
        '<li class="etiqueta roxa">%s <span class="contagem">%d perfis</span></li>'
        % (escape(tag), len(perfis))
        for tag, perfis in list(comuns.items())[:QUANTAS_HASHTAGS])

    bloco_comuns = ('<ul class="etiquetas">%s</ul>' % itens_comuns
                    if itens_comuns else '<p class="vazio">nenhuma em comum</p>')

    return (
        "<section>"
        "<h2>Comparativo</h2>"
        '<div class="cartao">'
        '<div class="rolagem"><table><thead><tr>'
        "<th></th><th>Perfil</th><th>Seguidores</th>"
        "<th>Engajamento medio</th><th>Posts</th>"
        "</tr></thead><tbody>%s</tbody></table></div>"
        "<h4>Hashtags que mais de um perfil usa</h4>%s"
        "</div></section>" % ("".join(linhas), bloco_comuns))


def montar_html(analises, comparativo, termo, css):
    perfis = "".join(secao_perfil(analise) for analise in analises)
    agora = datetime.now().strftime("%d/%m/%Y as %H:%M")
    titulo = "Analise de Instagram" + (" - %s" % termo if termo else "")

    return (
        "<!doctype html>\n"
        '<html lang="pt-BR">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>%s</title>\n"
        "<style>\n%s\n</style>\n"
        "</head>\n<body>\n"
        '<div class="pagina">\n'
        '<header class="topo">'
        "<h1>Como os posts sao construidos%s</h1>"
        "<p>%d perfis analisados &middot; gerado em %s</p>"
        "</header>\n"
        "%s"
        "<section><h2>Perfil por perfil</h2>%s</section>\n"
        '<footer class="rodape">Gerado por analise-instagram. '
        "Dados publicos, coletados para pesquisa propria.</footer>\n"
        "</div>\n</body>\n</html>\n" % (
            escape(titulo),
            css,
            (' <span class="termo">&mdash; %s</span>' % escape(termo)) if termo else "",
            len(analises),
            agora,
            secao_comparativo(comparativo),
            perfis,
        ))


def main():
    console.preparar()
    parser = argparse.ArgumentParser(description="Monta o relatorio HTML.")
    parser.add_argument("--termo", help="So para aparecer no titulo.")
    parser.add_argument("--saida", help="Caminho do HTML. Padrao: saida/relatorio.html")
    args = parser.parse_args()

    analises, comparativo = carregar_analises()
    if not analises:
        print("Nenhuma analise encontrada.", file=sys.stderr)
        print("Rode antes:  python src/analisar.py", file=sys.stderr)
        return 1

    css = (config.RAIZ / "src" / CSS).read_text(encoding="utf-8")
    html = montar_html(analises, comparativo, args.termo, css)

    config.garantir_pastas()
    destino = (config.RAIZ / args.saida) if args.saida else (config.SAIDA / "relatorio.html")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(html, encoding="utf-8")

    print("Relatorio gerado: %s" % destino)
    print("Abra com duplo clique - nao precisa de servidor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
