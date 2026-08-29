# ADR 005 — Apify para descobrir, yt-dlp para baixar; a raspagem própria sai

- **Data:** 2026-08-26
- **Status:** aceita
- **Decisor:** o usuário, expressamente
- **Revoga:** a restrição "Sem API paga" do `CLAUDE.md`
- **Aposenta:** a [ADR 001](001-instaloader-em-vez-de-scrapegraphai.md) na parte da coleta

## O problema que travou o projeto

A coleta dependia de uma conta descartável do Instagram. A conta nunca
conseguiu entrar: o Instagram recusou o login programático com
*"An unexpected error occurred"*, que na prática significa "esta conta ainda
não está liberada para entrar por fora do aplicativo".

Foram tentados dois caminhos, e os dois esbarraram na mesma parede:

1. **Login por senha** — recusado pelo Instagram. Insistir endurece a checagem.
2. **Cookie do navegador** — o Edge guarda cookie criptografado com chave que
   só ele abre; Chrome, Brave, Opera e Vivaldi não estão instalados. Sobrava o
   Firefox, e ele não tinha sessão do Instagram.

`dados/` ficou vazia. **Nada foi coletado, nunca.** O gargalo não era técnico
de código — era de identidade e de risco de bloqueio.

## Decisão

**Descoberta e listagem vão para a Apify. Download vai para o yt-dlp.**

A divisão não é arbitrária: cada um cobre exatamente o buraco do outro.

| | Apify | yt-dlp |
|---|---|---|
| Achar perfil por termo | ✅ | ❌ |
| Listar posts de um perfil | ✅ | ❌ `_WORKING = False` |
| Baixar o vídeo | caro (é peso) | ✅ |
| Metadado por post | ✅ | ✅ |
| Exige conta sua | **não** | não, para post público |

### `[VERIFICADO]` As duas afirmações que sustentam a decisão

**1. O yt-dlp não lista perfil.** Lido no código-fonte
(`yt_dlp/extractor/instagram.py`): a classe `InstagramUserIE` tem
`_WORKING = False`. A `InstagramTagIE` não está marcada como quebrada, mas usa
`sharedData` e `query_hash` — a API que o Instagram aposentou anos atrás.

**2. O yt-dlp baixa Reels público sem login.** Testado em 26/08/2026 contra
`instagram.com/reel/Chunk8-jurw/`: **1,95 MB em 8,1s, sem cookie, sem conta.**
Era a maior suposição do plano e virou fato antes de o código ser escrito.

## O que muda de restrição

O `CLAUDE.md` listava **"Sem API paga"** como uma das cinco restrições. Ela cai.
Não é detalhe — é o usuário assumindo custo variável onde antes havia só tempo.

Os números, com o preço publicado pela Apify (US$ 2,70 por 1.000 resultados no
plano grátis; 1 resultado = 1 item cobrado):

| Rodada | Resultados | Custo |
|---|---|---|
| 40 perfis × 10 reels | 440 | **US$ 1,19** |
| 40 perfis × 30 reels | 1.240 | **US$ 3,35** |

O plano grátis dá **US$ 5/mês sem cartão** — cerca de 4 rodadas completas.

**O botão de custo é silencioso**, e é por isso que existem três freios no
código, não um:

1. `avisar_acima_de_usd` — o pipeline estima antes e pergunta
2. `teto_usd_por_rodada` — vai como `max_total_charge_usd` na chamada, então
   quem para o gasto é a Apify, não a fatura
3. `max_items` — teto de resultados na própria chamada

## Por que a API e não o MCP da Apify

O MCP só funciona com um assistente aberto na frente. Um pipeline precisa rodar
sozinho. Usamos `apify-client` (Apache-2.0, Python 3.11+; a máquina tem 3.12.10).

O MCP continua útil para investigação pontual do schema do Actor — não para o
caminho de produção.

## O que isso custa em código

**Morre:** `src/ig.py`, `src/buscar.py`, `src/coletar.py`, a conta descartável,
o cookie, o ritmo lento, `.sessoes/` e a dependência `browser_cookie3`.

**Sobrevive intacto, com as 78 conferências que já passavam:** `banco.py`,
`consultas.py`, `metricas.py`, `analisar.py`, `relatorio.py`, `transcrever.py`,
`midia.py`, `legenda.py`, `editar.py`, `config.py`.

A troca é só na ponta de entrada. **A etapa de análise não sabe que o Instagram
mudou de mãos** — e é por isso que o novo coletor foi obrigado a produzir
exatamente o mesmo `post.json` e o mesmo layout `dados/perfis/<user>/<id>/`.

## Riscos aceitos, declarados

- **O Actor é caixa-preta.** Não é open source: procurei `org:apify instagram`
  no GitHub e não existe. Se a Apify quebrar ou mudar o formato de saída, a
  gente espera por eles. Em troca, não somos mais nós que apanhamos quando o
  Instagram muda.
- **O mapeamento de campos ainda é hipótese.** Veio da documentação do Actor,
  não de uma rodada real. Por isso o normalizador aceita vários nomes para o
  mesmo dado, e existe o comando `pipeline.py schema`, que roda no menor
  tamanho possível e despeja o item cru. **Enquanto isso não rodar, o
  mapeamento está `[NÃO VERIFICADO]`.**
- **O yt-dlp anônimo tem teto.** Está no código-fonte dele: *"You have exceeded
  the rate-limit for accessing posts anonymously"*. Por isso a concorrência
  nasce em 2 e existe a opção `cookies_do_navegador` para quando o volume pedir.
- **Os termos de uso não mudaram.** O risco de bloqueio saiu da conta do
  usuário; a questão legal é a mesma de antes.

## Quando reconsiderar

O próprio pipeline mede o que decide isso: custo por perfil, custo por vídeo,
vídeos por perfil, taxa de falha e tempo médio ficam nas tabelas `coletas` e
`downloads`, e saem em `pipeline.py status`.

**Trocar a Apify por infraestrutura própria só com esses números na mão** — e
sabendo que a infraestrutura própria traz de volta exatamente o problema de
conta e bloqueio que esta ADR resolveu.
