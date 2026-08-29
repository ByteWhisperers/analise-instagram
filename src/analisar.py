"""T5 - Analise.

Le o que foi baixado e transcrito e transforma em numeros comparaveis:
gancho, ritmo, estrutura no tempo, legenda, hashtags, chamada para acao,
engajamento, horario e formato.

Aqui so entra numero calculado. A leitura qualitativa - "o que os melhores
fazem diferente" - e escrita depois, olhando estes numeros.

Uso:
    python src/analisar.py
    python src/analisar.py --perfil algumperfil
"""

import argparse
import json
import sys
from datetime import datetime

import console
import banco
import config
import metricas

DIAS_EM_PORTUGUES = {
    "Monday": "segunda", "Tuesday": "terca", "Wednesday": "quarta",
    "Thursday": "quinta", "Friday": "sexta", "Saturday": "sabado",
    "Sunday": "domingo",
}


def _ler_json(caminho):
    with caminho.open(encoding="utf-8") as aberto:
        return json.load(aberto)


def listar_perfis_coletados(filtro=None):
    if not config.PERFIS.is_dir():
        return []
    pastas = [p for p in sorted(config.PERFIS.iterdir())
              if p.is_dir() and (p / "perfil.json").exists()]
    if filtro:
        pastas = [p for p in pastas if p.name == filtro]
    return pastas


def analisar_post(post, transcricao, seguidores):
    """Um post vira um bloco de numeros. Sem interpretacao, so medida."""
    segmentos = (transcricao or {}).get("segmentos", [])
    texto_falado = (transcricao or {}).get("texto", "")
    duracao = post.get("duracao_segundos")

    legenda = post.get("legenda", "")
    texto_para_chamada = "%s %s" % (legenda, texto_falado)

    return {
        "id": post["id"],
        "link": post["link"],
        "tipo": post["tipo"],
        "duracao_segundos": duracao,
        "gancho": {
            "falado": metricas.gancho_falado(segmentos),
            "escrito": metricas.primeira_linha(legenda),
        },
        "ritmo_palavras_por_minuto": metricas.palavras_por_minuto(texto_falado, duracao),
        "estrutura_no_tempo": metricas.blocos_no_tempo(segmentos),
        "legenda": metricas.analisar_legenda(legenda),
        "hashtags": {
            "quantas": len(post.get("hashtags", [])),
            "quais": post.get("hashtags", []),
        },
        "chamadas_para_acao": metricas.detectar_chamadas(texto_para_chamada),
        "engajamento": {
            "curtidas": post.get("curtidas"),
            "comentarios": post.get("comentarios"),
            "visualizacoes": post.get("visualizacoes"),
            "taxa_percentual": metricas.taxa_de_engajamento(
                post.get("curtidas"), post.get("comentarios"), seguidores),
        },
        "publicacao": {
            "data": post.get("data_local"),
            "dia": DIAS_EM_PORTUGUES.get(post.get("dia_da_semana"),
                                         post.get("dia_da_semana")),
            "hora": post.get("hora"),
        },
        "tem_transcricao": transcricao is not None,
    }


def resumir_perfil(posts_analisados):
    """As medias e as contagens que permitem comparar um perfil com outro."""
    if not posts_analisados:
        return {}

    com_taxa = [p for p in posts_analisados
                if p["engajamento"]["taxa_percentual"] is not None]
    melhores = sorted(com_taxa,
                      key=lambda p: p["engajamento"]["taxa_percentual"],
                      reverse=True)

    formatos = metricas.contar_ocorrencias([[p["tipo"]] for p in posts_analisados])
    dias = metricas.contar_ocorrencias([[p["publicacao"]["dia"]]
                                        for p in posts_analisados
                                        if p["publicacao"]["dia"]])
    horas = metricas.contar_ocorrencias([[(p["publicacao"]["hora"] or "")[:2] + "h"]
                                         for p in posts_analisados
                                         if p["publicacao"]["hora"]])
    hashtags = metricas.contar_ocorrencias([p["hashtags"]["quais"]
                                            for p in posts_analisados])

    tipos_de_chamada = metricas.contar_ocorrencias(
        [list(p["chamadas_para_acao"].keys()) for p in posts_analisados])
    com_chamada = sum(1 for p in posts_analisados if p["chamadas_para_acao"])

    return {
        "posts_analisados": len(posts_analisados),
        "com_transcricao": sum(1 for p in posts_analisados if p["tem_transcricao"]),
        "media_taxa_engajamento": metricas.media(
            [p["engajamento"]["taxa_percentual"] for p in posts_analisados]),
        "media_curtidas": metricas.media(
            [p["engajamento"]["curtidas"] for p in posts_analisados]),
        "media_comentarios": metricas.media(
            [p["engajamento"]["comentarios"] for p in posts_analisados]),
        "media_duracao_segundos": metricas.media(
            [p["duracao_segundos"] for p in posts_analisados]),
        "media_ritmo_palavras_por_minuto": metricas.media(
            [p["ritmo_palavras_por_minuto"] for p in posts_analisados]),
        "media_hashtags": metricas.media(
            [p["hashtags"]["quantas"] for p in posts_analisados]),
        "media_caracteres_legenda": metricas.media(
            [p["legenda"]["caracteres"] for p in posts_analisados]),
        "formatos": formatos,
        "dias_que_publica": dias,
        "horarios_que_publica": horas,
        "hashtags_mais_usadas": dict(list(hashtags.items())[:15]),
        "chamadas_por_tipo": tipos_de_chamada,
        "posts_com_chamada_percentual": round(
            com_chamada / len(posts_analisados) * 100, 1),
        "melhores_posts": [
            {"id": p["id"], "link": p["link"], "tipo": p["tipo"],
             "taxa": p["engajamento"]["taxa_percentual"],
             "gancho": p["gancho"]["falado"] or p["gancho"]["escrito"]}
            for p in melhores[:3]
        ],
    }


def analisar_perfil(pasta_perfil):
    perfil = _ler_json(pasta_perfil / "perfil.json")
    seguidores = perfil.get("seguidores")

    posts_analisados = []
    for pasta_post in sorted(pasta_perfil.iterdir()):
        if not pasta_post.is_dir():
            continue
        arquivo_post = pasta_post / "post.json"
        if not arquivo_post.exists():
            continue

        arquivo_transcricao = pasta_post / "transcricao.json"
        transcricao = (_ler_json(arquivo_transcricao)
                       if arquivo_transcricao.exists() else None)

        posts_analisados.append(
            analisar_post(_ler_json(arquivo_post), transcricao, seguidores))

    return {
        "perfil": perfil,
        "analisado_em": datetime.now().isoformat(timespec="seconds"),
        "resumo": resumir_perfil(posts_analisados),
        "posts": posts_analisados,
    }


def montar_comparativo(analises):
    """O que so aparece quando se olha varios perfis juntos."""
    hashtags_por_perfil = {
        a["perfil"]["usuario"]: set(a["resumo"].get("hashtags_mais_usadas", {}))
        for a in analises
    }

    compartilhadas = {}
    for usuario, tags in hashtags_por_perfil.items():
        for outro, outras in hashtags_por_perfil.items():
            if usuario >= outro:
                continue
            for tag in tags & outras:
                compartilhadas.setdefault(tag, set()).update([usuario, outro])

    ranking = sorted(
        analises,
        key=lambda a: a["resumo"].get("media_taxa_engajamento") or 0,
        reverse=True)

    return {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "perfis": len(analises),
        "ranking_por_engajamento": [
            {"usuario": a["perfil"]["usuario"],
             "seguidores": a["perfil"]["seguidores"],
             "media_taxa_engajamento": a["resumo"].get("media_taxa_engajamento"),
             "posts_analisados": a["resumo"].get("posts_analisados")}
            for a in ranking
        ],
        "hashtags_em_comum": {
            tag: sorted(perfis)
            for tag, perfis in sorted(compartilhadas.items(),
                                      key=lambda par: len(par[1]), reverse=True)
        },
    }


def mostrar(analise):
    resumo = analise["resumo"]
    perfil = analise["perfil"]
    print("\n=== %s (%s seguidores) ===" % (
        perfil["usuario"], "{:,}".format(perfil["seguidores"] or 0)))
    print("  posts analisados      : %s (%s com transcricao)" % (
        resumo.get("posts_analisados"), resumo.get("com_transcricao")))
    print("  engajamento medio     : %s%%" % resumo.get("media_taxa_engajamento"))
    print("  duracao media         : %ss" % resumo.get("media_duracao_segundos"))
    print("  ritmo medio           : %s palavras/min" % (
        resumo.get("media_ritmo_palavras_por_minuto")))
    print("  hashtags por post     : %s" % resumo.get("media_hashtags"))
    print("  posts com chamada     : %s%%" % (
        resumo.get("posts_com_chamada_percentual")))
    if resumo.get("melhores_posts"):
        melhor = resumo["melhores_posts"][0]
        print("  melhor post           : %s (%s%%)" % (melhor["link"], melhor["taxa"]))
        if melhor["gancho"]:
            print("    gancho: \"%s\"" % melhor["gancho"][:70])


def main():
    console.preparar()
    parser = argparse.ArgumentParser(description="Transforma o que foi baixado em numeros.")
    parser.add_argument("--perfil", help="So este perfil.")
    args = parser.parse_args()

    pastas = listar_perfis_coletados(args.perfil)
    if not pastas:
        print("Nenhum perfil coletado ainda.", file=sys.stderr)
        print("Rode antes:  python src/coletar.py --termo \"...\"", file=sys.stderr)
        return 1

    config.garantir_pastas()
    analises = []
    conexao = banco.conectar()

    try:
        for pasta in pastas:
            analise = analisar_perfil(pasta)
            destino = config.ANALISES / ("%s.json" % pasta.name)
            with destino.open("w", encoding="utf-8") as aberto:
                json.dump(analise, aberto, ensure_ascii=False, indent=2)

            for post in analise["posts"]:
                banco.salvar_metricas(conexao, post["id"], post)

            analises.append(analise)
            mostrar(analise)
    finally:
        conexao.close()

    comparativo = montar_comparativo(analises)
    destino_geral = config.ANALISES / "_comparativo.json"
    with destino_geral.open("w", encoding="utf-8") as aberto:
        json.dump(comparativo, aberto, ensure_ascii=False, indent=2)

    print("\n%d perfil(is) analisado(s)." % len(analises))
    print("Pasta: %s" % config.ANALISES)
    return 0


if __name__ == "__main__":
    sys.exit(main())
