# Análise Instagram

Descobre **como uma comunidade do Instagram fala e o que ela publica**, a partir
de um termo em português comum.

Você digita `"grau de moto"`. O sistema descobre o vocabulário real do assunto,
separa as tribos que dividem aquele território, mede a banda de seguidores do
nicho, coleta os posts, transcreve o que é falado e monta um relatório.

```
termo → tribos + vocabulário → perfis → posts + mídia → transcrição → métricas
```

## O problema que ele resolve

Um termo não identifica uma comunidade — identifica o **território onde várias
comunidades vivem**.

Medido em 31/08/2026, no tema "grau de moto": as hashtags `#grau`, `#moto` e
`#graudemoto` aparecem em quase todos os perfis e não distinguem ninguém. Quem
distingue são os **subgrafos linguísticos**. O sistema encontrou dez tribos e
separou a comunidade que de fato dá grau (`grauéarte`, `graunãoécrime`,
`graudequebrada`) de **lojas** (`quilômetros rodados`, `pela confiança`), de
**notícia e classificado** (`motocicleta`, `placa`, `⚠️`), de **fotógrafos de
evento** (`nivercross`, `📸`) e de **páginas de meme** (`memes`, `😂`).

O mesmo vale para `#tragédias`, que são pelo menos três comunidades diferentes:
literatura (`sêneca`, `aristófanes`), desastre real (`acidenteaéreo`, `br242`) e
drama pessoal (`amor`, `autopiedade`).

## Como ele decide isso

Sem LLM e sem embeddings. As contas estão todas em função pura e testadas:

```
similaridade(A,B) = Σ idf(t) em A∩B / Σ idf(t) em A∪B     ← o território não pesa
generalidade(t)   = H(distribuição entre tribos) / log(total)   0=marca, 1=território
exclusividade     = P(t|tribo) / P(t|fora)                 ← com suavização add-k
classificar       = softmax( Σ log P(t|tribo) / nº de termos )
```

Um perfil recebe uma **distribuição**, nunca um rótulo — e `outros` é um
competidor de verdade, usando o corpus de fundo. Perfil que só fala genérico faz
o fundo ganhar, e a resposta vira "nenhuma das tribos que eu conheço".

## Comandos

| Etapa | Comando |
|---|---|
| Preparo do ambiente | `preparar.py verificar` |
| Esquema do banco | `migrar.py aplicar` |
| **Mapeamento** | `pipeline.py mapear "<tema>"` — seco; só grava com `--aplicar` |
| Descoberta | `pipeline.py descobrir "<nicho>"` |
| Coleta | `pipeline.py coletar --nicho X` |
| Download | `pipeline.py baixar` |
| Situação e custo | `pipeline.py status` |
| Score | `pipeline.py ranking --nicho X` |
| Faxina | `pipeline.py limpar` — só apaga com `--aplicar` |

Nada entra no banco sem você aprovar: o mapeamento devolve um dossiê JSON e
espera você marcar `"entra": true` no que presta.

## Como rodar

Requer Python 3.12+, PostgreSQL 17 e ffmpeg.

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
cp config.local.example.json config.local.json   # preencha token e senha
.venv/Scripts/python src/preparar.py verificar
.venv/Scripts/python src/migrar.py aplicar
```

`config.local.json` está no `.gitignore` e **nunca** deve ser versionado.

## Testes

**1.027 conferências**, em 16 arquivos, sem framework — cada arquivo roda
sozinho e imprime o que conferiu.

```bash
.venv/Scripts/python tests/test_grafo.py
```

As `test_repos_*` exigem o PostgreSQL de pé; se ele não responder, avisam e saem
sem falhar.

## Limites, declarados

- **Só leitura.** Nunca posta, curte ou comenta. Nenhuma conta de Instagram é
  usada — a descoberta é da Apify e o download é anônimo.
- **Só perfil público.**
- **A descoberta custa dinheiro:** US$ 2,70 por 1.000 resultados. Três freios no
  código: estimativa, teto por rodada e limite de itens.
- **Nenhum LLM entra na conta.** O Python calcula os números; a leitura
  qualitativa é escrita por gente.
- **A Fase 3 ainda fala SQLite.** Transcrição, análise e edição não foram
  portadas para o PostgreSQL. É dívida conhecida.
- **Conteúdo de terceiro tem dono.** O editor aceita vídeo baixado, e
  republicar vídeo alheio com marca própria é risco de denúncia e remoção. O
  sistema não impede; também não esconde que o risco existe.

## Documentação

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — as camadas, as 22 tabelas e
  todas as fórmulas
- [`docs/decisions/`](docs/decisions/) — sete ADRs, cada um com as alternativas
  descartadas e o porquê
- [`CHANGELOG.md`](CHANGELOG.md) — o que mudou, com os números medidos
- [`tasks/`](tasks/) — a fila de trabalho

Projeto pessoal, sem licença de uso definida — todos os direitos reservados.
