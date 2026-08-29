# ADR 006 — PostgreSQL nativo em vez de Docker

**Data:** 29/08/2026
**Estado:** aceita
**Decide:** usuário, depois de ver a medição
**Prazo de validade:** vale **enquanto a máquina for esta**. Ver "Quando reabrir".

## Contexto

O pedido foi: *"acho que preciso de um Docker, pra organizar essa parte da
aplicação, pra organizar melhor os arquivos e banco de dados"*.

O pedido é legítimo e os incômodos por trás dele são reais — arquivos crescendo
sem controle e projeto que não sobe em máquina nova. A questão é se **Docker** é
o instrumento certo para eles, nesta máquina.

## A medição

Antes de opinar, medimos (V1 §10 — evidência, não suposição):

| | RAM |
|---|---|
| PostgreSQL 17 nativo, rodando | **17 MB** em 7 processos |
| Docker Desktop + WSL2 | **~1,2 GB** *(estimativa — não medimos, exigiria instalar)* |
| Livre na máquina no momento da decisão | **521 MB** de 3.971 |
| Pagefile já em uso | 400 MB |

Contexto que agrava: a máquina é um i3-6006U de dois núcleos, e a próxima etapa
do projeto (T11) roda `faster-whisper`, que quer ~290 MB.

Virtualização **está** habilitada (VT-x confirmado), então Docker era
tecnicamente possível. A barreira não é capacidade, é orçamento.

## Decisão

**Não usar Docker neste projeto, nesta máquina.** O PostgreSQL continua
instalado nativamente, como serviço do Windows.

## Por quê

1. **A conta não fecha.** Docker custaria ~70x a RAM da peça que substituiria,
   e substituiria justamente a que está funcionando sem reclamar.
2. **Para arquivos, pioraria.** Bind mount de centenas de MB entre Windows e
   WSL2 é lento, e `dados/` é exatamente onde o volume está.
3. **Docker resolveria só um terço do pedido.** Dos dois incômodos declarados,
   ele endereça reprodutibilidade do banco — e não toca em retenção de arquivo
   nem no fato de o projeto não ser um repositório Git.
4. **As causas reais eram outras, e mais baratas de consertar.** A investigação
   achou por que um clone novo não subia, e nenhuma delas tinha a ver com falta
   de contêiner:
   - `config.carregar()` exigia `instagram.usuario`, campo que **nenhum código
     lia** desde a ADR 005;
   - `config.local.example.json` não tinha a seção `postgres`;
   - `instalar-postgres.ps1` havia sido apagado, sem substituto.

## O que fizemos no lugar

| Necessidade | Resposta | Custo de RAM |
|---|---|---|
| Subir em máquina nova | `preparar.py verificar` — diz o que falta e como consertar | 0 |
| Config completo | seção `postgres` no exemplo; portão morto removido | 0 |
| Desfazer | `git init` + primeiro commit | 0 |
| Arquivo sob controle | `pipeline.py limpar`, seco por padrão | 0 |
| Saber o tamanho | `status` com quebra por tipo e por perfil | 0 |

## Consequências

**Aceitas:**
- O ambiente continua acoplado ao Windows. Quem clonar em Linux instala o
  PostgreSQL do jeito da distribuição — `preparar.py` diz o que falta, mas não
  instala.
- Não há isolamento: o banco é um serviço da máquina, e um `DROP DATABASE`
  errado atinge o banco de verdade. Mitigado pelo `tests/_pg.py`, que usa banco
  descartável com sufixo `_teste` e **recusa rodar** se o config apontar para um
  nome já terminado em `_teste`.

**Ganhas:**
- 1,2 GB de RAM que a transcrição vai usar na T11.
- Nada de camada nova para depurar quando algo falhar.

## Quando reabrir

Esta decisão **não vale para sempre**. Reabrir quando:

- a máquina mudar (o usuário indicou que este notebook é o ambiente "por
  enquanto") — numa máquina com 16 GB, a conta é outra;
- o projeto precisar rodar em mais de um lugar ao mesmo tempo;
- aparecer dependência que não instale no Windows sem sofrimento — `pgvector`
  é a candidata óbvia, porque exige MSVC.

Nesses casos, o caminho já está meio andado: `db.py` conecta por parâmetros
separados, então apontar para um contêiner é **mudança de configuração, não de
código**. Trocar `host`/`port` no `config.local.json` basta.

## Relacionadas

- [ADR 003 — SQLite como espinha](003-sqlite-como-espinha.md), aposentada quando
  o usuário escolheu PostgreSQL
- [ADR 005 — Apify descobre, yt-dlp baixa](005-apify-em-vez-de-raspagem-propria.md),
  que aposentou a conta do Instagram e criou, sem querer, o portão morto no
  `config.py`
