> **CANCELADA em 26/08/2026 pela [ADR 005](../../docs/decisions/005-apify-em-vez-de-raspagem-propria.md).**
> A raspagem própria saiu do projeto; descoberta e coleta passaram para a
> Apify. O código desta task (`ig.py`, `buscar.py`, `coletar.py`) foi apagado
> em 28/08. O trabalho equivalente está na [T9](T9-pipeline-apify-ytdlp.md).

# T2 — Busca por termo

**ID:** T2
**Workflow:** BUILD (com ciclo de INVESTIGATION na verificação)
**Status:** CÓDIGO PRONTO — parado no gate da conta do Instagram
**Depende de:** T1 (concluída)
**Bloqueia:** T3

## Objetivo

Receber um termo ("apostas", "tigrinho") e devolver uma lista de perfis
candidatos, salva em `dados/buscas/<termo>.json`.

## Escopo

Dentro:
- `src/config.py` — caminhos e leitura do `config.local.json`
- `src/ig.py` — instância do Instaloader, ritmo lento, sessão salva
- `src/buscar.py` — as duas fontes de perfis, filtro e gravação

Fora:
- Baixar posts ou mídia (isso é T3)
- Criar a conta descartável (é do usuário — V1 §14)

## Como funciona

Duas fontes, somadas e sem repetição:

1. **`TopSearchResults`** — o que o próprio Instagram devolve ao buscar o termo.
   Acha quem tem o termo no nome de usuário ou no nome real.
2. **Posts em alta da hashtag** — os autores dos top posts de `#termo`.
   Esta é a fonte que acha quem **performa** sem ter o termo no nome.

Depois, uma requisição por perfil para ler seguidores/bio/nº de posts, filtro
por mínimo de seguidores e por ser público, ordenação por seguidores.

**Economia de requisição deliberada:** dos posts da hashtag eu pego só o nome do
autor, junto tudo, tiro os repetidos e só então busco o perfil. Sem isso, um
autor com 5 posts em alta viraria 5 requisições em vez de 1.

## Ritmo lento

`RitmoLento` (em `src/ig.py`) é uma subclasse do controle de taxa do Instaloader
que impõe **intervalo mínimo fixo** entre requisições, além do freio nativo — que
só age quando já está perto do limite. Padrão: 8 segundos.

## Passos

- [x] `src/config.py`
- [x] `src/ig.py` com sessão salva e login interativo
- [x] `src/buscar.py`
- [x] Verificação de sintaxe nos três arquivos
- [ ] **GATE: conta descartável do Instagram criada e "curtida" alguns dias**
- [ ] Copiar `config.local.example.json` → `config.local.json` com o usuário
- [ ] Rodar com um termo real
- [ ] **Abrir 5 perfis do resultado à mão no navegador** (ciclo INVESTIGATION)

## Critérios de aceitação

1. `dados/buscas/<termo>.json` existe e tem perfis.
2. Cada perfil traz usuário, nome, bio, seguidores, nº de posts, link e origem.
3. **Os perfis fazem sentido para o termo** — conferido no navegador, não no JSON.

Se o passo 3 falhar, o filtro é ajustado **antes** de a T3 ser construída em cima.

## Riscos conhecidos

- Conta nova que já sai buscando é a que mais toma bloqueio. Por isso o gate
  pede alguns dias de uso normal antes.
- `TopSearchResults` é API interna e pode mudar. Se falhar, o código avisa e
  segue só com a hashtag, em vez de morrer.

## Verificação

```
.venv\Scripts\python.exe src\buscar.py "apostas"
```

**Evidência exigida:** a saída real colada aqui + o print dos perfis abertos
no navegador (V1 §10).

## Resultado

_(preencher ao concluir)_
