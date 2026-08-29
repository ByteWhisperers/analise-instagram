"""As duas famílias de trabalho: coleta externa e processamento interno.

**`processing_jobs` é a fila do sistema.** Não há Redis nem Celery: a coluna
`status` é a fila, `queued` é quem espera vez, e um índice parcial cobre
exatamente essas linhas. Isso sobrevive a desligar o computador, custa zero
de memória e não é mais um serviço para manter de pé.

Uma mecânica só para todas as etapas caras. Download, transcrição, análise e
embedding são o mesmo problema com `job_type` diferente — duplicar a máquina
de estados quatro vezes seria erro.

A idempotência da fila é constraint do banco, não checagem em Python:
`UNIQUE (job_type, entity_type, entity_id)`. Rodar o pipeline duas vezes não
enfileira o mesmo download duas vezes, e não há como esquecer de verificar.
"""

from ._comum import dicts, exigir, id_de

# processing_jobs
NA_FILA = "queued"
RODANDO = "running"
PRONTO = "done"
FALHOU = "failed"
PULADO = "skipped"

# collection_jobs
SUCESSO = "succeeded"
FALHA = "failed"


# ------------------------------------------------------- coleta externa


def abrir_coleta(conexao, tipo, fonte, ator=None, run_id=None, nicho_id=None,
                 perfil_id=None):
    """Marca o começo de uma chamada externa. Devolve o id para fechar depois."""
    cursor = conexao.execute(
        """
        INSERT INTO collection_jobs
            (job_type, source, source_actor, raw_run_id, niche_id, profile_id)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        """,
        (exigir(tipo, "tipo"), exigir(fonte, "fonte"), ator, run_id,
         nicho_id, perfil_id))
    return id_de(cursor)


def fechar_coleta(conexao, coleta_id, encontrados=0, criados=0, atualizados=0,
                  status=SUCESSO, erro=None, run_id=None):
    conexao.execute(
        """
        UPDATE collection_jobs SET
            items_found = %s, items_created = %s, items_updated = %s,
            status = %s, error = %s,
            raw_run_id = COALESCE(%s, raw_run_id),
            finished_at = now()
        WHERE id = %s
        """,
        (encontrados, criados, atualizados, status, erro, run_id, coleta_id))


# --------------------------------------------------------------- a fila


def enfileirar(conexao, tipo, entidade_id, entidade="content", prioridade=100,
               carga=None, max_tentativas=3):
    """Põe na fila. Devolve True se entrou agora, False se já estava lá.

    Um job já concluído **não volta** para a fila: o `WHERE` do `DO UPDATE`
    protege o que já foi feito. É isso que faz reprocessar o pipeline não
    rebaixar tudo de novo.
    """
    import json

    cursor = conexao.execute(
        """
        INSERT INTO processing_jobs
            (job_type, entity_type, entity_id, priority, payload, max_attempts)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (job_type, entity_type, entity_id) DO UPDATE SET
            priority = EXCLUDED.priority,
            payload  = COALESCE(EXCLUDED.payload, processing_jobs.payload)
        WHERE processing_jobs.status IN ('queued', 'failed')
        RETURNING (xmax = 0) AS nasceu_agora
        """,
        (exigir(tipo, "tipo"), entidade, exigir(entidade_id, "entidade_id"),
         prioridade, json.dumps(carga, ensure_ascii=False) if carga else None,
         max_tentativas))

    linha = cursor.fetchone()
    # Sem linha: o DO UPDATE foi barrado pelo WHERE, ou seja, o job já existe
    # num estado que não se mexe. `xmax = 0` distingue INSERT de UPDATE.
    return bool(linha and linha[0])


def proximos(conexao, tipo, limite=10):
    """Os próximos a executar. **Esta consulta é a fila.**

    Prioridade menor primeiro, e entre iguais o mais antigo — para nada ficar
    para trás para sempre.
    """
    cursor = conexao.execute(
        """
        SELECT id, job_type, entity_type, entity_id, attempts, max_attempts, payload
        FROM processing_jobs
        WHERE job_type = %s AND status = 'queued'
        ORDER BY priority, created_at
        LIMIT %s
        """,
        (tipo, limite))
    return dicts(cursor, ("id", "job_type", "entity_type", "entity_id",
                          "attempts", "max_attempts", "payload"))


def reservar(conexao, job_id):
    """Marca como rodando e **conta a tentativa antes de tentar**.

    Contar antes, e não depois, é o que impede um item que derruba o processo
    de ser tentado para sempre: se o programa morrer no meio, a tentativa já
    está registrada.
    """
    conexao.execute(
        "UPDATE processing_jobs SET status = %s, attempts = attempts + 1, "
        "started_at = now() WHERE id = %s", (RODANDO, job_id))


def concluir(conexao, job_id, duracao_ms=None):
    conexao.execute(
        "UPDATE processing_jobs SET status = %s, error = NULL, "
        "finished_at = now(), duration_ms = %s WHERE id = %s",
        (PRONTO, duracao_ms, job_id))


def falhar(conexao, job_id, erro, duracao_ms=None):
    conexao.execute(
        "UPDATE processing_jobs SET status = %s, error = %s, "
        "finished_at = now(), duration_ms = %s WHERE id = %s",
        (FALHOU, str(erro)[:2000], duracao_ms, job_id))


def pular(conexao, job_id, motivo=None):
    """Nem sucesso nem falha: não era para fazer. Ex.: post que não é vídeo."""
    conexao.execute(
        "UPDATE processing_jobs SET status = %s, error = %s, finished_at = now() "
        "WHERE id = %s", (PULADO, motivo, job_id))


def reenfileirar_falhas(conexao, tipo=None):
    """Devolve à fila o que falhou e ainda tem crédito. Devolve quantos.

    O teto por job (`max_attempts`) existe para o sistema não insistir
    eternamente num vídeo que foi apagado ou virou privado.
    """
    sql = ("UPDATE processing_jobs SET status = %s, error = NULL "
           "WHERE status = %s AND attempts < max_attempts")
    parametros = [NA_FILA, FALHOU]

    if tipo:
        sql += " AND job_type = %s"
        parametros.append(tipo)

    return conexao.execute(sql, parametros).rowcount


def destravar_orfaos(conexao, tipo=None):
    """Devolve à fila o que ficou preso em `running`.

    Acontece ao desligar o computador ou dar Ctrl+C. Sem isto o item ficaria
    reservado para sempre e nunca mais seria processado.
    """
    sql = "UPDATE processing_jobs SET status = %s WHERE status = %s"
    parametros = [NA_FILA, RODANDO]

    if tipo:
        sql += " AND job_type = %s"
        parametros.append(tipo)

    return conexao.execute(sql, parametros).rowcount


def contagem_por_status(conexao, tipo=None):
    sql = "SELECT status, count(*) FROM processing_jobs"
    parametros = ()

    if tipo:
        sql += " WHERE job_type = %s"
        parametros = (tipo,)

    sql += " GROUP BY status ORDER BY status"
    return {linha[0]: linha[1] for linha in conexao.execute(sql, parametros)}


def taxa_de_falha(conexao, tipo=None):
    """Fração de 0 a 1 entre o que já foi tentado. None se nada foi tentado."""
    sql = ("SELECT count(*) FILTER (WHERE status = 'failed'), count(*) "
           "FROM processing_jobs WHERE attempts > 0")
    parametros = ()

    if tipo:
        sql += " AND job_type = %s"
        parametros = (tipo,)

    falhas, tentados = conexao.execute(sql, parametros).fetchone()
    return None if not tentados else falhas / tentados
