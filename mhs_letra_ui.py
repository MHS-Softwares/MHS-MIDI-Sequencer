# -*- coding: utf-8 -*-
"""
Janelas da letra de karaokê (MHS MIDI Sequencer): o editor de sílabas (EditorLetraDialog), a pergunta do canal da melodia
e a tela do cantor (JanelaCantor). A parte sem janela (ler/gravar a letra, dividir em sílabas, encaixar nas notas) está em mhs_letra.py.
"""
import bisect
import threading

import mido
import wx

from mhs_letra import (LetraModelo, contar_notas_por_canal, escrever_letra, ler_letra, palpite_canal_melodia,
                       texto_para_silabas)

try:
    from mhs_utils import falar_status
except Exception:                           # testes sem o resto do programa
    def falar_status(texto, imediato=False):
        pass


TEMPO = -1      # "canal" do modo por tempo: sem melodia, cada sílaba tem o seu tempo


def rotulos_dos_canais(midi, canais, nomes=None):
    """texto de cada canal na pergunta: diz se a letra do arquivo está nas notas daquele canal ('com letra') ou não ('sem letra').
    -> (rótulo do modo por tempo, [rótulo de cada canal])"""
    fonte, sil = ler_letra(midi)
    tem_arquivo = bool(sil)
    rotulos = []
    for ch in canais:
        nome = (nomes or {}).get(ch, "")
        nome = "" if not nome or nome == "Track %d" % (ch + 1) else " - " + str(nome)
        com = False
        if tem_arquivo:
            try:
                m = LetraModelo.do_midi(midi, ch)
                com = m.lidas > 0 and m.coincidem >= 0.6 * m.lidas
            except Exception:
                com = False
        rotulos.append("Canal %d%s: %s" % (ch + 1, nome, "com letra" if com else "sem letra"))
    tempo = "Sem melodia gravada: editar a letra pelo tempo (colocar no cursor)"
    if tem_arquivo:
        tempo += " - o arquivo já tem letra"
    return tempo, rotulos


def escolher_canal_melodia(parent, midi, canal_atual=None, nomes=None):
    """pergunta qual canal é a melodia (cada canal diz se tem letra ou não; o palpite já vem marcado) ou o modo por tempo (sem melodia).
    Devolve o canal, TEMPO (-1) ou None se cancelou. Se a letra do arquivo não está presa às notas do canal provável, já vem marcado
    o modo por tempo."""
    cont = contar_notas_por_canal(midi)
    canais = sorted(cont)
    palpite = palpite_canal_melodia(midi, canal_atual, nomes) if cont else None
    tempo, por_canal = rotulos_dos_canais(midi, canais, nomes)
    rotulos = [tempo] + por_canal
    marcado = 1 + canais.index(palpite) if palpite in canais else 0
    if palpite in canais:
        try:
            if not LetraModelo.do_midi(midi, palpite).letra_presa_as_notas():
                marcado = 0                                 # a letra existente não bate com as notas: sugere o modo por tempo
        except Exception:
            pass
    dlg = wx.SingleChoiceDialog(parent, "Qual canal é a melodia, a que o cantor segue?", "Letra do Karaokê", rotulos)
    dlg.SetSelection(marcado)
    escolhido = None
    if dlg.ShowModal() == wx.ID_OK:
        sel = dlg.GetSelection()
        escolhido = TEMPO if sel == 0 else canais[sel - 1]
    dlg.Destroy()
    return escolhido


class EditorLetraDialog(wx.Dialog):
    """Editor de sílabas. Dois modos:
    - por NOTA (canal da melodia): a lista tem só as notas da melodia e cada linha é a sílaba da nota;
    - por TEMPO (canal = TEMPO): a lista tem as sílabas da letra, cada uma no seu tempo, sem precisar de notas (MIDIs sem melodia
      gravada ou com a letra sincronizada à parte). I (ou Insert) coloca uma sílaba no ponto do cursor de reprodução.
    O leitor de tela fala só a sílaba. O leitor automático (A) fala cada sílaba na hora certa enquanto a música toca."""

    AJUDA_NOTA = ("Enter edita a sílaba. Delete apaga. I insere empurrando as seguintes; o Insert faz o mesmo. Control Delete apaga puxando as seguintes. "
                  "L liga ou desliga linha nova. V vai para a próxima nota sem letra. F4 cola a letra da música. "
                  "F2 abre a letra em texto com hífens para editar. T mostra a letra para ler, sem hífens. "
                  "A liga ou desliga o leitor automático. Control Z desfaz. Espaço toca a partir daqui. Escape fecha.")
    AJUDA_TEMPO = ("Enter edita a sílaba. Delete remove. I coloca uma sílaba no ponto do cursor de reprodução; o Insert faz o mesmo. "
                   "Shift I coloca entre esta e a próxima. C prepara a letra para colocar tocando a música, e N coloca a próxima "
                   "sílaba no ponto atual. M leva a sílaba selecionada para o ponto atual. Alt seta esquerda ou direita adianta ou atrasa 10 "
                   "ticks; com Shift 1 tick; com Control um tempo. L liga ou desliga linha nova. F2 letra em texto, T para ler, "
                   "A leitor automático, Control Z desfaz, Espaço toca daqui, Escape fecha.")

    def __init__(self, parent, canal, modelo=None):
        titulo = "Letra do Karaokê - por tempo" if canal == TEMPO else "Letra do Karaokê - Canal %d" % (canal + 1)
        super().__init__(parent, title=titulo, size=(540, 460), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.parent = parent
        self.canal = canal
        if modelo is None:
            if canal == TEMPO:
                fonte, sil = ler_letra(parent.midi_file)
                modelo = LetraModelo.por_tempo(sil, fonte)
            else:
                modelo = LetraModelo.do_midi(parent.midi_file, canal)
        self.modelo = modelo
        self.undo = []
        self.modificado = False
        self.idx = 0
        self.preview_timer = None
        self.preview_note = None
        self.fila = []               # letra preparada para colocar no tempo da música (tecla C, depois N)
        self.silencio = False        # os testes ligam: sem caixas de pergunta de verdade
        cfg = getattr(parent, "config", None)
        self.leitor_auto = bool(cfg.get("letra_leitor_auto", False)) if isinstance(cfg, dict) else False
        self._ultimo_lido = None

        v = wx.BoxSizer(wx.VERTICAL)
        self.dummy_focus = wx.Panel(self, size=(0, 0), style=wx.WANTS_CHARS)
        v.Add(self.dummy_focus, 0)
        self.lbl = wx.StaticText(self, label="")
        v.Add(self.lbl, 0, wx.ALL, 6)
        self.lista = wx.ListBox(self, style=wx.LB_SINGLE)
        v.Add(self.lista, 1, wx.EXPAND | wx.ALL, 6)
        self.SetSizer(v)

        self.lista.Bind(wx.EVT_SET_FOCUS, lambda e: self.dummy_focus.SetFocus())
        self.dummy_focus.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.Bind(wx.EVT_CLOSE, self.on_fechar)
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, lambda e: self.tick_leitor())
        if self.leitor_auto:
            self.timer.Start(40)

        self.idx = self._nota_do_cursor()
        self.reconstruir()
        wx.CallAfter(self.dummy_focus.SetFocus)
        wx.CallLater(500, self.falar_abertura)

    # --- util
    @property
    def tempo(self):
        return self.modelo.modo_tempo

    def _tick_agora(self):
        try:
            return int(self.parent.get_tick_at_sec(getattr(self.parent, "current_playback_time", 0.0)))
        except Exception:
            return None

    def _nota_do_cursor(self):
        if not self.modelo.notas:
            return 0
        tick = self._tick_agora() or 0
        ticks = [n["tick"] for n in self.modelo.notas]
        return min(len(ticks) - 1, bisect.bisect_left(ticks, tick))

    def _resumo(self):
        if self.tempo:
            return "%d palavras" % self.modelo.total_silabas()
        return "%d notas, %d sílabas" % (len(self.modelo.notas), self.modelo.total_silabas())

    def reconstruir(self):
        self.lista.Set([self.modelo.fala(i) for i in range(len(self.modelo.notas))])
        self.lbl.SetLabel(self._resumo())
        if self.modelo.notas:
            self.idx = max(0, min(self.idx, len(self.modelo.notas) - 1))
            self.lista.SetSelection(self.idx)

    def atualizar_item(self, i):
        self.lista.SetString(i, self.modelo.fala(i))
        self.lbl.SetLabel(self._resumo())

    def falar_abertura(self):
        if not self.modelo.notas:
            if self.tempo:
                falar_status("Letra por tempo, ainda vazia. I coloca uma sílaba no ponto do cursor. C prepara a letra para colocar "
                             "tocando a música. F1 fala todas as teclas.", imediato=True)
            else:
                falar_status("Este canal não tem notas.", imediato=True)
            return
        if self.tempo:
            falar_status("Letra por tempo. %s. %s" % (self._resumo(), self.modelo.fala(self.idx)), imediato=True)
        else:
            falar_status("Letra, canal %d. %s. %s" % (self.canal + 1, self._resumo(), self.modelo.fala(self.idx)), imediato=True)

    def ir_para(self, i, falar=True):
        if not self.modelo.notas:
            return
        self.idx = max(0, min(len(self.modelo.notas) - 1, i))
        self.lista.SetSelection(self.idx)
        if falar:
            falar_status(self.modelo.fala(self.idx), imediato=True)
        self.tocar_nota(self.idx)
        self.posicionar_reproducao(self.idx)

    def _estado(self):
        return {"m": self.modelo.estado(), "fila": list(self.fila)}

    def registrar_desfazer(self):
        self.undo.append(self._estado())
        if len(self.undo) > 60:
            self.undo.pop(0)
        self.modificado = True

    # --- som: a nota toca ao navegar, como no Event List (no modo por tempo não há nota para tocar)
    def matar_nota_preview(self):
        if self.preview_timer:
            self.preview_timer.cancel()
            self.preview_timer = None
        saida = getattr(self.parent, "output", None)
        if self.preview_note is not None and saida:
            try:
                saida.send(mido.Message("note_off", channel=self.canal, note=self.preview_note, velocity=0))
            except Exception:
                pass
        self.preview_note = None

    def tocar_nota(self, i):
        saida = getattr(self.parent, "output", None)
        n = self.modelo.notas[i]
        if not saida or getattr(self.parent, "tocando", False) or n.get("nota") is None or self.canal < 0:
            return
        self.matar_nota_preview()
        try:
            saida.send(mido.Message("note_on", channel=self.canal, note=n["nota"], velocity=90))
        except Exception:
            return
        self.preview_note = n["nota"]
        try:
            dur = self.parent.get_sec_at_tick(n["tick"] + n["dur"]) - self.parent.get_sec_at_tick(n["tick"])
        except Exception:
            dur = 0.3
        self.preview_timer = threading.Timer(min(0.4, max(0.05, dur)), self.matar_nota_preview)
        self.preview_timer.start()

    def posicionar_reproducao(self, i):
        """Espaço toca a partir desta nota/sílaba: leva o cursor de reprodução do programa até ela"""
        try:
            alvo = max(0.0, self.parent.get_sec_at_tick(self.modelo.notas[i]["tick"]) - 0.001)
            if getattr(self.parent, "tocando", False):
                self.parent.all_notes_off()
            self.parent.current_playback_time = alvo
            self.parent.last_start_time = alvo
            self.parent.seek_flag = True
        except Exception:
            pass

    # --- leitor automático: fala cada sílaba na hora certa enquanto a música toca (como o exibidor de letras do Winamp)
    def alternar_leitor(self):
        self.leitor_auto = not self.leitor_auto
        cfg = getattr(self.parent, "config", None)
        if isinstance(cfg, dict):
            cfg["letra_leitor_auto"] = self.leitor_auto
        self._ultimo_lido = None
        if self.leitor_auto:
            self.timer.Start(40)
        else:
            self.timer.Stop()
        falar_status("Leitor automático ligado." if self.leitor_auto else "Leitor automático desligado.", imediato=True)

    def tick_leitor(self):
        """chamado pelo relógio (40 ms): com a música tocando, fala a sílaba que acabou de chegar e acompanha a seleção"""
        if not self.leitor_auto:
            return
        if not getattr(self.parent, "tocando", False):
            self._ultimo_lido = None
            return
        tick = self._tick_agora()
        ticks = [n["tick"] for n in self.modelo.notas]
        if tick is None or not ticks:
            return
        i = bisect.bisect_right(ticks, tick + 2) - 1          # 2 ticks de antecedência: a fala demora um pouco
        if self._ultimo_lido is None:                          # começou a tocar agora: o que já passou não é lido
            self._ultimo_lido = bisect.bisect_right(ticks, tick - 1) - 1
        if i != self._ultimo_lido and i >= 0:
            self._ultimo_lido = i
            self.idx = i
            self.lista.SetSelection(i)
            s = self.modelo.slots[i]
            if s:
                falar_status(s["texto"], imediato=True)

    # --- teclas
    def on_key(self, event):
        code = event.GetKeyCode()
        ctrl, shift, alt = event.ControlDown(), event.ShiftDown(), event.AltDown()
        n = len(self.modelo.notas)
        if code == wx.WXK_ESCAPE:
            self.fechar()
            return
        if code == wx.WXK_F1:
            falar_status(self.AJUDA_TEMPO if self.tempo else self.AJUDA_NOTA, imediato=True)
            return
        if code == wx.WXK_SPACE and not (shift or alt):
            if ctrl:
                if hasattr(self.parent, "toggle_pausa"):
                    self.parent.toggle_pausa(None)
            elif hasattr(self.parent, "toggle_reproducao"):
                self.parent.toggle_reproducao(None)
            return
        if code == wx.WXK_F4 or (code in (ord("V"), ord("v")) and ctrl and not shift and not alt):
            if self.tempo:
                falar_status("No modo por tempo, use C para colocar a letra no tempo da música, ou I para uma sílaba só.", imediato=True)
            else:
                self.colar_texto(usar_area=(code != wx.WXK_F4))
            return
        if code in (ord("Z"), ord("z")) and ctrl and not shift and not alt:
            self.desfazer()
            return
        if code in (ord("A"), ord("a")) and not (ctrl or alt or shift):
            self.alternar_leitor()
            return
        # o Insert é a tecla modificadora do NVDA e não chega ao programa: o I (ou Ctrl+I, como no Event List) faz o mesmo
        eh_inserir = (code == wx.WXK_INSERT or code in (ord("I"), ord("i"))) and not alt
        if self.tempo:
            if eh_inserir:
                entre = (ctrl and code == wx.WXK_INSERT) or (shift and code in (ord("I"), ord("i")))
                self.inserir_depois() if entre else self.inserir_no_cursor()
                return
            if code in (ord("C"), ord("c")) and not (ctrl or alt or shift):
                self.iniciar_captura()
                return
            if code in (ord("N"), ord("n")) and not (ctrl or alt or shift):
                self.colocar_proxima()
                return
            if n and code in (ord("M"), ord("m")) and not (ctrl or alt or shift):
                self.marcar_agora()
                return
            if n and alt and code in (wx.WXK_LEFT, wx.WXK_RIGHT):
                passo = 1 if shift else (max(1, getattr(self.parent.midi_file, "ticks_per_beat", 480)) if ctrl else 10)
                self.mover(-passo if code == wx.WXK_LEFT else passo)
                return
        if not n:
            event.Skip()
            return
        if code == wx.WXK_UP:
            self.ir_para(self.idx - 1)
        elif code == wx.WXK_DOWN:
            self.ir_para(self.idx + 1)
        elif code == wx.WXK_PAGEUP:
            self.ir_para(self.idx - 10)
        elif code == wx.WXK_PAGEDOWN:
            self.ir_para(self.idx + 10)
        elif code == wx.WXK_HOME:
            self.ir_para(0)
        elif code == wx.WXK_END:
            self.ir_para(n - 1)
        elif code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.editar()
        elif code == wx.WXK_DELETE:
            self.apagar(puxando=ctrl)
        elif eh_inserir:
            self.inserir()
        elif code in (ord("L"), ord("l")) and not (ctrl or alt):
            self.alternar_linha()
        elif code in (ord("V"), ord("v")) and not (ctrl or alt):
            self.proxima_vazia(retroceder=shift)
        elif code == wx.WXK_F2 and not (ctrl or alt):
            self.abrir_bloco()
        elif code in (ord("T"), ord("t")) and not (ctrl or alt or shift):
            self.abrir_leitura()
        else:
            event.Skip()

    # --- ações
    def _perguntar(self, titulo, valor=""):
        """abre a caixa de texto da sílaba; os testes trocam por uma função que devolve o texto"""
        dlg = wx.TextEntryDialog(self, "Sílaba (hífen no fim: a palavra continua; / no começo: linha nova; vazio apaga):", titulo, valor)
        ok = dlg.ShowModal() == wx.ID_OK
        texto = dlg.GetValue() if ok else None
        dlg.Destroy()
        wx.CallAfter(self.dummy_focus.SetFocus)
        return texto

    def _perguntar_texto_longo(self):
        dlg = wx.TextEntryDialog(self, "Cole a letra (uma frase por linha; hífen separa sílabas; _ pula uma nota). "
                                 "Começa na nota atual:", "Colar letra", "", style=wx.TE_MULTILINE | wx.OK | wx.CANCEL)
        texto = dlg.GetValue() if dlg.ShowModal() == wx.ID_OK else ""
        dlg.Destroy()
        wx.CallAfter(self.dummy_focus.SetFocus)
        return texto

    def _area_de_transferencia(self):
        texto = ""
        if wx.TheClipboard.Open():
            try:
                dado = wx.TextDataObject()
                if wx.TheClipboard.GetData(dado):
                    texto = dado.GetText()
            finally:
                wx.TheClipboard.Close()
        return texto

    def desfazer(self):
        if self.undo:
            est = self.undo.pop()
            self.modelo.restaurar_estado(est["m"])
            self.fila = list(est["fila"])
            self.idx = min(self.idx, max(0, len(self.modelo.notas) - 1))
            self.reconstruir()
            falar_status("Desfeito. %s" % (self.modelo.fala(self.idx) if self.modelo.notas else "Lista vazia."), imediato=True)
        else:
            falar_status("Nada para desfazer.", imediato=True)

    def editar(self):
        texto = self._perguntar("Editar sílaba", self.modelo.texto_de_edicao(self.idx))
        if texto is None:
            return
        self.registrar_desfazer()
        self.modelo.definir(self.idx, texto)
        self.atualizar_item(self.idx)
        falar_status("Apagada." if not self.modelo.slots[self.idx] else "Gravada: " + self.modelo.fala(self.idx), imediato=True)

    def apagar(self, puxando=False):
        if self.tempo:                                   # no modo por tempo a sílaba some da lista (e do arquivo)
            self.registrar_desfazer()
            self.modelo.remover_item(self.idx)
            self.reconstruir()
            falar_status("Removida. %s" % (self.modelo.fala(self.idx) if self.modelo.notas else "Lista vazia."), imediato=True)
            return
        if not self.modelo.slots[self.idx]:
            falar_status("Já está sem letra.", imediato=True)
            return
        self.registrar_desfazer()
        if puxando:
            self.modelo.apagar_puxando(self.idx)
            self.reconstruir()
            falar_status("Apagada, seguintes puxadas. %s" % self.modelo.fala(self.idx), imediato=True)
        else:
            self.modelo.apagar(self.idx)
            self.atualizar_item(self.idx)
            falar_status("Apagada.", imediato=True)

    def inserir(self):
        texto = self._perguntar("Inserir sílaba (empurra as seguintes)")
        if not texto or not texto.strip():
            return
        self.registrar_desfazer()
        if self.modelo.inserir_empurrando(self.idx, texto):
            self.reconstruir()
            falar_status("Inserida: " + self.modelo.fala(self.idx), imediato=True)
        else:
            self.undo.pop()
            falar_status("Não cabe: a última nota já tem sílaba. Apague uma sílaba no fim antes.", imediato=True)

    # --- só no modo por tempo
    def inserir_no_cursor(self):
        """I (ou Insert): coloca uma sílaba no ponto do cursor de reprodução (o ponto de agora, se a música estiver tocando)"""
        tick = self._tick_agora()
        if tick is None:
            falar_status("Não consegui ler o ponto do cursor.", imediato=True)
            return
        texto = self._perguntar("Colocar sílaba no ponto do cursor")
        item = LetraModelo.ler_edicao(texto) if texto else None
        if item is None:
            return
        self.registrar_desfazer()
        self.idx = self.modelo.inserir_item_tempo(tick, item)
        self.reconstruir()
        falar_status("Colocada: " + self.modelo.fala(self.idx), imediato=True)

    def inserir_depois(self):
        """Shift+I (ou Ctrl+Insert): coloca uma sílaba entre a selecionada e a próxima"""
        if not self.modelo.notas:
            self.inserir_no_cursor()
            return
        t0 = self.modelo.notas[self.idx]["tick"]
        t1 = self.modelo.notas[self.idx + 1]["tick"] if self.idx + 1 < len(self.modelo.notas) else t0 + max(
            2, getattr(self.parent.midi_file, "ticks_per_beat", 480) // 2)
        texto = self._perguntar("Colocar sílaba depois desta")
        item = LetraModelo.ler_edicao(texto) if texto else None
        if item is None:
            return
        self.registrar_desfazer()
        self.idx = self.modelo.inserir_item_tempo((t0 + t1) // 2 if t1 - t0 > 1 else t0 + 1, item)
        self.reconstruir()
        falar_status("Colocada: " + self.modelo.fala(self.idx), imediato=True)

    def marcar_agora(self):
        """M: leva a sílaba selecionada para o ponto atual da música (toque a música e aperte M na hora certa)"""
        tick = self._tick_agora()
        if tick is None:
            return
        self.registrar_desfazer()
        self.idx = self.modelo.mover_para(self.idx, tick)
        self.reconstruir()
        falar_status("Movida para o ponto atual: " + self.modelo.fala(self.idx), imediato=True)

    def mover(self, delta):
        self.registrar_desfazer()
        self.idx = self.modelo.mover(self.idx, delta)
        self.reconstruir()
        self.posicionar_reproducao(self.idx)
        falar_status("Adiantada." if delta < 0 else "Atrasada.", imediato=True)

    def iniciar_captura(self):
        """C: prepara a letra (colada como texto); depois, tocando a música, N coloca a próxima sílaba no ponto atual"""
        texto = self._perguntar_texto_longo()
        itens = [it for it in texto_para_silabas(texto) if not it.get("vazio")]
        if not itens:
            return
        self.registrar_desfazer()
        self.fila = itens
        falar_status("Letra preparada: %d sílabas. Toque a música e aperte N a cada sílaba. Primeira: %s." % (len(itens), itens[0]["texto"]),
                     imediato=True)

    def colocar_proxima(self):
        if not self.fila:
            falar_status("Não há letra preparada. Aperte C para colar a letra.", imediato=True)
            return
        tick = self._tick_agora()
        if tick is None:
            return
        self.registrar_desfazer()
        item = self.fila.pop(0)
        self.idx = self.modelo.inserir_item_tempo(tick, item)
        self.reconstruir()
        if self.fila:
            falar_status("%s. Próxima: %s." % (item["texto"], self.fila[0]["texto"]), imediato=True)
        else:
            falar_status("%s. Era a última sílaba." % item["texto"], imediato=True)

    def alternar_linha(self):
        if not self.modelo.slots[self.idx]:
            falar_status("Esta nota está sem letra.", imediato=True)
            return
        self.registrar_desfazer()
        r = self.modelo.alternar_linha(self.idx)
        self.atualizar_item(self.idx)
        falar_status("Linha nova ligada." if r else "Linha nova desligada.", imediato=True)

    def proxima_vazia(self, retroceder=False):
        n = len(self.modelo.notas)
        passo = -1 if retroceder else 1
        i = self.idx + passo
        while 0 <= i < n:
            if not self.modelo.slots[i]:
                self.ir_para(i)
                return
            i += passo
        falar_status("Não há mais notas sem letra.", imediato=True)

    def _leitura(self, texto, pos):
        """abre a letra só para leitura. Os testes trocam por uma função."""
        dlg = LetraLeituraDialog(self, texto, pos)
        dlg.ShowModal()
        dlg.Destroy()
        wx.CallAfter(self.dummy_focus.SetFocus)

    def abrir_leitura(self):
        """T: a letra como texto normal (sem hífens), só para ler, como o exibidor de letras do Winamp"""
        texto, posicoes = self.modelo.para_texto_leitura()
        pos = posicoes.get(self.idx)
        if pos is None:
            depois = [p for i, p in posicoes.items() if i >= self.idx]
            pos = min(depois) if depois else 0
        self._leitura(texto, pos)

    def _bloco_de_notas(self, texto, pos, inicio):
        """abre o bloco de notas; devolve o texto novo ou None. Os testes trocam por uma função."""
        dlg = TextoLetraDialog(self, texto, pos, self.modelo, inicio)
        novo = dlg.texto() if dlg.ShowModal() == wx.ID_OK else None
        dlg.Destroy()
        wx.CallAfter(self.dummy_focus.SetFocus)
        return novo

    def abrir_bloco(self):
        """F2: a letra inteira como texto com hífens; ao aplicar, reencaixa as sílabas (nas notas, ou nos tempos que elas já têm)"""
        texto, posicoes, inicio = self.modelo.para_texto()
        if not texto:
            if self.tempo:
                falar_status("A letra ainda está vazia. Use I ou C para colocar sílabas.", imediato=True)
                return
            inicio = self.idx                       # letra vazia: começa na nota atual
        pos = posicoes.get(self.idx)
        if pos is None:
            depois = [p for i, p in posicoes.items() if i >= self.idx]
            pos = min(depois) if depois else 0
        novo = self._bloco_de_notas(texto, pos, inicio)
        if novo is None or novo == texto:
            return
        self.registrar_desfazer()
        colocadas, falta = self.modelo.aplicar_texto(novo, inicio)
        if colocadas is None:
            self.undo.pop()
            ok, msg = self.modelo.validar_texto(novo, inicio)
            falar_status(msg or "Não coube: faltam %d notas." % falta, imediato=True)
            return
        self.reconstruir()
        falar_status("Letra atualizada: %d sílabas." % colocadas, imediato=True)

    def colar_texto(self, usar_area=False):
        texto = self._area_de_transferencia() if usar_area else ""
        if not texto.strip():
            texto = self._perguntar_texto_longo()
        if not texto.strip():
            return
        self.registrar_desfazer()
        colocadas, sobraram = self.modelo.distribuir(texto, self.idx)
        self.reconstruir()
        if sobraram:
            falar_status("%d sílabas colocadas. Faltaram notas para %d sílabas." % (colocadas, sobraram), imediato=True)
        else:
            falar_status("%d sílabas colocadas." % colocadas, imediato=True)

    # --- fechar: grava no MIDI do programa
    def aplicar(self):
        if self.modificado:
            escrever_letra(self.parent.midi_file, self.modelo.silabas())
            self.parent.dirty = True
            if hasattr(self.parent, "atualizar_titulo"):
                try:
                    self.parent.atualizar_titulo()
                except Exception:
                    pass

    def fechar(self):
        self.timer.Stop()
        self.matar_nota_preview()
        if getattr(self.parent, "tocando", False) and hasattr(self.parent, "toggle_reproducao"):
            self.parent.toggle_reproducao(None)
        self.aplicar()
        if self.IsModal():
            self.EndModal(wx.ID_OK if self.modificado else wx.ID_CANCEL)

    def on_fechar(self, event):
        self.fechar()


class TextoLetraDialog(wx.Dialog):
    """Bloco de notas da letra: a música inteira como texto, para ver as palavras e as linhas e editar de uma vez.
    Hífen separa sílabas (co-ra-ção), _ é uma nota sem sílaba, cada linha do texto é uma frase. Ctrl+Enter aplica, Esc cancela."""

    AJUDA = ("Bloco de notas da letra. Cada linha é uma frase. Hífen separa as sílabas, como co hífen ra hífen ção. "
             "O sublinhado é uma nota sem sílaba. Control Enter aplica. Escape cancela. F6 fala quantas sílabas e quantas notas.")

    def __init__(self, parent, texto, pos, modelo, inicio):
        super().__init__(parent, title="Letra em texto (bloco de notas)", size=(680, 480), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.modelo = modelo
        self.inicio = inicio
        self.original = texto
        self.silencio = False
        v = wx.BoxSizer(wx.VERTICAL)
        v.Add(wx.StaticText(self, label="&Letra (uma frase por linha; hífen separa sílabas; _ é nota sem sílaba):"), 0, wx.ALL, 6)
        self.txt = wx.TextCtrl(self, value=texto, style=wx.TE_MULTILINE | wx.TE_RICH2)
        self.txt.SetName("Letra em texto")
        v.Add(self.txt, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 6)
        self.lbl = wx.StaticText(self, label="")
        v.Add(self.lbl, 0, wx.ALL, 6)
        botoes = wx.StdDialogButtonSizer()
        self.btn_ok = wx.Button(self, wx.ID_OK, "&Aplicar (Ctrl+Enter)")
        self.btn_cancel = wx.Button(self, wx.ID_CANCEL, "&Cancelar (Esc)")
        botoes.AddButton(self.btn_ok)
        botoes.AddButton(self.btn_cancel)
        botoes.Realize()
        v.Add(botoes, 0, wx.EXPAND | wx.ALL, 6)
        self.SetSizer(v)
        self.txt.Bind(wx.EVT_TEXT, lambda e: self.atualizar_contagem())
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.btn_ok.Bind(wx.EVT_BUTTON, lambda e: self.aplicar())
        self.btn_cancel.Bind(wx.EVT_BUTTON, lambda e: self.cancelar())
        self.atualizar_contagem()
        self.txt.SetInsertionPoint(max(0, min(pos, len(texto))))
        wx.CallAfter(self.txt.SetFocus)

    def texto(self):
        return self.txt.GetValue().replace("\r\n", "\n")

    def contagem(self):
        return self.modelo.contar_texto(self.texto(), self.inicio)

    def fala_contagem(self):
        nec, disp = self.contagem()
        silabas = sum(1 for it in texto_para_silabas(self.texto()) if not it.get("vazio"))
        return "%d sílabas em %d notas. %d notas disponíveis." % (silabas, nec, disp)

    def atualizar_contagem(self):
        ok, msg = self.modelo.validar_texto(self.texto(), self.inicio)
        self.lbl.SetLabel(self.fala_contagem() + ("" if ok else " NÃO CABE: " + msg))

    def avisar(self, texto):
        falar_status(texto, imediato=True)
        if not self.silencio:
            wx.MessageBox(texto, "Letra do Karaokê", wx.OK | wx.ICON_WARNING, self)

    def aplicar(self):
        ok, msg = self.modelo.validar_texto(self.texto(), self.inicio)
        if not ok:
            self.avisar(msg)
            return
        if not self.texto().strip() and self.original.strip():
            if not self.silencio and wx.MessageBox("O texto está vazio: isto apaga a letra inteira. Continuar?", "Letra do Karaokê",
                                                    wx.YES_NO | wx.ICON_QUESTION, self) != wx.YES:
                return
        self.EndModal(wx.ID_OK)

    def cancelar(self):
        if self.texto() != self.original and not self.silencio:
            if wx.MessageBox("Descartar as mudanças no texto?", "Letra do Karaokê", wx.YES_NO | wx.ICON_QUESTION, self) != wx.YES:
                return
        self.EndModal(wx.ID_CANCEL)

    def on_key(self, e):
        c = e.GetKeyCode()
        if c in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and e.ControlDown():
            self.aplicar()
        elif c == wx.WXK_ESCAPE:
            self.cancelar()
        elif c == wx.WXK_F1:
            falar_status(self.AJUDA, imediato=True)
        elif c == wx.WXK_F6:
            falar_status(self.fala_contagem(), imediato=True)
        else:
            e.Skip()


class LetraLeituraDialog(wx.Dialog):
    """Só leitura: a letra como texto normal (palavras inteiras, sem hífens), uma frase por linha, como o exibidor de letras do Winamp.
    Dá para navegar com as setas, selecionar e copiar (Ctrl+A, Ctrl+C). Esc ou Enter fecha."""

    AJUDA = "Letra só para leitura. Use as setas para ler linha por linha. F6 fala quantas linhas e palavras. Escape ou Enter fecha."

    def __init__(self, parent, texto, pos):
        super().__init__(parent, title="Letra (somente leitura)", size=(680, 480), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.texto_original = texto
        v = wx.BoxSizer(wx.VERTICAL)
        v.Add(wx.StaticText(self, label="&Letra:"), 0, wx.ALL, 6)
        self.txt = wx.TextCtrl(self, value=texto if texto else "Este canal ainda não tem letra.",
                               style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        self.txt.SetName("Letra")
        v.Add(self.txt, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 6)
        self.btn = wx.Button(self, wx.ID_CLOSE, "&Fechar (Esc)")
        v.Add(self.btn, 0, wx.ALIGN_RIGHT | wx.ALL, 6)
        self.SetSizer(v)
        self.btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.txt.SetInsertionPoint(max(0, min(pos, len(texto))))
        wx.CallAfter(self.txt.SetFocus)

    def resumo(self):
        linhas = [l for l in self.texto_original.split("\n") if l.strip()]
        palavras = len(self.texto_original.split())
        return "%d linhas, %d palavras." % (len(linhas), palavras)

    def on_key(self, e):
        c = e.GetKeyCode()
        if c in (wx.WXK_ESCAPE, wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.EndModal(wx.ID_CLOSE)
        elif c == wx.WXK_F1:
            falar_status(self.AJUDA, imediato=True)
        elif c == wx.WXK_F6:
            falar_status(self.resumo(), imediato=True)
        else:
            e.Skip()


class JanelaCantor(wx.Frame):
    """Janela de karaokê para quem canta: a frase atual em letra grande, a sílaba cantada colorida, a próxima frase embaixo
    e pontinhos de entrada antes da primeira sílaba. Segue o cursor de reprodução do programa; abre sem tirar o foco do teclado."""

    COR_FUNDO = (20, 20, 20)
    COR_TEXTO = (240, 240, 240)
    COR_CANTADA = (255, 214, 0)

    def __init__(self, parent):
        super().__init__(parent, title="Letra do Karaokê - tela do cantor", size=(980, 420))
        self.parent = parent
        self.fonte_pt = 54
        self.linhas = []
        self.painel = wx.Panel(self)
        self.painel.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.painel.Bind(wx.EVT_PAINT, self.on_paint)
        self.painel.Bind(wx.EVT_SIZE, lambda e: (self.painel.Refresh(), e.Skip()))
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.Bind(wx.EVT_CLOSE, self.on_fechar)
        self.carregar()
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, lambda e: self.painel.Refresh())
        self.timer.Start(40)

    def carregar(self):
        """lê a letra do MIDI do programa e monta as linhas [(segundo, texto, continua)]"""
        _, silabas = ler_letra(self.parent.midi_file)
        self.linhas = []
        for s in silabas:
            try:
                seg = self.parent.get_sec_at_tick(s["tick"])
            except Exception:
                seg = 0.0
            if s["linha"] or not self.linhas:
                self.linhas.append([])
            self.linhas[-1].append((seg, s["texto"], s["cont"]))

    def on_key(self, e):
        c = e.GetKeyCode()
        if c == wx.WXK_ESCAPE:
            self.Close()
        elif c in (ord("+"), ord("="), wx.WXK_ADD, wx.WXK_NUMPAD_ADD):
            self.fonte_pt = min(120, self.fonte_pt + 4)
            self.painel.Refresh()
        elif c in (ord("-"), wx.WXK_SUBTRACT, wx.WXK_NUMPAD_SUBTRACT):
            self.fonte_pt = max(16, self.fonte_pt - 4)
            self.painel.Refresh()
        elif c == wx.WXK_F5:
            self.carregar()
            self.painel.Refresh()
        else:
            e.Skip()

    def posicao(self, t):
        """(linha atual, índice da última sílaba já começada nela ou -1). A próxima linha vira a atual 1,5 s antes de começar."""
        atual = 0
        for li, linha in enumerate(self.linhas):
            if t >= linha[0][0] - 1.5:
                atual = li
        ultima = -1
        for si, (seg, _, _) in enumerate(self.linhas[atual]):
            if seg <= t + 0.02:
                ultima = si
        return atual, ultima

    @staticmethod
    def pedacos(linha):
        return [txt + ("" if cont else " ") for _, txt, cont in linha]

    def _fonte(self, pt):
        return wx.Font(pt, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)

    def desenhar_linha(self, dc, y, largura, linha, ultima):
        ped = self.pedacos(linha)
        pt = self.fonte_pt
        while pt > 14:
            dc.SetFont(self._fonte(pt))
            if dc.GetTextExtent("".join(ped))[0] <= largura - 40:
                break
            pt -= 2
        dc.SetFont(self._fonte(pt))
        x = (largura - dc.GetTextExtent("".join(ped))[0]) // 2
        for i, p in enumerate(ped):
            dc.SetTextForeground(wx.Colour(*(self.COR_CANTADA if i <= ultima else self.COR_TEXTO)))
            dc.DrawText(p, x, y)
            x += dc.GetTextExtent(p)[0]
        return dc.GetCharHeight()

    def on_paint(self, _):
        dc = wx.AutoBufferedPaintDC(self.painel)
        larg, alt = self.painel.GetClientSize()
        dc.SetBackground(wx.Brush(wx.Colour(*self.COR_FUNDO)))
        dc.Clear()
        if not self.linhas:
            dc.SetFont(wx.Font(24, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
            dc.SetTextForeground(wx.Colour(*self.COR_TEXTO))
            dc.DrawText("Este MIDI ainda não tem letra.", 30, alt // 2 - 20)
            return
        t = getattr(self.parent, "current_playback_time", 0.0)
        atual, ultima = self.posicao(t)
        linha = self.linhas[atual]
        falta = linha[0][0] - t
        h = self.desenhar_linha(dc, alt // 4, larg, linha, ultima)
        if 0 < falta <= 4.0:                                  # pontinhos de entrada
            dc.SetTextForeground(wx.Colour(*self.COR_CANTADA))
            dc.SetFont(self._fonte(28))
            dc.DrawText("● " * int(falta + 0.999), 30, max(0, alt // 4 - 44))
        if atual + 1 < len(self.linhas):
            self.desenhar_linha(dc, alt // 4 + h + 30, larg, self.linhas[atual + 1], -1)

    def on_fechar(self, e):
        self.timer.Stop()
        if getattr(self.parent, "janela_cantor", None) is self:
            self.parent.janela_cantor = None
        self.Destroy()
