# ADR 001 — Instaloader em vez de ScrapeGraphAI

**Data:** 2026-08-25
**Status:** Aceita

## Contexto

O usuário tinha em mente o ScrapeGraphAI como ferramenta de coleta.
O projeto precisa, a partir de um termo de busca: achar perfis, baixar
**vídeos** e recuperar metadados completos de cada post (legenda, hashtags,
curtidas, comentários, data, duração, tipo).

## Decisão

Usar **Instaloader**.

## Por quê

| Requisito | ScrapeGraphAI | Instaloader |
|---|---|---|
| Baixar o arquivo de vídeo | Não | Sim |
| Login (necessário para busca por termo) | Não | Sim, com sessão salva |
| Metadados estruturados do post | Extraídos por IA, variável | Nativos e completos |
| Custo | Uma chamada de IA por página | Zero |
| Busca por hashtag / top search | Não | `TopSearchResults`, `Hashtag.get_top_posts()` |

O ScrapeGraphAI é bom para extrair texto estruturado de páginas web genéricas.
Este projeto precisa de mídia binária, autenticação e campos numéricos exatos —
fora do que ele entrega.

## Consequências

- Depende de uma conta Instagram para busca por termo → **conta descartável**, com
  risco de bloqueio assumido e ritmo lento embutido no código.
- Se o Instagram mudar a API interna, a coleta quebra. Nesse dia é **DEBUG**, não BUILD.
- Sem custo de API na coleta. O único custo de máquina é a transcrição local.

## Alternativas descartadas

- **ScrapeGraphAI** — não baixa mídia, não faz login, cobra por página.
- **API Oficial (Instagram Graph)** — só dá acesso a contas que você administra.
  Inútil para analisar concorrentes.
- **Apify / serviços pagos de scraping** — resolvem, mas custam mensalidade.
  Fica como caminho B se o Instaloader for bloqueado com frequência.
