# T1 — Ambiente

**ID:** T1
**Workflow:** BUILD
**Status:** CONCLUÍDA (25/08/2026)
**Depende de:** nada
**Bloqueia:** T2, T3, T4, T5, T6

## Objetivo

Deixar a máquina capaz de rodar o projeto: Python, ffmpeg, ambiente isolado
e as bibliotecas de coleta e transcrição.

## Contexto

Máquina sem Python e sem ffmpeg. `winget` disponível (v1.29.290).
345 GB livres — espaço não é restrição.

## Escopo

Dentro:
- Instalar Python 3.12 e ffmpeg via winget
- Criar `.venv` dentro do projeto
- Instalar `instaloader` e `faster-whisper` no `.venv`
- Criar `config.local.json` a partir do exemplo

Fora:
- Criar a conta descartável do Instagram (é do usuário — V1 §14)
- Qualquer código de coleta (isso é T2)

## Passos

- [x] Criar estrutura de pastas (V1 §13)
- [x] `.gitignore` protegendo segredos e dados
- [x] `requirements.txt`
- [x] `config.local.example.json`
- [x] ADR 001
- [x] **GATE: autorização do usuário para instalar** — autorizado
- [x] `winget install Python.Python.3.12`
- [x] `winget install Gyan.FFmpeg`
- [x] `python -m venv .venv`
- [x] `.venv\Scripts\pip install -r requirements.txt`
- [x] Rodar o teste de verificação

## Critérios de aceitação

Um comando roda e imprime, sem erro:
- versão do Python
- versão do ffmpeg
- versão do instaloader
- versão do faster-whisper

Se qualquer uma faltar, T1 não está concluída.

## Verificação

```
.venv\Scripts\python -c "import instaloader, faster_whisper, sys; print(sys.version); print(instaloader.__version__); print(faster_whisper.__version__)"
ffmpeg -version
```

**Evidência exigida:** a saída real colada aqui, não a suposição de que funcionou (V1 §10).

## Resultado

**CONCLUÍDA em 25/08/2026.** Saída real dos comandos de verificação:

```
--- ffmpeg ---
ffmpeg version 9.0-full_build-www.gyan.dev Copyright (c) 2000-2026 the FFmpeg developers
--- python + bibliotecas ---
Python         3.12.10
instaloader    4.14.1
faster-whisper 1.1.1
```

Os quatro critérios de aceitação foram atendidos. Nada foi declarado pronto por
leitura de código (V1 §10).

### Observações para as próximas tasks

- O `ffmpeg` entrou no PATH do Windows, mas **terminal já aberto não enxerga** —
  é preciso abrir um novo, ou reler o PATH do registro.
- O Python do projeto é `.venv\Scripts\python.exe`. O `python` solto do sistema
  não tem as bibliotecas — sempre usar o do `.venv`.
- Rodar com `PYTHONUTF8=1` no Windows evita erro de acento quando a saída é
  redirecionada para arquivo.
- `.sessoes/` foi acrescentada ao `.gitignore`: o arquivo de sessão do Instaloader
  equivale a uma senha guardada.
