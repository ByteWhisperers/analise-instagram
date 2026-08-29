"""Onde o arquivo baixado vai parar.

Uma interface e uma implementacao. A interface existe porque o downloader nao
pode saber onde o arquivo mora — trocar disco local por S3 ou R2 depois nao
pode obrigar a mexer no downloader.

**Nao ha adaptador de nuvem aqui, de proposito.** Escrever um adaptador de S3
que ninguem usa e a complexidade especulativa que o V1 §12 proibe. A interface
custa quinze linhas e compra o desacoplamento; o adaptador se escreve no dia em
que houver nuvem.

O layout local NAO e escolha nova: `dados/perfis/<usuario>/<post_id>/midia.<ext>`
e exatamente onde `transcrever.py` e `analisar.py` ja procuram. Mudar isso
quebraria a etapa de analise, que ja esta pronta e testada.
"""

import json
import shutil
from pathlib import Path

import config

NOME_DA_MIDIA = "midia"
NOME_DOS_DADOS = "post.json"


class ErroDeStorage(Exception):
    """Falha ao guardar. Mensagem ja pronta para quem chamou."""


class Storage:
    """O contrato. Qualquer storage do futuro implementa estes quatro metodos."""

    def pasta_de(self, usuario, post_id):
        raise NotImplementedError

    def ja_tem(self, usuario, post_id):
        raise NotImplementedError

    def guardar(self, arquivo, usuario, post_id):
        """Move o arquivo para o lugar definitivo. Devolve o caminho final."""
        raise NotImplementedError

    def guardar_dados(self, dados, usuario, post_id):
        """Grava o `post.json` que a etapa de analise le."""
        raise NotImplementedError


class LocalStorage(Storage):
    """Disco local, no layout que o resto do projeto ja usa."""

    def __init__(self, raiz=None):
        self._raiz = Path(raiz) if raiz else None

    @property
    def raiz(self):
        # Lido na hora, e nao no __init__, porque os testes trocam
        # `config.PERFIS` por uma pasta temporaria depois de importar.
        return self._raiz or config.PERFIS

    def pasta_de(self, usuario, post_id):
        return self.raiz / usuario / post_id

    def ja_tem(self, usuario, post_id):
        pasta = self.pasta_de(usuario, post_id)
        return pasta.is_dir() and any(pasta.glob(NOME_DA_MIDIA + "*"))

    def guardar(self, arquivo, usuario, post_id):
        origem = Path(arquivo)
        if not origem.is_file():
            raise ErroDeStorage("O arquivo a guardar nao existe: %s" % origem)

        pasta = self.pasta_de(usuario, post_id)
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / (NOME_DA_MIDIA + origem.suffix)

        try:
            # `move` e nao `copy`: o arquivo veio de uma pasta de trabalho
            # temporaria e nao deve sobrar duas vezes num disco de 900 MB.
            shutil.move(str(origem), str(destino))
        except OSError as erro:
            raise ErroDeStorage(
                "Nao consegui mover %s para %s: %s" % (origem, destino, erro)
            ) from erro

        return str(destino)

    def guardar_dados(self, dados, usuario, post_id):
        pasta = self.pasta_de(usuario, post_id)
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / NOME_DOS_DADOS

        with destino.open("w", encoding="utf-8") as aberto:
            json.dump(dados, aberto, ensure_ascii=False, indent=2)

        return str(destino)
