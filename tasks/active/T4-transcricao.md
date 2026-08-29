# T4 — Transcrição

**ID:** T4
**Workflow:** BUILD
**Status:** CÓDIGO PRONTO E MEDIDO — falta rodar em vídeo real do Instagram
**Depende de:** T3
**Bloqueia:** T5

## Objetivo

Vídeo → texto com o segundo em que cada trecho começa. É isso que permite a T5
perguntar "o que foi falado nos primeiros 3 segundos".

## Escopo

Dentro: `src/midia.py` (achar o ffmpeg, extrair áudio) e `src/transcrever.py`.
Fora: interpretar o que foi dito (T5).

## Decisões de construção

- **`midia.py` separado.** Achar executável e rodar processo é problema de
  sistema; a transcrição não precisa saber disso.
- **`achar_ffmpeg()` não confia no PATH.** Terminal aberto antes da instalação
  não enxerga o ffmpeg. Ele procura no PATH e, se não achar, na pasta do WinGet.
  **Verificado:** funciona com o PATH velho.
- **VAD ligado.** Corta silêncio antes de transcrever — acelera bastante.
- **`beam_size=1`.** Máquina fraca; beam maior custa caro e ganha pouco.
- **O WAV é apagado depois.** Só serve para transcrever.
- **Retomável:** vídeo com `transcricao.json` é pulado.

## Medição real nesta máquina (25/08/2026)

Áudio de teste: 42,7s de fala em português acentuado (voz Microsoft Maria).

| | `base` | `small` |
|---|---|---|
| Carga do modelo, em cache | 8,0s | 8,8s |
| Transcrição | **0,17x** a duração | **0,49x** a duração |
| Palavras erradas | 1 de 85 (1,2%) | 1 de 85 (1,2%) |
| RAM ocupada | ~240 MB | ~290 MB |

**O plano estimava 3 a 5 minutos por minuto de vídeo. Errou por uma ordem de
grandeza para mais.** A transcrição não é o gargalo — a pausa entre requisições
ao Instagram é.

Decisão em [ADR 002](../../docs/decisions/002-modelo-de-transcricao.md): `small`
por padrão, pela margem em áudio sujo; `base` como escape rápido.

**Erro de método corrigido no meio da medição:** a primeira rodada usou roteiro
sem acentos, a voz do Windows pronunciou torto e os dois modelos erraram feio.
Isso quase virou "o `base` é ruim em português". Com texto acentuado, empataram.

**Limite deste teste:** voz sintética é áudio limpo. Reels tem música por cima,
corte seco e gíria. O teste **não** decide entre os dois para o caso real — daí
a reavaliação marcada abaixo.

## Passos

- [x] `src/midia.py` com localizador de ffmpeg
- [x] `src/transcrever.py`
- [x] Extração de áudio verificada (16 kHz mono, 5,00s exatos)
- [x] Velocidade e RAM medidas com fala real
- [ ] Rodar em um Reels de verdade (depende da T3)
- [ ] **Ouvir o vídeo e ler a transcrição lado a lado**
- [ ] **Reavaliação da ADR 002:** transcrever o mesmo Reels com `base` e `small`
      e comparar de ouvido. Se empatarem em áudio com música, o padrão vira `base`.

## Critérios de aceitação

1. `transcricao.json` com texto, trechos e segundos.
2. O texto **corresponde ao que se ouve** — conferido de ouvido.
3. O custo de tempo por vídeo fica registrado.

## Resultado

_(preencher ao concluir)_
