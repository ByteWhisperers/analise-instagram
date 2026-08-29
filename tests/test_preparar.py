"""Confere o preparo do ambiente e a saida de console.

Duas coisas que nasceram do mesmo dia e do mesmo motivo: em 29/08/2026 a
simulacao de clone limpo mostrou que o projeto nao subia em maquina nova, e
mostrou tambem que a propria ferramenta de diagnostico quebrava ao imprimir o
diagnostico.

Nada de rede nem de banco aqui: o que se testa e a nossa logica de checagem e
a de saida. As checagens que dependem de servidor sao exercidas de verdade em
`preparar.py verificar`, contra a maquina.

    .venv\\Scripts\\python.exe tests\\test_preparar.py
"""

import io
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import console
import preparar

falhas = []


def conferir(descricao, obtido, esperado):
    if obtido == esperado:
        print("  ok   %s" % descricao)
    else:
        print("  FALHOU  %s\n         esperado: %r\n         obtido:   %r"
              % (descricao, esperado, obtido))
        falhas.append(descricao)


def conferir_que(descricao, condicao):
    conferir(descricao, bool(condicao), True)


def _saida_de(funcao, *args):
    """Roda a funcao capturando o que ela imprimiu."""
    antigo = sys.stdout
    sys.stdout = io.StringIO()
    try:
        funcao(*args)
        return sys.stdout.getvalue()
    finally:
        sys.stdout = antigo


print("=== console: emoji nao pode derrubar comando ===")
# [VERIFICADO 29/08/2026] `pipeline.py ranking` quebrava com traceback em
# "Morango Cravejado 🍓", que era o primeiro colocado do nicho receitas.
MORANGO = "Morango Cravejado \U0001f353"

console.preparar()
try:
    fluxo = io.StringIO()
    fluxo.write(MORANGO)
    conferir_que("emoji atravessa a escrita", MORANGO in fluxo.getvalue())
except UnicodeEncodeError:
    conferir_que("emoji atravessa a escrita", False)

conferir_que("stdout aguenta emoji depois de preparar()",
             (getattr(sys.stdout, "errors", "replace") in ("replace", "backslashreplace")
              or (getattr(sys.stdout, "encoding", "") or "").lower()
              in ("utf-8", "utf8")))

# Chamar duas vezes nao pode estourar: cada `main()` chama uma vez, e um
# comando pode chamar outro.
console.preparar()
console.preparar()
conferir_que("preparar() e idempotente", True)


class _FluxoBurro:
    """Sem `reconfigure` — e o caso de um dublê de teste ou stream fechado."""

    def write(self, _texto):
        return 0

    def flush(self):
        pass


antigo = sys.stdout
sys.stdout = _FluxoBurro()
try:
    console.preparar()
    deu_certo = True
except Exception:
    deu_certo = False
finally:
    sys.stdout = antigo
conferir_que("fluxo sem reconfigure nao derruba preparar()", deu_certo)


print("\n=== Resultado: marca, detalhe e conserto ===")
ok = preparar.Resultado("Uma coisa", True, "detalhe")
saida = _saida_de(ok.imprimir)
conferir_que("passou aparece como [ok]", "[ok]" in saida)
conferir_que("passou mostra o detalhe", "detalhe" in saida)

ruim = preparar.Resultado("Outra coisa", False, "nao existe", "faca assim\ne assim")
saida = _saida_de(ruim.imprimir)
conferir_que("falhou aparece como [FALTA]", "[FALTA]" in saida)
conferir_que("falhou mostra a primeira linha do conserto", "faca assim" in saida)
conferir_que("falhou mostra a segunda linha tambem", "e assim" in saida)
conferir_que("conserto vem marcado com ->", "->" in saida)

# O conserto so aparece quando ha o que consertar. Instrucao em checagem que
# passou e ruido.
conferir_que("passou nao imprime conserto",
             "->" not in _saida_de(
                 preparar.Resultado("X", True, "", "nao deveria sair").imprimir))


print("\n=== checar_dependencias ===")
resultado = preparar.checar_dependencias()
conferir_que("as dependencias reais do projeto estao instaladas", resultado.ok)
conferir_que("diz quantas de quantas", "de %d" % len(preparar.DEPENDENCIAS)
             in resultado.detalhe)

inventada = preparar.checar_dependencias(
    (("modulo_que_nao_existe_xyz", "nada"),))
conferir_que("dependencia ausente e reprovada", not inventada.ok)
conferir_que("a ausente e nomeada no conserto",
             "modulo_que_nao_existe_xyz" in inventada.conserto)
conferir_que("o conserto manda instalar pelo requirements",
             "requirements.txt" in inventada.conserto)


print("\n=== checar_python ===")
resultado = preparar.checar_python()
conferir_que("reconhece o interpretador do venv", resultado.ok)
conferir_que("mostra o caminho do interpretador",
             "python" in resultado.detalhe.lower())
conferir_que("mostra a versao", "Python 3" in resultado.detalhe)


print("\n=== checar_config quando o arquivo nao existe ===")
import config

antigo_config = config.CONFIG
config.CONFIG = RAIZ / "config.que.nao.existe.json"
try:
    resultado = preparar.checar_config()
finally:
    config.CONFIG = antigo_config

conferir_que("arquivo ausente e reprovado", not resultado.ok)
conferir_que("manda copiar o exemplo", "config.local.example.json" in resultado.conserto)
conferir_que("nao pede conta do Instagram (ADR 005)",
             "instagram" not in resultado.conserto.lower())


print("\n=== a lista de dependencias nao cobra o que o projeto nao usa ===")
nomes = [modulo for modulo, _ in preparar.DEPENDENCIAS]
conferir_que("nao cobra pgvector, que nao esta instalado nesta fase",
             "pgvector" not in nomes)
conferir_que("nao cobra instaloader, aposentado pela ADR 005",
             "instaloader" not in nomes)
conferir_que("cobra psycopg, que e o banco", "psycopg" in nomes)
conferir_que("cobra faster_whisper, que e a transcricao",
             "faster_whisper" in nomes)


print("\n" + "=" * 52)
if falhas:
    print("%d TESTE(S) FALHARAM:" % len(falhas))
    for falha in falhas:
        print("  - " + falha)
    sys.exit(1)
print("Todos os testes de preparo passaram.")
