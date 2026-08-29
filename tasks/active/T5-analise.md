# T5 — Análise

**ID:** T5
**Workflow:** BUILD
**Status:** CÓDIGO PRONTO E TESTADO — falta rodar em dados reais
**Depende de:** T4
**Bloqueia:** T6

## Objetivo

Transformar o que foi baixado e transcrito em números comparáveis entre perfis.

## Escopo

Dentro: `src/metricas.py` (as contas) e `src/analisar.py` (ler arquivos, agregar).
Fora: escrever a interpretação — isso é leitura humana, feita depois, olhando
estes números.

## O que é medido

| Medida | Como |
|---|---|
| Gancho falado | o que é dito antes dos 3s |
| Gancho escrito | a primeira linha da legenda (a única que o Instagram mostra) |
| Ritmo | palavras por minuto |
| Estrutura no tempo | os trechos com seu segundo de início |
| Legenda | letras, linhas, emojis, parágrafos, se termina em pergunta |
| Hashtags | quantas, quais, e quais se repetem entre perfis |
| Chamada para ação | 6 tipos: clicar, comentar, salvar, seguir, compartilhar, cadastrar |
| Engajamento | (curtidas + comentários) ÷ seguidores, em % |
| Publicação | dia da semana e faixa de horário |
| Formato | vídeo, carrossel ou foto, e duração |

## Decisões de construção

- **`metricas.py` é só função pura.** Entra texto, sai número. Não lê arquivo,
  não acessa rede. É o que permite conferir cada conta isoladamente.
- **A detecção de chamada ignora acento e maiúscula.** "Comenta aí" e
  "COMENTA AI" caem no mesmo lugar.
- **Chamada é procurada na legenda E na fala.** Muito Reels só fala o CTA.
- **Engajamento usa os seguidores do dia da coleta**, gravados pela T3.

## Verificação já feita

`tests/test_metricas.py` — **33 conferências, todas passaram**, sem instalar
pytest (seria mais uma dependência para conferir umas contas).

```
.venv\Scripts\python.exe tests\test_metricas.py
```

## Passos

- [x] `src/metricas.py`
- [x] `src/analisar.py`
- [x] `tests/test_metricas.py` — 33 conferências passando
- [ ] Rodar sobre dados reais (depende da T4)
- [ ] **Conferir à mão as métricas de 2 posts contra o post real**

## Critérios de aceitação

1. `dados/analises/<perfil>.json` + `_comparativo.json` gerados.
2. As métricas de 2 posts conferem com o post no Instagram.

## Resultado

_(preencher ao concluir)_
