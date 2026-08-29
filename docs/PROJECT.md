# Projeto "Análise Instagram" — Plano V1

## Contexto

Você quer entender **como os posts que funcionam no Instagram são construídos**. Hoje isso é feito no olho: você abre um perfil, assiste, tenta perceber o padrão. O projeto transforma isso em processo repetível: você dá um termo ("apostas", "cassino online", "tigrinho"), o sistema acha os perfis, baixa os posts, transcreve o que é falado, mede a estrutura e monta um relatório comparativo.

**O que muda no fim:** você digita um termo e recebe uma página no navegador mostrando, perfil por perfil e post por post, qual é o gancho dos primeiros 3 segundos, como a legenda é escrita, quantas hashtags usam, onde entra a chamada para ação e qual formato engaja mais.

---

## Classificação (V1 §4)

**Primário: BUILD.** A capacidade não existe.
Composição: a última etapa (relatório) roda em **DESIGN**; a primeira busca real tem um ciclo de **INVESTIGATION** (descobrir o que o Instagram de fato devolve).

Workflows: `~/.claude/workflows/BUILD.md` e `DESIGN.md`. Nenhum workflow novo é criado — os cinco existentes cobrem (V1 §12).

---

## Decisões desta rodada

| Decisão | Escolha | Por quê |
|---|---|---|
| Ferramenta de coleta | **Instaloader**, não ScrapeGraphAI | ScrapeGraphAI não baixa vídeo, não faz login e cobra uma chamada de IA por página. Instaloader faz busca por termo, baixa mídia e devolve todos os metadados. Vira ADR. |
| Transcrição | **faster-whisper local**, de graça | Sua escolha, ciente da lentidão. |
| Conta Instagram | **Conta descartável nova** | Busca por termo exige login. |
| Formato final | **Página HTML** | Abre no navegador, sem instalar nada. |
| Análise qualitativa | **Eu leio os dados, sem API paga** | O Python calcula os números; eu escrevo a leitura. Custo zero de API. |

---

## Riscos declarados

1. **Termos de uso.** O Instagram proíbe coleta automatizada. O uso aqui é análise de conteúdo público para pesquisa própria, mas **a conta usada pode ser bloqueada**. Por isso: conta descartável, nunca a principal, e ritmo lento embutido no código.
2. **Sua máquina.** i3-6006U com 3,9 GB de RAM. A transcrição vai ser lenta — estimo **3 a 5 minutos para cada 1 minuto de vídeo**. Um lote de 20 Reels pode levar a madrugada. É o preço de não pagar API. Se incomodar, trocamos depois; o código já vai preparado para os dois caminhos.
3. **O Instagram muda.** Se eles alterarem a API interna, a coleta quebra. Nesse dia é DEBUG, não BUILD.

---

## O que precisa ser instalado (V1 §14 — ponto de parada)

Nada é instalado sem seu "pode".

| O quê | Como | Tamanho |
|---|---|---|
| Python 3.12 | `winget install Python.Python.3.12` | ~30 MB |
| ffmpeg | `winget install Gyan.FFmpeg` | ~150 MB |
| instaloader + faster-whisper | `pip` dentro do projeto | ~400 MB |
| Modelo de transcrição `small` | baixa sozinho no 1º uso | ~500 MB |

Você tem 345 GB livres. Espaço não é problema.

---

## Onde o projeto mora

```
C:\Users\55219\projetos\analise-instagram\
```

**Fora do `C:\xampp\htdocs\`** de propósito. Aquilo é pasta de site servido pelo Apache; isto é uma ferramenta sua, não um site publicado.

Estrutura (V1 §13):

```
analise-instagram/
├── CLAUDE.md              ← contexto do projeto
├── CHANGELOG.md
├── .gitignore             ← protege senha, sessão e dados baixados
├── config.local.json      ← usuário do IG (nunca vai para o Git)
├── .claude/workflows/
├── docs/PROJECT.md
├── docs/decisions/001-instaloader-em-vez-de-scrapegraphai.md
├── tasks/active/  tasks/completed/
├── src/
│   ├── buscar.py          ← termo → perfis
│   ├── coletar.py         ← perfil → posts + mídia
│   ├── transcrever.py     ← vídeo → texto
│   ├── analisar.py        ← dados → métricas
│   └── relatorio.py       ← métricas → HTML
├── dados/                 ← tudo que for baixado
└── saida/relatorio.html
```

---

## Decomposição (V1 §5)

Seis subtarefas em fila. Cada uma entrega algo que dá para olhar e conferir antes da seguinte começar.

### T1 — Ambiente `BUILD`

Instalar Python e ffmpeg, criar a pasta do projeto, o ambiente isolado (`.venv`), o `requirements.txt` e o `.gitignore`.

**Verificação:** rodo um comando que importa as bibliotecas e chama o ffmpeg. Se imprimir as versões, passou.

### T2 — Busca por termo `BUILD` *(depende de T1)*

`src/buscar.py`. Recebe um termo, usa `TopSearchResults` (perfis com o termo no nome/bio) **e** `Hashtag.get_top_posts()` (autores dos posts em alta da hashtag). Junta, tira repetidos, filtra por mínimo de seguidores e por ser público.

**Entrega:** `dados/buscas/<termo>.json` com nome, bio, seguidores, nº de posts, link.

**Verificação:** rodo com um termo seu de verdade e **abro 5 perfis à mão no navegador** para conferir se fazem sentido. Isso é o ciclo de INVESTIGATION — se os resultados vierem ruins, ajusto o filtro antes de seguir.

### T3 — Coleta `BUILD` *(depende de T2)*

`src/coletar.py`. Para cada perfil escolhido, baixa os últimos N posts: vídeo/foto, legenda, hashtags, curtidas, comentários, data/hora, tipo (Reels / carrossel / foto), duração, visualizações.

Ritmo lento embutido, login por sessão salva, **retomável** — se parar no meio, continua de onde estava em vez de baixar tudo de novo.

**Entrega:** `dados/perfis/<perfil>/<id-do-post>/` com o arquivo de mídia e um `post.json`.

**Verificação:** baixo 3 posts de 1 perfil, **abro o vídeo e comparo o JSON com o que está na tela do Instagram**.

### T4 — Transcrição `BUILD` *(depende de T3)*

`src/transcrever.py`. ffmpeg extrai o áudio em 16 kHz mono (fica ~20x menor que o vídeo, e é o que a máquina aguenta), o faster-whisper transcreve em português com marcação de tempo.

Modelo `small` em modo `int8`. Se a RAM engasgar, caio para `base` — fica em configuração, não chumbado no código.

**Entrega:** `transcricao.json` com o texto e o segundo em que cada trecho começa.

**Verificação:** transcrevo 1 Reels, **escuto o vídeo e leio a transcrição lado a lado**. Também cronometro para você saber o custo real de tempo por vídeo.

### T5 — Análise `BUILD` *(depende de T4)*

`src/analisar.py`. Números objetivos, calculados, sem chute:

- **Gancho:** o que é falado nos primeiros 3 segundos + a primeira linha da legenda
- **Ritmo:** palavras por minuto
- **Estrutura no tempo:** os blocos da transcrição com seus segundos
- **Legenda:** tamanho, número de linhas, emojis, se tem quebra de parágrafo
- **Hashtags:** quantas, quais, e quais se repetem entre perfis
- **Chamada para ação:** detectada por expressões ("link na bio", "comenta", "salva esse", "me segue")
- **Engajamento:** (curtidas + comentários) ÷ seguidores
- **Publicação:** dia da semana e horário
- **Formato:** Reels, carrossel ou foto, e a duração

Depois **eu leio esses dados e escrevo a interpretação** — o padrão que se repete, o que os melhores fazem diferente. Sem API paga.

**Entrega:** `dados/analises/<perfil>.json` + um resumo em texto.

**Verificação:** confiro à mão as métricas de 2 posts contra o post real.

### T6 — Relatório HTML `DESIGN` *(depende de T5)*

`src/relatorio.py` gera `saida/relatorio.html` — arquivo único, abre com duplo clique, sem servidor.

Design com variáveis CSS (seu projeto não tem Node; não vou introduzir Tailwind para "modernizar").

**Verificação — regra inegociável do seu padrão de UI:** eu **abro no navegador com o Playwright, tiro screenshot e olho**. Rodo `design-critic` e `responsive-critic`. **Só entrego com nota ≥ 8,0.** Nada de dar por pronto lendo o código.

---

## Ordem e gates

```
T1 → T2 → [olho os perfis] → T3 → [olho os vídeos] → T4 → [ouço e leio] → T5 → T6 → [gate visual 8.0]
```

Cada seta com colchete é um ponto onde eu paro e te mostro o resultado antes de seguir. Se a T2 trouxer perfis ruins, não adianta construir a T3 em cima.

**Paro e pergunto antes de:** instalar qualquer coisa, mexer em arquivo que não criei, e mudar o escopo (V1 §14).

---

## Verificação de ponta a ponta

Quando as seis estiverem prontas, o teste real é este, rodado de verdade:

1. Escolho um termo seu.
2. `python src/buscar.py "<termo>"` → confiro a lista de perfis.
3. `python src/coletar.py --perfis 3 --posts 10` → confiro que os arquivos existem e abrem.
4. `python src/transcrever.py` → leio 2 transcrições ouvindo os vídeos.
5. `python src/analisar.py` → confiro 2 posts na mão.
6. `python src/relatorio.py` → abro no navegador, tiro screenshot, rodo as críticas, mostro para você.

**Evidência, não suposição (V1 §10).** Nenhuma etapa é declarada pronta por leitura de código.

---

## O que fica registrado depois (V1 §11)

- **ADR** `001-instaloader-em-vez-de-scrapegraphai.md` — a escolha e o motivo, para não revisitarmos daqui a três meses
- **CHANGELOG** — a cada subtarefa concluída
- **CLAUDE.md do projeto** — o contexto permanente
- **KNOWLEDGE (memória)** — o que aprendermos sobre limites reais do Instagram e o tempo real de transcrição nesta máquina

---

## O que NÃO está neste plano

- Postar, curtir ou comentar no Instagram — só leitura
- Perfis privados
- Monitoramento contínuo/agendado — se você quiser depois, é outra task
- Gerar posts a partir da análise — outra task, depois que esta provar valor
