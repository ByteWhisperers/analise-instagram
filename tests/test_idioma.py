"""Confere o detector de idioma. Heuristica explicita, teste explicito.

O detector existe porque em 30/08/2026 o mapeamento de "desastres e tragedias"
voltou inteiro em espanhol e nada no sistema levantou a mao. Ele nao entende
texto: conta sinais. Estes testes cobrem os sinais e, principalmente, o
**terceiro estado** — "nao sei", que e o que impede o filtro de matar tag
legitima calado.

    .venv\\Scripts\\python.exe tests\\test_idioma.py
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import idioma

falhas = []


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


print("=== legendas de verdade, do tipo que o Instagram tem ===")

conferir("legenda portuguesa",
         idioma.detectar("Receita de bolo de chocolate, você vai amar! "
                         "Não deixe de fazer hoje"), "pt")
conferir("legenda espanhola",
         idioma.detectar("Simulacro de emergencias en el colegio. "
                         "¡Gracias a todos los niños!"), "es")
conferir("o par que quase engana: prevencao x prevención",
         (idioma.detectar("Prevenção de acidentes no trabalho, a segurança "
                          "começa na atenção"),
          idioma.detectar("Prevención de accidentes, la seguridad empieza en "
                          "la atención")),
         ("pt", "es"))
conferir("curso hispano-americano, que foi o que o mapeamento achou",
         idioma.detectar("Curso de gestión del riesgo de desastres. "
                         "Inscripciones abiertas"), "es")


print("\n=== o terceiro estado: nao saber nao e saber que nao ===")

conferir("texto vazio nao opina", idioma.detectar(""), None)
conferir("so emoji nao opina", idioma.detectar("🔥🔥🔥"), None)
conferir("so mencao e numero nao opina", idioma.detectar("@amigo 2026"), None)
conferir("palavra que existe nos dois idiomas nao decide sozinha",
         idioma.detectar("total"), None)
conferir("None tambem para texto nenhum", idioma.detectar(None), None)


print("\n=== os sinais, um a um ===")

conferir_que("`ã` puxa forte para portugues",
             idioma.pontuar("irmão")["pt"] >= 3)
conferir_que("`ñ` puxa forte para espanhol",
             idioma.pontuar("niño")["es"] >= 3)
conferir_que("`lh` e `nh` sao portugueses",
             idioma.pontuar("trabalho")["pt"] >= 2
             and idioma.pontuar("banho")["pt"] >= 2)
conferir_que("`ll` e espanhol", idioma.pontuar("llamar")["es"] >= 2)
conferir_que("sufixo `ção` conta", idioma.pontuar("atenção")["pt"] >= 2)
conferir_que("sufixo `ción` conta", idioma.pontuar("atención")["es"] >= 2)
conferir_que("`¿` e `¡` contam", idioma.pontuar("¿qué? ¡vamos!")["es"] >= 3)

conferir("um sinal solto nao basta: precisa de vantagem de 2",
         idioma.detectar("llama"), None)
conferir_que("mas dois sinais bastam",
             idioma.detectar("llama a los niños") == "es")

conferir_que("palavra ambigua nao pontua para ninguem",
             idioma.pontuar("que") == {"pt": 0, "es": 0})


print("\n=== votacao entre varios textos ===")

lingua, votos = idioma.votar([
    "Receita facil de bolo, você precisa fazer hoje",
    "Não perca essa dica de trabalho",
    "🔥",
])
conferir("dois portugueses e um mudo dao portugues", lingua, "pt")
conferir("e os mudos ficam contados", votos["?"], 1)

lingua, votos = idioma.votar(["🔥", "😍", ""])
conferir("so mudos nao elegem ninguem", lingua, None)
conferir("e os tres aparecem no placar", votos, {"pt": 0, "es": 0, "?": 3})

lingua, _ = idioma.votar([
    "Você não vai acreditar nisso hoje",
    "Los niños de la escuela, ¡gracias!",
])
conferir("empate nao elege ninguem", lingua, None)

conferir("lista vazia nao elege ninguem", idioma.votar([])[0], None)

lingua, _ = idioma.votar(["🔥", "🔥", "Los niños de la escuela, ¡gracias!"])
conferir("uma opiniao vale mais que nove silencios", lingua, "es")

print("\n" + "=" * 52)
if falhas:
    print("%d TESTE(S) FALHARAM:" % len(falhas))
    for falha in falhas:
        print("  - " + falha)
    sys.exit(1)
print("Todos os testes de idioma passaram.")
