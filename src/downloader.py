"""Link do Instagram -> arquivo de video.

Uma interface e uma implementacao em cima do yt-dlp.

Por que yt-dlp e nao a URL do CDN que o coletor devolve: **a URL do CDN do
Instagram vence.** Entre a coleta rodar e o download acontecer ela pode ter
expirado. O yt-dlp resolve o link do post na hora, e ainda lida com
redirecionamento, manifesto DASH e escolha de formato.

Limite conhecido do yt-dlp com Instagram, lido no codigo-fonte dele
(`yt_dlp/extractor/instagram.py`): sem cookie de sessao existe teto de
requisicao — *"You have exceeded the rate-limit for accessing posts
anonymously"*. Por isso a concorrencia do pipeline nasce baixa, e existe a
opcao `cookies_do_navegador` para quando o volume exigir.
"""

import time
from pathlib import Path

import midia

# Preferir mp4 ja pronto; so remuxar se nao houver. Remuxar custa CPU, e a
# maquina e fraca.
FORMATO_PADRAO = "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b"

TIMEOUT_PADRAO = 120       # segundos por download
TENTATIVAS_INTERNAS = 2    # do proprio yt-dlp; o retry do pipeline fica no banco


class ResultadoDownload:
    """O que o downloader devolve. Nunca levanta excecao para quem chama."""

    def __init__(self, sucesso, arquivo=None, erro=None, bytes_=0, duracao_ms=0):
        self.sucesso = sucesso
        self.arquivo = arquivo
        self.erro = erro
        self.bytes = bytes_
        self.duracao_ms = duracao_ms

    def __repr__(self):
        if self.sucesso:
            return "<ok %s (%d bytes, %d ms)>" % (
                self.arquivo, self.bytes, self.duracao_ms)
        return "<falhou: %s>" % self.erro


class VideoDownloader:
    """O contrato. Trocar yt-dlp por outra coisa nao pode mexer no pipeline."""

    def baixar(self, url, pasta_trabalho):
        raise NotImplementedError


class YtDlpDownloader(VideoDownloader):
    """yt-dlp pela API de Python, nao por linha de comando.

    Pela API porque a saida vem como dicionario — sem parsear texto, sem
    problema de aspas no Windows, e o erro chega como excecao com causa.
    """

    def __init__(self, formato=FORMATO_PADRAO, timeout=TIMEOUT_PADRAO,
                 cookies_do_navegador=None, ffmpeg=None, verboso=False):
        self.formato = formato
        self.timeout = timeout
        self.cookies_do_navegador = cookies_do_navegador
        self.verboso = verboso
        self._ffmpeg = ffmpeg

    def _achar_ffmpeg(self):
        """O ffmpeg do PATH pode nao existir num terminal aberto antes da
        instalacao. `midia.achar_ffmpeg()` ja resolve isso — reaproveitado."""
        if self._ffmpeg is None:
            try:
                self._ffmpeg = str(Path(midia.achar_ffmpeg()).parent)
            except midia.ErroDeMidia:
                self._ffmpeg = ""
        return self._ffmpeg or None

    def _opcoes(self, pasta_trabalho):
        opcoes = {
            "outtmpl": str(Path(pasta_trabalho) / "%(id)s.%(ext)s"),
            "format": self.formato,
            "noplaylist": True,       # carrossel com varios videos: pega o primeiro
            "quiet": not self.verboso,
            "no_warnings": not self.verboso,
            "noprogress": True,
            "socket_timeout": self.timeout,
            "retries": TENTATIVAS_INTERNAS,
            "fragment_retries": TENTATIVAS_INTERNAS,
            "merge_output_format": "mp4",
            "overwrites": True,
        }

        pasta_ffmpeg = self._achar_ffmpeg()
        if pasta_ffmpeg:
            opcoes["ffmpeg_location"] = pasta_ffmpeg

        if self.cookies_do_navegador:
            opcoes["cookiesfrombrowser"] = (self.cookies_do_navegador,)

        return opcoes

    def baixar(self, url, pasta_trabalho):
        """Baixa e devolve `ResultadoDownload`. Nunca levanta."""
        import yt_dlp

        pasta_trabalho = Path(pasta_trabalho)
        pasta_trabalho.mkdir(parents=True, exist_ok=True)

        comeco = time.monotonic()

        try:
            with yt_dlp.YoutubeDL(self._opcoes(pasta_trabalho)) as ydl:
                info = ydl.extract_info(url, download=True)
        except Exception as erro:  # DownloadError, rede, extractor quebrado
            return ResultadoDownload(
                False, erro="%s: %s" % (type(erro).__name__, erro),
                duracao_ms=int((time.monotonic() - comeco) * 1000))

        duracao_ms = int((time.monotonic() - comeco) * 1000)

        arquivo = self._arquivo_de(info, pasta_trabalho)
        if arquivo is None:
            return ResultadoDownload(
                False, erro="yt-dlp terminou sem erro mas nao deixou arquivo",
                duracao_ms=duracao_ms)

        return ResultadoDownload(True, arquivo=arquivo,
                                 bytes_=arquivo.stat().st_size,
                                 duracao_ms=duracao_ms)

    @staticmethod
    def _arquivo_de(info, pasta_trabalho):
        """O caminho que o yt-dlp realmente escreveu.

        Ele nem sempre devolve o nome final em `filepath`: quando junta video
        e audio, o nome muda depois. Por isso ha o passo de varrer a pasta.
        """
        if not isinstance(info, dict):
            info = {}

        if info.get("_type") == "playlist":
            entradas = [e for e in (info.get("entries") or []) if e]
            info = entradas[0] if entradas else {}

        for chave in ("filepath", "_filename"):
            caminho = info.get(chave)
            if caminho and Path(caminho).is_file():
                return Path(caminho)

        baixados = info.get("requested_downloads") or []
        for pedido in baixados:
            caminho = pedido.get("filepath")
            if caminho and Path(caminho).is_file():
                return Path(caminho)

        arquivos = [a for a in pasta_trabalho.iterdir() if a.is_file()]
        if arquivos:
            return max(arquivos, key=lambda a: a.stat().st_mtime)

        return None
