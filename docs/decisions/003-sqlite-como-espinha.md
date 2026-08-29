# ADR 003 — SQLite como espinha, no lugar de JSON solto

**Data:** 2026-08-25
**Status:** Aceita

## Contexto

O desenho original gravava cada etapa em arquivo JSON separado:
`dados/buscas/<termo>.json`, `dados/perfis/<perfil>/<id>/post.json`,
`dados/analises/<perfil>.json`.

Funciona para "mostrar o que foi coletado". Não funciona para o que o usuário
pediu depois: **catalogar as principais hashtags comparando com visualização e
tema**. Isso é cruzamento — e cruzar JSON espalhado significa escrever código que
abre todos os arquivos, monta dicionário na memória e junta na mão. Cada pergunta
nova vira código novo.

O usuário pediu explicitamente uma lista "armazenável em um banco de dados".

## Decisão

**SQLite**, um arquivo em `dados/analise.db`.

Os arquivos de mídia continuam em disco. O banco guarda o **caminho** do vídeo,
nunca o vídeo.

## Por quê SQLite e não outro

| | SQLite | Postgres/MySQL | Continuar em JSON |
|---|---|---|---|
| Instalar algo | **não, vem no Python** | sim, servidor | não |
| Servidor rodando | **não** | sim | não |
| Cruzar dados | **consulta** | consulta | código na mão |
| Buscar texto nas transcrições | **FTS5, nativo** | sim | varrer arquivo |
| Copiar / mandar para alguém | **um arquivo** | dump | pasta inteira |
| Sobrevive a esta máquina fraca | **sim** | pesado | sim |

Verificado na máquina: **SQLite 3.49.1, com FTS5 e JSON1 disponíveis**.

O projeto tem uma restrição declarada de não instalar o que não for necessário
(V1 §12). Subir um servidor de banco para um projeto de uma pessoa numa máquina
com 900 MB livres seria complexidade especulativa.

## Consequências

- `buscar.py` e `coletar.py` precisam passar a gravar no banco. **Os JSON não
  desaparecem** — continuam sendo escritos, porque servem para conferir a olho o
  que foi coletado. O banco é adicional, não substituto.
- Aparece um módulo novo, `src/banco.py`, com o esquema e o acesso. Nenhum outro
  módulo escreve SQL solto.
- A tabela `hashtags` guarda **uma linha por par (post, tag)**. É o que permite
  agrupar por tag numa consulta em vez de varrer texto de legenda.
- A tabela `palavras` guarda cada palavra com início e fim. Nasce para a análise,
  mas é o que vai alimentar a legenda palavra-por-palavra da etapa de edição.
- Perguntas novas passam a ser consulta, não código.

## Alternativas descartadas

- **Continuar só em JSON** — o pedido de cruzar hashtag com visualização e tema
  é exatamente o que JSON solto não faz bem.
- **Postgres / MySQL** — servidor rodando numa máquina com 900 MB livres, para
  um usuário só. Custo sem retorno.
- **Pandas** — resolveria o cruzamento, mas é dependência pesada e a memória
  some quando o volume cresce. SQLite lê do disco sem carregar tudo.
- **Guardar a mídia no banco** — deixa o arquivo intratável e não ganha nada.
