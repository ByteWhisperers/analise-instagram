# ADR 002 — Modelo de transcrição: `small` por padrão, `base` como escape

**Data:** 2026-08-25
**Status:** Aceita, com reavaliação marcada

## Contexto

O plano do projeto assumia que a transcrição local seria o gargalo: estimava
**3 a 5 minutos de processamento para cada 1 minuto de vídeo** numa máquina
i3-6006U com 3,9 GB de RAM, e previa cair de `small` para `base` se a memória
não aguentasse.

Nada disso tinha sido medido. Era suposição.

## Medição

Áudio de teste: 42,7 segundos de fala em português, gerada pela voz
**Microsoft Maria Desktop** do próprio Windows, com um roteiro no estilo dos
Reels que o projeto vai analisar.

| | `base` | `small` |
|---|---|---|
| Carga do modelo, já em cache | 8,0s | 8,8s |
| Transcrição | 7,0s — **0,17x** a duração | 20,5s — **0,49x** a duração |
| Palavras erradas | 1 de 85 (1,2%) | 1 de 85 (1,2%) |
| RAM ocupada | ~240 MB | ~290 MB |
| Tamanho em disco | 142 MB | ~590 MB |

O único erro dos dois foi transcrever "trinta" como "30" — o que não é erro.

**A estimativa do plano errou por uma ordem de grandeza, para mais.** Um Reels
de 1 minuto leva de 10 a 30 segundos, não 3 a 5 minutos. A RAM nunca chegou perto
do limite: sobraram mais de 570 MB livres no pior caso.

### Um erro de método, e a correção

A primeira rodada de medição usou um roteiro **sem acentos** ("voce", "diario",
"infalivel"). A voz do Windows pronunciou tudo torto e os dois modelos erraram
feio — o `base` escreveu "na alter limite da Ariel" no lugar de "não ter limite
diário". Isso foi lido, no primeiro momento, como fraqueza do modelo.

Era defeito do áudio de teste, não do modelo. Com o texto acentuado, o mesmo
`base` acertou a frase inteira. Fica registrado porque a conclusão errada quase
virou decisão.

## Decisão

**Padrão: `small`. Escape: `base`.** Ambos ficam em `config.local.json`, nunca
chumbados no código.

## Por quê, se na medição empataram

Porque a medição não consegue decidir entre os dois **para o caso real**.

O áudio de teste é voz sintética: limpa, sem trilha sonora, sem ruído de fundo,
sem duas pessoas falando junto, com articulação perfeita e ritmo constante.
Reels de verdade tem música por cima da voz, corte seco, fala acelerada, gíria e
nome de marca. É exatamente nessa condição degradada que um modelo maior costuma
abrir vantagem — e o teste não cobre isso.

Como o `small` custa 0,49x contra 0,17x, e nenhum dos dois chega perto de ser
um gargalo, **pagar 3x por uma margem de segurança em áudio sujo é barato**.
Se o custo fosse 5x a duração, como o plano supunha, a conta seria outra.

## Consequências

- O `small` ocupa ~590 MB em disco, no cache do Hugging Face
  (`C:\Users\<usuário>\.cache\huggingface`), **fora da pasta do projeto**.
  Apagar o projeto não apaga o modelo.
- A carga do modelo (~9s) acontece **uma vez por execução**, não por vídeo. Por
  isso `transcrever.py` carrega o modelo antes do laço e transcreve tudo de uma vez.
- Quem tiver pressa troca para `base` em `config.local.json` e ganha 3x, com
  perda de qualidade que ainda não foi medida em áudio real.

## Reavaliação marcada

Na verificação da T4, quando houver Reels de verdade baixado: transcrever o
**mesmo vídeo** com os dois modelos e comparar de ouvido. Se em áudio real com
música o `base` empatar de novo, o padrão muda para `base` e esta ADR é revisada.

## Alternativas descartadas

- **`tiny`** — rápido demais para o que se ganha; erra muito em português.
- **`medium`/`large`** — não cabem confortavelmente em 3,9 GB de RAM e o ganho
  não se justifica para fala em português com boa captação.
- **API paga de transcrição** — o projeto tem custo zero de API como restrição
  declarada. Com 0,49x local, não há motivo para pagar.
