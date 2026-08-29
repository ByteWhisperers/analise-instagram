"""O terminal do Windows não aguenta o que o Instagram publica.

`[VERIFICADO 29/08/2026]` Isto não é preciosismo: `pipeline.py ranking`
**quebrava com traceback** em qualquer legenda com emoji, que é quase toda
legenda de Instagram. O erro era este:

    UnicodeEncodeError: 'charmap' codec can't encode character
    '\\U0001f353' in position 52

`\\U0001f353` é o morango de "Morango Cravejado 🍓", o post que estava em
primeiro lugar no ranking do nicho `receitas`. Ou seja: o comando quebrava
justamente no melhor resultado.

O bug ficou escondido porque toda conferência da sessão em que o ranking foi
escrito rodou com `PYTHONIOENCODING=utf-8` no ambiente. A variável mascarava a
falha — quem rodasse o comando normalmente levava o traceback.

Duas linhas de defesa, nesta ordem:

1. `utf-8` para o que o Python escrever. No console do Windows isso funciona
   porque o Python usa `WriteConsoleW`, e em arquivo ou pipe sai UTF-8 honesto.
2. `errors="replace"` como rede: se ainda assim algum caractere não couber,
   ele vira `?` — **um relatório feio é melhor que um relatório que não sai.**

Vale principalmente para ferramenta de diagnóstico: `preparar.py` existe para
dizer o que está errado, e um diagnosticador que quebra ao imprimir o
diagnóstico é pior que nenhum.
"""

import sys


def preparar():
    """Deixa stdout e stderr aguentarem emoji. Idempotente e sem exceção.

    Chamada no começo de cada `main()`. Não é feita no import de propósito:
    efeito colateral em import é armadilha para quem importa o módulo só para
    usar uma função.
    """
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            # Fluxo já fechado, substituído por um dublê de teste, ou sem
            # suporte a reconfigure. Nada disso justifica derrubar o comando.
            pass
