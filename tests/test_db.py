"""Confere a camada de conexao e o descobridor de migrations.

Nao precisa de servidor de pe: o que se testa aqui e a nossa logica —
ordenacao das migrations, montagem da URL e, principalmente, que a senha
NUNCA vaza para tela nem para mensagem de erro.

    .venv\\Scripts\\python.exe tests\\test_db.py
"""

import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import config
import db

falhas = []

# De proposito com os caracteres que quebram URI. A senha real gerada para
# este projeto tem `/` e `[`, e foi exatamente isso que derrubou a primeira
# tentativa de conectar por URL.
SENHA = "P:1Iiop[xox/bSmiw@1xLmM9"

CFG = {"postgres": {"host": "127.0.0.1", "port": 5432,
                    "database": "analise_instagram", "user": "postgres",
                    "password": SENHA}}


def conferir(descricao, obtido, esperado):
    if obtido == esperado:
        print("  ok   %s" % descricao)
    else:
        print("  FALHOU  %s\n         esperado: %r\n         obtido:   %r"
              % (descricao, esperado, obtido))
        falhas.append(descricao)


def conferir_que(descricao, condicao):
    if condicao:
        print("  ok   %s" % descricao)
    else:
        print("  FALHOU  %s" % descricao)
        falhas.append(descricao)


def _erro_de(funcao, *args):
    """A excecao que a funcao levantou, para conferir o texto dela."""
    try:
        funcao(*args)
    except Exception as erro:
        return erro
    return None


print("=== conexao por parametros, nao por URL ===")
conferir("os parametros que o psycopg recebe",
         db.parametros_de_conexao(CFG),
         {"host": "127.0.0.1", "port": 5432, "dbname": "analise_instagram",
          "user": "postgres", "password": SENHA})
conferir("a senha vai crua nos parametros, sem escape nenhum",
         db.parametros_de_conexao(CFG)["password"], SENHA)
conferir("aceita outro banco (para o CREATE DATABASE)",
         db.parametros_de_conexao(CFG, "postgres")["dbname"], "postgres")
conferir("porta vira inteiro mesmo se vier como texto",
         db.parametros_de_conexao({"postgres": dict(CFG["postgres"],
                                                    port="5432")})["port"], 5432)

print("\n=== a URL so de depuracao escapa o que quebraria o URI ===")
url = db.string_de_conexao(CFG)
conferir_que("a senha crua NAO aparece na URL", SENHA not in url)
conferir_que("os delimitadores foram escapados",
             "%3A" in url and "%2F" in url and "%40" in url and "%5B" in url)
conferir_que("e mesmo assim aponta para o banco certo",
             url.endswith("@127.0.0.1:5432/analise_instagram"))

print("\n=== a senha nao pode aparecer na tela ===")
descricao = db.descrever(CFG)
conferir_que("descrever() nao contem a senha", SENHA not in descricao)
conferir("descrever() diz o que interessa", descricao,
         "postgres@127.0.0.1:5432/analise_instagram")

print("\n=== configuracao incompleta vira instrucao, nao KeyError ===")
for faltando in ("host", "port", "database", "user", "password"):
    parcial = {"postgres": {c: v for c, v in CFG["postgres"].items()
                            if c != faltando}}
    try:
        db.string_de_conexao(parcial)
        conferir_que("faltar %s deveria estourar" % faltando, False)
    except db.ErroDeBanco as erro:
        conferir_que("faltar %s e reclamado pelo nome" % faltando,
                     faltando in str(erro))

try:
    db.string_de_conexao({})
    conferir_que("config sem secao postgres deveria estourar", False)
except db.ErroDeBanco:
    conferir_que("config sem secao postgres levanta ErroDeBanco", True)

print("\n=== o que config.carregar() exige (e o que deixou de exigir) ===")
# Ate 29/08/2026 o portao era `instagram.usuario`, que nenhum codigo lia. A
# ADR 005 tirou a conta do Instagram do projeto; exigi-la impedia o projeto
# e os proprios testes de subir em maquina limpa.
conferir_que("usuario_instagram() nao existe mais",
             not hasattr(config, "usuario_instagram"))
conferir_que("PLACEHOLDER_USUARIO nao existe mais",
             not hasattr(config, "PLACEHOLDER_USUARIO"))

try:
    config._exigir_postgres(CFG)
    conferir_que("config sem secao instagram passa", True)
except config.ErroDeConfig as erro:
    conferir_que("config sem secao instagram passa (erro: %s)" % erro, False)

try:
    config._exigir_postgres({"apify": {"token": "x"}})
    conferir_que("config sem postgres deveria estourar", False)
except config.ErroDeConfig as erro:
    conferir_que("sem postgres, o erro diz o nome da secao",
                 "postgres" in str(erro))
    conferir_que("sem postgres, o erro aponta o arquivo de exemplo",
                 "example" in str(erro))

for faltando in config.OBRIGATORIAS_DO_POSTGRES:
    parcial = {"postgres": {c: v for c, v in CFG["postgres"].items()
                            if c != faltando}}
    try:
        config._exigir_postgres(parcial)
        conferir_que("faltar %s no carregar deveria estourar" % faltando, False)
    except config.ErroDeConfig as erro:
        conferir_que("carregar reclama %s pelo nome" % faltando,
                     faltando in str(erro))

conferir_que("a senha nunca aparece no erro de config incompleto",
             SENHA not in str(_erro_de(config._exigir_postgres,
                                       {"postgres": {"host": "h",
                                                     "password": SENHA}})))

print("\n=== servidor fora do ar: erro legivel e SEM a senha ===")
morto = {"postgres": dict(CFG["postgres"], port=59999)}
try:
    db.conectar(morto)
    conferir_que("conectar em porta morta deveria estourar", False)
except db.ErroDeBanco as erro:
    texto = str(erro)
    conferir_que("levanta ErroDeBanco, nao OperationalError cru", True)
    conferir_que("A SENHA NAO VAZA na mensagem de erro", SENHA not in texto)
    conferir_que("e diz como conferir o servico", "Get-Service" in texto)

print("\n=== descobrir migrations ===")
reais = db.arquivos_de_migration()
conferir_que("acha a 001_intelligence.sql do projeto",
             any(a.stem == "001_intelligence" for a in reais))

TEMPORARIA = Path(tempfile.mkdtemp(prefix="teste-migrations-"))
original = db.MIGRATIONS
db.MIGRATIONS = TEMPORARIA

for nome in ("010_dez.sql", "002_dois.sql", "001_um.sql", "100_cem.sql",
             "leiame.md", "rascunho.sql", "_esboco.sql"):
    (TEMPORARIA / nome).write_text("-- vazio", encoding="utf-8")

achados = [a.name for a in db.arquivos_de_migration()]
conferir("em ordem numerica, e nao alfabetica de qualquer jeito",
         achados, ["001_um.sql", "002_dois.sql", "010_dez.sql", "100_cem.sql"])
conferir_que("arquivo que nao segue o padrao e ignorado",
             "leiame.md" not in achados and "rascunho.sql" not in achados
             and "_esboco.sql" not in achados)

db.MIGRATIONS = TEMPORARIA / "nao-existe"
conferir("pasta ausente devolve lista vazia, nao estoura",
         db.arquivos_de_migration(), [])

db.MIGRATIONS = original
shutil.rmtree(TEMPORARIA, ignore_errors=True)

print("\n=== a migration 001 declara o que foi combinado ===")
sql = (RAIZ / "migrations" / "001_intelligence.sql").read_text(encoding="utf-8")

ESPERADAS = ["niches", "profiles", "niche_profiles", "profile_snapshots",
             "contents", "content_hashtags", "content_mentions",
             "content_metric_snapshots", "comments", "media_assets",
             "content_analyses", "comment_analyses", "embeddings",
             "collection_jobs", "processing_jobs", "data_costs"]
for tabela in ESPERADAS:
    conferir_que("declara a tabela %s" % tabela,
                 "CREATE TABLE IF NOT EXISTS %s " % tabela in sql
                 or "CREATE TABLE IF NOT EXISTS %s(" % tabela in sql)

conferir_que("idempotencia de conteudo: platform + platform_content_id unico",
             "UNIQUE (platform, platform_content_id)" in sql)
conferir_que("idempotencia da fila: um job por tipo e entidade",
             "UNIQUE (job_type, entity_type, entity_id)" in sql)
conferir_que("cost_level restrito a 1..4",
             "cost_level BETWEEN 1 AND 4" in sql)
conferir_que("embedding nasce REAL[], nao vector",
             "embedding    REAL[]" in sql and "vector(1536)" not in
             sql.split("-- ============================================================== TRIGGERS")[0]
             .split("CREATE TABLE IF NOT EXISTS embeddings")[1])
conferir_que("raw_data preservado em contents", "raw_data            JSONB" in sql)
conferir_que("a migration e transacional: BEGIN antes de qualquer CREATE",
             0 <= sql.index("BEGIN;") < sql.index("CREATE TABLE"))
conferir_que("e termina em COMMIT", sql.strip().endswith("COMMIT;"))
conferir_que("e registra a propria versao no fim",
             "INSERT INTO schema_migrations (version) VALUES ('001_intelligence')" in sql)
conferir_que("todo id e IDENTITY, nao serial",
             sql.count("GENERATED ALWAYS AS IDENTITY") >= 12
             and "SERIAL" not in sql.upper().replace("SERIALIZABLE", ""))

print("\n=== T13: os criterios saem do codigo e viram configuracao ===")

VAZIO = {"postgres": CFG["postgres"]}

padrao = config.descoberta(VAZIO)
conferir("sem secao, o eixo padrao e o nome", padrao["eixos"], ["nome"])
conferir("sem secao, a banda nasce em 10k", padrao["seguidores_min"], 10000)
conferir("sem secao, a banda termina em 500k", padrao["seguidores_max"], 500000)
conferir("sem secao, so perfil publico", padrao["somente_publicos"], True)
conferir("sem secao, qualificar tem teto", padrao["max_qualificar"], 20)

escolhido = config.descoberta(dict(VAZIO, descoberta={
    "eixos": ["hashtag", "NOME"], "seguidores_min": 1, "seguidores_max": 2}))
conferir("o config manda mais que o padrao", escolhido["seguidores_min"], 1)
conferir("eixo aceita maiuscula e espaco", escolhido["eixos"],
         ["hashtag", "nome"])
conferir("o que o config nao diz, o padrao completa",
         escolhido["max_qualificar"], 20)

try:
    config.descoberta(dict(VAZIO, descoberta={"eixos": ["telepatia"]}))
    conferir_que("eixo inventado no config deveria estourar", False)
except config.ErroDeConfig as erro:
    conferir_que("eixo inventado no config lista os que existem",
                 "hashtag" in str(erro) and "telepatia" in str(erro))

try:
    config.descoberta(dict(VAZIO, descoberta={"seguidores_min": 500000,
                                              "seguidores_max": 10000}))
    conferir_que("banda invertida deveria estourar", False)
except config.ErroDeConfig as erro:
    conferir_que("banda invertida avisa que ninguem passaria",
                 "nenhum perfil passa" in str(erro))

padrao = config.coleta(VAZIO)
conferir("sem secao, a janela e de 30 dias", padrao["janela_dias"], 30)
conferir("sem secao, pede reels", padrao["tipo"], "reels")
conferir("sem secao, fixado entra marcado", padrao["incluir_fixados"], True)
conferir("sem secao, maturidade de 48h", padrao["maturidade_horas"], 48)
conferir("as pausas antigas continuam de pe",
         padrao["segundos_entre_requisicoes"], 8)

conferir("janela nula e jeito legitimo de nao filtrar por data",
         config.coleta(dict(VAZIO, coleta={"janela_dias": None}))["janela_dias"],
         None)

for ruim in (0, -5, "trinta", 1.5):
    try:
        config.coleta(dict(VAZIO, coleta={"janela_dias": ruim}))
        conferir_que("janela_dias=%r deveria estourar" % (ruim,), False)
    except config.ErroDeConfig as erro:
        conferir_que("janela_dias=%r e recusada com explicacao" % (ruim,),
                     "janela_dias" in str(erro))

try:
    config.coleta(dict(VAZIO, coleta={"tipo": "carrossel"}))
    conferir_que("tipo inventado deveria estourar", False)
except config.ErroDeConfig as erro:
    conferir_que("tipo inventado diz quais existem",
                 "reels" in str(erro) and "posts" in str(erro))


print("\n=== T13: a migration do post fixado ===")

sql_004 = (db.MIGRATIONS / "004_fixado.sql").read_text(encoding="utf-8")
conferir_que("004 acrescenta a coluna sem quebrar quem ja tem",
             "ADD COLUMN IF NOT EXISTS is_pinned" in sql_004)
conferir_que("004 refaz a view para expor o campo",
             "CREATE OR REPLACE VIEW v_content_current" in sql_004)
conferir_que("a coluna nova entra NO FIM da view — CREATE OR REPLACE so "
             "aceita assim",
             sql_004.index("c.is_pinned\n\nFROM contents c") >
             sql_004.index("engagement_base"))
conferir_que("o indice do fixado e parcial, e nao sobre a coluna inteira",
             "WHERE is_pinned IS TRUE" in sql_004)

print("\n=== T14: os freios do mapeamento ===")

padrao = config.mapeamento(VAZIO)
conferir("sem secao, o teto e US$ 0,30", padrao["teto_usd"], 0.30)
conferir("sem secao, tres rodadas", padrao["rodadas"], 3)
conferir("sem secao, satura em 20%", padrao["saturacao"], 0.20)
conferir("sem secao, 30 itens por tag", padrao["itens_por_tag"], 30)
conferir("sem secao, mede ate 12 perfis para a distribuicao",
         padrao["perfis_para_medir"], 12)

conferir("o config manda mais que o padrao",
         config.mapeamento(dict(VAZIO, mapeamento={"teto_usd": 0.05}))["teto_usd"],
         0.05)

for ruim in (0, -1, "muito", None):
    try:
        config.mapeamento(dict(VAZIO, mapeamento={"teto_usd": ruim}))
        conferir_que("teto_usd=%r deveria estourar" % (ruim,), False)
    except config.ErroDeConfig as erro:
        conferir_que("teto_usd=%r e recusado com explicacao" % (ruim,),
                     "teto_usd" in str(erro))

for ruim in (0, 1, 1.5, -0.2, "vinte"):
    try:
        config.mapeamento(dict(VAZIO, mapeamento={"saturacao": ruim}))
        conferir_que("saturacao=%r deveria estourar" % (ruim,), False)
    except config.ErroDeConfig as erro:
        conferir_que("saturacao=%r e recusada com explicacao" % (ruim,),
                     "saturacao" in str(erro))

conferir("descoberta ganhou teto de tags por rodada",
         config.descoberta(VAZIO)["max_tags_por_rodada"], 3)


print("\n=== T14: a migration do mapeamento ===")

sql_005 = (db.MIGRATIONS / "005_mapeamento.sql").read_text(encoding="utf-8")
conferir_que("005 abre o CHECK de job_type para niche_mapping",
             "'niche_mapping'" in sql_005 and "collection_jobs_job_type_check" in sql_005)
conferir_que("005 abre o CHECK de operation tambem",
             "data_costs_operation_check" in sql_005)
conferir_que("005 cria niche_terms", "CREATE TABLE IF NOT EXISTS niche_terms" in sql_005)
conferir_que("005 guarda a EVIDENCIA, e nao so o resultado",
             "profiles_count" in sql_005 and "posts_count" in sql_005)
conferir_que("o indice de aprovados e parcial",
             "WHERE is_approved IS TRUE" in sql_005)

for versao in ("004_fixado", "005_mapeamento"):
    sql = (db.MIGRATIONS / ("%s.sql" % versao)).read_text(encoding="utf-8")
    conferir_que("%s se registra em schema_migrations (senao roda pra sempre)"
                 % versao,
                 "INSERT INTO schema_migrations (version) VALUES ('%s')" % versao
                 in sql)

print("\n" + "=" * 52)
if falhas:
    print("%d TESTE(S) FALHARAM:" % len(falhas))
    for falha in falhas:
        print("  - " + falha)
    sys.exit(1)
print("Todos os testes de db passaram.")
