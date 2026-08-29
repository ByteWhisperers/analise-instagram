# T6 — Relatório HTML

**ID:** T6
**Workflow:** DESIGN
**Status:** CÓDIGO PRONTO — **portão visual NÃO passado**
**Depende de:** T5

## Objetivo

`saida/relatorio.html` — arquivo único, abre com duplo clique, sem servidor.

## Escopo

Dentro: `src/relatorio.css` (design system) e `src/relatorio.py` (montagem).
Fora: qualquer dependência de internet, CDN ou biblioteca.

## Decisões de construção

- **Design system em variáveis CSS.** O projeto não tem Node; não foi introduzido
  Tailwind nem shadcn para "modernizar" (regra do padrão de UI).
- **Nenhum valor solto no HTML.** Toda cor, espaço e tamanho sai de um token
  em `:root`.
- **Modo escuro por `prefers-color-scheme`**, com a paleta completa redefinida.
- **CSS embutido no arquivo.** Um HTML só, que funciona offline e pode ser
  mandado por WhatsApp.
- **Tabelas dentro de `.rolagem`** (`overflow-x: auto`) — a página nunca rola
  na horizontal.
- **Todo texto passa por `escape()`.** Legenda de terceiro pode conter `<` e `>`.

## Bug encontrado e corrigido na verificação

A linha do tempo do vídeo aparecia **zero vezes**. Motivo: o relatório mostrava
a estrutura no tempo apenas do post mais engajado, e quando esse post era um
carrossel (sem fala), a estrutura sumia da página inteira.

Corrigido com `melhor_post_com_tempo()`: a linha do tempo passa a vir do **vídeo**
mais engajado, mesmo que o campeão geral seja um carrossel. Depois da correção:
3 linhas do tempo, uma por perfil.

## Passos

- [x] `src/relatorio.css` com os tokens
- [x] `src/relatorio.py`
- [x] Conferência estrutural do HTML gerado (bem formado, CSS embutido,
      viewport, modo escuro, regra de tela pequena)
- [x] Correção da linha do tempo ausente
- [ ] **PORTÃO: renderizar no navegador, tirar screenshot e OLHAR**
- [ ] `design-critic` ≥ 8,0
- [ ] `responsive-critic` ≥ 8,0
- [ ] `frontend-quality-review`

## Por que o portão não passou

Nesta sessão **não há navegador automatizado** (o MCP Playwright não está
carregado). A regra do padrão de UI é explícita: nunca declarar uma tela pronta
com base na leitura do código.

Então: o HTML foi conferido **estruturalmente** e aberto na tela do usuário para
olho humano. **A nota visual continua pendente** e a T6 não pode ser fechada
até que um navegador esteja disponível.

## Critérios de aceitação

1. O HTML abre com duplo clique, sem servidor e sem internet.
2. Nota ≥ 8,0 em visual e em responsivo, com screenshot como prova.
3. Sem erro de console e sem rolagem horizontal da página.

## Resultado

_(preencher ao concluir)_
