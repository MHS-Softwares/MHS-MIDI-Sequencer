# -*- coding: utf-8 -*-
"""Áudio Guia do MIDI Sequencer, pela placa de som escolhida e alinhado ao MIDI pelo relógio da própria placa.

Antes o guia tocava pelo pygame.mixer. Agora:
  - o miniaudio decodifica o arquivo (WAV, MP3, OGG, FLAC) por inteiro, uma vez, para PCM de 16 bits estéreo;
  - o sounddevice (PortAudio) toca esse PCM pelo sistema de som e pela placa que a pessoa escolheu em Preferências > Áudio
    (ASIO, WASAPI, DirectSound, MME, WDM-KS): é a mesma saída do Audio Style do Style Creator.

SINCRONIA. O áudio e o MIDI andam em relógios diferentes (o do computador e o da placa de som), e cada bloco que a placa pede
começa num ponto qualquer entre dois blocos. Por isso "começar o áudio agora" nunca cai no mesmo instante do MIDI. Aqui o início é
calculado pelo relógio da placa: quem toca anota o instante em que a posição do MIDI vale tal (t0), converte para o relógio da placa
e, no primeiro bloco, usa o instante em que ele realmente sai pelo conversor (outputBufferDacTime) para escolher o frame exato do
arquivo (ou encher o começo de silêncio, se o bloco sai antes de t0). Durante a passagem, se o áudio que está saindo fugir da linha
do tempo da placa por mais que RESSINCRONIA_MS, o bloco seguinte volta ao lugar com uma emenda suave. O "Ajuste fino" soma por cima
o que sobra (o atraso do MIDI e do sintetizador).

A escolha mora no config.json:
  audio_host         nome do sistema de som ("" = automático: WASAPI na saída padrão do Windows)
  audio_saida        nome da placa dentro desse sistema
  audio_canais       primeiro canal do par de saída (0 = 1 e 2, 2 = 3 e 4...), só no ASIO
  audio_latencia_ms  0 = a mais baixa que o driver aceita; senão, o tamanho do buffer
  audio_compensar    alinhar pelo relógio da placa (senão, só pela latência informada)
  audio_adiantar_ms  ajuste fino em milissegundos (positivo adianta o áudio, negativo atrasa)
"""

import array
import os
import threading
import time

# O sounddevice (PortAudio) só mostra o ASIO se esta variável existir ANTES do primeiro "import sounddevice".
os.environ.setdefault("SD_ENABLE_ASIO", "1")
try:
    import _sounddevice_data  # os .dll do PortAudio (com e sem ASIO): o compilador só os leva se ele aparecer aqui
    import sounddevice as sd
except Exception:  # sem a biblioteca ou sem o PortAudio
    sd = None
try:
    import miniaudio
except Exception:
    miniaudio = None
try:
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import audioop
except Exception:  # Python 3.13 em diante não tem o audioop: o volume cai num laço mais lento
    audioop = None

TAXA = 44100
BYTES_POR_FRAME = 4                  # 16 bits, 2 canais
LATENCIAS = [("A mais baixa que o driver aceitar", 0), ("Curta, 10 milissegundos", 10),
             ("Média, 30 milissegundos", 30), ("Longa, 100 milissegundos", 100)]
NOME_AUTOMATICO = "Automático: saída padrão do Windows com sincronia exata (recomendado)"
OCIOSO_SEGUNDOS = 20.0
# Dentro da passagem: se o áudio que está saindo fugir da linha do tempo da placa por mais que isto (blocos perdidos, relógio da
# placa diferente do do computador), o próximo bloco volta ao lugar com uma emenda suave.
RESSINCRONIA_MS = 4.0
FADE_FRAMES = 64
JANELA_MEDIANA = 9
JANELA_MAXIMA = 64


def disponivel():
    return sd is not None and miniaudio is not None


def _no_principal(funcao, espera=4.0):
    # Os drivers ASIO só carregam (e só descarregam) na thread principal do programa, a que tem o COM da janela: aberto de dentro da
    # thread do Play, o PortAudio devolve "Failed to load ASIO driver". Quem chama de outra thread pede à janela principal e espera.
    try:
        import wx
        app = wx.GetApp()
        if app is None or wx.IsMainThread():
            return funcao()
    except Exception:
        return funcao()
    pronto = threading.Event()
    caixa = {}

    def executar():
        try:
            caixa['valor'] = funcao()
        except BaseException as e:
            caixa['erro'] = e
        finally:
            pronto.set()

    wx.CallAfter(executar)
    if not pronto.wait(espera):
        raise RuntimeError("a janela principal não respondeu a tempo para abrir a saída de áudio")
    if 'erro' in caixa:
        raise caixa['erro']
    return caixa.get('valor')


def listar_sistemas():
    if sd is None:
        return []
    return [h['name'] for h in sd.query_hostapis()]


def listar_saidas(sistema):
    # [(índice no PortAudio, nome)] das placas com saída dentro do sistema de som.
    if sd is None:
        return []
    saida = []
    for i, d in enumerate(sd.query_devices()):
        if d['max_output_channels'] > 0 and sd.query_hostapis(d['hostapi'])['name'] == sistema:
            saida.append((i, d['name']))
    return saida


def achar_saida(sistema, nome):
    # O Windows às vezes renumera ou encurta o nome da placa: tenta o nome igual e depois o começo dele.
    saidas = listar_saidas(sistema)
    for i, n in saidas:
        if n == nome:
            return i
    base = (nome or "").strip().lower()
    for i, n in saidas:
        if base and (n.lower().startswith(base) or base.startswith(n.lower())):
            return i
    return None


def pares_de_canais(indice):
    # [(canal inicial, "1 e 2")...] - o ASIO deixa escolher em qual par de saídas o áudio sai.
    n = int(sd.query_devices(indice)['max_output_channels'])
    pares = [(c, f"{c + 1} e {c + 2}") for c in range(0, n - 1, 2)]
    return pares or [(0, "1")]


def _saida_padrao_wasapi():
    # Índice da saída padrão do Windows dentro do WASAPI, ou None.
    if sd is None:
        return None
    try:
        for h in sd.query_hostapis():
            if h['name'] == 'Windows WASAPI' and h.get('default_output_device', -1) >= 0:
                return h['default_output_device']
    except Exception:
        pass
    return None


def decodificar(caminho, taxa=TAXA):
    """O arquivo inteiro (WAV, MP3, OGG ou FLAC) como PCM de 16 bits estéreo na taxa pedida, em bytes. Levanta se não conseguir."""
    if miniaudio is None:
        raise RuntimeError("a biblioteca miniaudio não está instalada")
    # O arquivo é lido aqui e entregue em bytes: o decode_file do miniaudio abre o caminho pela página de código do Windows e falha
    # (erro -7) em nomes com acento, como "Se não tivesse ido.mp3".
    with open(caminho, 'rb') as f:
        dados = f.read()
    d = miniaudio.decode(dados, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=2, sample_rate=int(taxa))
    return d.samples.tobytes()


def _com_volume(pcm, volume):
    if volume >= 0.999:
        return pcm
    if volume <= 0.0:
        return bytes(len(pcm))
    if audioop is not None:
        return audioop.mul(pcm, 2, volume)
    amostras = array.array('h')
    amostras.frombytes(pcm)
    for i in range(len(amostras)):
        amostras[i] = int(amostras[i] * volume)
    return amostras.tobytes()


def _emenda_suave(velho, novo, frames_fade):
    # Os primeiros `frames_fade` frames passam do que ia tocar (velho) para o que vai tocar (novo), sem estalo.
    k = min(frames_fade, len(novo) // BYTES_POR_FRAME, len(velho) // BYTES_POR_FRAME)
    a = array.array('h'); a.frombytes(velho[:k * BYTES_POR_FRAME])
    b = array.array('h'); b.frombytes(novo[:k * BYTES_POR_FRAME])
    for i in range(k):
        w = (i + 1) / float(k + 1)
        a[2 * i] = int(a[2 * i] * (1.0 - w) + b[2 * i] * w)
        a[2 * i + 1] = int(a[2 * i + 1] * (1.0 - w) + b[2 * i + 1] * w)
    return a.tobytes() + novo[k * BYTES_POR_FRAME:]


def _fatia(dados, frame_inicial, frames):
    """`frames` frames a partir de `frame_inicial` (pode ser negativo: silêncio antes do começo; além do fim: silêncio)."""
    total = len(dados) // BYTES_POR_FRAME
    n = frames * BYTES_POR_FRAME
    if frame_inicial >= total or frame_inicial + frames <= 0:
        return bytes(n)
    antes = max(0, -frame_inicial)
    ini = max(0, frame_inicial)
    fim = min(total, frame_inicial + frames)
    miolo = dados[ini * BYTES_POR_FRAME:fim * BYTES_POR_FRAME]
    depois = frames - antes - (fim - ini)
    return bytes(antes * BYTES_POR_FRAME) + miolo + bytes(depois * BYTES_POR_FRAME)


class GuiaDeAudio:
    """Toca o Áudio Guia pela placa escolhida. O fluxo fica aberto entre um Play e outro por OCIOSO_SEGUNDOS (abrir um driver
    ASIO leva uma fração de segundo); depois disso é fechado, para o ASIO não prender a interface de áudio de outros programas."""

    def __init__(self, indice=None, canal_inicial=0, latencia_ms=0, compensar=True, adiantar_ms=0):
        self.indice = indice
        self.canal_inicial = canal_inicial
        self.latencia_ms = latencia_ms
        self.compensar = compensar
        self.adiantar_ms = adiantar_ms
        self.erro = None
        self.latencia_s = 0.0
        self.ressincronias = 0
        self.volume = 1.0
        self._trava = threading.RLock()
        self._cb_trava = threading.Lock()
        self._fluxo = None
        self._taxa = TAXA
        self._caminho = None
        self._pcm = {}                      # taxa -> PCM do arquivo carregado
        self._dados = None                  # PCM na taxa do fluxo, enquanto toca
        self._prox = 0                      # próximo frame do arquivo que o fluxo vai ler (contínuo entre blocos)
        self._ativo = False
        self._alinhar = None                # (t0 na linha do tempo da placa, frame do arquivo nesse instante)
        self._t0_ref = None
        self._difs = []
        self._f0_comp = 0
        self._offset_relogio = 0.0
        self._ultimo = (0.0, 0, 0)          # (dac, frame, tamanho do bloco) do último bloco, para medir o desvio
        self._timer = None

    # --- carregar ---
    def carregar(self, caminho):
        """Decodifica o arquivo (na taxa de 44100; outra taxa só se a placa exigir). Levanta se não conseguir."""
        with self._trava:
            self._parar()
            self._pcm = {}
            self._caminho = None
            pcm = decodificar(caminho, TAXA)
            self._pcm = {TAXA: pcm}
            self._caminho = caminho
            return len(pcm) // BYTES_POR_FRAME / float(TAXA)

    @property
    def carregado(self):
        return self._caminho is not None

    @property
    def tocando(self):
        return self._ativo

    def _pcm_na_taxa(self, taxa):
        if taxa not in self._pcm:
            self._pcm[taxa] = decodificar(self._caminho, taxa)
        return self._pcm[taxa]

    # --- fluxo ---
    def preparar(self):
        # Chamado pela thread principal quando o Play começa: abre a placa já, antes de o motor MIDI precisar dela.
        with self._trava:
            self._cancelar_timer()
            try:
                self.erro = None
                self._abrir()
            except Exception as e:
                self.erro = str(e) or e.__class__.__name__

    def _abrir(self):
        if self._fluxo is not None:
            return
        _no_principal(self._abrir_aqui)

    def _abrir_aqui(self):
        if self._fluxo is not None:
            return
        if sd is None:
            raise RuntimeError("a biblioteca sounddevice não está instalada")
        info = sd.query_devices(self.indice)
        sistema = sd.query_hostapis(info['hostapi'])['name']
        extra = None
        if sistema == 'ASIO':
            extra = sd.AsioSettings(channel_selectors=[self.canal_inicial, self.canal_inicial + 1])
        elif sistema == 'Windows WASAPI':
            extra = sd.WasapiSettings(auto_convert=True)
        latencia = 'low' if not self.latencia_ms else self.latencia_ms / 1000.0
        taxas = [TAXA]
        padrao = int(info['default_samplerate'])
        if padrao != TAXA:
            taxas.append(padrao)
        ultimo_erro = None
        for taxa in taxas:
            try:
                fluxo = sd.RawOutputStream(samplerate=taxa, channels=2, dtype='int16', device=self.indice,
                                           latency=latencia, callback=self._cb, extra_settings=extra)
                fluxo.start()
            except Exception as e:
                ultimo_erro = e
                continue
            self._fluxo = fluxo
            self._taxa = taxa
            try:
                self.latencia_s = float(fluxo.latency)
            except Exception:
                self.latencia_s = 0.0
            return
        raise ultimo_erro

    def _fechar(self):
        fluxo, self._fluxo = self._fluxo, None
        if fluxo is not None:
            try:
                fluxo.stop()
                fluxo.close()
            except Exception:
                pass

    def fechar(self):
        with self._trava:
            self._parar()
            self._cancelar_timer()
            self._fechar()

    def _cancelar_timer(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _fechar_ocioso(self):
        # Roda numa thread do Timer: quem fecha o driver (ASIO) é a janela principal.
        try:
            import wx
            wx.CallAfter(self._fechar_ocioso_principal)
        except Exception:
            self._fechar_ocioso_principal()

    def _fechar_ocioso_principal(self):
        with self._trava:
            if not self._ativo:
                self._fechar()
                self._timer = None

    # --- a placa pede áudio ---
    def _cb(self, saida, frames, tempo, status):
        n = frames * BYTES_POR_FRAME
        with self._cb_trava:
            dados = self._dados
            if not self._ativo or not dados:
                saida[:n] = bytes(n)
                return
            pos = self._prox
            dac = tempo.outputBufferDacTime
            corrigir = None
            silencio = 0
            if self._alinhar is not None:
                t0_placa, f0 = self._alinhar
                if dac > 0.0:
                    # O 1º frame deste bloco sai pelo conversor em `dac`; a posição f0 do arquivo devia sair em t0_placa.
                    delta = int(round((dac - t0_placa) * self._taxa))
                    if delta >= 0:
                        pos = f0 + delta
                    else:
                        # o bloco sai antes de a posição pedida chegar: silêncio até lá (nunca toca o que vem antes de f0)
                        pos = f0
                        silencio = -delta
                        if silencio >= frames:      # ainda não é a hora: silêncio e tenta no próximo bloco
                            self._ultimo = (dac, f0 + delta, frames)
                            saida[:n] = bytes(n)
                            return
                    self._t0_ref = (t0_placa, f0)
                else:
                    # O driver não informa o instante de saída: cai na compensação pela latência.
                    pos = self._f0_comp
                    self._t0_ref = None
                self._alinhar = None
            elif self._t0_ref is not None and dac > 0.0:
                t0_placa, f0 = self._t0_ref
                esperado = f0 + int(round((dac - t0_placa) * self._taxa))
                # O instante de saída que o driver informa oscila de bloco para bloco (WASAPI, principalmente). Um bloco perdido
                # desloca todos os seguintes; a oscilação vai para os dois lados. Por isso só vale a mediana dos últimos blocos.
                self._difs.append(pos - esperado)
                # a janela cobre uns 300 ms de blocos (com buffers grandes o instante informado oscila mais, e uma janela curta
                # ressincronizava à toa); o limite sobe com o tamanho do bloco
                janela = max(JANELA_MEDIANA, min(JANELA_MAXIMA, int(0.3 * self._taxa / frames)))
                while len(self._difs) > janela:
                    self._difs.pop(0)
                mediana = sorted(self._difs)[len(self._difs) // 2]
                limite = max(RESSINCRONIA_MS, 1000.0 * frames / self._taxa * 0.3) * self._taxa / 1000.0
                if len(self._difs) >= janela and abs(mediana) > limite:
                    corrigir = pos - mediana
                    self._difs = []
                    self.ressincronias += 1
            corpo = _fatia(dados, pos, frames - silencio)
            if corrigir is not None:
                certo = _fatia(dados, corrigir, frames)
                corpo = _emenda_suave(corpo, certo, FADE_FRAMES)
                pos = corrigir
            if silencio:
                corpo = bytes(silencio * BYTES_POR_FRAME) + corpo
            self._prox = pos + frames - silencio
            self._ultimo = (dac, pos - silencio, frames)
            volume = self.volume
        saida[:n] = _com_volume(corpo, volume)

    # --- contrato ---
    def tocar_de(self, pos_segundos, atraso_midi=0.0):
        """Começa a tocar a partir de `pos_segundos` do arquivo, alinhado ao MIDI. `atraso_midi`: quantos segundos DEPOIS de agora
        o MIDI vai de fato passar por essa posição (o laço do Play marca o início 5 ms adiante)."""
        t_entrada = time.perf_counter()        # a posição do MIDI vale `pos_segundos` AGORA (abrir a placa pode demorar: a conta é daqui)
        with self._trava:
            self.erro = None
            self._cancelar_timer()
            if not self._caminho:
                return False
            try:
                self._abrir()
            except Exception as e:
                self.erro = str(e) or e.__class__.__name__
                raise
            dados = self._pcm_na_taxa(self._taxa)
            f0 = int(round(pos_segundos * self._taxa)) + int(round(self.adiantar_ms * self._taxa / 1000.0))
            self._f0_comp = f0 + int(round(self.latencia_s * self._taxa))
            # Relógio da placa em relação ao do computador, medido agora (perf_counter antes e depois da leitura).
            try:
                a = time.perf_counter()
                st = self._fluxo.time
                b = time.perf_counter()
                self._offset_relogio = st - (a + b) / 2.0
            except Exception:
                self._offset_relogio = 0.0
            t0 = t_entrada + atraso_midi
            with self._cb_trava:
                self._dados = dados
                self._prox = f0
                self._ultimo = (0.0, 0, 0)
                self._alinhar = (t0 + self._offset_relogio, f0) if self.compensar else None
                self._t0_ref = None
                self._difs = []
                self._ativo = True
            return True

    def parar(self):
        with self._trava:
            self._parar()

    def _parar(self):
        with self._cb_trava:
            self._ativo = False
            self._dados = None
        if self._fluxo is not None and self._timer is None:
            self._timer = threading.Timer(OCIOSO_SEGUNDOS, self._fechar_ocioso)
            self._timer.daemon = True
            self._timer.start()

    def desvio_ms(self):
        """Quanto o áudio que está saindo AGORA pelo conversor está fora de onde devia estar em relação ao MIDI (positivo: adiantado).
        None se ainda não deu para medir. Só para diagnóstico."""
        with self._cb_trava:
            if self._t0_ref is None or not self._ultimo[2]:
                return None
            dac, pos, bloco = self._ultimo
            t0_placa, f0 = self._t0_ref
        agora_placa = time.perf_counter() + self._offset_relogio
        audivel = pos + (agora_placa - dac) * self._taxa
        esperado = f0 + (agora_placa - t0_placa) * self._taxa
        return (audivel - esperado) * 1000.0 / self._taxa


def criar(config, classe=None):
    """O guia que a configuração pede. Sem escolha ("automático"): WASAPI na saída padrão do Windows. Se a placa escolhida não existe
    mais, cai no automático. Devolve None se não há como tocar (sem sounddevice, miniaudio ou saída)."""
    if not disponivel():
        return None
    sistema = config.get("audio_host") or ""
    indice, canais = None, 0
    if sistema:
        indice = achar_saida(sistema, config.get("audio_saida", ""))
        canais = int(config.get("audio_canais", 0) or 0)
    if indice is None:
        indice = _saida_padrao_wasapi()
        canais = 0
    if indice is None:
        try:
            indice = sd.default.device[1]
            if indice is None or indice < 0:
                return None
        except Exception:
            return None
    return (classe or GuiaDeAudio)(indice, canais, int(config.get("audio_latencia_ms", 0) or 0), bool(config.get("audio_compensar", True)),
                                   int(config.get("audio_adiantar_ms", 0) or 0))


def pcm_de_teste():
    # Três toques curtos (1 kHz) em um segundo, para ouvir a saída escolhida.
    import math
    n = TAXA
    amostras = array.array('h', bytes(n * 4))
    for inicio in (0, TAXA // 3, 2 * TAXA // 3):
        for i in range(TAXA // 25):
            v = int(9000 * math.sin(2 * math.pi * 1000 * i / TAXA) * (1 - i / (TAXA // 25)))
            amostras[2 * (inicio + i)] = v
            amostras[2 * (inicio + i) + 1] = v
    return amostras.tobytes()


class TocadorDeTeste(GuiaDeAudio):
    """Para o botão "Testar a saída de áudio": toca o PCM de teste (três toques) pela saída que está na tela."""

    def tocar_teste(self):
        with self._trava:
            self.erro = None
            self._cancelar_timer()
            self._abrir()
            self._caminho = "(teste)"
            self._pcm = {TAXA: pcm_de_teste()}
            if self._taxa != TAXA:
                self._pcm[self._taxa] = _reamostrar_simples(self._pcm[TAXA], self._taxa)
        return self.tocar_de(0.0)


def _reamostrar_simples(pcm, taxa_destino):
    amostras = array.array('h')
    amostras.frombytes(pcm)
    n = len(amostras) // 2
    total = int(n * taxa_destino / TAXA)
    saida = array.array('h', bytes(total * 4))
    for i in range(total):
        j = min(n - 1, int(i * TAXA / taxa_destino))
        saida[2 * i] = amostras[2 * j]
        saida[2 * i + 1] = amostras[2 * j + 1]
    return saida.tobytes()
