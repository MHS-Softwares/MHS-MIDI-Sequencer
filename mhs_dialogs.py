import wx
import mido
import threading
import random
import time
import os
import re
import copy
import json

# Importamos as ferramentas do arquivo que criamos!
from mhs_utils import (
    falar_status, get_nome_nota, get_cc_name, NRPN_MSB_NAMES, get_drum_name, CONFIG_FILE,
    REV_MSB_LIST, CHO_MSB_LIST, VARIATION_EFEITOS_LIST, DSP_PARAM_NAMES,
    DSP_LONG_PARAM_INDICES, DSP_PARAM_MAX, DSP_PARAM_OPTIONS, nomes_presets,
    OFFSETS_REV_PARAMS, OFFSETS_CHO_PARAMS, DRUM_NRPN_PARAMS, DRUM_NRPN_DEFAULTS,
    achar_porta_certa, verificar_nova_versao,
    listar_ins_online, pasta_ins_files, baixar_e_extrair_ins
)


def _rotulo_valor_dsp(nome, valor, opcoes):
    # Parâmetro de DSP que é uma lista curta de opções com nome (ex: "Device":
    # Transistor, Vintage Tube, ...) - fala o NOME da opção pro NVDA em vez
    # de só o número puro. `opcoes` = (valor_mínimo, [nomes]) ou None (a
    # maioria dos parâmetros é contínua e continua falando só o número).
    if opcoes:
        min_v, nomes_opcao = opcoes
        j = valor - min_v
        if 0 <= j < len(nomes_opcao):
            return f"{nome}: {nomes_opcao[j]} ({valor})"
    return f"{nome}: {valor}"




class SelecaoEventosDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="Seleção de Eventos (Filtro)", size=(400, 480))
        self.parent = parent
        self.preview_note = None
        self.preview_timer = None
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Bloco de Notas (Pitch)
        self.chk_nota = wx.CheckBox(self, label="Filtrar por Notas (Pitch)")
        self.chk_nota.SetValue(True)
        sizer.Add(self.chk_nota, 0, wx.ALL, 10)
        
        self.panel_nota = wx.Panel(self)
        sz_nota = wx.BoxSizer(wx.VERTICAL)
        sz_nota.Add(wx.StaticText(self.panel_nota, label="Nota Mínima:"), 0, wx.LEFT, 5)
        self.sp_nota_min = wx.SpinCtrl(self.panel_nota, value="0", min=0, max=127)
        sz_nota.Add(self.sp_nota_min, 0, wx.EXPAND | wx.ALL, 5)
        sz_nota.Add(wx.StaticText(self.panel_nota, label="Nota Máxima:"), 0, wx.LEFT, 5)
        self.sp_nota_max = wx.SpinCtrl(self.panel_nota, value="127", min=0, max=127)
        sz_nota.Add(self.sp_nota_max, 0, wx.EXPAND | wx.ALL, 5)
        self.panel_nota.SetSizer(sz_nota)
        sizer.Add(self.panel_nota, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 15)

        # Bloco de Velocity
        self.chk_vel = wx.CheckBox(self, label="Filtrar por Velocity")
        self.chk_vel.SetValue(False)
        sizer.Add(self.chk_vel, 0, wx.ALL, 10)
        
        self.panel_vel = wx.Panel(self)
        sz_vel = wx.BoxSizer(wx.VERTICAL)
        sz_vel.Add(wx.StaticText(self.panel_vel, label="Velocity Mínimo:"), 0, wx.LEFT, 5)
        self.sp_vel_min = wx.SpinCtrl(self.panel_vel, value="1", min=1, max=127)
        sz_vel.Add(self.sp_vel_min, 0, wx.EXPAND | wx.ALL, 5)
        sz_vel.Add(wx.StaticText(self.panel_vel, label="Velocity Máximo:"), 0, wx.LEFT, 5)
        self.sp_vel_max = wx.SpinCtrl(self.panel_vel, value="127", min=1, max=127)
        sz_vel.Add(self.sp_vel_max, 0, wx.EXPAND | wx.ALL, 5)
        self.panel_vel.SetSizer(sz_vel)
        sizer.Add(self.panel_vel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 15)

        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 15)
        self.SetSizer(sizer)

        # Eventos para Som e Visibilidade
        self.chk_nota.Bind(wx.EVT_CHECKBOX, self.on_toggle_panels)
        self.chk_vel.Bind(wx.EVT_CHECKBOX, self.on_toggle_panels)
        self.sp_nota_min.Bind(wx.EVT_SPINCTRL, lambda e: self.tocar_preview(self.sp_nota_min.GetValue(), 100))
        self.sp_nota_max.Bind(wx.EVT_SPINCTRL, lambda e: self.tocar_preview(self.sp_nota_max.GetValue(), 100))
        self.sp_vel_min.Bind(wx.EVT_SPINCTRL, lambda e: self.tocar_preview(60, self.sp_vel_min.GetValue()))
        self.sp_vel_max.Bind(wx.EVT_SPINCTRL, lambda e: self.tocar_preview(60, self.sp_vel_max.GetValue()))
        
        self.on_toggle_panels(None)
        wx.CallLater(100, self.sp_nota_min.SetFocus)

    def on_toggle_panels(self, event):
        self.panel_nota.Show(self.chk_nota.GetValue())
        self.panel_vel.Show(self.chk_vel.GetValue())
        self.Layout()

    def tocar_preview(self, nota, vel):
        if not self.parent.output: return
        self.matar_nota()
        import mido
        ch = getattr(self.parent, 'canal_atual', 0)
        msg = mido.Message('note_on', channel=ch, note=nota, velocity=vel)
        try:
            self.parent.output.send(msg)
            self.preview_note = msg
            import threading
            self.preview_timer = threading.Timer(0.4, self.matar_nota)
            self.preview_timer.start()
        except: pass

    def matar_nota(self):
        if self.preview_timer: self.preview_timer.cancel()
        if self.preview_note and self.parent.output:
            import mido
            try: self.parent.output.send(mido.Message('note_off', channel=self.preview_note.channel, note=self.preview_note.note, velocity=0))
            except: pass
        self.preview_note = None

    def get_values(self):
        return {
            'usar_nota': self.chk_nota.GetValue(),
            'nota_min': self.sp_nota_min.GetValue(),
            'nota_max': self.sp_nota_max.GetValue(),
            'usar_vel': self.chk_vel.GetValue(),
            'vel_min': self.sp_vel_min.GetValue(),
            'vel_max': self.sp_vel_max.GetValue()
        }
class VelocityControlDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="Velocity Midi Control", size=(400, 300))
        self.parent_seq = parent
        
        # --- Salva os valores originais para caso o usuário cancele ---
        self.orig_min = getattr(self.parent_seq, 'in_vel_min', 1)
        self.orig_max = getattr(self.parent_seq, 'in_vel_max', 127)
        self.orig_on = getattr(self.parent_seq, 'in_vel_ctrl_on', False)
        
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        self.cb_on = wx.CheckBox(panel, label="Ativar Controle de Velocity no Input")
        self.cb_on.SetValue(self.orig_on)
        vbox.Add(self.cb_on, 0, wx.ALL, 10)
        
        # Sliders agora forçados a ler de 1 a 127 e pulando de 1 em 1
        lbl_min = wx.StaticText(panel, label="Velocity Mínimo (1 - 127):")
        vbox.Add(lbl_min, 0, wx.LEFT | wx.RIGHT, 10)
        self.sl_min = wx.Slider(panel, value=self.orig_min, minValue=1, maxValue=127, style=wx.SL_HORIZONTAL | wx.SL_LABELS)
        self.sl_min.SetPageSize(1)
        self.sl_min.SetLineSize(1)
        self.sl_min.SetName("Velocity Mínimo")
        vbox.Add(self.sl_min, 0, wx.EXPAND | wx.ALL, 10)
        
        lbl_max = wx.StaticText(panel, label="Velocity Máximo (1 - 127):")
        vbox.Add(lbl_max, 0, wx.LEFT | wx.RIGHT, 10)
        self.sl_max = wx.Slider(panel, value=self.orig_max, minValue=1, maxValue=127, style=wx.SL_HORIZONTAL | wx.SL_LABELS)
        self.sl_max.SetPageSize(1)
        self.sl_max.SetLineSize(1)
        self.sl_max.SetName("Velocity Máximo")
        vbox.Add(self.sl_max, 0, wx.EXPAND | wx.ALL, 10)
        
        btn_sizer = wx.StdDialogButtonSizer()
        self.btn_ok = wx.Button(panel, wx.ID_OK, "Aplicar")
        self.btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Cancelar")
        btn_sizer.AddButton(self.btn_ok)
        btn_sizer.AddButton(self.btn_cancel)
        btn_sizer.Realize()
        
        vbox.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        panel.SetSizer(vbox)
        
        # Amarra os eventos para atualizar em TEMPO REAL!
        self.cb_on.Bind(wx.EVT_CHECKBOX, self.on_change_live)
        self.sl_min.Bind(wx.EVT_SLIDER, self.on_slider_min)
        self.sl_max.Bind(wx.EVT_SLIDER, self.on_slider_max)
        
        self.btn_ok.Bind(wx.EVT_BUTTON, self.on_ok)
        self.btn_cancel.Bind(wx.EVT_BUTTON, self.on_cancel)
        
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        wx.CallLater(100, self.sl_min.SetFocus)
        self.timer_nota = None

    def on_change_live(self, event=None):
        # Transfere os valores do painel direto pro programa enquanto está aberto!
        self.parent_seq.in_vel_ctrl_on = self.cb_on.GetValue()
        self.parent_seq.in_vel_min = self.sl_min.GetValue()
        self.parent_seq.in_vel_max = self.sl_max.GetValue()
        if event: event.Skip()

    def tocar_nota_preview(self, vel):
        """Toca um C4 no gerador para teste rápido sem usar o teclado físico"""
        if not self.parent_seq.output: return
        import mido
        import threading
        ch = getattr(self.parent_seq, 'canal_atual', 0)
        nota = 60 # C4
        
        try: self.parent_seq.output.send(mido.Message('note_off', channel=ch, note=nota, velocity=0))
        except: pass
        try: self.parent_seq.output.send(mido.Message('note_on', channel=ch, note=nota, velocity=vel))
        except: pass
        
        if self.timer_nota:
            self.timer_nota.cancel()
        self.timer_nota = threading.Timer(0.3, lambda: getattr(self.parent_seq, 'output', None) and self.parent_seq.output.send(mido.Message('note_off', channel=ch, note=nota, velocity=0)))
        self.timer_nota.start()

    def on_slider_min(self, event):
        val = self.sl_min.GetValue()
        if val > self.sl_max.GetValue():
            self.sl_max.SetValue(val)
            val = self.sl_max.GetValue()
            
        self.on_change_live()
        self.tocar_nota_preview(val)
        
        from mhs_utils import falar_status
        falar_status(f"Mínimo: {val}", imediato=True)
        event.Skip()
        
    def on_slider_max(self, event):
        val = self.sl_max.GetValue()
        if val < self.sl_min.GetValue():
            self.sl_min.SetValue(val)
            val = self.sl_min.GetValue()
            
        self.on_change_live()
        self.tocar_nota_preview(val)
        
        from mhs_utils import falar_status
        falar_status(f"Máximo: {val}", imediato=True)
        event.Skip()

    def restaurar(self):
        # Restaura caso venha ordem de fora
        self.parent_seq.in_vel_ctrl_on = self.orig_on
        self.parent_seq.in_vel_min = self.orig_min
        self.parent_seq.in_vel_max = self.orig_max

    def on_ok(self, event):
        self.on_change_live()
        self.EndModal(wx.ID_OK)
        
    def on_cancel(self, event):
        # Desfaz as alterações ao vivo e devolve o programa do jeito que entrou
        self.restaurar()
        self.EndModal(wx.ID_CANCEL)

    def on_key(self, event):
        code = event.GetKeyCode()
        foco = wx.Window.FindFocus()
        
        if code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            if isinstance(foco, wx.Button) and foco.GetId() == wx.ID_CANCEL:
                self.on_cancel(None)
            else:
                self.on_ok(None)
            return
        elif code == wx.WXK_ESCAPE:
            self.on_cancel(None)
            return
        event.Skip()
class RippleEditingDialog(wx.Dialog):
    def __init__(self, parent, current_mode):
        super().__init__(parent, title="Ripple Editing", size=(350, 200))
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        opcoes = ["Desativado", "Canais Selecionados", "Todos os Canais"]
        self.radio_box = wx.RadioBox(self, label="Modo de Comportamento:", choices=opcoes, majorDimension=1, style=wx.RA_SPECIFY_COLS)
        self.radio_box.SetSelection(current_mode)
        sizer.Add(self.radio_box, 0, wx.ALL | wx.EXPAND, 10)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)
        wx.CallLater(100, self.radio_box.SetFocus)

    def get_mode(self):
        return self.radio_box.GetSelection()

class SubstituirNotasDialog(wx.Dialog):
    def __init__(self, parent, old_note, old_vel):
        super().__init__(parent.parent, title=f"Substituição em Massa", size=(400, 350))
        self.parent_list = parent 
        self.old_note = old_note
        self.old_vel = old_vel
        
        self.b = self.parent_list.parent.canais[self.parent_list.canal_idx]["Bank"]
        self.p = self.parent_list.parent.canais[self.parent_list.canal_idx]["Patch"]
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        nome_nota = self.parent_list.parent.key_names.get((self.b, self.p), {}).get(old_note, get_nome_nota(old_note))
        
        self.lbl_note = wx.StaticText(self, label=f"1. Nova Nota de Referência: {nome_nota} ({old_note})")
        sizer.Add(self.lbl_note, 0, wx.ALL, 5)
        self.sl_note = wx.Slider(self, value=old_note, minValue=0, maxValue=127, style=wx.SL_HORIZONTAL)
        self.sl_note.SetToolTip("Nova Nota de Referência")
        sizer.Add(self.sl_note, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.sl_note.Bind(wx.EVT_SLIDER, self.on_note_change)
        
        self.lbl_vel = wx.StaticText(self, label="2. Ajustar Velocity: 0")
        sizer.Add(self.lbl_vel, 0, wx.ALL, 5)
        self.sl_vel = wx.Slider(self, value=0, minValue=-127, maxValue=127, style=wx.SL_HORIZONTAL)
        self.sl_vel.SetToolTip("Ajustar Velocity")
        sizer.Add(self.sl_vel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.sl_vel.Bind(wx.EVT_SLIDER, self.on_vel_change)

        self.lbl_dur = wx.StaticText(self, label="3. Ajustar Duração em milissegundos: 0")
        sizer.Add(self.lbl_dur, 0, wx.ALL, 5)
        self.sl_dur = wx.Slider(self, value=0, minValue=-1000, maxValue=1000, style=wx.SL_HORIZONTAL)
        self.sl_dur.SetToolTip("Ajustar Duração em milissegundos")
        sizer.Add(self.sl_dur, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        self.sl_dur.Bind(wx.EVT_SLIDER, self.on_dur_change)

        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)
        wx.CallLater(100, self.sl_note.SetFocus)

    def play_preview(self):
        if self.parent_list.parent.output:
            self.parent_list.matar_nota_preview()
            v_note = self.sl_note.GetValue()
            v_vel = max(1, min(127, self.old_vel + self.sl_vel.GetValue()))
            msg = mido.Message('note_on', channel=self.parent_list.canal_idx, note=v_note, velocity=v_vel)
            self.parent_list.preview_note = msg
            self.parent_list.parent.output.send(msg)
            self.parent_list.preview_timer = threading.Timer(0.3, self.parent_list.matar_nota_preview)
            self.parent_list.preview_timer.start()

    def on_note_change(self, event):
        v = self.sl_note.GetValue()
        nome_nota = self.parent_list.parent.key_names.get((self.b, self.p), {}).get(v, get_nome_nota(v))
        self.lbl_note.SetLabel(f"1. Nova Nota de Referência: {nome_nota} ({v})")
        self.play_preview()
        # --- MÁGICA DA FALA EXATA ---
        falar_status(f"{nome_nota} ({v})", imediato=True)

    def on_vel_change(self, event):
        v = self.sl_vel.GetValue()
        sinal = "+" if v > 0 else ""
        self.lbl_vel.SetLabel(f"2. Ajustar Velocity: {sinal}{v}")
        self.play_preview()
        # --- MÁGICA DA FALA EXATA ---
        falar_status(f"{sinal}{v}", imediato=True)

    def on_dur_change(self, event):
        v = self.sl_dur.GetValue()
        sinal = "+" if v > 0 else ""
        self.lbl_dur.SetLabel(f"3. Ajustar Duração em milissegundos: {sinal}{v}")
        self.play_preview()
        # --- MÁGICA DA FALA EXATA ---
        falar_status(f"{sinal}{v}", imediato=True)

    def get_values(self):
        return self.sl_note.GetValue(), self.sl_vel.GetValue(), self.sl_dur.GetValue()
class ProgramChangeDialog(wx.Dialog):
    def __init__(self, parent, bank_val, patch_val):
        super().__init__(parent, title="Editar Timbre (Program Change)", size=(300, 200))
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        sizer.Add(wx.StaticText(self, label="Banco (0-16384):"), 0, wx.ALL, 5)
        self.txt_bank = wx.TextCtrl(self, value=str(bank_val))
        sizer.Add(self.txt_bank, 0, wx.EXPAND | wx.ALL, 5)
        
        sizer.Add(wx.StaticText(self, label="Patch/Instrumento (0-127):"), 0, wx.ALL, 5)
        self.txt_patch = wx.TextCtrl(self, value=str(patch_val))
        sizer.Add(self.txt_patch, 0, wx.EXPAND | wx.ALL, 5)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)

    def get_values(self):
        try: b = int(self.txt_bank.GetValue())
        except: b = 0
        try: p = int(self.txt_patch.GetValue())
        except: p = 0
        return max(0, min(16384, b)), max(0, min(127, p))

class ControlChangeDialog(wx.Dialog):
    def __init__(self, parent, cc_num, cc_val):
        super().__init__(parent, title="Editar Control Change", size=(300, 200))
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        sizer.Add(wx.StaticText(self, label="Control Change (Número 0-127):"), 0, wx.ALL, 5)
        self.txt_cc = wx.TextCtrl(self, value=str(cc_num))
        sizer.Add(self.txt_cc, 0, wx.EXPAND | wx.ALL, 5)
        
        sizer.Add(wx.StaticText(self, label="Valor (0-127):"), 0, wx.ALL, 5)
        self.txt_val = wx.TextCtrl(self, value=str(cc_val))
        sizer.Add(self.txt_val, 0, wx.EXPAND | wx.ALL, 5)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)

    def get_values(self):
        try: c = int(self.txt_cc.GetValue())
        except: c = 0
        try: v = int(self.txt_val.GetValue())
        except: v = 0
        return max(0, min(127, c)), max(0, min(127, v))

class TimeSignatureDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="Figura de Compasso (Time Signature)", size=(350, 250))
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        sizer.Add(wx.StaticText(self, label="Numerador (Ex: 3, 4, 6):"), 0, wx.ALL, 5)
        self.txt_num = wx.TextCtrl(self, value="4")
        sizer.Add(self.txt_num, 0, wx.EXPAND | wx.ALL, 5)
        
        sizer.Add(wx.StaticText(self, label="Denominador (/2, /4, /8, /16):"), 0, wx.ALL, 5)
        self.combo_den = wx.ComboBox(self, choices=["2", "4", "8", "16", "32"], style=wx.CB_READONLY)
        self.combo_den.SetStringSelection("4")
        sizer.Add(self.combo_den, 0, wx.EXPAND | wx.ALL, 5)
        
        self.chk_local = wx.CheckBox(self, label="Inserir no cursor atual (desmarque para global)")
        self.chk_local.SetValue(False)
        sizer.Add(self.chk_local, 0, wx.ALL, 10)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)
        wx.CallLater(100, self.txt_num.SetFocus)
        
    def get_valores(self):
        try: num = int(self.txt_num.GetValue())
        except: num = 4
        try: den = int(self.combo_den.GetValue())
        except: den = 4
        # 255 é o teto real do formato (numerador do 'time_signature' MIDI
        # é 1 byte só) - sem isso, digitar um número maior travava mais na
        # frente com um ValueError do mido ao montar a mensagem.
        return max(1, min(255, num)), den, self.chk_local.GetValue()

class EnvelopeCCDialog(wx.Dialog):
    def __init__(self, parent, canal_idx):
        super().__init__(parent, title="Envelope de Automação de CC", size=(400, 250))
        self.parent = parent
        self.canal_idx = canal_idx
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.cc_choices = []
        self.cc_map = {}
        for num in range(128):
            nome = get_cc_name(num)
            if nome == f"CC {num}":
                label = f"{num:03d} - Control Change {num}"
            else:
                label = f"{num:03d} - {nome}"
            self.cc_choices.append(label)
            self.cc_map[label] = num
            
        sizer.Add(wx.StaticText(self, label="Selecione o Control Change (CC):"), 0, wx.ALL, 5)
        self.combo_cc = wx.ComboBox(self, choices=self.cc_choices, style=wx.CB_READONLY)
        self.combo_cc.SetSelection(7) 
        sizer.Add(self.combo_cc, 0, wx.EXPAND | wx.ALL, 5)
        self.combo_cc.Bind(wx.EVT_COMBOBOX, self.on_cc_change)
        
        sz_h = wx.BoxSizer(wx.HORIZONTAL)
        
        sz_start = wx.BoxSizer(wx.VERTICAL)
        sz_start.Add(wx.StaticText(self, label="Valor Inicial (Origem):"), 0, wx.BOTTOM, 5)
        vol_atual = parent.canais[canal_idx]["Volume"]
        self.txt_start = wx.TextCtrl(self, value=str(vol_atual))
        sz_start.Add(self.txt_start, 0, wx.EXPAND)
        
        sz_end = wx.BoxSizer(wx.VERTICAL)
        sz_end.Add(wx.StaticText(self, label="Valor Final (Destino):"), 0, wx.BOTTOM, 5)
        self.txt_end = wx.TextCtrl(self, value=str(vol_atual))
        sz_end.Add(self.txt_end, 0, wx.EXPAND)
        
        sz_h.Add(sz_start, 1, wx.EXPAND | wx.RIGHT, 10)
        sz_h.Add(sz_end, 1, wx.EXPAND)
        sizer.Add(sz_h, 0, wx.EXPAND | wx.ALL, 10)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        
        self.SetSizer(sizer)
        wx.CallLater(100, self.combo_cc.SetFocus)
        
    def on_cc_change(self, event):
        label = self.combo_cc.GetValue()
        cc_num = self.cc_map[label]
        val = 64
        if cc_num == 7: val = self.parent.canais[self.canal_idx]["Volume"]
        elif cc_num == 10: val = self.parent.canais[self.canal_idx]["Pan"]
        elif cc_num == 11: val = self.parent.canais[self.canal_idx]["Expression"]
        elif cc_num == 91: val = self.parent.canais[self.canal_idx]["Reverb"]
        elif cc_num == 93: val = self.parent.canais[self.canal_idx]["Chorus"]
        
        self.txt_start.SetValue(str(val))
        self.txt_end.SetValue(str(val))
        falar_status(f"{label} selecionado", imediato=True)
        
    def get_valores(self):
        cc_num = self.cc_map[self.combo_cc.GetValue()]
        try: st = int(self.txt_start.GetValue())
        except: st = 64
        try: en = int(self.txt_end.GetValue())
        except: en = 64
        return cc_num, max(0, min(127, st)), max(0, min(127, en))

class TempoEnvelopeDialog(wx.Dialog):
    def __init__(self, parent, current_bpm, has_selection):
        super().__init__(parent, title="Envelope de Tempo / BPM", size=(400, 250))
        self.parent = parent
        self.has_selection = has_selection
        
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.panel_abrupto = wx.Panel(self)
        sz_abr = wx.BoxSizer(wx.VERTICAL)
        sz_abr.Add(wx.StaticText(self.panel_abrupto, label="Novo Andamento (BPM):"), 0, wx.ALL, 5)
        self.txt_bpm_abrupto = wx.TextCtrl(self.panel_abrupto, value=str(current_bpm))
        sz_abr.Add(self.txt_bpm_abrupto, 0, wx.EXPAND | wx.ALL, 5)
        self.panel_abrupto.SetSizer(sz_abr)
        self.sizer.Add(self.panel_abrupto, 0, wx.EXPAND | wx.ALL, 0)
        
        self.chk_gradual = wx.CheckBox(self, label="Alteração de tempo gradual")
        self.sizer.Add(self.chk_gradual, 0, wx.ALL, 10)
        self.chk_gradual.Bind(wx.EVT_CHECKBOX, self.on_chk_gradual)
            
        self.panel_gradual = wx.Panel(self)
        sz_grad = wx.BoxSizer(wx.VERTICAL)
        sz_grad.Add(wx.StaticText(self.panel_gradual, label="BPM Inicial (Origem):"), 0, wx.ALL, 5)
        self.txt_bpm_start = wx.TextCtrl(self.panel_gradual, value=str(current_bpm))
        sz_grad.Add(self.txt_bpm_start, 0, wx.EXPAND | wx.ALL, 5)
        
        sz_grad.Add(wx.StaticText(self.panel_gradual, label="BPM Final (Destino):"), 0, wx.ALL, 5)
        self.txt_bpm_end = wx.TextCtrl(self.panel_gradual, value=str(current_bpm))
        sz_grad.Add(self.txt_bpm_end, 0, wx.EXPAND | wx.ALL, 5)
        self.panel_gradual.SetSizer(sz_grad)
        
        self.sizer.Add(self.panel_gradual, 0, wx.EXPAND | wx.ALL, 0)
        self.panel_gradual.Hide()
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        self.sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        
        self.SetSizer(self.sizer)
        
        # MAGIA DA SELEÇÃO: Ao abrir a tela, o número antigo fica azul para apagar
        wx.CallLater(100, self.set_initial_focus)
        
    def set_initial_focus(self):
        self.txt_bpm_abrupto.SetFocus()
        self.txt_bpm_abrupto.SelectAll()
        
    def on_chk_gradual(self, event):
        if self.chk_gradual.GetValue():
            if not self.has_selection:
                falar_status("Aviso: Marque um trecho com as teclas I e O antes de aplicar a rampa gradual.", imediato=True)
            self.panel_abrupto.Hide()
            self.panel_gradual.Show()
            self.txt_bpm_end.SetFocus()
            self.txt_bpm_end.SelectAll() # Seleciona tudo para apagar ao digitar
            falar_status("Modo gradual. Digite o BPM final.", imediato=True)
        else:
            self.panel_gradual.Hide()
            self.panel_abrupto.Show()
            self.txt_bpm_abrupto.SetFocus()
            self.txt_bpm_abrupto.SelectAll() # Seleciona tudo para apagar ao digitar
            falar_status("Modo abrupto ativado.", imediato=True)
        self.Layout()

    def get_valores(self):
        is_gradual = self.chk_gradual.GetValue()
        if is_gradual:
            try: st = int(self.txt_bpm_start.GetValue())
            except: st = 120
            try: en = int(self.txt_bpm_end.GetValue())
            except: en = 120
            return True, st, en
        else:
            try: ab = int(self.txt_bpm_abrupto.GetValue())
            except: ab = 120
            return False, ab, ab

class QuantizacaoOfflineDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="Quantização Offline", size=(400, 250))
        self.parent = parent
        self.restaurado = False
        
        # O SEGREDO DO PREVIEW: Faz backup do projeto inteiro antes de mexermos!
        import copy
        self.backup_midi = copy.deepcopy(parent.midi_file)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.resolucoes = [
            ("1/1 (Semibreve)", 1), ("1/2 (Mínima)", 2), ("1/2T (Mínima Tercina)", 3),
            ("1/4 (Semínima)", 4), ("1/4D (Semínima Pontuada)", 8/3.0), ("1/4T (Semínima Tercina)", 6),
            ("1/8 (Colcheia)", 8), ("1/8D (Colcheia Pontuada)", 16/3.0), ("1/8T (Colcheia Tercina)", 12),
            ("1/16 (Semicolcheia)", 16), ("1/16D (Semicolcheia Pontuada)", 32/3.0), ("1/16T (Semicolcheia Tercina)", 24),
            ("1/32 (Fusa)", 32), ("1/32T (Fusa Tercina)", 48), ("1/64 (Semifusa)", 64)
        ]
        
        sizer.Add(wx.StaticText(self, label="Grade de Quantização:"), 0, wx.ALL, 5)
        self.combo_res = wx.ComboBox(self, choices=[r[0] for r in self.resolucoes], style=wx.CB_READONLY)
        self.combo_res.SetSelection(9) 
        sizer.Add(self.combo_res, 0, wx.EXPAND | wx.ALL, 5)
        
        self.btn_play = wx.Button(self, label="Ouvir Preview (Espaço: Play/Stop, CTRL+Espaço: Pausa)")
        sizer.Add(self.btn_play, 0, wx.EXPAND | wx.ALL, 10)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)
        
        # Nossos gatilhos (Binds)
        self.combo_res.Bind(wx.EVT_COMBOBOX, self.on_change)
        self.btn_play.Bind(wx.EVT_BUTTON, self.on_play_pause)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        
        # Garante que, ao sair, devolvamos o arquivo limpo para o MHS.py processar
        self.Bind(wx.EVT_BUTTON, self.on_btn_click)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        
        wx.CallLater(100, self.combo_res.SetFocus)
        wx.CallLater(200, self.aplicar_preview) # Já aplica a grade inicial (1/16) assim que abre
        
    def on_key(self, event):
        code = event.GetKeyCode()
        ctrl = event.ControlDown()
        if code == wx.WXK_SPACE:
            if ctrl:
                self.parent.toggle_pausa(None) # Ctrl+Espaço: Aciona Pausa
            else:
                self.parent.toggle_reproducao(None) # Espaço: Aciona Play/Stop
            return 
        event.Skip()
        
    def on_play_pause(self, event):
        self.parent.toggle_reproducao(None)
            
    def on_change(self, event):
        self.aplicar_preview()
        from mhs_utils import falar_status
        falar_status(self.combo_res.GetValue(), imediato=True)
        
    def aplicar_preview(self):
        import copy
        import mido
        import time
        res = self.get_resolucao()
        
        self.parent.midi_file = copy.deepcopy(self.backup_midi)
        
        ticks_per_beat = max(1, getattr(self.parent.midi_file, 'ticks_per_beat', 480))
        grid_ticks = (ticks_per_beat * 4.0) / res
        
        has_selection = False
        start_tick = 0
        end_tick = float('inf')
        
        if getattr(self.parent, 'time_selection_start', None) is not None and getattr(self.parent, 'time_selection_end', None) is not None:
            if abs(self.parent.time_selection_end - self.parent.time_selection_start) > 0.01:
                has_selection = True
                st_sec = min(self.parent.time_selection_start, self.parent.time_selection_end)
                ed_sec = max(self.parent.time_selection_start, self.parent.time_selection_end)
                start_tick = self.parent.get_tick_at_sec(st_sec)
                end_tick = self.parent.get_tick_at_sec(ed_sec)
        
        for i, track in enumerate(self.parent.midi_file.tracks):
            abs_time = 0
            abs_events = []
            for msg in track:
                abs_time += msg.time
                abs_events.append([abs_time, msg])
            
            active_notes = {}
            for item in abs_events:
                tick, msg = item[0], item[1]
                ch = getattr(msg, 'channel', None)
                
                if ch in self.parent.canais_selecionados:
                    in_sel = not has_selection or (start_tick <= tick < end_tick)
                        
                    if msg.type == 'note_on' and msg.velocity > 0:
                        if in_sel:
                            snapped = max(0, int(round(tick / grid_ticks) * grid_ticks))
                            offset = snapped - tick
                            item[0] = snapped
                            active_notes[(ch, msg.note)] = offset
                    elif msg.type in ['note_off', 'note_on']:
                        key = (ch, getattr(msg, 'note', None))
                        if key in active_notes:
                            item[0] = max(0, tick + active_notes[key])
                            del active_notes[key]
                            
            abs_events.sort(key=lambda x: x[0])
            new_track = mido.MidiTrack()
            last_tick = 0
            for tick, msg in abs_events:
                delta = max(0, int(round(tick - last_tick)))
                new_track.append(msg.copy(time=delta))
                last_tick = tick
                
            self.parent.midi_file.tracks[i] = new_track
            
        was_playing = self.parent.tocando
        play_time = self.parent.current_playback_time
        
        if self.parent.tocando:
            self.parent.tocando = False
            self.parent.all_notes_off()
            time.sleep(0.05)
            
        self.parent.ler_midi_memoria(reset_canais=False)
        self.parent.current_playback_time = play_time
        self.parent.last_start_time = play_time
        self.parent.seek_flag = True
        
        if was_playing:
            self.parent.tocando = True
            import threading
            threading.Thread(target=self.parent.play_thread, daemon=True).start()
    def on_btn_click(self, event):
        self.restaurar_original()
        event.Skip()
        
    def on_close(self, event):
        self.restaurar_original()
        event.Skip()
        
    def restaurar_original(self):
        if self.restaurado: return
        self.restaurado = True
        
        import copy
        import time
        was_playing = self.parent.tocando
        play_time = self.parent.current_playback_time
        
        if self.parent.tocando:
            self.parent.tocando = False
            self.parent.all_notes_off()
            time.sleep(0.05)
            
        # Ao clicar em OK ou Cancelar, devolvemos a música intacta para o MHS.py fazer a mágica real.
        self.parent.midi_file = copy.deepcopy(self.backup_midi)
        self.parent.ler_midi_memoria(reset_canais=False)
        self.parent.current_playback_time = play_time
        self.parent.last_start_time = play_time
        self.parent.seek_flag = True
        
        if was_playing:
            self.parent.tocando = True
            import threading
            threading.Thread(target=self.parent.play_thread, daemon=True).start()
            
    def get_resolucao(self):
        return self.resolucoes[self.combo_res.GetSelection()][1]
class QuantizacaoRealTimeDialog(wx.Dialog):
    def __init__(self, parent, enabled_atual, res_atual):
        super().__init__(parent, title="Quantização em Tempo Real (Input)", size=(380, 200))
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.resolucoes = [
            ("1/1 (Semibreve)", 1), ("1/2 (Mínima)", 2), ("1/2T (Mínima Tercina)", 3),
            ("1/4 (Semínima)", 4), ("1/4D (Semínima Pontuada)", 8/3.0), ("1/4T (Semínima Tercina)", 6),
            ("1/8 (Colcheia)", 8), ("1/8D (Colcheia Pontuada)", 16/3.0), ("1/8T (Colcheia Tercina)", 12),
            ("1/16 (Semicolcheia)", 16), ("1/16D (Semicolcheia Pontuada)", 32/3.0), ("1/16T (Semicolcheia Tercina)", 24),
            ("1/32 (Fusa)", 32), ("1/32T (Fusa Tercina)", 48), ("1/64 (Semifusa)", 64)
        ]
        
        self.chk_enable = wx.CheckBox(self, label="Gravar Quantizando")
        self.chk_enable.SetValue(enabled_atual)
        sizer.Add(self.chk_enable, 0, wx.ALL, 10)
        
        sizer.Add(wx.StaticText(self, label="Grade de Quantização:"), 0, wx.ALL, 5)
        self.combo_res = wx.ComboBox(self, choices=[r[0] for r in self.resolucoes], style=wx.CB_READONLY)
        
        idx = 9
        for i, r in enumerate(self.resolucoes):
            if abs(r[1] - res_atual) < 0.001:
                idx = i
                break
        self.combo_res.SetSelection(idx)
        sizer.Add(self.combo_res, 0, wx.EXPAND | wx.ALL, 5)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)

        wx.CallLater(100, self.chk_enable.SetFocus)

    def get_valores(self):
        return self.chk_enable.GetValue(), self.resolucoes[self.combo_res.GetSelection()][1]
class HumanizarDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="Humanizar (Variação Aleatória em Tempo Real)", size=(400, 250))
        self.parent = parent

        sizer = wx.BoxSizer(wx.VERTICAL)

        sz_time = wx.BoxSizer(wx.HORIZONTAL)
        sz_time.Add(wx.StaticText(self, label="Variação de Tempo Máxima (ms):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.sp_time = wx.SpinCtrl(self, value="5", min=0, max=500)
        sz_time.Add(self.sp_time, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(sz_time, 0, wx.EXPAND | wx.ALL, 5)

        sz_vel = wx.BoxSizer(wx.HORIZONTAL)
        sz_vel.Add(wx.StaticText(self, label="Variação de Velocity Máxima (+/-):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.sp_vel = wx.SpinCtrl(self, value="8", min=0, max=127)
        sz_vel.Add(self.sp_vel, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(sz_vel, 0, wx.EXPAND | wx.ALL, 5)

        lbl_info = wx.StaticText(self, label="Pressione ESPAÇO para ouvir o preview ().\nMude os valores e ouça a diferença na hora!\nPressione ENTER para aplicar.")
        sizer.Add(lbl_info, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        self.SetSizer(sizer)

        # Variáveis que o motor de reprodução lê em tempo real!
        self.current_ms = self.sp_time.GetValue()
        self.current_vel = self.sp_vel.GetValue()

        # A renderização atual: um ÚNICO sorteio, guardado aqui. O preview
        # (Espaço) SEMPRE toca isto, e aplicar_definitivo (Enter/OK) SEMPRE
        # grava isto - nunca sorteando de novo entre ouvir e confirmar. É
        # isso que garante que o resultado gravado fique igualzinho ao que
        # tocou no preview.
        self.rendered_tracks = None
        self.preview_eventos = []

        self.sp_time.Bind(wx.EVT_SPINCTRL, self.on_spin)
        self.sp_time.Bind(wx.EVT_TEXT, self.on_spin)
        self.sp_vel.Bind(wx.EVT_SPINCTRL, self.on_spin)
        self.sp_vel.Bind(wx.EVT_TEXT, self.on_spin)

        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)

        self.timer_debounce = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_timer_render, self.timer_debounce)

        self._renderizar()
        wx.CallLater(100, self.sp_time.SetFocus)

    def on_spin(self, event):
        self.current_ms = self.sp_time.GetValue()
        self.current_vel = self.sp_vel.GetValue()
        self.timer_debounce.Start(100, oneShot=True)
        event.Skip()

    def _on_timer_render(self, event):
        self._renderizar()

    def _renderizar(self):
        """Sorteia UMA VEZ a humanização com os valores atuais dos spinners
        e guarda o resultado em self.rendered_tracks (o que será gravado se
        o usuário confirmar) e self.preview_eventos (a mesma coisa, já
        ordenada por horário final, pronta pra tocar). Chamado na abertura
        do diálogo e sempre que um spinner muda - nunca dentro do preview
        nem de aplicar_definitivo."""
        import mido
        import random

        ms_shift = self.sp_time.GetValue()
        vel_shift = self.sp_vel.GetValue()

        t_start, t_end = self.parent.get_selection_bounds()
        st_tick = self.parent.get_tick_at_sec(t_start) if t_start != float('inf') else 0
        ed_tick = self.parent.get_tick_at_sec(t_end) if t_end != float('inf') else float('inf')

        canais_alvo = getattr(self.parent, 'canais_selecionados', {self.parent.canal_atual})

        tpb = max(1, getattr(self.parent.midi_file, 'ticks_per_beat', 480))
        tempo_map = []
        for track in self.parent.midi_file.tracks:
            abs_t_track = 0
            for msg in track:
                abs_t_track += msg.time
                if msg.type == 'set_tempo':
                    tempo_map.append((abs_t_track, msg.tempo))
        tempo_map.sort(key=lambda x: x[0])
        if not tempo_map: tempo_map.append((0, 500000))

        def get_tempo_at(target_tick):
            cur_tempo = 500000
            for tm_tick, tm_val in tempo_map:
                if tm_tick > target_tick: break
                cur_tempo = tm_val
            return cur_tempo

        def tick_to_sec(target_tick):
            last_t = 0
            last_s = 0.0
            cur_tempo = 500000
            for tm_tick, tm_val in tempo_map:
                if tm_tick >= target_tick: break
                diff_ticks = tm_tick - last_t
                last_s += mido.tick2second(diff_ticks, tpb, cur_tempo)
                last_t = tm_tick
                cur_tempo = tm_val
            diff_ticks = max(0, target_tick - last_t)
            if diff_ticks > 0:
                last_s += mido.tick2second(diff_ticks, tpb, cur_tempo)
            return last_s

        novas_tracks = []
        preview_eventos = []

        for track in self.parent.midi_file.tracks:
            abs_t = 0
            # Dicionário de LISTAS para suportar notas repetidas/Flans na mesma altura.
            active = {}
            flat = []

            for msg in track:
                abs_t += msg.time
                ch = getattr(msg, 'channel', None)

                if ch in canais_alvo and (st_tick <= abs_t < ed_tick):
                    if msg.type == 'note_on' and msg.velocity > 0:
                        cur_tempo = get_tempo_at(abs_t)

                        max_ticks = mido.second2tick(ms_shift / 1000.0, tpb, cur_tempo)
                        shift = int(round(random.uniform(-max_ticks, max_ticks)))
                        new_start = max(0, abs_t + shift)

                        new_vel = msg.velocity + random.randint(-vel_shift, vel_shift)
                        new_vel = max(1, min(127, new_vel))

                        key = (ch, msg.note)
                        if key not in active:
                            active[key] = []
                        # Enfileira a nota ao invés de esmagar a anterior!
                        active[key].append((new_start, abs_t, msg.copy(velocity=new_vel)))

                    elif msg.type in ['note_off', 'note_on'] and (ch, getattr(msg, 'note', None)) in active and active[(ch, msg.note)]:
                        key = (ch, msg.note)
                        # Puxa a nota mais antiga da fila (FIFO)
                        new_s, old_s, m_on = active[key].pop(0)

                        # Calcula o tamanho exato da nota e move o bloco inteiro
                        dur = max(1, abs_t - old_s)
                        new_end = new_s + dur

                        # 1 = Note On, 0 = Note Off. Se caírem no mesmo tick, o Off vem primeiro e não mata o On.
                        flat.append([new_s, 1, m_on])
                        flat.append([new_end, 0, msg])
                    else:
                        flat.append([abs_t, 2, msg])
                else:
                    flat.append([abs_t, 2, msg])

            # Ordena por Posição, e depois por Tipo (Note Off antes de Note On)
            flat.sort(key=lambda x: (x[0], x[1]))

            new_track = mido.MidiTrack()
            curr = 0
            for t, prioridade, m in flat:
                delta = max(0, int(round(t - curr)))
                new_track.append(m.copy(time=delta))
                curr += delta
                if prioridade in (0, 1):
                    # Nota humanizada (on ou off) - entra na lista de preview,
                    # já com o horário final em segundos.
                    preview_eventos.append((tick_to_sec(t), m))

            novas_tracks.append(new_track)

        # Ordena a lista de preview pelo horário FINAL (pós-humanização), não
        # pela ordem original - é isso que evita uma nota atrasada "atropelar"
        # a próxima e achatar a variação durante a reprodução ao vivo.
        preview_eventos.sort(key=lambda x: x[0])

        self.rendered_tracks = novas_tracks
        self.preview_eventos = preview_eventos

    def on_key(self, event):
        code = event.GetKeyCode()

        if code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            if hasattr(self.parent, 'preview_is_playing'): self.parent.preview_is_playing = False
            if hasattr(self.parent, 'all_notes_off'): self.parent.all_notes_off()
            self.EndModal(wx.ID_OK)
            return

        if code in [wx.WXK_SPACE, 32]:
            if getattr(self.parent, 'preview_is_playing', False):
                self.parent.preview_is_playing = False
                if hasattr(self.parent, 'all_notes_off'): self.parent.all_notes_off()
                from mhs_utils import falar_status
                falar_status("Preview parado.", imediato=True)
            else:
                if hasattr(self.parent, 'play_humanize_preview'):
                    self.parent.play_humanize_preview(self)
            return

        if code == wx.WXK_ESCAPE:
            if hasattr(self.parent, 'preview_is_playing'): self.parent.preview_is_playing = False
            if hasattr(self.parent, 'all_notes_off'): self.parent.all_notes_off()
            self.EndModal(wx.ID_CANCEL)
            return

        event.Skip()

    def aplicar_definitivo(self):
        self.parent.save_state("Humanização")

        # Nenhum sorteio novo aqui - só grava a renderização que já existe
        # (a mesma que o preview tocou por último).
        if self.rendered_tracks is None:
            self._renderizar()

        self.parent.midi_file.tracks = self.rendered_tracks
        self.parent.dirty = True
        self.parent.ler_midi_memoria(reset_canais=False)
class BaixarInsDialog(wx.Dialog):
    # Varre a página jososoft.dk, lista os teclados Yamaha que têm .ins
    # disponível, e baixa/extrai o escolhido na pasta "Ins files" do
    # programa. Ao terminar com sucesso fecha sozinha (ID_OK) devolvendo os
    # caminhos em self.arquivos_baixados - quem abriu já adiciona/seleciona
    # na lista de Instrumentos, só falta o usuário confirmar com OK.
    def __init__(self, parent):
        super().__init__(parent, title="Baixar arquivos .ins da Internet", size=(540, 480))
        self.arquivos_baixados = []
        self._entradas = []
        self._ocupado = False

        vbox = wx.BoxSizer(wx.VERTICAL)
        self.lbl_status = wx.StaticText(self, label="Procurando a lista de teclados no site jososoft.dk...")
        vbox.Add(self.lbl_status, 0, wx.ALL, 10)
        vbox.Add(wx.StaticText(self, label="&Teclados disponíveis (digite o nome para ir direto; Tab vai ao botão Baixar):"), 0, wx.LEFT | wx.RIGHT, 10)
        self.lista = wx.ListBox(self, style=wx.LB_SINGLE, name="Teclados disponíveis")
        vbox.Add(self.lista, 1, wx.EXPAND | wx.ALL, 10)
        bs = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_baixar = wx.Button(self, label="&Baixar")
        self.btn_baixar.Disable()
        self.btn_baixar.SetDefault()
        self.btn_fechar = wx.Button(self, wx.ID_CANCEL, label="&Fechar")
        bs.Add(self.btn_baixar, 0, wx.ALL, 5)
        bs.Add(self.btn_fechar, 0, wx.ALL, 5)
        vbox.Add(bs, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)
        self.SetSizer(vbox)

        self.btn_baixar.Bind(wx.EVT_BUTTON, self.OnBaixar)
        self.lista.Bind(wx.EVT_LISTBOX_DCLICK, self.OnBaixar)
        falar_status("Procurando a lista de teclados no site.", imediato=True)
        threading.Thread(target=self._carregar_lista_thread, daemon=True).start()

    def _carregar_lista_thread(self):
        try:
            entradas = listar_ins_online()
        except Exception as e:
            wx.CallAfter(self._lista_falhou, str(e))
            return
        wx.CallAfter(self._lista_pronta, entradas)

    def _lista_falhou(self, motivo):
        if not self:
            return
        msg = "Não foi possível acessar o site agora. Confira sua conexão com a internet e tente de novo."
        self.lbl_status.SetLabel(msg)
        falar_status(msg, imediato=True)

    def _lista_pronta(self, entradas):
        if not self:
            return
        self._entradas = entradas
        self.lista.Set([f"{e['nome']} ({e['grupo']})" for e in entradas])
        if not entradas:
            msg = "O site respondeu, mas nenhum arquivo .ins foi encontrado."
            self.lbl_status.SetLabel(msg)
            falar_status(msg, imediato=True)
            return
        self.lista.SetSelection(0)
        self.lista.SetFocus()
        self.btn_baixar.Enable()
        msg = f"{len(entradas)} teclados encontrados. Escolha o seu e aperte Enter, ou Tab até o botão Baixar."
        self.lbl_status.SetLabel(msg)
        falar_status(msg, imediato=True)

    def OnBaixar(self, event):
        if self._ocupado or not self._entradas:
            return
        sel = self.lista.GetSelection()
        if sel == wx.NOT_FOUND:
            falar_status("Escolha um teclado na lista primeiro.", imediato=True)
            return
        entrada = self._entradas[sel]
        self._ocupado = True
        self.btn_baixar.Disable()
        msg = f"Baixando o arquivo de {entrada['nome']}, aguarde..."
        self.lbl_status.SetLabel(msg)
        falar_status(msg, imediato=True)
        threading.Thread(target=self._baixar_thread, args=(entrada,), daemon=True).start()

    def _baixar_thread(self, entrada):
        try:
            pasta = pasta_ins_files()
            arquivos = baixar_e_extrair_ins(entrada['url'], pasta)
        except Exception as e:
            wx.CallAfter(self._baixar_falhou, entrada, str(e))
            return
        wx.CallAfter(self._baixar_ok, entrada, pasta, arquivos)

    def _baixar_falhou(self, entrada, motivo):
        if not self:
            return
        self._ocupado = False
        self.btn_baixar.Enable()
        msg = f"Não foi possível baixar o arquivo de {entrada['nome']}. Confira sua conexão e tente de novo."
        self.lbl_status.SetLabel(msg)
        falar_status(msg, imediato=True)

    def _baixar_ok(self, entrada, pasta, arquivos):
        if not self:
            return
        self.arquivos_baixados = arquivos
        self._pasta = pasta
        self._nome = entrada['nome']
        self.EndModal(wx.ID_OK)


class ChangelogDialog(wx.Dialog):
    # Aparece SOZINHA, uma única vez por versão nova instalada (ver
    # mostrar_changelog_se_necessario em MHS.py) - mostra o que mudou nesta
    # versão e, no fim, um convite pra contribuir. Texto num wx.TextCtrl
    # multi-linha SOMENTE LEITURA (não um wx.MessageBox, que trunca texto
    # longo e não dá pra navegar linha a linha/copiar com o NVDA) - o foco
    # já entra direto nele, pronto pra ler com as setas. Mesmo padrão do
    # MHS Style Creator.
    def __init__(self, parent, versao, texto):
        super().__init__(parent, title=f"Novidades da versão {versao}",
                          size=(620, 520), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        vbox = wx.BoxSizer(wx.VERTICAL)
        vbox.Add(wx.StaticText(self, label=f"O que mudou na versão {versao}:"), 0, wx.ALL, 10)
        self.txt = wx.TextCtrl(self, value=texto,
                                style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_BESTWRAP)
        self.txt.SetName(f"Novidades da versão {versao}")
        vbox.Add(self.txt, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        btnsizer = self.CreateButtonSizer(wx.OK)
        vbox.Add(btnsizer, 0, wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, 12)
        self.SetSizer(vbox)
        wx.CallLater(150, self.txt.SetFocus)


class PreferenciasDialog(wx.Dialog):
    def __init__(self, parent, config_atual, versao_atual=None, repo_github=None):
        super().__init__(parent, title="Preferências", size=(500, 560))
        self.parent = parent
        self.config_temp = config_atual.copy()
        self.versao_atual = versao_atual or "?"
        self.repo_github = repo_github or "MHS-MIDI-Sequencer"
        
        self.notebook = wx.Notebook(self)
        
        self.aba_midi = wx.Panel(self.notebook)
        sizer_midi = wx.BoxSizer(wx.VERTICAL)
        
        # --- A MÁGICA: MÚLTIPLAS ENTRADAS DE MIDI ---
        sizer_midi.Add(wx.StaticText(self.aba_midi, label="Entrada MIDI (Selecione uma ou mais portas):"), 0, wx.ALL, 5)
        
        try: portas_in = mido.get_input_names()
        except Exception: portas_in = []; falar_status("Aviso: Motor MIDI não encontrado.", imediato=True)
            
        self.lista_in = wx.CheckListBox(self.aba_midi, choices=portas_in, size=(-1, 100))
        
        # Eventos de Acessibilidade para o NVDA!
        self.lista_in.Bind(wx.EVT_CHECKLISTBOX, self.on_lista_in_toggle)
        self.lista_in.Bind(wx.EVT_LISTBOX, self.on_lista_in_nav)
        
        salvas = self.config_temp.get('portas_in', [])
        if not salvas and self.config_temp.get('porta_in'):
            salvas = [self.config_temp.get('porta_in')]

        # Usa a MESMA função de casamento de nomes que conectar_midi() usa
        # de verdade (mhs_utils.achar_porta_certa) - assim a tela sempre
        # mostra pré-marcado exatamente o que vai ser reconectado, sem uma
        # lógica de casamento separada (e potencialmente divergente) só
        # pra decidir o que aparece marcado aqui.
        for s in salvas:
            porta_certa = achar_porta_certa(s, portas_in)
            if porta_certa:
                self.lista_in.Check(portas_in.index(porta_certa))

        sizer_midi.Add(self.lista_in, 0, wx.ALL | wx.EXPAND, 5)

        # --- SAÍDA MIDI ---
        sizer_midi.Add(wx.StaticText(self.aba_midi, label="Saída MIDI (Gerador):"), 0, wx.ALL, 5)

        try: portas_out = mido.get_output_names()
        except Exception: portas_out = []

        self.combo_out = wx.ComboBox(self.aba_midi, choices=portas_out, style=wx.CB_READONLY)

        out_salvo = self.config_temp.get('porta_out')
        if out_salvo:
            porta_certa = achar_porta_certa(out_salvo, portas_out)
            if porta_certa:
                self.combo_out.SetValue(porta_certa)

        sizer_midi.Add(self.combo_out, 0, wx.ALL | wx.EXPAND, 5)
        
        # --- A CHAVE DE MESTRE: PADRÃO MIDI ---
        sizer_midi.Add(wx.StaticText(self.aba_midi, label="Padrão de Saída MIDI (Sintetizador):"), 0, wx.ALL, 5)
        self.combo_padrao = wx.ComboBox(self.aba_midi, choices=["XG (Yamaha)", "GM / GS (Microsoft Wavetable)"], style=wx.CB_READONLY)
        idx_padrao = 1 if self.config_temp.get('padrao_midi', 'XG') == 'GM' else 0
        self.combo_padrao.SetSelection(idx_padrao)
        sizer_midi.Add(self.combo_padrao, 0, wx.ALL | wx.EXPAND, 5)
        
        self.combo_padrao.Bind(wx.EVT_COMBOBOX, self.on_padrao_change)
        
        self.aba_midi.SetSizer(sizer_midi)

        self.aba_pastas = wx.Panel(self.notebook)
        sizer_pastas = wx.BoxSizer(wx.VERTICAL)
        
        sizer_pastas.Add(wx.StaticText(self.aba_pastas, label="Pasta Padrão para Abrir MIDI:"), 0, wx.ALL, 5)
        sz_abrir = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_pasta_abrir = wx.TextCtrl(self.aba_pastas, value=self.config_temp.get('pasta_abrir', ''))
        btn_abrir = wx.Button(self.aba_pastas, label="Alterar Pasta de Abertura")
        sz_abrir.Add(self.txt_pasta_abrir, 1, wx.EXPAND | wx.RIGHT, 5)
        sz_abrir.Add(btn_abrir, 0)
        sizer_pastas.Add(sz_abrir, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
        btn_abrir.Bind(wx.EVT_BUTTON, self.on_alterar_pasta_abrir)
        
        sizer_pastas.Add(wx.StaticText(self.aba_pastas, label="Pasta Padrão para Salvar MIDI:"), 0, wx.ALL, 5)
        sz_salvar = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_pasta_salvar = wx.TextCtrl(self.aba_pastas, value=self.config_temp.get('pasta_salvar', ''))
        btn_salvar = wx.Button(self.aba_pastas, label="Alterar Pasta de Salvamento")
        sz_salvar.Add(self.txt_pasta_salvar, 1, wx.EXPAND | wx.RIGHT, 5)
        sz_salvar.Add(btn_salvar, 0)
        sizer_pastas.Add(sz_salvar, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
        btn_salvar.Bind(wx.EVT_BUTTON, self.on_alterar_pasta_salvar)
        
        self.aba_pastas.SetSizer(sizer_pastas)
        
        self.aba_ins = wx.Panel(self.notebook)
        sizer_ins = wx.BoxSizer(wx.VERTICAL)
        
        sizer_ins.Add(wx.StaticText(self.aba_ins, label="Arquivos .ins:"), 0, wx.ALL, 5)
        self.lista_ins = wx.ListBox(self.aba_ins, choices=[os.path.basename(p) for p in self.config_temp.get('arquivos_ins', [])])
        if self.config_temp.get('ins_selecionado') is not None and self.config_temp['ins_selecionado'] < len(self.config_temp.get('arquivos_ins', [])):
            self.lista_ins.SetSelection(self.config_temp['ins_selecionado'])
        sizer_ins.Add(self.lista_ins, 1, wx.ALL | wx.EXPAND, 5)
        
        btn_sizer_ins = wx.BoxSizer(wx.HORIZONTAL)
        btn_add = wx.Button(self.aba_ins, label="Adicionar .ins")
        btn_rem = wx.Button(self.aba_ins, label="Remover")
        btn_baixar_ins = wx.Button(self.aba_ins, label="Baixar da &Internet...")
        btn_sizer_ins.Add(btn_add, 0, wx.ALL, 5)
        btn_sizer_ins.Add(btn_rem, 0, wx.ALL, 5)
        btn_sizer_ins.Add(btn_baixar_ins, 0, wx.ALL, 5)
        sizer_ins.Add(btn_sizer_ins, 0, wx.CENTER)
        
        sizer_ins.Add(wx.StaticText(self.aba_ins, label="Instrumento do Arquivo:"), 0, wx.ALL, 5)
        self.combo_inst = wx.ComboBox(self.aba_ins, style=wx.CB_READONLY)
        sizer_ins.Add(self.combo_inst, 0, wx.ALL | wx.EXPAND, 5)
        
        self.aba_ins.SetSizer(sizer_ins)
        
        self.aba_metro = wx.Panel(self.notebook)
        sizer_metro = wx.BoxSizer(wx.VERTICAL)
        
        self.lbl_note_down = wx.StaticText(self.aba_metro, label=f"Nota da Cabeça do Compasso (Downbeat): {self.config_temp.get('metro_note_down', 22)}")
        sizer_metro.Add(self.lbl_note_down, 0, wx.LEFT | wx.TOP, 5)
        self.sl_note_down = wx.Slider(self.aba_metro, value=self.config_temp.get('metro_note_down', 22), minValue=0, maxValue=127, style=wx.SL_HORIZONTAL)
        self.sl_note_down.SetToolTip("Nota da Cabeça do Compasso")
        sizer_metro.Add(self.sl_note_down, 0, wx.EXPAND | wx.ALL, 5)
        self.sl_note_down.Bind(wx.EVT_SLIDER, self.on_change_note_down)
        
        self.lbl_vel_down = wx.StaticText(self.aba_metro, label=f"Volume da Cabeça do Compasso: {self.config_temp.get('metro_vel_down', 100)}")
        sizer_metro.Add(self.lbl_vel_down, 0, wx.LEFT | wx.TOP, 5)
        self.sl_vel_down = wx.Slider(self.aba_metro, value=self.config_temp.get('metro_vel_down', 100), minValue=0, maxValue=127, style=wx.SL_HORIZONTAL)
        self.sl_vel_down.SetToolTip("Volume da Cabeça do Compasso")
        sizer_metro.Add(self.sl_vel_down, 0, wx.EXPAND | wx.ALL, 5)
        self.sl_vel_down.Bind(wx.EVT_SLIDER, self.on_change_vel_down)

        self.lbl_note_beat = wx.StaticText(self.aba_metro, label=f"Nota dos Tempos Normais (Beat): {self.config_temp.get('metro_note_beat', 21)}")
        sizer_metro.Add(self.lbl_note_beat, 0, wx.LEFT | wx.TOP, 5)
        self.sl_note_beat = wx.Slider(self.aba_metro, value=self.config_temp.get('metro_note_beat', 21), minValue=0, maxValue=127, style=wx.SL_HORIZONTAL)
        self.sl_note_beat.SetToolTip("Nota dos Tempos Normais")
        sizer_metro.Add(self.sl_note_beat, 0, wx.EXPAND | wx.ALL, 5)
        self.sl_note_beat.Bind(wx.EVT_SLIDER, self.on_change_note_beat)

        self.lbl_vel_beat = wx.StaticText(self.aba_metro, label=f"Volume dos Tempos Normais: {self.config_temp.get('metro_vel_beat', 100)}")
        sizer_metro.Add(self.lbl_vel_beat, 0, wx.LEFT | wx.TOP, 5)
        self.sl_vel_beat = wx.Slider(self.aba_metro, value=self.config_temp.get('metro_vel_beat', 100), minValue=0, maxValue=127, style=wx.SL_HORIZONTAL)
        self.sl_vel_beat.SetToolTip("Volume dos Tempos Normais")
        sizer_metro.Add(self.sl_vel_beat, 0, wx.EXPAND | wx.ALL, 5)
        self.sl_vel_beat.Bind(wx.EVT_SLIDER, self.on_change_vel_beat)
        
        # --- PORTA MIDI SEPARADA DO METRÔNOMO (canal 10, dispositivo à parte) ---
        sizer_metro.Add(wx.StaticText(self.aba_metro, label="Porta MIDI do Metrônomo (canal 10, dispositivo à parte):"), 0, wx.LEFT | wx.TOP, 5)
        opcoes_metro = ["(mesma porta principal)"] + (portas_out if portas_out else [])
        self.combo_metro_out = wx.ComboBox(self.aba_metro, choices=opcoes_metro, style=wx.CB_READONLY)
        metro_out_salvo = self.config_temp.get('metro_out', '')
        metro_out_certa = achar_porta_certa(metro_out_salvo, portas_out) if metro_out_salvo else None
        if metro_out_certa:
            self.combo_metro_out.SetValue(metro_out_certa)
        else:
            self.combo_metro_out.SetSelection(0)
        sizer_metro.Add(self.combo_metro_out, 0, wx.EXPAND | wx.ALL, 5)

        sizer_metro.Add(wx.StaticText(self.aba_metro, label="Volume do Metrônomo:"), 0, wx.LEFT | wx.TOP, 5)
        self.sp_metro_volume = wx.SpinCtrl(self.aba_metro, value=str(self.config_temp.get('metro_volume', 100)), min=0, max=127)
        sizer_metro.Add(self.sp_metro_volume, 0, wx.EXPAND | wx.ALL, 5)

        self.btn_test = wx.Button(self.aba_metro, label="Testar Metrônomo (120 BPM)")
        sizer_metro.Add(self.btn_test, 0, wx.ALL | wx.CENTER, 10)
        self.btn_test.Bind(wx.EVT_BUTTON, self.on_test_metro)

        self.aba_metro.SetSizer(sizer_metro)

        # Aba de Atualizações - pedido do Michel: checagem automática opcional
        # ao iniciar (checkbox) + botão pra checar na hora, sempre disponível
        # independente da checkbox estar marcada ou não.
        self.aba_atualizacoes = wx.Panel(self.notebook)
        sizer_atualizacoes = wx.BoxSizer(wx.VERTICAL)
        sizer_atualizacoes.Add(wx.StaticText(self.aba_atualizacoes, label=f"Versão instalada: {self.versao_atual}"), 0, wx.ALL, 10)
        self.chk_verificar_atualizacoes = wx.CheckBox(self.aba_atualizacoes, label="&Verificar atualizações automaticamente ao iniciar o programa")
        self.chk_verificar_atualizacoes.SetValue(self.config_temp.get('verificar_atualizacoes', True))
        sizer_atualizacoes.Add(self.chk_verificar_atualizacoes, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.btn_verificar_agora = wx.Button(self.aba_atualizacoes, label="&Procurar Atualizações Agora")
        self.btn_verificar_agora.Bind(wx.EVT_BUTTON, self.on_verificar_atualizacoes_agora)
        sizer_atualizacoes.Add(self.btn_verificar_agora, 0, wx.ALL, 10)
        self.aba_atualizacoes.SetSizer(sizer_atualizacoes)

        self.notebook.AddPage(self.aba_midi, "Midi")
        self.notebook.AddPage(self.aba_pastas, "Pastas de Trabalho")
        self.notebook.AddPage(self.aba_ins, "Instrument Definitions")
        self.notebook.AddPage(self.aba_metro, "Metrônomo")
        self.notebook.AddPage(self.aba_atualizacoes, "Atualizações")
        
        btn_add.Bind(wx.EVT_BUTTON, self.on_add)
        btn_rem.Bind(wx.EVT_BUTTON, self.on_rem)
        btn_baixar_ins.Bind(wx.EVT_BUTTON, self.on_baixar_ins)
        self.lista_ins.Bind(wx.EVT_LISTBOX, self.on_ins_selecionado)
        
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_aplicar = wx.Button(self, label="&Aplicar")
        self.btn_fechar = wx.Button(self, wx.ID_CLOSE, label="&Fechar")
        
        btn_sizer.Add(self.btn_aplicar, 0, wx.ALL, 5)
        btn_sizer.Add(self.btn_fechar, 0, wx.ALL, 5)
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(self.notebook, 1, wx.EXPAND)
        main_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(main_sizer)
        
        if self.lista_ins.GetSelection() != wx.NOT_FOUND:
            self.on_ins_selecionado(None)

        self.btn_aplicar.Bind(wx.EVT_BUTTON, self.on_aplicar)
        self.btn_fechar.Bind(wx.EVT_BUTTON, self.on_fechar)
        self.Bind(wx.EVT_CLOSE, self.on_fechar) 
        
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key_hook)

    # --- FUNÇÕES DE ACESSIBILIDADE DO CHECKLISTBOX ---
    def on_lista_in_toggle(self, event):
        idx = event.GetInt()
        estado = "Marcado" if self.lista_in.IsChecked(idx) else "Desmarcado"
        from mhs_utils import falar_status
        falar_status(estado, imediato=True)
        event.Skip()

    def on_lista_in_nav(self, event):
        idx = event.GetSelection()
        if idx != wx.NOT_FOUND:
            estado = "Marcado" if self.lista_in.IsChecked(idx) else "Desmarcado"
            nome = self.lista_in.GetString(idx)
            from mhs_utils import falar_status
            falar_status(f"{nome}, {estado}", imediato=True)
        event.Skip()

    def on_padrao_change(self, event):
        sel = self.combo_padrao.GetSelection()
        if sel == 1:
            n_down = 34
            n_beat = 33
            nome_padrao = "GM"
        else:
            n_down = 22
            n_beat = 21
            nome_padrao = "XG"
            
        self.sl_note_down.SetValue(n_down)
        self.sl_note_beat.SetValue(n_beat)
        
        self.lbl_note_down.SetLabel(f"Nota da Cabeça do Compasso (Downbeat): {n_down}")
        self.lbl_note_beat.SetLabel(f"Nota dos Tempos Normais (Beat): {n_beat}")
        
        from mhs_utils import falar_status
        falar_status(f"Padrão {nome_padrao} selecionado. Notas ajustadas para {n_down} e {n_beat}.", imediato=True)
        
        event.Skip()

    def on_alterar_pasta_abrir(self, event):
        dir_atual = self.txt_pasta_abrir.GetValue()
        with wx.DirDialog(self, "Escolha a pasta padrão para Abrir MIDI", defaultPath=dir_atual) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                nova_pasta = dlg.GetPath()
                self.txt_pasta_abrir.SetValue(nova_pasta)
                from mhs_utils import falar_status
                falar_status("Pasta de abertura selecionada", imediato=True)
                
    def on_alterar_pasta_salvar(self, event):
        dir_atual = self.txt_pasta_salvar.GetValue()
        with wx.DirDialog(self, "Escolha a pasta padrão para Salvar MIDI", defaultPath=dir_atual) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                nova_pasta = dlg.GetPath()
                self.txt_pasta_salvar.SetValue(nova_pasta)
                from mhs_utils import falar_status
                falar_status("Pasta de salvamento selecionada", imediato=True)

    def on_key_hook(self, event):
        code = event.GetKeyCode()
        ctrl = event.ControlDown()
        shift = event.ShiftDown()

        if code == wx.WXK_ESCAPE:
            self.on_fechar(None)
            return

        if code in [wx.WXK_TAB, ord('\t')] and ctrl:
            total = self.notebook.GetPageCount()
            current = self.notebook.GetSelection()
            if shift:
                next_page = (current - 1) % total
            else:
                next_page = (current + 1) % total
                
            self.notebook.SetSelection(next_page)
            from mhs_utils import falar_status
            falar_status(self.notebook.GetPageText(next_page), imediato=True)
            return

        event.Skip()

    def on_aplicar_silencioso(self, event):
        self._salvar_e_aplicar(silencioso=True)
        event.Skip()

    def on_aplicar(self, event):
        self._salvar_e_aplicar(silencioso=False)

    def on_fechar(self, event):
        self._salvar_e_aplicar(silencioso=True)
        self.EndModal(wx.ID_OK)

    def on_verificar_atualizacoes_agora(self, event):
        self.btn_verificar_agora.Disable()
        self.btn_verificar_agora.SetLabel("Procurando...")
        from mhs_utils import falar_status
        falar_status("Procurando atualizações...", imediato=True)
        threading.Thread(target=self._checar_atualizacao_thread, daemon=True).start()

    def _checar_atualizacao_thread(self):
        tem, versao_nova, url = verificar_nova_versao(self.repo_github, self.versao_atual)
        wx.CallAfter(self._mostrar_resultado_atualizacao, tem, versao_nova, url)

    def _mostrar_resultado_atualizacao(self, tem, versao_nova, url):
        if not self:
            return
        self.btn_verificar_agora.Enable()
        self.btn_verificar_agora.SetLabel("&Procurar Atualizações Agora")
        if versao_nova is None:
            wx.MessageBox("Não foi possível verificar atualizações agora. Confira sua conexão com a internet.", "Atualizações", wx.OK | wx.ICON_WARNING, self)
        elif tem:
            resp = wx.MessageBox(
                f"Uma nova versão está disponível: {versao_nova} (você está usando a {self.versao_atual}).\n\nDeseja abrir a página de download agora?",
                "Atualização disponível", wx.YES_NO | wx.ICON_INFORMATION, self)
            if resp == wx.YES:
                import webbrowser
                webbrowser.open(url)
        else:
            wx.MessageBox("Você já está com a versão mais recente.", "Atualizações", wx.OK | wx.ICON_INFORMATION, self)

    def _salvar_e_aplicar(self, silencioso=False):
        portas_selecionadas = [self.lista_in.GetString(i) for i in self.lista_in.GetCheckedItems()]
        novo_out = self.combo_out.GetValue()
        novo_padrao = "GM" if self.combo_padrao.GetSelection() == 1 else "XG"
        
        portas_in_antigas = self.config_temp.get('portas_in', [])
        if not portas_in_antigas and self.config_temp.get('porta_in'):
            portas_in_antigas = [self.config_temp.get('porta_in')]
            
        portas_mudaram = (set(portas_in_antigas) != set(portas_selecionadas)) or (self.config_temp.get('porta_out') != novo_out)
        
        self.config_temp['portas_in'] = portas_selecionadas
        self.config_temp['porta_in'] = portas_selecionadas[0] if portas_selecionadas else ""
        self.config_temp['porta_out'] = novo_out
        self.config_temp['padrao_midi'] = novo_padrao
        self.config_temp['pasta_abrir'] = self.txt_pasta_abrir.GetValue()
        self.config_temp['pasta_salvar'] = self.txt_pasta_salvar.GetValue()
        
        self.config_temp['metro_note_down'] = self.sl_note_down.GetValue()
        self.config_temp['metro_note_beat'] = self.sl_note_beat.GetValue()
        self.config_temp['metro_vel_down'] = self.sl_vel_down.GetValue()
        self.config_temp['metro_vel_beat'] = self.sl_vel_beat.GetValue()

        sel_metro_out = self.combo_metro_out.GetValue()
        novo_metro_out = "" if sel_metro_out == "(mesma porta principal)" else sel_metro_out
        self.config_temp['metro_out'] = novo_metro_out
        self.config_temp['metro_volume'] = self.sp_metro_volume.GetValue()

        sel_ins = self.lista_ins.GetSelection()
        self.config_temp['ins_selecionado'] = sel_ins if sel_ins != wx.NOT_FOUND else 0
        self.config_temp['ins_instrumento'] = self.combo_inst.GetValue()

        self.config_temp['verificar_atualizacoes'] = self.chk_verificar_atualizacoes.GetValue()

        try:
            from mhs_utils import CONFIG_FILE
            import json
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f: 
                json.dump(self.config_temp, f, indent=4, ensure_ascii=False)
            
            self.parent.config = self.config_temp
            
            if portas_mudaram:
                self.parent.conectar_midi(portas_selecionadas, novo_out)

            self.parent.conectar_midi_metronomo()

            self.parent.carregar_ins_ativo()
            
            if not silencioso:
                from mhs_utils import falar_status
                falar_status("Configurações aplicadas com sucesso.", imediato=True)
        except Exception:
            if not silencioso:
                from mhs_utils import falar_status
                falar_status("Erro ao salvar as configurações.", imediato=True)

    def play_preview(self, note, vel):
        saida = getattr(self.parent, 'output_metronomo', None) or self.parent.output
        if saida:
            try:
                import threading
                saida.send(mido.Message('note_on', channel=9, note=note, velocity=vel))
                threading.Timer(0.1, lambda p=saida: p.send(mido.Message('note_off', channel=9, note=note))).start()
            except: pass

    def on_change_note_down(self, event):
        val = self.sl_note_down.GetValue()
        self.lbl_note_down.SetLabel(f"Nota da Cabeça do Compasso (Downbeat): {val}")
        self.play_preview(val, self.sl_vel_down.GetValue())
        
        from mhs_utils import get_drum_name, falar_status
        nome_peca = get_drum_name(val)
        falar_status(f"{nome_peca} ({val})", imediato=True)

    def on_change_vel_down(self, event):
        val = self.sl_vel_down.GetValue()
        self.lbl_vel_down.SetLabel(f"Volume da Cabeça do Compasso: {val}")
        self.play_preview(self.sl_note_down.GetValue(), val)
        
        from mhs_utils import falar_status
        falar_status(str(val), imediato=True)

    def on_change_note_beat(self, event):
        val = self.sl_note_beat.GetValue()
        self.lbl_note_beat.SetLabel(f"Nota dos Tempos Normais (Beat): {val}")
        self.play_preview(val, self.sl_vel_beat.GetValue())
        
        from mhs_utils import get_drum_name, falar_status
        nome_peca = get_drum_name(val)
        falar_status(f"{nome_peca} ({val})", imediato=True)

    def on_change_vel_beat(self, event):
        val = self.sl_vel_beat.GetValue()
        self.lbl_vel_beat.SetLabel(f"Volume dos Tempos Normais: {val}")
        self.play_preview(self.sl_note_beat.GetValue(), val)
        
        from mhs_utils import falar_status
        falar_status(str(val), imediato=True)

    def on_test_metro(self, event):
        import threading
        threading.Thread(target=self._test_thread, daemon=True).start()

    def _test_thread(self):
        import time
        nd = self.sl_note_down.GetValue()
        vd = self.sl_vel_down.GetValue()
        nb = self.sl_note_beat.GetValue()
        vb = self.sl_vel_beat.GetValue()
        for i in range(8):
            is_down = (i % 4 == 0)
            self.play_preview(nd if is_down else nb, vd if is_down else vb)
            time.sleep(0.5)

    def get_instruments_from_ins(self, path):
        insts = []
        try:
            import re
            with open(path, 'r', encoding='latin-1') as f:
                current = None
                has_patch = False
                for line in f:
                    line = line.strip()
                    if not line or line.startswith(';'): continue
                    
                    m = re.match(r'^\[(.*)\]$', line)
                    if m:
                        if current and has_patch:
                            insts.append(current)
                        current = m.group(1).strip()
                        has_patch = False
                    elif current and 'patch[' in line.lower():
                        has_patch = True
                if current and has_patch:
                    insts.append(current)
        except: pass
        return insts

    def on_ins_selecionado(self, event):
        import os
        sel = self.lista_ins.GetSelection()
        if sel != wx.NOT_FOUND:
            path = self.config_temp['arquivos_ins'][sel]
            if os.path.exists(path):
                insts = self.get_instruments_from_ins(path)
                self.combo_inst.Clear()
                if insts:
                    self.combo_inst.AppendItems(insts)
                    salvo = self.config_temp.get('ins_instrumento', '')
                    if salvo in insts:
                        self.combo_inst.SetValue(salvo)
                    else:
                        self.combo_inst.SetSelection(0)

    def on_add(self, event):
        import os
        with wx.FileDialog(self, "Abrir .ins", wildcard="*.ins", style=wx.FD_OPEN) as fd:
            if fd.ShowModal() == wx.ID_OK:
                p = fd.GetPath()
                if 'arquivos_ins' not in self.config_temp: self.config_temp['arquivos_ins'] = []
                self.config_temp['arquivos_ins'].append(p)
                self.lista_ins.Append(os.path.basename(p))
                self.lista_ins.SetSelection(self.lista_ins.GetCount()-1)
                self.on_ins_selecionado(None)

    def on_baixar_ins(self, event):
        import os
        dlg = BaixarInsDialog(self)
        if dlg.ShowModal() == wx.ID_OK and dlg.arquivos_baixados:
            if 'arquivos_ins' not in self.config_temp: self.config_temp['arquivos_ins'] = []
            existentes = [p.lower() for p in self.config_temp['arquivos_ins']]
            for p in dlg.arquivos_baixados:
                if p.lower() not in existentes:
                    self.config_temp['arquivos_ins'].append(p)
                    self.lista_ins.Append(os.path.basename(p))
            alvo = dlg.arquivos_baixados[0].lower()
            idx = next((i for i, p in enumerate(self.config_temp['arquivos_ins']) if p.lower() == alvo), wx.NOT_FOUND)
            if idx != wx.NOT_FOUND:
                self.lista_ins.SetSelection(idx)
                self.on_ins_selecionado(None)
            from mhs_utils import falar_status
            falar_status(f"Arquivo de {dlg._nome} baixado, salvo em {dlg._pasta} e já definido como instrumento. Clique em Aplicar ou Fechar para confirmar.", imediato=True)
            self.lista_ins.SetFocus()
        dlg.Destroy()

    def on_rem(self, event):
        sel = self.lista_ins.GetSelection()
        if sel != wx.NOT_FOUND:
            self.lista_ins.Delete(sel)
            self.config_temp['arquivos_ins'].pop(sel)
            self.combo_inst.Clear()
            if self.lista_ins.GetCount() > 0:
                self.lista_ins.SetSelection(0)
                self.on_ins_selecionado(None)
class DrumSetupDialog(wx.Dialog):
    def __init__(self, parent, canal_idx):
        super().__init__(parent, title="Yamaha XG Drum Setup (Modo SysEx)", size=(500, 500))
        self.parent = parent
        self.canal_idx = canal_idx
        self.preview_timer = None
        
        self.drum_params = self.parent.canais[canal_idx].get("DrumParams", {}).copy()
        self.custom_maps = self.parent.canais[canal_idx].get("CustomDrumMap", {}).copy()
        # Guia 3 (NRPN): mesma ideia da Guia 1, mas por NRPN padrão MIDI
        # (control_change 99/98/6) em vez de SysEx exclusiva da Yamaha -
        # funciona em qualquer sintetizador XG/GS, não só no teclado real.
        self.drum_params_nrpn = self.parent.canais[canal_idx].get("DrumParamsNRPN", {}).copy()
        self.removido = False

        # Cada nome já traz o & do atalho Alt+letra embutido - assim toda
        # vez que o rótulo é reescrito (SetLabel, ao trocar de peça ou
        # mudar o valor) o atalho continua funcionando, sem precisar
        # lembrar de reincluir o & em cada lugar que reconstrói o texto.
        # Letras escolhidas sem repetir dentro desta aba - mesmas letras
        # do Style Creator, pra manter o mesmo atalho nos dois programas
        # (o R fica livre pro botão Remover, mais abaixo).
        # Cada item é (endereço, nome, mínimo, máximo) - os 5 últimos (Envio
        # de Variação e o EQ Grave/Agudo por peça, com ganho e frequência)
        # foram achados no Data List oficial do PSR-SX600 (MIDI Parameter
        # Change table, DRUM SETUP) e ainda não existiam aqui - a
        # frequência tem faixa própria, mais estreita que 0-127.
        self.sysex_params = [
            (0x02, "&Volume da Peça (Level)", 0, 127), (0x04, "&Panorâmico (Pan)", 0, 127),
            (0x05, "R&everb Send", 0, 127), (0x06, "C&horus Send", 0, 127),
            (0x07, "Envio de Variação (&Insertion)", 0, 127),
            (0x0B, "C&utoff (Filtro)", 0, 127), (0x0C, "Re&ssonância (Filtro)", 0, 127), (0x0D, "&Ataque (Attack)", 0, 127),
            (0x0E, "&Decay 1 (Soco/Corpo)", 0, 127), (0x0F, "Decay &2 (Cauda/Release)", 0, 127),
            (0x00, "Afinação em Semitons (C&oarse)", 0, 127), (0x01, "Afinação Fina em Cents (&Fine)", 0, 127),
            (0x03, "A&grupamento (Alt Group - 0=Desligado)", 0, 127), (0x08, "&Key Assign (0=Single, 1=Multi)", 0, 127),
            (0x20, "Grave da Peça (E&Q Bass)", 0, 127), (0x21, "Agudo da Peça (EQ &Treble)", 0, 127),
            (0x24, "Frequência do Grave (EQ &Bass)", 4, 40), (0x25, "Frequência do Agudo (Treb&le)", 28, 58),
        ]
        self.sliders = {}
        self.labels = {}
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        self.notebook = wx.Notebook(self)
        
        # --- GUIA 1: EDIÇÃO DE PARÂMETROS (SYSEX PURO) ---
        self.tab_params = wx.Panel(self.notebook)
        sz_params = wx.BoxSizer(wx.VERTICAL)
        
        self.lbl_nota = wx.StaticText(self.tab_params, label="Peça (&Nota) a ser editada:")
        sz_params.Add(self.lbl_nota, 0, wx.ALL, 5)
        
        self.sl_nota = wx.Slider(self.tab_params, value=38, minValue=0, maxValue=127, style=wx.SL_HORIZONTAL, name="Peça a ser editada")
        sz_params.Add(self.sl_nota, 0, wx.EXPAND | wx.ALL, 5)
        self.sl_nota.Bind(wx.EVT_SLIDER, self.on_nota_change)
        
        # Padrão de fábrica só pras 2 frequências de EQ (faixa própria, mais
        # estreita que o 64 central usado no resto) - conferido no Data
        # List oficial (0x24=0x0C, 0x25=0x36).
        self._padrao_por_param = {0x24: 12, 0x25: 54}
        for param_id, name, min_v, max_v in self.sysex_params:
            init_val = self.drum_params.get((38, param_id), self._padrao_por_param.get(param_id, 64))
            lbl = wx.StaticText(self.tab_params, label=f"{name}: {init_val}")
            sz_params.Add(lbl, 0, wx.ALL, 2)

            sl = wx.SpinCtrl(self.tab_params, value=str(init_val), min=min_v, max=max_v, name=name)
            sz_params.Add(sl, 0, wx.EXPAND | wx.ALL, 2)
            
            sl.Bind(wx.EVT_SPINCTRL, lambda e, p=param_id, s=sl, l=lbl: self.on_param_change(e, p, s, l))
            sl.Bind(wx.EVT_TEXT, lambda e, p=param_id, s=sl, l=lbl: self.on_param_change(e, p, s, l))
            
            self.sliders[param_id] = sl
            self.labels[param_id] = lbl
            
        self.tab_params.SetSizer(sz_params)
        
        # --- GUIA 2: MAPEDADOR AVANÇADO ---
        self.tab_map = wx.Panel(self.notebook)
        sz_map = wx.BoxSizer(wx.VERTICAL)
        
        lbl_aviso = wx.StaticText(self.tab_map, label="Mapeador de Bateria (Puxar peças de outros Kits do SX600)")
        sz_map.Add(lbl_aviso, 0, wx.ALL | wx.ALIGN_CENTER, 10)
        
        # Valor inicial de verdade da Guia 2 (peça 38, o padrão) - lido de
        # self.custom_maps ANTES de construir os widgets, e passado direto
        # no parâmetro `value=` de cada um (nunca via `.SetValue()` depois
        # de já estarem com o evento ligado). Sem isso, os controles
        # nasciam com os valores de fábrica (16256/0/38), nunca com o
        # mapeamento REAL já salvo pra peça 38 - mesmo bug já corrigido no
        # Style Creator (ver plano: peça 38 "se perdendo sozinha" no
        # Country MHS.sty).
        _peca_inicial = 38
        if _peca_inicial in self.custom_maps:
            _m_inicial = self.custom_maps[_peca_inicial]
            _bank_inicial = _m_inicial['bank']
            _patch_inicial = _m_inicial['patch']
            _dest_inicial = _m_inicial['dest_note']
        else:
            _bank_inicial = self.parent.canais[canal_idx].get("Bank", 16256)
            _patch_inicial = self.parent.canais[canal_idx].get("Patch", 0)
            _dest_inicial = _peca_inicial

        self.lbl_map_orig = wx.StaticText(self.tab_map, label="1. Peça (&Nota) Alvo a ser trocada:")
        sz_map.Add(self.lbl_map_orig, 0, wx.ALL, 5)
        self.sl_map_orig = wx.Slider(self.tab_map, value=_peca_inicial, minValue=0, maxValue=127, style=wx.SL_HORIZONTAL, name="Peça Alvo")
        sz_map.Add(self.sl_map_orig, 0, wx.EXPAND | wx.ALL, 5)

        self.lbl_map_bank = wx.StaticText(self.tab_map, label="2. &Banco do Kit Doador (ex: 16256):")
        sz_map.Add(self.lbl_map_bank, 0, wx.ALL, 5)
        self.sp_map_bank = wx.SpinCtrl(self.tab_map, value=str(_bank_inicial), min=0, max=16384, name="Banco do Kit Doador")
        sz_map.Add(self.sp_map_bank, 0, wx.EXPAND | wx.ALL, 5)

        self.lbl_map_patch = wx.StaticText(self.tab_map, label="3. Pa&tch do Kit Doador (0 a 127):")
        sz_map.Add(self.lbl_map_patch, 0, wx.ALL, 5)
        self.sl_map_patch = wx.SpinCtrl(self.tab_map, value=str(_patch_inicial), min=0, max=127, name="Patch do Kit Doador")
        sz_map.Add(self.sl_map_patch, 0, wx.EXPAND | wx.ALL, 5)

        self.lbl_map_dest = wx.StaticText(self.tab_map, label="4. Peça do Kit &Doador (O novo som):")
        sz_map.Add(self.lbl_map_dest, 0, wx.ALL, 5)
        self.sl_map_dest = wx.Slider(self.tab_map, value=_dest_inicial, minValue=0, maxValue=127, style=wx.SL_HORIZONTAL, name="Peça do Kit Doador")
        sz_map.Add(self.sl_map_dest, 0, wx.EXPAND | wx.ALL, 5)
        
        self.btn_aplicar_custom = wx.Button(self.tab_map, label="&Aplicar Mapeamento desta Peça")
        sz_map.Add(self.btn_aplicar_custom, 0, wx.ALL | wx.ALIGN_CENTER, 15)
        self.btn_aplicar_custom.Bind(wx.EVT_BUTTON, self.on_aplicar_custom)
        
        self.tab_map.SetSizer(sz_map)

        # --- GUIA 3: EDIÇÃO VIA NRPN (PADRÃO MIDI, NÃO SÓ YAMAHA) ---
        # Mesma ideia da Guia 1 (uma peça de cada vez, um slider por
        # parâmetro), mas gravando NRPN puro (control_change 99=parâmetro,
        # 98=peça, 6=valor) em vez da SysEx `43 1n 4C` - funciona em
        # qualquer sintetizador XG/GS (é o mesmo protocolo que o Sonar usava
        # no Event List em 2011), não só no teclado Yamaha real. Uma
        # ScrolledWindow (a Guia 1 não tem - 15 parâmetros não cabem sem
        # rolar, mesmo com a janela no tamanho normal).
        self.tab_nrpn = wx.Panel(self.notebook)
        sz_nrpn_outer = wx.BoxSizer(wx.VERTICAL)
        scr_nrpn = wx.ScrolledWindow(self.tab_nrpn, style=wx.VSCROLL)
        scr_nrpn.SetScrollRate(0, 20)
        sz_nrpn = wx.BoxSizer(wx.VERTICAL)

        self.lbl_nota_nrpn = wx.StaticText(scr_nrpn, label="Peça (&Nota) a ser editada:")
        sz_nrpn.Add(self.lbl_nota_nrpn, 0, wx.ALL, 5)

        self.sl_nota_nrpn = wx.Slider(scr_nrpn, value=38, minValue=0, maxValue=127, style=wx.SL_HORIZONTAL, name="Peça a ser editada (NRPN)")
        sz_nrpn.Add(self.sl_nota_nrpn, 0, wx.EXPAND | wx.ALL, 5)
        self.sl_nota_nrpn.Bind(wx.EVT_SLIDER, self.on_nota_change_nrpn)

        self.sliders_nrpn = {}
        self.labels_nrpn = {}
        for param_id, name, min_v, max_v in DRUM_NRPN_PARAMS:
            init_val = self.drum_params_nrpn.get((38, param_id), DRUM_NRPN_DEFAULTS.get(param_id, 64))
            lbl = wx.StaticText(scr_nrpn, label=f"{name}: {init_val}")
            sz_nrpn.Add(lbl, 0, wx.ALL, 2)

            sl = wx.SpinCtrl(scr_nrpn, value=str(init_val), min=min_v, max=max_v, name=name)
            sz_nrpn.Add(sl, 0, wx.EXPAND | wx.ALL, 2)

            sl.Bind(wx.EVT_SPINCTRL, lambda e, p=param_id, s=sl, l=lbl: self.on_param_change_nrpn(e, p, s, l))
            sl.Bind(wx.EVT_TEXT, lambda e, p=param_id, s=sl, l=lbl: self.on_param_change_nrpn(e, p, s, l))

            self.sliders_nrpn[param_id] = sl
            self.labels_nrpn[param_id] = lbl

        scr_nrpn.SetSizer(sz_nrpn)
        sz_nrpn_outer.Add(scr_nrpn, 1, wx.EXPAND)
        self.tab_nrpn.SetSizer(sz_nrpn_outer)

        self.notebook.AddPage(self.tab_params, "Edição e Filtros (SysEx)")
        self.notebook.AddPage(self.tab_map, "Montagem de Kit (Custom)")
        self.notebook.AddPage(self.tab_nrpn, "Edição via NRPN (Padrão MIDI)")
        main_sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 5)

        # Mesma ideia do "Remover Efeito Existente" do DSP - apaga TODA a
        # edição de Drum Setup deste canal (SysEx, Montagem de Kit e NRPN),
        # de uma vez, em vez de precisar zerar peça por peça na mão. Igual
        # ao Style Creator (que já tinha esse botão).
        self.btn_remover = wx.Button(self, label="&Remover Toda a Configuração de Bateria deste Canal")
        main_sizer.Add(self.btn_remover, 0, wx.EXPAND | wx.ALL, 5)
        self.btn_remover.Bind(wx.EVT_BUTTON, self.on_remover)

        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        main_sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        self.SetSizer(main_sizer)
        self.Layout()

        self.sl_map_orig.Bind(wx.EVT_SLIDER, self.on_map_orig_change)
        self.sp_map_bank.Bind(wx.EVT_SPINCTRL, self.on_map_param_change)
        self.sp_map_bank.Bind(wx.EVT_TEXT, self.on_map_param_change)
        
        self.sl_map_patch.Bind(wx.EVT_SPINCTRL, self.on_map_param_change)
        self.sl_map_patch.Bind(wx.EVT_TEXT, self.on_map_param_change)
        
        self.sl_map_dest.Bind(wx.EVT_SLIDER, self.on_map_param_change)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        
        self.update_nota_label()
        self.update_map_labels()
        self.update_nota_label_nrpn()

        wx.CallLater(100, self.sl_nota.SetFocus)

    def update_map_labels(self):
        orig = self.sl_map_orig.GetValue()
        b = self.sp_map_bank.GetValue()
        p = self.sl_map_patch.GetValue()
        dest = self.sl_map_dest.GetValue()
        
        from mhs_utils import get_drum_name
        self.lbl_map_orig.SetLabel(f"1. Peça (&Nota) Alvo: {get_drum_name(orig)} ({orig})")
        self.lbl_map_bank.SetLabel(f"2. &Banco do Kit Doador: {b}")

        nome_kit = f"Kit {p}"
        if hasattr(self.parent, 'instrument_names'):
            nome_kit = self.parent.instrument_names.get(b, {}).get(p, nome_kit)

        self.lbl_map_patch.SetLabel(f"3. Pa&tch do Kit Doador: {nome_kit} ({p})")
        self.lbl_map_dest.SetLabel(f"4. Peça do Kit &Doador: {get_drum_name(dest)} ({dest})")

    def on_map_orig_change(self, event):
        orig = self.sl_map_orig.GetValue()
        from mhs_utils import get_drum_name, falar_status
        falar_status(f"Alvo: {get_drum_name(orig)} ({orig})", imediato=True)

        if orig in self.custom_maps:
            m = self.custom_maps[orig]
            self.sp_map_bank.SetValue(m['bank'])
            self.sl_map_patch.SetValue(m['patch'])
            self.sl_map_dest.SetValue(m['dest_note'])
        else:
            ch = self.canal_idx
            b_atual = self.parent.canais[ch].get("Bank", 16256)
            p_atual = self.parent.canais[ch].get("Patch", 0)
            self.sp_map_bank.SetValue(b_atual)
            self.sl_map_patch.SetValue(p_atual)
            self.sl_map_dest.SetValue(orig)

        self.update_map_labels()
        self.play_preview_direct(orig)

    def _comitar_mapeamento_atual(self):
        # Grava de verdade (em self.custom_maps, o que get_values() devolve
        # pro OK) o mapeamento que está nos controles AGORA - a Guia 1 já
        # grava sozinha a cada mudança de valor (on_param_change); esta guia
        # só gravava quando alguém clicava o botão "Aplicar Mapeamento", e
        # o preview ao vivo (que já soa certo ao mexer no slider) mascarava
        # isso - dava pra ouvir tudo certo, clicar OK sem nunca ter clicado
        # o botão, e a troca de peça sumia (só o que a Guia 1 mexeu ficava).
        # Chamado a cada mudança de valor aqui também, pra ficar do mesmo
        # jeito que a Guia 1.
        orig = self.sl_map_orig.GetValue()
        b = self.sp_map_bank.GetValue()
        p = self.sl_map_patch.GetValue()
        d = self.sl_map_dest.GetValue()
        self.custom_maps[orig] = {'bank': b, 'patch': p, 'dest_note': d}
        self.parent.canais[self.canal_idx]["CustomDrumMap"] = self.custom_maps

    def on_aplicar_custom(self, event):
        orig = self.sl_map_orig.GetValue()
        b = self.sp_map_bank.GetValue()
        p = self.sl_map_patch.GetValue()
        d = self.sl_map_dest.GetValue()

        self._comitar_mapeamento_atual()

        if getattr(self.parent, 'output', None):
            import mido
            ch = self.canal_idx
            part_byte = 0x30 if ch == 9 else 0x31
            b_msb = min(127, b // 128)
            syx_data = [0xF0, 0x43, 0x10, 0x4C, part_byte, orig, 0x70, b_msb, b % 128, p, d, 0xF7]
            try: self.parent.output.send(mido.Message.from_bytes(syx_data))
            except: pass
            
        self.play_preview_direct(orig)
        
        from mhs_utils import get_drum_name, falar_status
        falar_status(f"Mapeamento aplicado. Testando a peça {get_drum_name(orig)}.", imediato=True)

    def play_preview_map(self):
        if not self.parent.output: return
        import mido
        import threading
        
        if getattr(self, 'preview_timer', None): 
            self.preview_timer.cancel()
            
        ch = self.canal_idx
        b_atual = self.parent.canais[ch].get("Bank", 16256)
        p_atual = self.parent.canais[ch].get("Patch", 0)
        
        b_novo = self.sp_map_bank.GetValue()
        p_novo = self.sl_map_patch.GetValue()
        nota_nova = self.sl_map_dest.GetValue()
        
        try:
            self.parent.output.send(mido.Message('control_change', channel=ch, control=123, value=0))
            
            self.parent.output.send(mido.Message('control_change', channel=ch, control=0, value=b_novo // 128))
            self.parent.output.send(mido.Message('control_change', channel=ch, control=32, value=b_novo % 128))
            self.parent.output.send(mido.Message('program_change', channel=ch, program=p_novo))
            self.parent.output.send(mido.Message('note_on', channel=ch, note=nota_nova, velocity=100))
            
            def restaurar_e_parar():
                if getattr(self.parent, 'output', None):
                    try:
                        self.parent.output.send(mido.Message('note_off', channel=ch, note=nota_nova, velocity=0))
                        self.parent.output.send(mido.Message('control_change', channel=ch, control=0, value=b_atual // 128))
                        self.parent.output.send(mido.Message('control_change', channel=ch, control=32, value=b_atual % 128))
                        self.parent.output.send(mido.Message('program_change', channel=ch, program=p_atual))
                        # Mesmo bug achado no Style Creator: resselecionar o
                        # Banco/Patch (pra tocar o kit doador e pra voltar)
                        # RESETA a afinação por nota no teclado real - sem
                        # isso, qualquer peça já CONFIRMADA (Alt+Aplicar)
                        # em OUTRA nota deste canal "se desfazia" sozinha
                        # no teclado só de mexer nos controles de uma peça
                        # diferente, mesmo sem clicar Aplicar pra ela.
                        self.reapply_preview_state()
                    except: pass

            self.preview_timer = threading.Timer(0.4, restaurar_e_parar)
            self.preview_timer.start()
        except: pass

    def update_nota_label(self):
        v = self.sl_nota.GetValue()
        b = self.parent.canais[self.canal_idx].get("Bank", 16256)
        p = self.parent.canais[self.canal_idx].get("Patch", 0)
        from mhs_utils import get_drum_name
        name = self.parent.key_names.get((b, p), {}).get(v, get_drum_name(v))
        self.lbl_nota.SetLabel(f"Peça (&Nota) a ser editada: {name}")

    def on_nota_change(self, event):
        note = self.sl_nota.GetValue()
        self.update_nota_label()
        
        for param_id, slider in self.sliders.items():
            val = self.drum_params.get((note, param_id), self._padrao_por_param.get(param_id, 64))
            slider.SetValue(val)
            name = next(n for c, n, mn, mx in self.sysex_params if c == param_id)
            self.labels[param_id].SetLabel(f"{name}: {val}")
            
        self.play_preview_direct(note)
        b = self.parent.canais[self.canal_idx].get("Bank", 16256)
        p = self.parent.canais[self.canal_idx].get("Patch", 0)
        from mhs_utils import get_drum_name, falar_status
        name = self.parent.key_names.get((b, p), {}).get(note, get_drum_name(note))
        falar_status(f"{name} ({note})", imediato=True)

    def on_param_change(self, event, param_id, slider, label):
        try:
            val = int(slider.GetValue()) 
        except ValueError:
            return 
            
        note = self.sl_nota.GetValue()
        
        if self.drum_params.get((note, param_id)) == val:
            return
        
        self.drum_params[(note, param_id)] = val
        self.parent.canais[self.canal_idx]["DrumParams"] = self.drum_params
        
        name = next(n for c, n, mn, mx in self.sysex_params if c == param_id)
        label.SetLabel(f"{name}: {val}")
        
        self.enviar_sysex_combo(note)
        self.play_preview_direct(note)

    def update_nota_label_nrpn(self):
        v = self.sl_nota_nrpn.GetValue()
        b = self.parent.canais[self.canal_idx].get("Bank", 16256)
        p = self.parent.canais[self.canal_idx].get("Patch", 0)
        name = self.parent.key_names.get((b, p), {}).get(v, get_drum_name(v))
        self.lbl_nota_nrpn.SetLabel(f"Peça (&Nota) a ser editada: {name}")

    def on_nota_change_nrpn(self, event):
        note = self.sl_nota_nrpn.GetValue()
        self.update_nota_label_nrpn()

        for param_id, slider in self.sliders_nrpn.items():
            val = self.drum_params_nrpn.get((note, param_id), DRUM_NRPN_DEFAULTS.get(param_id, 64))
            slider.SetValue(val)
            name = next(n for c, n, mn, mx in DRUM_NRPN_PARAMS if c == param_id)
            self.labels_nrpn[param_id].SetLabel(f"{name}: {val}")

        self.play_preview_direct(note)
        b = self.parent.canais[self.canal_idx].get("Bank", 16256)
        p = self.parent.canais[self.canal_idx].get("Patch", 0)
        name = self.parent.key_names.get((b, p), {}).get(note, get_drum_name(note))
        falar_status(f"{name} ({note})", imediato=True)

    def on_param_change_nrpn(self, event, param_id, slider, label):
        try:
            val = int(slider.GetValue())
        except ValueError:
            return

        note = self.sl_nota_nrpn.GetValue()

        if self.drum_params_nrpn.get((note, param_id)) == val:
            return

        self.drum_params_nrpn[(note, param_id)] = val
        self.parent.canais[self.canal_idx]["DrumParamsNRPN"] = self.drum_params_nrpn

        name = next(n for c, n, mn, mx in DRUM_NRPN_PARAMS if c == param_id)
        label.SetLabel(f"{name}: {val}")

        self.enviar_nrpn_combo(note)
        self.play_preview_direct(note)

    def enviar_nrpn_combo(self, note):
        # NRPN puro: 99=MSB (o parâmetro), 98=LSB (a peça/nota), 6=valor. O
        # Data List oficial diz que a LSB do Data Entry (CC38) é ignorada
        # pra esse bloco - só manda os 3 CCs de verdade, igual o próprio
        # motor de "restaurar estado ao dar Play" deste programa já espera
        # (ver o loop de nrpns_values no play_thread).
        if not self.parent.output: return
        import mido
        ch = self.canal_idx
        for (n, p_id), val in self.drum_params_nrpn.items():
            if n == note:
                for msg in (mido.Message('control_change', channel=ch, control=99, value=p_id),
                            mido.Message('control_change', channel=ch, control=98, value=note),
                            mido.Message('control_change', channel=ch, control=6, value=val)):
                    try: self.parent.output.send(msg)
                    except: pass

    def on_map_param_change(self, event):
        try:
            b = int(self.sp_map_bank.GetValue())
            p = int(self.sl_map_patch.GetValue())
            d = int(self.sl_map_dest.GetValue())
        except ValueError:
            return
            
        estado_atual = (b, p, d)
        if getattr(self, 'ultimo_estado_map', None) == estado_atual:
            return
        self.ultimo_estado_map = estado_atual
        
        from mhs_utils import falar_status, get_drum_name
        obj = event.GetEventObject()
        if obj == self.sp_map_bank:
            falar_status(f"Banco Doador: {b}", imediato=True)
        elif obj == self.sl_map_patch:
            nome_kit = f"Kit {p}"
            if hasattr(self.parent, 'instrument_names'):
                nome_kit = self.parent.instrument_names.get(b, {}).get(p, nome_kit)
            falar_status(f"Patch: {nome_kit} ({p})", imediato=True)
        elif obj == self.sl_map_dest:
            falar_status(f"Nova Peça: {get_drum_name(d)} ({d})", imediato=True)

        self.update_map_labels()
        # NÃO comita aqui - só o botão "&Aplicar Mapeamento desta Peça"
        # comita de verdade (mesmo fix aplicado no Style Creator): uma
        # "rede de segurança" anterior comitava a cada mudança de valor
        # E no próprio OK, o que sobrescrevia o mapeamento de QUALQUER
        # peça - mesmo sem editar nada - só de abrir e fechar a tela.
        # Só o preview ao vivo mesmo, pra poder ouvir a peça antes de
        # decidir aplicar de verdade.
        self.play_preview_map()

    def enviar_sysex_combo(self, note):
        if not self.parent.output: return
        import mido
        ch = self.canal_idx
        part_byte = 0x30 if ch == 9 else 0x31
        
        if note in self.custom_maps:
            m = self.custom_maps[note]
            syx_map = [0xF0, 0x43, 0x10, 0x4C, part_byte, note, 0x70, m['bank']//128, m['bank']%128, m['patch'], m['dest_note'], 0xF7]
            try: self.parent.output.send(mido.Message.from_bytes(syx_map))
            except: pass
            
        for (n, p_id), val in self.drum_params.items():
            if n == note:
                syx_param = [0xF0, 0x43, 0x10, 0x4C, part_byte, note, p_id, val, 0xF7]
                try: self.parent.output.send(mido.Message.from_bytes(syx_param))
                except: pass

    def play_preview_direct(self, note):
        if not self.parent.output: return
        import mido
        import threading
        
        if getattr(self, 'preview_timer', None): 
            self.preview_timer.cancel()
        
        ch = self.canal_idx
        
        try:
            self.parent.output.send(mido.Message('control_change', channel=ch, control=123, value=0))
            self.parent.output.send(mido.Message('note_on', channel=ch, note=note, velocity=100))
            
            def stop_note():
                if getattr(self.parent, 'output', None):
                    try: self.parent.output.send(mido.Message('note_off', channel=ch, note=note, velocity=0))
                    except: pass
                    
            self.preview_timer = threading.Timer(0.4, stop_note)
            self.preview_timer.start()
        except: pass

    def handle_midi_in(self, msg):
        if not getattr(self.parent, 'output', None): return
        import mido
        
        if msg.type in ['note_on', 'note_off', 'polytouch']:
            is_hit = (msg.type == 'note_on' and msg.velocity > 0)
            orig_note = msg.note
            ch = self.canal_idx
            
            if is_hit:
                self.enviar_sysex_combo(orig_note)
                self.enviar_nrpn_combo(orig_note)

            out_msg = msg.copy(channel=ch)
            try: self.parent.output.send(out_msg)
            except: pass

    def on_key(self, event):
        import wx
        code = event.GetKeyCode()
        ctrl = event.ControlDown()
        
        if code == wx.WXK_SPACE:
            if ctrl: self.parent.toggle_pausa(None)
            else: self.parent.toggle_reproducao(None)
            # O arquivo ainda não tem a edição desta tela (só é gravado de
            # verdade no OK) - o Play, tocando o arquivo do jeito que ele
            # ainda está, manda o Banco/Patch e o SysEx por peça ANTIGOS
            # logo na entrada, o que reseta a peça pro padrão do kit.
            # Reenviar por cima (valores novos) precisa chegar DEPOIS desse
            # envio antigo mas ANTES da primeira nota - uma tentativa só
            # (300ms) às vezes perdia a primeira batida quando ela caía bem
            # no começo. Várias tentativas num intervalo curto cobrem essa
            # margem sem apostar tudo num único palpite de tempo.
            for atraso in (20, 60, 150, 300):
                wx.CallLater(atraso, self.reapply_preview_state)
            return

        focus = wx.Window.FindFocus()
        if focus:
            spin = focus if isinstance(focus, wx.SpinCtrl) else focus.GetParent()
            
            if isinstance(spin, wx.SpinCtrl):
                if code in [wx.WXK_HOME, wx.WXK_END, wx.WXK_PAGEUP, wx.WXK_PAGEDOWN]:
                    val = spin.GetValue()
                    min_val = spin.GetMin()
                    max_val = spin.GetMax()
                    
                    step = 10 if max_val <= 127 else 1000 
                    
                    if code == wx.WXK_HOME:
                        novo_val = max_val  
                    elif code == wx.WXK_END:
                        novo_val = min_val  
                    elif code == wx.WXK_PAGEUP:
                        novo_val = min(max_val, val + step)
                    elif code == wx.WXK_PAGEDOWN:
                        novo_val = max(min_val, val - step)
                        
                    spin.SetValue(int(novo_val))
                    
                    evt = wx.CommandEvent(wx.wxEVT_TEXT, spin.GetId())
                    evt.SetEventObject(spin)
                    spin.GetEventHandler().ProcessEvent(evt)
                    
                    return 

        event.Skip()

    def reapply_preview_state(self):
        if not self.parent.output: return
        import mido
        ch = self.canal_idx
        part_byte = 0x30 if ch == 9 else 0x31
        
        for orig_note, m in self.custom_maps.items():
            syx_map = [0xF0, 0x43, 0x10, 0x4C, part_byte, orig_note, 0x70, m['bank']//128, m['bank']%128, m['patch'], m['dest_note'], 0xF7]
            try: self.parent.output.send(mido.Message.from_bytes(syx_map))
            except: pass

        for (note, param_id), val in self.drum_params.items():
            syx_param = [0xF0, 0x43, 0x10, 0x4C, part_byte, note, param_id, val, 0xF7]
            try: self.parent.output.send(mido.Message.from_bytes(syx_param))
            except: pass

        for (note, param_id), val in self.drum_params_nrpn.items():
            for msg in (mido.Message('control_change', channel=ch, control=99, value=param_id),
                        mido.Message('control_change', channel=ch, control=98, value=note),
                        mido.Message('control_change', channel=ch, control=6, value=val)):
                try: self.parent.output.send(msg)
                except: pass

    def on_remover(self, event):
        from mhs_utils import falar_status
        if not self.drum_params and not self.custom_maps and not self.drum_params_nrpn:
            falar_status("Este canal não tem nenhuma configuração de bateria personalizada.", imediato=True)
            return

        self.drum_params = {}
        self.custom_maps = {}
        self.drum_params_nrpn = {}
        self.parent.canais[self.canal_idx]["DrumParams"] = {}
        self.parent.canais[self.canal_idx]["CustomDrumMap"] = {}
        self.parent.canais[self.canal_idx]["DrumParamsNRPN"] = {}

        # Reseta ao vivo pra você já ouvir o kit voltando ao padrão de
        # fábrica, sem precisar fechar e reabrir - reenviar o mesmo
        # Banco+Patch é o que realmente reseta a afinação/pan/nível por
        # nota que o SysEx de Drum Setup já tinha aplicado no kit
        # (resselecionar o kit, mesmo que seja o mesmo, é o próprio
        # gatilho de reset - aqui é exatamente esse comportamento que a
        # gente quer provocar de propósito).
        if getattr(self.parent, 'output', None):
            import mido
            ch = self.canal_idx
            try:
                self.parent.output.send(mido.Message('control_change', channel=ch, control=123, value=0))
            except: pass
            c = self.parent.canais[ch]
            try:
                self.parent.enviar_midi_param("Bank", c["Bank"], ch)
                self.parent.enviar_midi_param("Patch", c["Patch"], ch)
            except: pass

        self.removido = True
        falar_status("Toda a configuração de bateria deste canal foi removida.", imediato=True)
        self.EndModal(wx.ID_OK)

    def get_values(self):
        # SEM rede de segurança aqui - devolve exatamente o que já foi
        # comitado de verdade (só pelo botão "Aplicar Mapeamento desta
        # Peça", ver on_aplicar_custom). Uma versão anterior comitava aqui
        # incondicionalmente (o que estivesse nos controles da Guia 2 no
        # instante do OK) - como o valor padrão dos controles ao ABRIR a
        # tela é sempre a peça 38 (o valor inicial fixo de sl_map_orig),
        # confirmar a tela SEM NUNCA ter tocado na Guia 2 sobrescrevia o
        # mapeamento real da peça 38. Mesmo fix já aplicado no Style
        # Creator (confirmado com o arquivo real do Michel).
        return self.drum_params, self.custom_maps, self.drum_params_nrpn
class MidiRouterDialog(wx.Dialog):
    def __init__(self, parent, rotas_atuais):
        super().__init__(parent, title="Conversor MIDI (Midi Convert to CC)", size=(500, 350))
        self.parent = parent
        self.rotas = rotas_atuais
            
        self.opcoes_cc = ["Pitch Bend"] + [f"CC {i} - {get_cc_name(i)}" for i in range(128)]
        self.mapa_opcoes = {"PB": 0}
        for i in range(128): self.mapa_opcoes[str(i)] = i + 1
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.chks = []
        self.cb_src = []
        self.cb_dst = []
        self.panels = []
        
        for i in range(4):
            sz_linha = wx.BoxSizer(wx.VERTICAL)
            chk = wx.CheckBox(self, label=f"Ativar Rota {i+1}")
            chk.SetValue(self.rotas[i]['active'])
            sz_linha.Add(chk, 0, wx.ALL, 5)
            
            panel_combos = wx.Panel(self)
            sz_combos = wx.BoxSizer(wx.HORIZONTAL)
            
            cb_s = wx.ComboBox(panel_combos, choices=self.opcoes_cc, style=wx.CB_READONLY, name=f"Origem da Rota {i+1}")
            idx_s = self.mapa_opcoes.get(self.rotas[i]['src'], 1)
            cb_s.SetSelection(idx_s)
            
            cb_d = wx.ComboBox(panel_combos, choices=self.opcoes_cc, style=wx.CB_READONLY, name=f"Destino da Rota {i+1}")
            idx_d = self.mapa_opcoes.get(self.rotas[i]['dst'], 1)
            cb_d.SetSelection(idx_d)
            
            sz_combos.Add(wx.StaticText(panel_combos, label="Origem: "), 0, wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, 5)
            sz_combos.Add(cb_s, 1, wx.EXPAND|wx.RIGHT, 15)
            sz_combos.Add(wx.StaticText(panel_combos, label="Destino: "), 0, wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, 5)
            sz_combos.Add(cb_d, 1, wx.EXPAND)
            
            panel_combos.SetSizer(sz_combos)
            sz_linha.Add(panel_combos, 0, wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM, 10)
            
            if not chk.GetValue():
                panel_combos.Hide()
                
            chk.Bind(wx.EVT_CHECKBOX, lambda e, p=panel_combos, c=chk, num=i+1: self.on_chk_toggle(e, p, c, num))
            
            self.chks.append(chk)
            self.cb_src.append(cb_s)
            self.cb_dst.append(cb_d)
            self.panels.append(panel_combos)
            
            sizer.Add(sz_linha, 0, wx.EXPAND|wx.BOTTOM, 5)

        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)
        wx.CallLater(100, self.chks[0].SetFocus)
        
    def on_chk_toggle(self, event, panel, chk, num):
        if chk.GetValue():
            panel.Show()
            falar_status(f"Rota {num} ativada", imediato=True)
        else:
            panel.Hide()
            falar_status(f"Rota {num} desativada", imediato=True)
        self.Layout()
        
    def get_valores(self):
        vals = []
        for i in range(4):
            src_val = "PB" if self.cb_src[i].GetSelection() == 0 else str(self.cb_src[i].GetSelection() - 1)
            dst_val = "PB" if self.cb_dst[i].GetSelection() == 0 else str(self.cb_dst[i].GetSelection() - 1)
            vals.append({
                'active': self.chks[i].GetValue(),
                'src': src_val,
                'dst': dst_val
            })
        return vals

class PropriedadesCanalDialog(wx.Dialog):
    def __init__(self, parent, canal_idx):
        super().__init__(parent, title=f"Propriedades do Canal {canal_idx+1}", size=(400, 450))
        self.parent = parent
        self.canal_idx = canal_idx
        self.canal_data = parent.canais[canal_idx]

        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(wx.StaticText(self, label="Banco:"), 0, wx.ALL, 5)
        self.bancos_ids = []
        self.bancos_list = []
        if self.parent.bank_names:
            for b_id in sorted(self.parent.bank_names.keys()):
                self.bancos_ids.append(b_id)
                self.bancos_list.append(f"{b_id} - {self.parent.bank_names[b_id]}")
        else:
            self.bancos_ids = [self.canal_data["Bank"]]
            self.bancos_list = [str(self.canal_data["Bank"])]

        self.combo_bank = wx.Choice(self, choices=self.bancos_list, name="Banco")
        self.combo_bank.SetToolTip("Banco")
        sizer.Add(self.combo_bank, 0, wx.EXPAND | wx.ALL, 5)

        try:
            idx_b = self.bancos_ids.index(self.canal_data["Bank"])
        except ValueError:
            idx_b = 0
        if self.bancos_list:
            self.combo_bank.SetSelection(idx_b)

        sizer.Add(wx.StaticText(self, label="Patch / Instrumento:"), 0, wx.ALL, 5)
        self.combo_patch = wx.Choice(self, choices=[], name="Patch do Instrumento")
        self.combo_patch.SetToolTip("Patch do Instrumento")
        sizer.Add(self.combo_patch, 0, wx.EXPAND | wx.ALL, 5)
        self.update_patch_choices()

        try:
            idx_p = self.patches_ids.index(self.canal_data["Patch"])
            self.combo_patch.SetSelection(idx_p)
        except ValueError:
            if self.patches_ids:
                self.combo_patch.SetSelection(0)

        self.combo_bank.Bind(wx.EVT_CHOICE, self.on_bank_change)
        self.combo_patch.Bind(wx.EVT_CHOICE, self.on_param_change)

        self.sliders = {}
        
        params = [
            ("Volume", self.canal_data["Volume"]),
            ("Pan", self.canal_data["Pan"]),
            ("Expression", self.canal_data["Expression"]),
            ("Reverb", self.canal_data["Reverb"]),
            ("Chorus", self.canal_data["Chorus"])
        ]

        for p_name, p_val in params:
            lbl = wx.StaticText(self, label=f"{p_name}: {p_val}")
            sizer.Add(lbl, 0, wx.ALL, 2)
            sl = wx.Slider(self, value=p_val, minValue=0, maxValue=127, style=wx.SL_HORIZONTAL, name=p_name)
            sl.SetToolTip(p_name)
            sizer.Add(sl, 0, wx.EXPAND | wx.ALL, 2)
            sl.Bind(wx.EVT_SLIDER, lambda e, p=p_name, s=sl, l=lbl: self.on_slider_change(e, p, s, l))
            self.sliders[p_name] = sl

        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        self.SetSizer(sizer)
        self.Layout()
        wx.CallLater(100, self.combo_bank.SetFocus)

    def update_patch_choices(self):
        sel_b = self.combo_bank.GetSelection()
        if sel_b == wx.NOT_FOUND: return
        bank_id = self.bancos_ids[sel_b]
        
        self.patches_ids = []
        self.patches_list = []
        
        if bank_id in self.parent.instrument_names:
            for p_id in sorted(self.parent.instrument_names[bank_id].keys()):
                self.patches_ids.append(p_id)
                self.patches_list.append(f"{p_id} - {self.parent.instrument_names[bank_id][p_id]}")
        else:
            self.patches_ids = [self.canal_data["Patch"]]
            self.patches_list = [str(self.canal_data["Patch"])]

        self.combo_patch.Clear()
        self.combo_patch.AppendItems(self.patches_list)
        if self.patches_list:
            self.combo_patch.SetSelection(0)

    def on_bank_change(self, event):
        self.update_patch_choices()
        self.apply_realtime()

    def on_param_change(self, event):
        self.apply_realtime()

    def on_slider_change(self, event, p_name, slider, label):
        val = slider.GetValue()
        label.SetLabel(f"{p_name}: {val}")
        self.apply_realtime()

    def apply_realtime(self):
        ch = self.canal_idx
        
        if hasattr(self, 'txt_nome'):
            novo_nome = self.txt_nome.GetValue().strip()
            if novo_nome:
                self.parent.canais[ch]["Nome"] = novo_nome
            
        if hasattr(self, 'txt_transp'):
            try: 
                self.parent.canais[ch]["Transpose"] = int(self.txt_transp.GetValue())
            except ValueError: 
                pass
                
        self.parent.dirty = True
        self.parent.atualizar_titulo()

        if not self.parent.output: return
        
        sel_b = self.combo_bank.GetSelection()
        sel_p = self.combo_patch.GetSelection()
        
        if sel_b != wx.NOT_FOUND and sel_p != wx.NOT_FOUND:
            b = self.bancos_ids[sel_b]
            p = self.patches_ids[sel_p]
            
            # Liberado todos os 16384 bancos em qualquer canal! Adeus travas!
            self.parent.output.send(mido.Message('control_change', channel=ch, control=0, value=b // 128))
            self.parent.output.send(mido.Message('control_change', channel=ch, control=32, value=b % 128))
            self.parent.output.send(mido.Message('program_change', channel=ch, program=p))
            
        vol = self.sliders["Volume"].GetValue()
        pan = self.sliders["Pan"].GetValue()
        exp = self.sliders["Expression"].GetValue()
        rev = self.sliders["Reverb"].GetValue()
        cho = self.sliders["Chorus"].GetValue()
        
        self.parent.output.send(mido.Message('control_change', channel=ch, control=7, value=vol))
        self.parent.output.send(mido.Message('control_change', channel=ch, control=10, value=pan))
        self.parent.output.send(mido.Message('control_change', channel=ch, control=11, value=exp))
        self.parent.output.send(mido.Message('control_change', channel=ch, control=91, value=rev))
        self.parent.output.send(mido.Message('control_change', channel=ch, control=93, value=cho))
        
        self.parent.enviar_xg_param(ch, "Volume", vol)
        self.parent.enviar_xg_param(ch, "Pan", pan)
        self.parent.enviar_xg_param(ch, "Reverb", rev)
        self.parent.enviar_xg_param(ch, "Chorus", cho)
    def get_valores(self):
        sel_b = self.combo_bank.GetSelection()
        sel_p = self.combo_patch.GetSelection()
        
        b = self.bancos_ids[sel_b] if sel_b != wx.NOT_FOUND else self.canal_data["Bank"]
        p = self.patches_ids[sel_p] if sel_p != wx.NOT_FOUND else self.canal_data["Patch"]
        
        return {
            "Bank": b,
            "Patch": p,
            "Volume": self.sliders["Volume"].GetValue(),
            "Pan": self.sliders["Pan"].GetValue(),
            "Expression": self.sliders["Expression"].GetValue(),
            "Reverb": self.sliders["Reverb"].GetValue(),
            "Chorus": self.sliders["Chorus"].GetValue()
        }

class SysExEditorDialog(wx.Dialog):
    def __init__(self, parent, canal_idx):
        super().__init__(parent, title="Editor de SysEx", size=(400, 500))
        self.parent = parent
        self.canal_idx = canal_idx
        self.preview_timer = None 
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        sizer.Add(wx.StaticText(self, label="Cabeçalho padrão (Hex):"), 0, wx.ALL, 5)
        self.txt_header = wx.TextCtrl(self, value="F0 43 10 4C")
        self.txt_header.SetToolTip("Cabeçalho padrão. Exemplo: F0 43 10 4C")
        sizer.Add(self.txt_header, 0, wx.EXPAND | wx.ALL, 5)
        
        sizer.Add(wx.StaticText(self, label="Multi Part (Hex):"), 0, wx.ALL, 5)
        self.txt_part = wx.TextCtrl(self, value="08")
        self.txt_part.SetToolTip("Multi Part. Exemplo: 08")
        sizer.Add(self.txt_part, 0, wx.EXPAND | wx.ALL, 5)
        
        sizer.Add(wx.StaticText(self, label="Canal MIDI (Hex):"), 0, wx.ALL, 5)
        self.txt_ch = wx.TextCtrl(self, value=f"{canal_idx:02X}")
        self.txt_ch.SetToolTip("Canal MIDI selecionado em Hexadecimal")
        sizer.Add(self.txt_ch, 0, wx.EXPAND | wx.ALL, 5)
        
        sizer.Add(wx.StaticText(self, label="Endereço Hexadecimal:"), 0, wx.ALL, 5)
        self.txt_addr = wx.TextCtrl(self, value="18")
        self.txt_addr.SetToolTip("Endereço do parâmetro. Exemplo: 16 para Vibrato, 18 para Filtro, 20 para MW Vibrato")
        sizer.Add(self.txt_addr, 0, wx.EXPAND | wx.ALL, 5)
        
        self.lbl_val = wx.StaticText(self, label="Valor da Intensidade: 64 (Hex: 40)")
        sizer.Add(self.lbl_val, 0, wx.ALL, 5)
        self.sl_val = wx.Slider(self, value=64, minValue=0, maxValue=127, style=wx.SL_HORIZONTAL)
        self.sl_val.SetToolTip("Valor da Intensidade")
        sizer.Add(self.sl_val, 0, wx.EXPAND | wx.ALL, 5)
        self.sl_val.Bind(wx.EVT_SLIDER, self.on_slider_change)
        
        sizer.Add(wx.StaticText(self, label="Fim da Mensagem (Hex):"), 0, wx.ALL, 5)
        self.txt_end = wx.TextCtrl(self, value="F7")
        self.txt_end.SetToolTip("Fim do SysEx. Padrão: F7")
        sizer.Add(self.txt_end, 0, wx.EXPAND | wx.ALL, 5)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        
        self.SetSizer(sizer)
        
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        
        wx.CallLater(100, self.txt_header.SetFocus)
        
    def on_key(self, event):
        code = event.GetKeyCode()
        ctrl = event.ControlDown()
        
        if code == wx.WXK_SPACE:
            if ctrl:
                self.parent.toggle_pausa(None)
            else:
                self.parent.toggle_reproducao(None)
            
            wx.CallLater(300, self.reapply_sysex)
            return 
        event.Skip()

    def reapply_sysex(self):
        bytes_sysex = self.get_sysex_bytes()
        if bytes_sysex and self.parent.output:
            try:
                self.parent.output.send(mido.Message.from_bytes(bytes_sysex))
            except: pass
            
    def on_slider_change(self, event):
        val = self.sl_val.GetValue()
        self.lbl_val.SetLabel(f"Valor da Intensidade: {val} (Hex: {val:02X})")
        self.play_preview()
        
    def play_preview(self):
        bytes_sysex = self.get_sysex_bytes()
        if bytes_sysex and self.parent.output:
            try:
                sysex_msg = mido.Message.from_bytes(bytes_sysex)
                self.parent.output.send(sysex_msg)
                
                if self.preview_timer:
                    self.preview_timer.cancel()
                
                ch = self.canal_idx
                note = 38 if ch == 9 else 60
                vel = 100
                
                self.parent.output.send(mido.Message('note_off', channel=ch, note=note, velocity=0))
                self.parent.output.send(mido.Message('note_on', channel=ch, note=note, velocity=vel))
                
                def stop_note():
                    if getattr(self.parent, 'output', None):
                        try:
                            self.parent.output.send(mido.Message('note_off', channel=ch, note=note, velocity=0))
                            self.parent.output.send(mido.Message('control_change', channel=ch, control=64, value=0))
                            self.parent.output.send(mido.Message('control_change', channel=ch, control=1, value=0))
                            self.parent.output.send(mido.Message('pitchwheel', channel=ch, pitch=0))
                        except: pass

                self.preview_timer = threading.Timer(0.5, stop_note)
                self.preview_timer.start()
            except: pass
            
    def get_sysex_bytes(self):
        try:
            h = self.txt_header.GetValue().replace("0x", "").replace(" ", "")
            p = self.txt_part.GetValue().replace("0x", "").replace(" ", "")
            c = self.txt_ch.GetValue().replace("0x", "").replace(" ", "")
            a = self.txt_addr.GetValue().replace("0x", "").replace(" ", "")
            v = f"{self.sl_val.GetValue():02X}"
            f = self.txt_end.GetValue().replace("0x", "").replace(" ", "")
            
            full_hex = h + p + c + a + v + f
            byte_array = bytearray.fromhex(full_hex)
            return list(byte_array)
        except Exception:
            return None

class AudioGuiaDialog(wx.Dialog):
    def __init__(self, parent, audio_path, audio_volume, audio_offset):
        super().__init__(parent, title="Áudio Guia / Playback", size=(450, 350))
        self.parent = parent
        self.audio_path = audio_path
        self.audio_volume = audio_volume
        self.audio_offset = audio_offset
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        sizer.Add(wx.StaticText(self, label="Arquivo de Áudio:"), 0, wx.ALL, 5)
        sz_file = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_path = wx.TextCtrl(self, value=self.audio_path if self.audio_path else "Nenhum arquivo carregado", style=wx.TE_READONLY)
        btn_browse = wx.Button(self, label="Procurar...")
        btn_clear = wx.Button(self, label="Remover")
        sz_file.Add(self.txt_path, 1, wx.EXPAND | wx.RIGHT, 5)
        sz_file.Add(btn_browse, 0, wx.RIGHT, 5)
        sz_file.Add(btn_clear, 0)
        sizer.Add(sz_file, 0, wx.EXPAND | wx.ALL, 5)
        
        self.lbl_vol = wx.StaticText(self, label=f"Volume do Áudio: {self.audio_volume}%")
        sizer.Add(self.lbl_vol, 0, wx.ALL, 5)
        self.sl_vol = wx.Slider(self, value=self.audio_volume, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)
        sizer.Add(self.sl_vol, 0, wx.EXPAND | wx.ALL, 5)
        
        off_ms = int(self.audio_offset * 1000)
        self.lbl_offset = wx.StaticText(self, label=f"Deslocamento: {off_ms} ms (+ atrasa o áudio, - adianta)")
        sizer.Add(self.lbl_offset, 0, wx.ALL, 5)
        self.sl_offset = wx.Slider(self, value=off_ms, minValue=-3600000, maxValue=3600000, style=wx.SL_HORIZONTAL)
        self.sl_offset.SetToolTip("Ajuste fino de sincronismo do áudio em milissegundos")
        sizer.Add(self.sl_offset, 0, wx.EXPAND | wx.ALL, 5)
        
        btn_browse.Bind(wx.EVT_BUTTON, self.on_browse)
        btn_clear.Bind(wx.EVT_BUTTON, self.on_clear)
        self.sl_vol.Bind(wx.EVT_SLIDER, self.on_vol_change)
        self.sl_offset.Bind(wx.EVT_SLIDER, self.on_offset_change)
        
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        
        self.SetSizer(sizer)
        wx.CallLater(100, btn_browse.SetFocus)
        
    def on_browse(self, event):
        with wx.FileDialog(self, "Escolha o Áudio Guia", wildcard="Áudio (*.mp3;*.wav;*.ogg)|*.mp3;*.wav;*.ogg", style=wx.FD_OPEN) as fd:
            if fd.ShowModal() == wx.ID_OK:
                self.audio_path = fd.GetPath()
                self.txt_path.SetValue(self.audio_path)
                
                # --- MÁGICA 1: O áudio é ancorado no tempo exato do cursor em SEGUNDOS ---
                cursor_sec = getattr(self.parent, 'current_playback_time', 0.0)
                self.audio_offset = cursor_sec
                self.parent.audio_offset = self.audio_offset
                
                # --- MÁGICA 2: O áudio ganha um "Alfinete Musical" no TICK exato ---
                if hasattr(self.parent, 'get_tick_at_sec'):
                    self.parent.audio_offset_tick = self.parent.get_tick_at_sec(cursor_sec)
                
                off_ms = int(self.audio_offset * 1000)
                self.sl_offset.SetValue(off_ms)
                self.lbl_offset.SetLabel(f"Deslocamento: {off_ms} ms (+ atrasa o áudio, - adianta)")

                self.parent.audio_path = self.audio_path
                try:
                    self.parent._audio_reset_mixer_format()
                except Exception:
                    pass

                if getattr(self.parent, 'tocando', False):
                    self.parent.seek_flag = True
                    
                from mhs_utils import falar_status
                falar_status("Áudio cravado na posição do cursor. Pressione espaço para testar.", imediato=True)
                
    def on_clear(self, event):
        self.audio_path = None
        self.txt_path.SetValue("Nenhum arquivo carregado")
        self.parent.audio_path = None
        try: self.parent._audio_stop()
        except Exception: pass
        from mhs_utils import falar_status
        falar_status("Áudio removido.", imediato=True)
        
        # Grava a remoção do áudio no config.json na hora!
        self.parent.salvar_config_audio()
        
    def on_vol_change(self, event):
        self.audio_volume = self.sl_vol.GetValue()
        self.lbl_vol.SetLabel(f"Volume do Áudio: {self.audio_volume}%")
        self.parent.audio_volume = self.audio_volume
        try: self.parent._apply_audio_vol()
        except Exception: pass
        
    def on_offset_change(self, event):
        off_ms = self.sl_offset.GetValue()
        self.audio_offset = off_ms / 1000.0
        self.lbl_offset.SetLabel(f"Deslocamento: {off_ms} ms (+ atrasa o áudio, - adianta)")
        
        self.parent.audio_offset = self.audio_offset
        if hasattr(self.parent, 'get_tick_at_sec'):
            self.parent.audio_offset_tick = self.parent.get_tick_at_sec(self.audio_offset)
            
        if getattr(self.parent, 'tocando', False):
            self.parent.seek_flag = True
        
    def on_key(self, event):
        code = event.GetKeyCode()
        ctrl = event.ControlDown()
        alt = event.AltDown()
        
        if code == wx.WXK_SPACE:
            if ctrl:
                self.parent.toggle_pausa(None)
            else:
                self.parent.toggle_reproducao(None)
            return 
            
        if code == ord('T') or code == ord('t'):
            if not (ctrl or alt):
                self.parent.do_tap_tempo(None)
                return

        foco = self.FindFocus()
        if foco == self.sl_offset:
            val = self.sl_offset.GetValue()
            mudou = False
            
            if code == wx.WXK_LEFT:
                novo_val = max(self.sl_offset.GetMin(), val - 10)
                mudou = True
            elif code == wx.WXK_RIGHT:
                novo_val = min(self.sl_offset.GetMax(), val + 10)
                mudou = True
            elif code == wx.WXK_UP:
                novo_val = min(self.sl_offset.GetMax(), val + 1)
                mudou = True
            elif code == wx.WXK_DOWN:
                novo_val = max(self.sl_offset.GetMin(), val - 1)
                mudou = True
                
            if mudou:
                self.sl_offset.SetValue(novo_val)
                self.on_offset_change(None)
                from mhs_utils import falar_status
                falar_status(f"{novo_val}", imediato=True)
                return
                
        event.Skip()
        
    def get_valores(self):
        return self.audio_path, self.audio_volume, self.audio_offset
class PreciseTempoDialog(wx.Dialog):
    def __init__(self, parent, current_bpm):
        # Título limpo e profissional, sem citar o vizinho! kkkkkk
        super().__init__(parent, title="Alterar BPM", size=(350, 150))
        self.parent = parent
        self.bpm = float(current_bpm)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        lbl = wx.StaticText(self, label="Digite o BPM (ex: 125.352) ou use Setas Cima/Baixo:")
        sizer.Add(lbl, 0, wx.ALL, 5)
        
        self.txt_bpm = wx.TextCtrl(self, value=f"{self.bpm:.3f}", style=wx.TE_PROCESS_ENTER)
        sizer.Add(self.txt_bpm, 0, wx.EXPAND | wx.ALL, 5)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        self.SetSizer(sizer)
        
        self.txt_bpm.Bind(wx.EVT_KEY_DOWN, self.on_key)
        self.txt_bpm.Bind(wx.EVT_TEXT_ENTER, self.on_enter)
        wx.CallLater(100, self.txt_bpm.SetFocus)
        
    def on_key(self, event):
        code = event.GetKeyCode()
        try:
            # Aceita tanto ponto quanto vírgula
            atual = float(self.txt_bpm.GetValue().replace(',', '.'))
        except:
            atual = self.bpm
            
        mudou = False
        if code == wx.WXK_UP:
            atual += 1.0
            mudou = True
        elif code == wx.WXK_DOWN:
            atual -= 1.0
            mudou = True
            
        if mudou:
            atual = max(20.0, min(999.0, atual))
            self.txt_bpm.SetValue(f"{atual:.3f}")
            self.txt_bpm.SetInsertionPointEnd()
            from mhs_utils import falar_status
            falar_status(f"{atual:.3f}", imediato=True)
        else:
            event.Skip()

    def on_enter(self, event):
        self.EndModal(wx.ID_OK)
        
    def get_bpm(self):
        try:
            return float(self.txt_bpm.GetValue().replace(',', '.'))
        except:
            return self.bpm

class QuantizeProDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="Quantização de Precisão", size=(400, 250))
        self.parent = parent
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.grids = [
            ("Semínima (1/4)", 480),
            ("Semínima Tercina (1/4T)", 320),
            ("Colcheia (1/8)", 240),
            ("Colcheia Tercina (1/8T)", 160),
            ("Semicolcheia (1/16)", 120),
            ("Semicolcheia Tercina (1/16T)", 80),
            ("Fusa (1/32)", 60),
            ("Fusa Tercina (1/32T)", 40),
            ("Semifusa (1/64)", 30)
        ]
        
        sizer.Add(wx.StaticText(self, label="Grade de Quantização:"), 0, wx.ALL, 5)
        self.cb_grid = wx.ComboBox(self, value=self.grids[4][0], choices=[g[0] for g in self.grids], style=wx.CB_READONLY)
        self.cb_grid.SetSelection(4)
        sizer.Add(self.cb_grid, 0, wx.EXPAND | wx.ALL, 5)
        
        sizer.Add(wx.StaticText(self, label="Força (%):"), 0, wx.ALL, 5)
        self.sp_forca = wx.SpinCtrl(self, value="100", min=1, max=100)
        sizer.Add(self.sp_forca, 0, wx.EXPAND | wx.ALL, 5)
        
        self.lbl_preview = wx.StaticText(self, label="ESPAÇO: Ouvir/Parar Preview", style=wx.ALIGN_CENTER)
        sizer.Add(self.lbl_preview, 0, wx.ALL | wx.EXPAND, 10)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)
        
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        wx.CallLater(100, self.cb_grid.SetFocus)
        
    def get_values(self):
        base_grid = self.grids[self.cb_grid.GetSelection()][1]
        # Pega o TPB do arquivo MIDI de onde quer que o parent esteja
        target = self.parent.parent if hasattr(self.parent, 'display_events') else self.parent
        tpb = getattr(target.midi_file, 'ticks_per_beat', 480)
        grid_ticks = int(round(base_grid * (tpb / 480.0)))
        return grid_ticks, self.sp_forca.GetValue()

    def on_key(self, event):
        code = event.GetKeyCode()
        
        # --- A CORREÇÃO: O Enter (OK) agora processa e salva a quantização de verdade! ---
        if code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            grid_ticks, forca = self.get_values()
            
            # Puxa as referências do Sequencer
            seq = self.parent.parent if hasattr(self.parent, 'display_events') else self.parent
            seq.save_state("Quantização Offline")
            
            t_start, t_end = seq.get_selection_bounds()
            st_tick = seq.get_tick_at_sec(t_start) if t_start != float('inf') else 0
            ed_tick = seq.get_tick_at_sec(t_end) if t_end != float('inf') else float('inf')
            canais_alvo = getattr(seq, 'canais_selecionados', {seq.canal_atual})
            
            import mido
            notas_mudadas = 0
            for i, track in enumerate(seq.midi_file.tracks):
                abs_t, active, flat = 0, {}, []
                for msg in track:
                    abs_t += msg.time
                    ch = getattr(msg, 'channel', None)
                    if ch in canais_alvo and (st_tick <= abs_t < ed_tick):
                        if msg.type == 'note_on' and msg.velocity > 0:
                            closest = round(abs_t / grid_ticks) * grid_ticks
                            offset = (closest - abs_t) * (forca / 100.0)
                            new_start = max(0, int(round(abs_t + offset)))
                            active[(ch, msg.note)] = (new_start, abs_t, msg)
                            notas_mudadas += 1
                        elif msg.type in ['note_off', 'note_on'] and (ch, getattr(msg, 'note', None)) in active:
                            new_s, old_s, m_on = active.pop((ch, msg.note))
                            flat.append([new_s, m_on])
                            flat.append([new_s + (abs_t - old_s), msg])
                        else: flat.append([abs_t, msg])
                    else: flat.append([abs_t, msg])
                
                flat.sort(key=lambda x: x[0])
                new_track = mido.MidiTrack()
                curr = 0
                for t, m in flat:
                    new_track.append(m.copy(time=t - curr))
                    curr = t
                seq.midi_file.tracks[i] = new_track

            seq.dirty = True
            seq.ler_midi_memoria(reset_canais=False)
            
            if hasattr(self.parent, 'preview_is_playing'): self.parent.preview_is_playing = False
            if hasattr(seq, 'all_notes_off'): seq.all_notes_off()
            
            from mhs_utils import falar_status
            falar_status(f"{notas_mudadas} notas quantizadas com sucesso.", imediato=True)
            self.EndModal(wx.ID_OK)
            return
            
        if code in [wx.WXK_SPACE, 32]:
            if getattr(self.parent, 'preview_is_playing', False):
                self.parent.preview_is_playing = False
                if hasattr(self.parent, 'all_notes_off'): self.parent.all_notes_off()
                from mhs_utils import falar_status
                falar_status("Preview parado.", imediato=True)
            else:
                grid, forca = self.get_values()
                if hasattr(self.parent, 'play_quantize_preview'):
                    self.parent.play_quantize_preview(grid, forca)
            return
            
        if code == wx.WXK_ESCAPE:
            if hasattr(self.parent, 'preview_is_playing'): self.parent.preview_is_playing = False
            if hasattr(self.parent, 'all_notes_off'): self.parent.all_notes_off()
            self.EndModal(wx.ID_CANCEL)
            return
            
        event.Skip()
class GlobalEffectsDialog(wx.Dialog):
    # Reverb e Chorus Globais com os 16 parâmetros de cada um (não só
    # Decay/Return) e nomes de preset de verdade - mesmo modelo usado no
    # MHS Style Creator, com endereços conferidos contra o Data List
    # oficial do PSR-SX600 (bloco 02 01, 00-0D Reverb / 20-2D Chorus).
    def __init__(self, parent):
        super().__init__(parent, title="Efeitos DSP Globais (Yamaha XG)", size=(480, 640))
        self.parent_seq = parent

        # A MÁGICA: A tela apenas lê o Cache Oficial do programa, que já foi
        # preenchido na hora que você deu o "Load" no arquivo MIDI.
        if not hasattr(self.parent_seq, 'dsp_cache'):
            self.parent_seq.dsp_cache = {
                'active': False, 'rev_msb_idx': 1, 'rev_lsb_idx': 0,
                'rev_p': [-1] * 16, 'rev_ret': 64,
                'cho_msb_idx': 1, 'cho_lsb_idx': 0,
                'cho_p': [-1] * 16, 'cho_ret': 64,
            }
        cache = self.parent_seq.dsp_cache

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        notebook = wx.Notebook(panel)

        rev_msb_val = REV_MSB_LIST[cache.get('rev_msb_idx', 1)][1] if cache.get('rev_msb_idx', 1) < len(REV_MSB_LIST) else 1
        rev_scr, self.rev_msb_choice, self.rev_lsb_choice, self.rev_ret_spin, self.rev_modulos = self._monta_pagina(
            notebook, "Reverb", rev_msb_val, REV_MSB_LIST, cache.get('rev_msb_idx', 1),
            cache.get('rev_lsb_idx', 0), cache.get('rev_ret', 64), cache.get('rev_p', [-1] * 16))
        notebook.AddPage(rev_scr.GetParent(), "Reverb Global")

        cho_msb_val = CHO_MSB_LIST[cache.get('cho_msb_idx', 1)][1] if cache.get('cho_msb_idx', 1) < len(CHO_MSB_LIST) else 65
        cho_scr, self.cho_msb_choice, self.cho_lsb_choice, self.cho_ret_spin, self.cho_modulos = self._monta_pagina(
            notebook, "Chorus", cho_msb_val, CHO_MSB_LIST, cache.get('cho_msb_idx', 1),
            cache.get('cho_lsb_idx', 0), cache.get('cho_ret', 64), cache.get('cho_p', [-1] * 16))
        notebook.AddPage(cho_scr.GetParent(), "Chorus Global")

        vbox.Add(notebook, 1, wx.EXPAND | wx.ALL, 5)

        # --- Player na Tela ---
        transp_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_play = wx.Button(panel, label="Play / Stop")
        self.btn_play.SetName("Botão Play Stop")
        self.btn_pause = wx.Button(panel, label="Pausar / Retomar")
        self.btn_pause.SetName("Botão Pausar")
        transp_sizer.Add(self.btn_play, 0, wx.ALL, 5)
        transp_sizer.Add(self.btn_pause, 0, wx.ALL, 5)
        self.btn_play.Bind(wx.EVT_BUTTON, self.on_play)
        self.btn_pause.Bind(wx.EVT_BUTTON, self.on_pause)
        vbox.Add(transp_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 5)

        # --- Botões de Ação ---
        btn_sizer = wx.StdDialogButtonSizer()
        self.btn_ok = wx.Button(panel, wx.ID_OK, "Aplicar no Projeto")
        self.btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Cancelar")
        btn_sizer.AddButton(self.btn_ok)
        btn_sizer.AddButton(self.btn_cancel)
        btn_sizer.Realize()
        vbox.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        panel.SetSizer(vbox)

        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.rev_msb_choice.Bind(wx.EVT_CHOICE, self.on_rev_msb_change)
        self.cho_msb_choice.Bind(wx.EVT_CHOICE, self.on_cho_msb_change)
        for ctrl in ([self.rev_lsb_choice, self.rev_ret_spin] + [m for m in self.rev_modulos if m is not None]
                     + [self.cho_lsb_choice, self.cho_ret_spin] + [m for m in self.cho_modulos if m is not None]):
            ctrl.Bind(wx.EVT_CHOICE if isinstance(ctrl, wx.Choice) else wx.EVT_SPINCTRL, self.on_change)

    def _monta_pagina(self, notebook, rotulo, msb_val, msb_list, msb_idx, lsb_idx, ret_val, p_salvos):
        pai = wx.Panel(notebook)
        scr = wx.ScrolledWindow(pai, style=wx.VSCROLL)
        scr.SetScrollRate(0, 20)
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(wx.StaticText(scr, label=f"Categoria do {rotulo}:"), 0, wx.LEFT | wx.TOP, 10)
        msb_choice = wx.Choice(scr, choices=[item[0] for item in msb_list])
        msb_choice.SetSelection(msb_idx)
        msb_choice.SetName(f"Categoria do {rotulo}")
        sizer.Add(msb_choice, 0, wx.EXPAND | wx.ALL, 5)

        sizer.Add(wx.StaticText(scr, label=f"Preset do {rotulo}:"), 0, wx.LEFT | wx.TOP, 10)
        lsb_choice = wx.Choice(scr, choices=nomes_presets(msb_val))
        lsb_choice.SetSelection(lsb_idx if 0 <= lsb_idx < lsb_choice.GetCount() else wx.NOT_FOUND)
        lsb_choice.SetName(f"Preset do {rotulo}")
        sizer.Add(lsb_choice, 0, wx.EXPAND | wx.ALL, 5)

        sizer.Add(wx.StaticText(scr, label="Return / Dry-Wet Balance (0 a 127):"), 0, wx.LEFT | wx.TOP, 10)
        ret_spin = wx.SpinCtrl(scr, value=str(ret_val), min=0, max=127)
        ret_spin.SetName(f"Return do {rotulo}")
        sizer.Add(ret_spin, 0, wx.EXPAND | wx.ALL, 5)

        nomes = DSP_PARAM_NAMES.get(msb_val, [f"Parâmetro {i + 1}" for i in range(16)])
        maximos_msb = DSP_PARAM_MAX.get(msb_val, {})
        modulos = [None] * 16
        for i in range(16):
            if i >= len(nomes) or nomes[i] == "-":
                continue
            # Alguns parâmetros são uma lista curta de opções com nome (ex:
            # "Input Mode: Mono, Stereo") em vez de 0-127 livre - o Data List
            # documenta o valor máximo real, então o slider para no último
            # nome em vez de rolar até 127 à toa.
            max_i = maximos_msb.get(i, 127)
            sizer.Add(wx.StaticText(scr, label=f"{nomes[i]} (0 a {max_i}, -1 = não usar):"), 0, wx.LEFT | wx.TOP, 10)
            sl = wx.SpinCtrl(scr, value=str(p_salvos[i] if i < len(p_salvos) else -1), min=-1, max=max_i)
            sl.SetName(nomes[i])
            sl._opcoes_dsp = DSP_PARAM_OPTIONS.get(msb_val, {}).get(i)
            sizer.Add(sl, 0, wx.EXPAND | wx.ALL, 5)
            modulos[i] = sl

        scr.SetSizer(sizer)
        pai_sizer = wx.BoxSizer(wx.VERTICAL)
        pai_sizer.Add(scr, 1, wx.EXPAND)
        pai.SetSizer(pai_sizer)
        return scr, msb_choice, lsb_choice, ret_spin, modulos

    def on_rev_msb_change(self, event):
        msb_sel = self.rev_msb_choice.GetSelection()
        msb_val = REV_MSB_LIST[msb_sel][1] if msb_sel != wx.NOT_FOUND and msb_sel < len(REV_MSB_LIST) else 1
        self.rev_lsb_choice.Set(nomes_presets(msb_val))
        self.rev_lsb_choice.SetSelection(0)
        self.on_change(event)

    def on_cho_msb_change(self, event):
        msb_sel = self.cho_msb_choice.GetSelection()
        msb_val = CHO_MSB_LIST[msb_sel][1] if msb_sel != wx.NOT_FOUND and msb_sel < len(CHO_MSB_LIST) else 65
        self.cho_lsb_choice.Set(nomes_presets(msb_val))
        self.cho_lsb_choice.SetSelection(0)
        self.on_change(event)

    def on_play(self, event):
        if hasattr(self.parent_seq, 'toggle_reproducao'):
            self.parent_seq.toggle_reproducao(None)

    def on_pause(self, event):
        if hasattr(self.parent_seq, 'toggle_pausa'):
            self.parent_seq.toggle_pausa(None)

    def on_change(self, event=None):
        c = self.parent_seq.dsp_cache
        c['active'] = True
        c['rev_msb_idx'] = self.rev_msb_choice.GetSelection()
        c['rev_lsb_idx'] = self.rev_lsb_choice.GetSelection()
        c['rev_ret'] = self.rev_ret_spin.GetValue()
        c['rev_p'] = [m.GetValue() if m else -1 for m in self.rev_modulos]
        c['cho_msb_idx'] = self.cho_msb_choice.GetSelection()
        c['cho_lsb_idx'] = self.cho_lsb_choice.GetSelection()
        c['cho_ret'] = self.cho_ret_spin.GetValue()
        c['cho_p'] = [m.GetValue() if m else -1 for m in self.cho_modulos]

        obj = event.GetEventObject() if event is not None else None
        if obj is not None and hasattr(obj, 'GetName'):
            nome = obj.GetName()
            if isinstance(obj, wx.Choice):
                falar_status(f"{nome}: {obj.GetStringSelection()}", imediato=True)
            elif isinstance(obj, wx.SpinCtrl):
                falar_status(_rotulo_valor_dsp(nome, obj.GetValue(), getattr(obj, '_opcoes_dsp', None)), imediato=True)

        # Envia pro Teclado em Tempo Real pra você testar a sala
        if hasattr(self.parent_seq, 'enviar_ambientacao_completa'):
            self.parent_seq.enviar_ambientacao_completa()
        if event is not None:
            event.Skip()

    def on_key(self, event):
        code = event.GetKeyCode()
        ctrl = event.ControlDown()
        shift = event.ShiftDown()
        alt = event.AltDown()

        if code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            self.EndModal(wx.ID_OK)
            return
        elif code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return

        if code in [wx.WXK_SPACE, 32]:
            if ctrl and not alt and not shift:
                self.on_pause(None)
                return
            elif not ctrl and not alt and not shift:
                self.on_play(None)
                return

        obj = self.FindFocus()
        if isinstance(obj, wx.SpinCtrl):
            val, max_v, min_v = obj.GetValue(), obj.GetMax(), obj.GetMin()
            mudou = False
            if code == wx.WXK_HOME: val = max_v; mudou = True
            elif code == wx.WXK_END: val = min_v; mudou = True
            elif code in (wx.WXK_PAGEUP, wx.WXK_NUMPAD_PAGEUP): val = min(max_v, val + 10); mudou = True
            elif code in (wx.WXK_PAGEDOWN, wx.WXK_NUMPAD_PAGEDOWN): val = max(min_v, val - 10); mudou = True
            if mudou:
                obj.SetValue(val)
                self.on_change(None)
                falar_status(_rotulo_valor_dsp(obj.GetName(), val, getattr(obj, '_opcoes_dsp', None)), imediato=True)
                return

        event.Skip()

class SysExListDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="Gerenciador Avançado de SysEx", size=(750, 600))
        self.parent_seq = parent
        self.modificado = False
        self.todos_sysex = [] 
        self.sysex_visiveis = []
        
        # --- BACKUP DE EMERGÊNCIA ---
        self.backup_tracks = []
        if self.parent_seq.midi_file:
            import mido
            for track in self.parent_seq.midi_file.tracks:
                new_track = mido.MidiTrack()
                new_track.extend([msg.copy() for msg in track])
                self.backup_tracks.append(new_track)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # --- BARRA DE FILTROS ---
        filtro_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # 1º Campo: Foco (Canal)
        self.cb_canal = wx.ComboBox(self, choices=["Todos os Canais", "Canal Atual"], style=wx.CB_READONLY)
        self.cb_canal.SetSelection(0)
        self.cb_canal.SetName("Foco")
        self.cb_canal.Bind(wx.EVT_COMBOBOX, self.on_filtro_change)
        filtro_sizer.Add(wx.StaticText(self, label="Foco:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        filtro_sizer.Add(self.cb_canal, 0, wx.ALL, 5)
        
        # 2º Campo: Tipo SysEx (Categorias) - conferidas/reorganizadas com
        # base em tudo que foi trabalhado nesta sessão (Voice Creator +
        # Portamento, DSP Variation x Insertion, Drum Setup Guia 1 x Guia 2)
        # - ver extrair_todos_sysex, que atribui a categoria certa a cada
        # item (campo 'categoria', não mais um "contém no texto" frágil).
        self.categorias = [
            "Todos", "Mixagem", "Voice Creator", "DSP Global", "DSP Variation",
            "DSP Insertion", "Drum Setup - Parâmetros", "Drum Setup - Montagem de Kit",
            "Outros",
        ]
        self.cb_filtro = wx.ComboBox(self, choices=self.categorias, style=wx.CB_READONLY)
        self.cb_filtro.SetSelection(0)
        self.cb_filtro.SetName("Tipo SysEx")
        self.cb_filtro.Bind(wx.EVT_COMBOBOX, self.on_filtro_change)
        filtro_sizer.Add(wx.StaticText(self, label="Tipo SysEx:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        filtro_sizer.Add(self.cb_filtro, 0, wx.ALL, 5)
        
        sizer.Add(filtro_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # Lista Principal
        sizer.Add(wx.StaticText(self, label="Lista de SysEx (Use Shift ou Ctrl para selecionar vários):"), 0, wx.ALL, 5)
        self.lista_box = wx.ListBox(self, style=wx.LB_EXTENDED)
        sizer.Add(self.lista_box, 1, wx.EXPAND | wx.ALL, 5)
        
        # --- Botões de Ação ---
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_edit = wx.Button(self, label="Editar")
        self.btn_del = wx.Button(self, label="Apagar")
        self.btn_copy = wx.Button(self, label="Copiar")
        self.btn_cut = wx.Button(self, label="Recortar")
        self.btn_paste = wx.Button(self, label="Colar")
        btn_sizer.Add(self.btn_edit, 0, wx.ALL, 2)
        btn_sizer.Add(self.btn_del, 0, wx.ALL, 2)
        btn_sizer.Add(self.btn_copy, 0, wx.ALL, 2)
        btn_sizer.Add(self.btn_cut, 0, wx.ALL, 2)
        btn_sizer.Add(self.btn_paste, 0, wx.ALL, 2)
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        
        # --- Botões de Arquivo ---
        arq_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_import = wx.Button(self, label="Importar .syx")
        self.btn_export = wx.Button(self, label="Exportar .syx")
        self.btn_cancelar = wx.Button(self, wx.ID_CANCEL, label="Cancelar")
        self.btn_fechar = wx.Button(self, wx.ID_OK, label="Fechar")
        arq_sizer.Add(self.btn_import, 0, wx.ALL, 2)
        arq_sizer.Add(self.btn_export, 0, wx.ALL, 2)
        arq_sizer.Add(self.btn_cancelar, 0, wx.ALL, 2)
        arq_sizer.Add(self.btn_fechar, 0, wx.ALL, 2)
        sizer.Add(arq_sizer, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)
        
        self.SetSizer(sizer)
        
        self.extrair_todos_sysex()
        self.aplicar_filtro()
        
        # --- BINDINGS ---
        self.btn_edit.Bind(wx.EVT_BUTTON, self.on_edit)
        self.btn_del.Bind(wx.EVT_BUTTON, self.on_delete)
        self.btn_copy.Bind(wx.EVT_BUTTON, self.on_copy)
        self.btn_cut.Bind(wx.EVT_BUTTON, self.on_cut)
        self.btn_paste.Bind(wx.EVT_BUTTON, self.on_paste)
        self.btn_import.Bind(wx.EVT_BUTTON, self.on_import)
        self.btn_export.Bind(wx.EVT_BUTTON, self.on_export)
        self.btn_cancelar.Bind(wx.EVT_BUTTON, self.on_cancelar_click)
        self.btn_fechar.Bind(wx.EVT_BUTTON, self.on_fechar_click)
        self.lista_box.Bind(wx.EVT_LISTBOX_DCLICK, self.on_edit)
        self.lista_box.Bind(wx.EVT_LISTBOX, self.on_list_select)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        
        acel_entries = [(wx.ACCEL_CTRL, ord('A'), 1001)]
        self.SetAcceleratorTable(wx.AcceleratorTable(acel_entries))
        self.Bind(wx.EVT_MENU, self.on_select_all, id=1001)
        
        # Foco inicial cravado no primeiro filtro!
        wx.CallLater(100, self.cb_canal.SetFocus)

    # Endereços do bloco Multi Part (43 1n 4C 08) que são "Mixagem" de
    # verdade - Bank/Patch/Volume/Pan/Reverb Send/Chorus Send - todos com
    # equivalente 1:1 em CC/Program Change padrão (ver consolidar_projeto).
    # Qualquer OUTRO endereço desse mesmo bloco 0x08 (Grave/Agudo, Detune,
    # forma de onda/filtro/EG/EQ, etc) é Voice Creator - não tem CC padrão,
    # só existe via esta SysEx mesmo.
    _CAMPOS_MIXAGEM = {
        0x01: "Bank Select MSB", 0x02: "Bank Select LSB", 0x03: "Program Number",
        0x0B: "Volume", 0x0E: "Pan", 0x13: "Reverb Send", 0x12: "Chorus Send",
    }
    _CAMPOS_PORTAMENTO_0A = {
        0x01: "Mono Priority", 0x02: "Modo do Portamento", 0x03: "Modo do Tempo",
    }

    def extrair_todos_sysex(self):
        self.todos_sysex = []
        if not self.parent_seq.midi_file: return

        for tr_idx, track in enumerate(self.parent_seq.midi_file.tracks):
            abs_tick = 0
            for msg_idx, msg in enumerate(track):
                abs_tick += msg.time
                if msg.type == 'sysex':
                    data = msg.data
                    hex_str = "F0 " + " ".join([f"{b:02X}" for b in data]) + " F7"

                    desc = "SysEx Genérico"
                    categoria = "Outros"
                    canal_associado = -1

                    if len(data) >= 4 and tuple(data[0:4]) == (0x43, 0x10, 0x4C, 0x00):
                        desc = "XG System On"
                        categoria = "Outros"
                    elif len(data) == 4 and tuple(data[0:4]) == (0x7E, 0x7F, 0x09, 0x01):
                        desc = "GM System On"
                        categoria = "Outros"
                    elif len(data) >= 4 and tuple(data[0:4]) == (0x7F, 0x7F, 0x04, 0x01):
                        desc = "GS Reset"
                        categoria = "Outros"

                    # --- Drum Setup (Guia 1/2 - 43 1n 4C 30/31) - NUNCA a Guia
                    # 3 (NRPN), que não é SysEx e não aparece aqui.
                    elif len(data) >= 7 and tuple(data[0:3]) == (0x43, 0x10, 0x4C) and data[3] in (0x30, 0x31):
                        ch = 9 if data[3] == 0x30 else (data[3] - 0x31)
                        if 0 <= ch < 16:
                            canal_associado = ch
                            peca = get_drum_name(data[4])
                            if data[5] == 0x70 and len(data) >= 10:
                                categoria = "Drum Setup - Montagem de Kit"
                                desc = f"Drum Setup - Montagem de Kit (Canal {ch+1}, Peça {peca} → nota {data[9]})"
                            else:
                                categoria = "Drum Setup - Parâmetros"
                                desc = f"Drum Setup - Parâmetro (Canal {ch+1}, Peça {peca}, Endereço 0x{data[5]:02X})"

                    # --- Multi Part (43 1n 4C 08) - Mixagem OU Voice Creator, ---
                    # --- conforme o endereço (ver _CAMPOS_MIXAGEM acima).    ---
                    elif len(data) >= 6 and tuple(data[0:3]) == (0x43, 0x10, 0x4C) and data[3] == 0x08:
                        canal_associado = data[4]
                        addr = data[5]
                        if addr in self._CAMPOS_MIXAGEM:
                            categoria = "Mixagem"
                            desc = f"Mixagem (Canal {data[4]+1}): {self._CAMPOS_MIXAGEM[addr]}"
                        elif addr == 0x72:
                            categoria = "Voice Creator"
                            desc = f"Voice Creator (Canal {data[4]+1}): EQ Grave"
                        elif addr == 0x73:
                            categoria = "Voice Creator"
                            desc = f"Voice Creator (Canal {data[4]+1}): EQ Agudo"
                        elif addr in (0x09, 0x0A):
                            categoria = "Voice Creator"
                            desc = f"Voice Creator (Canal {data[4]+1}): Detune ({'nibble alto' if addr == 0x09 else 'nibble baixo'})"
                        else:
                            categoria = "Voice Creator"
                            desc = f"Voice Creator (Canal {data[4]+1}): Parâmetro 0x{addr:02X}"

                    # --- Portamento (43 1n 4C 0A) - bloco SEPARADO do 0x08,  ---
                    # --- também vira Voice Creator na tela (mesma aba que   ---
                    # --- edita Mono Priority/Modo do Portamento/Tempo).     ---
                    elif len(data) >= 7 and tuple(data[0:3]) == (0x43, 0x10, 0x4C) and data[3] == 0x0A:
                        canal_associado = data[4]
                        campo = self._CAMPOS_PORTAMENTO_0A.get(data[5], f"Parâmetro 0x{data[5]:02X}")
                        categoria = "Voice Creator"
                        desc = f"Voice Creator (Canal {data[4]+1}): Portamento - {campo}"

                    # --- DSP Global (Reverb/Chorus) e DSP Variation (Gaveta ---
                    # --- 1) - mesmo bloco 43 10 4C 02 01, endereço decide.  ---
                    elif len(data) >= 6 and tuple(data[0:3]) == (0x43, 0x10, 0x4C) and data[3] == 0x02 and data[4] == 0x01:
                        offset = data[5]
                        if 0x00 <= offset <= 0x0F:
                            categoria = "DSP Global"
                            if offset == 0x00: desc = "DSP Global: Reverb - Categoria/Preset"
                            elif offset == 0x02: desc = "DSP Global: Reverb - Tempo (Decay)"
                            elif offset == 0x0C: desc = "DSP Global: Reverb - Volume do Efeito"
                            else: desc = f"DSP Global: Reverb - Parâmetro (0x{offset:02X})"
                        elif 0x20 <= offset <= 0x2F:
                            categoria = "DSP Global"
                            if offset == 0x20: desc = "DSP Global: Chorus - Categoria/Preset"
                            elif offset == 0x22: desc = "DSP Global: Chorus - Intensidade"
                            elif offset == 0x2C: desc = "DSP Global: Chorus - Volume do Efeito"
                            else: desc = f"DSP Global: Chorus - Parâmetro (0x{offset:02X})"
                        elif 0x40 <= offset <= 0x5B:
                            categoria = "DSP Variation"
                            if len(data) >= 7 and data[6] < 16:
                                canal_associado = data[6]
                            if offset == 0x40: desc = "DSP Variation (Gaveta 1): Tipo do Efeito"
                            elif offset == 0x5A: desc = "DSP Variation (Gaveta 1): Conexão (System/Insertion)"
                            elif offset == 0x5B: desc = "DSP Variation (Gaveta 1): Canal de Destino (Part Number)"
                            elif offset in (0x54, 0x56): desc = "DSP Variation (Gaveta 1): Dry/Wet ou Parâmetro 10"
                            else: desc = f"DSP Variation (Gaveta 1): Parâmetro (0x{offset:02X})"
                        else:
                            categoria = "DSP Global"
                            desc = f"DSP Global: Parâmetro Extra (0x{offset:02X})"

                    # --- DSP Insertion (Gavetas 2-7) - 43 1n 4C 03 nn ---
                    elif len(data) >= 6 and tuple(data[0:3]) == (0x43, 0x10, 0x4C) and data[3] == 0x03:
                        categoria = "DSP Insertion"
                        nn = data[4]
                        addr = data[5]
                        if len(data) >= 7 and data[6] < 16:
                            canal_associado = data[6]
                        if addr == 0x00: desc = f"DSP Insertion (Gaveta {nn+2}): Tipo do Efeito"
                        elif addr == 0x0C: desc = f"DSP Insertion (Gaveta {nn+2}): Canal de Destino (Conexão)"
                        elif addr == 0x0B: desc = f"DSP Insertion (Gaveta {nn+2}): Mistura Seco/Molhado"
                        else: desc = f"DSP Insertion (Gaveta {nn+2}): Parâmetro (0x{addr:02X})"

                    elif len(data) >= 5 and tuple(data[0:3]) == (0x43, 0x10, 0x4C):
                        desc = f"Yamaha XG - Endereço 0x{data[3]:02X} Desconhecido"
                        categoria = "Outros"

                    self.todos_sysex.append({
                        'tr_idx': tr_idx, 'msg_idx': msg_idx,
                        'msg': msg, 'abs_tick': abs_tick,
                        'desc': desc, 'categoria': categoria, 'hex': hex_str, 'canal_associado': canal_associado
                    })

    def on_filtro_change(self, event):
        self.aplicar_filtro()

    def aplicar_filtro(self):
        cat_idx = self.cb_filtro.GetSelection() 
        canal_idx = self.cb_canal.GetSelection() 
        
        self.lista_box.Clear()
        self.sysex_visiveis = []
        c_alvo = self.parent_seq.canal_atual
        
        categoria_alvo = self.categorias[cat_idx] if 0 <= cat_idx < len(self.categorias) else "Todos"

        for item in self.todos_sysex:
            # Filtro de Canal Cruzado
            if canal_idx == 1 and item['canal_associado'] != c_alvo:
                continue

            # Filtro de Categoria Cruzado - compara o campo 'categoria' que
            # extrair_todos_sysex já atribuiu certinho a cada item (não mais
            # um "contém no texto" frágil, que confundia coisas como "DSP
            # Insertion Params" caindo dentro do filtro "DSP Variation").
            if categoria_alvo != "Todos" and item.get('categoria') != categoria_alvo:
                continue

            self.lista_box.Append(f"Trilha {item['tr_idx']} | Tick {item['abs_tick']} | {item['desc']} | {item['hex']}")
            self.sysex_visiveis.append(item)
            
        if self.lista_box.GetCount() > 0: self.lista_box.SetSelection(0)

    def on_text_filtro(self, event):
        self.aplicar_filtro()
        event.Skip()

    def on_list_select(self, event):
        selections = self.lista_box.GetSelections()
        if selections:
            item = self.sysex_visiveis[selections[-1]]
            target_tick = item['abs_tick']
            if hasattr(self.parent_seq, 'get_sec_at_tick'):
                sec = self.parent_seq.get_sec_at_tick(target_tick)
                self.parent_seq.current_playback_time = sec
                self.parent_seq.last_start_time = sec
                self.parent_seq.seek_flag = True

    def on_select_all(self, event):
        count = self.lista_box.GetCount()
        if count == 0: return
        try:
            self.lista_box.SetSelections(list(range(count)))
        except AttributeError:
            for i in range(count):
                self.lista_box.Select(i)
        from mhs_utils import falar_status
        falar_status(f"{count} itens selecionados.", imediato=True)

    def on_key(self, event):
        import wx
        code = event.GetKeyCode()
        ctrl = event.ControlDown()
        
        if code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            if self.FindFocus() in [self.cb_canal, self.cb_filtro]:
                self.lista_box.SetFocus()
            else:
                self.on_edit(None)
            return
        elif code in [wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE]:
            self.on_delete(None)
            return
        elif code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_OK if self.modificado else wx.ID_CANCEL)
            return
        elif ctrl and code == ord('C'):
            self.on_copy(None)
            return
        elif ctrl and code == ord('X'):
            self.on_cut(None)
            return
        elif ctrl and code == ord('V'):
            self.on_paste(None)
            return
            
        event.Skip()
    def get_selected_items(self):
        selections = self.lista_box.GetSelections()
        return [self.sysex_visiveis[i] for i in selections]

    def on_delete(self, event):
        items = self.get_selected_items()
        if not items: return
        self.parent_seq.save_state(f"Apagar {len(items)} SysEx")
        
        itens_por_trilha = {}
        for it in items:
            itens_por_trilha.setdefault(it['tr_idx'], []).append(it)
            data = it['msg'].data
            if len(data) >= 4 and tuple(data[0:4]) == (0x43, 0x10, 0x4C, 0x00):
                self.parent_seq.tem_xg_on = False
            if len(data) >= 6 and tuple(data[0:3]) == (0x43, 0x10, 0x4C):
                offset = data[5]
                if data[3] == 0x02 and data[4] == 0x01 and (0x00 <= offset <= 0x0F or 0x20 <= offset <= 0x2F):
                    if hasattr(self.parent_seq, 'dsp_cache'):
                        self.parent_seq.dsp_cache['active'] = False
                elif data[3] == 0x02 and data[4] == 0x01 and (0x40 <= offset <= 0x5B):
                    if hasattr(self.parent_seq, 'variation_dsp_cache'):
                        self.parent_seq.variation_dsp_cache['active'] = False
            
        import mido
        for tr_idx, lista in itens_por_trilha.items():
            lista.sort(key=lambda x: x['msg_idx'], reverse=True)
            track = self.parent_seq.midi_file.tracks[tr_idx]
            for it in lista:
                idx = it['msg_idx']
                tempo_apagado = track[idx].time
                del track[idx]
                if idx < len(track):
                    track[idx].time += tempo_apagado
                else:
                    track.append(mido.MetaMessage('text', text='', time=tempo_apagado))
                    
        self.modificado = True
        from mhs_utils import falar_status
        falar_status(f"{len(items)} SysEx apagados.", imediato=True)
        self.extrair_todos_sysex()
        self.aplicar_filtro()
        self.lista_box.SetFocus()
    def on_edit(self, event):
        items = self.get_selected_items()
        if not items: return
        if len(items) > 1:
            from mhs_utils import falar_status
            falar_status("Selecione apenas um SysEx para editar.", imediato=True)
            return
            
        it = items[0]
        hex_str = "F0 " + " ".join([f"{b:02X}" for b in it['msg'].data]) + " F7"
        
        dlg = wx.TextEntryDialog(self, "Modifique os bytes hexadecimais livremente:", "Editor Raw de SysEx", hex_str)
        if dlg.ShowModal() == wx.ID_OK:
            import re
            novo_hex = dlg.GetValue().replace("0x", "").replace(" ", "").upper()
            try:
                clean_hex = re.sub(r'[^0-9A-F]', '', novo_hex)
                byte_array = bytearray.fromhex(clean_hex)
                if byte_array and byte_array[0] == 0xF0: byte_array = byte_array[1:]
                if byte_array and byte_array[-1] == 0xF7: byte_array = byte_array[:-1]
                
                self.parent_seq.save_state("Editar SysEx da Lista")
                track = self.parent_seq.midi_file.tracks[it['tr_idx']]
                track[it['msg_idx']] = it['msg'].copy(data=list(byte_array))
                
                self.modificado = True
                from mhs_utils import falar_status
                falar_status("SysEx modificado com sucesso", imediato=True)
                self.extrair_todos_sysex()
                self.aplicar_filtro()
                self.lista_box.SetFocus()
            except Exception:
                from mhs_utils import falar_status
                falar_status("Erro de sintaxe hexadecimal.", imediato=True)
        dlg.Destroy()

    def on_copy(self, event):
        items = self.get_selected_items()
        from mhs_utils import falar_status
        if not items: 
            falar_status("Nenhum SysEx foi selecionado para copiar.", imediato=True)
            return
        primeiro_tick = min(it['abs_tick'] for it in items)
        self.parent_seq.global_sysex_clipboard = [
            {'msg': it['msg'].copy(time=0), 'offset': it['abs_tick'] - primeiro_tick} 
            for it in items
        ]
        falar_status(f"{len(items)} SysEx copiados para a RAM. Não feche o programa!", imediato=True)

    def on_cut(self, event):
        self.on_copy(None)
        self.on_delete(None)

    def on_paste(self, event):
        from mhs_utils import falar_status
        if not hasattr(self.parent_seq, 'global_sysex_clipboard') or not self.parent_seq.global_sysex_clipboard:
            falar_status("Área de transferência de SysEx vazia!", imediato=True)
            return
            
        self.parent_seq.save_state("Colar SysEx")
        target_tick = self.parent_seq.get_tick_at_sec(self.parent_seq.current_playback_time)
        
        if not self.parent_seq.midi_file.tracks:
            import mido
            self.parent_seq.midi_file.tracks.append(mido.MidiTrack())
            
        track = self.parent_seq.midi_file.tracks[0]
        abs_events = []
        current_abs = 0
        for msg in track:
            current_abs += msg.time
            abs_events.append([current_abs, msg])
            
        msgs_colar = self.parent_seq.global_sysex_clipboard
        for clip_item in msgs_colar:
            if isinstance(clip_item, dict):
                msg_to_paste = clip_item['msg'].copy()
                offset = clip_item['offset']
            else:
                msg_to_paste = clip_item.copy()
                offset = 0
            abs_events.append([target_tick + offset, msg_to_paste])
            
        abs_events.sort(key=lambda x: x[0])
        import mido
        new_track = mido.MidiTrack()
        last_tick = 0
        for tick, msg in abs_events:
            delta = max(0, int(round(tick - last_tick)))
            new_track.append(msg.copy(time=delta))
            last_tick = tick
            
        self.parent_seq.midi_file.tracks[0] = new_track
        self.modificado = True
        falar_status(f"{len(msgs_colar)} SysEx colados e espaçados", imediato=True)
        self.extrair_todos_sysex()
        self.aplicar_filtro()
        self.lista_box.SetFocus()

    def on_export(self, event):
        items = self.get_selected_items()
        if not items:
            from mhs_utils import falar_status
            falar_status("Selecione pelo menos um SysEx para exportar.", imediato=True)
            return
        import os
        pasta_padrao = self.parent_seq.config.get('pasta_salvar', '')
        pasta_sysex = os.path.join(pasta_padrao, "sysex")
        if not os.path.exists(pasta_sysex):
            try: os.makedirs(pasta_sysex)
            except: pasta_sysex = pasta_padrao
        with wx.FileDialog(self, "Exportar SysEx", defaultDir=pasta_sysex, wildcard="Arquivos SysEx (*.syx)|*.syx", style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as fd:
            if fd.ShowModal() == wx.ID_OK:
                path = fd.GetPath()
                try:
                    with open(path, 'wb') as f:
                        for it in items:
                            raw_bytes = [0xF0] + list(it['msg'].data) + [0xF7]
                            f.write(bytes(raw_bytes))
                    from mhs_utils import falar_status
                    falar_status("SysEx exportados com sucesso.", imediato=True)
                except Exception as e:
                    from mhs_utils import falar_status
                    falar_status(f"Erro ao exportar: {e}", imediato=True)

    def on_import(self, event):
        import os
        import mido
        pasta_padrao = self.parent_seq.config.get('pasta_salvar', '')
        pasta_sysex = os.path.join(pasta_padrao, "sysex")
        if not os.path.exists(pasta_sysex): pasta_sysex = pasta_padrao
        with wx.FileDialog(self, "Importar SysEx", defaultDir=pasta_sysex, wildcard="Arquivos SysEx (*.syx)|*.syx", style=wx.FD_OPEN) as fd:
            if fd.ShowModal() == wx.ID_OK:
                path = fd.GetPath()
                try:
                    with open(path, 'rb') as f: raw_data = f.read()
                    parser = mido.Parser()
                    parser.feed(raw_data)
                    syx_msgs = [m for m in parser if m.type == 'sysex']
                    if not syx_msgs:
                        from mhs_utils import falar_status
                        falar_status("Nenhum SysEx válido encontrado no arquivo.", imediato=True)
                        return
                    self.parent_seq.global_sysex_clipboard = [{'msg': m.copy(time=0), 'offset': 0} for m in syx_msgs]
                    self.on_paste(None) 
                except Exception as e:
                    from mhs_utils import falar_status
                    falar_status(f"Erro ao importar: {e}", imediato=True)

    def on_fechar_click(self, event):
        if self.modificado: self.EndModal(wx.ID_OK)
        else: self.EndModal(wx.ID_CANCEL)

    def on_cancelar_click(self, event):
        if self.parent_seq.midi_file: self.parent_seq.midi_file.tracks = self.backup_tracks
        self.EndModal(wx.ID_CANCEL)
class SelectDSPSlotDialog(wx.Dialog):
    def __init__(self, parent, dsp_cache):
        super().__init__(parent, title="Escolha a Gaveta DSP", size=(400, 300))
        
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        lbl = wx.StaticText(panel, label="Selecione a Gaveta (Slot DSP) desejada:")
        vbox.Add(lbl, 0, wx.ALL, 5)

        choices = []
        nomes_slots = ["Variation (DSP 1)", "Insertion DSP 2", "Insertion DSP 3", "Insertion DSP 4", "Insertion DSP 5", "Insertion DSP 6", "Insertion DSP 7"]

        # Monta a lista avisando o NVDA quem está livre e quem está ocupado
        for i in range(7):
            status = "Livre"
            if i in dsp_cache and dsp_cache[i].get('active', False):
                ch = dsp_cache[i].get('ch', 127)
                if ch < 16:
                    status = f"Em uso no Canal {ch + 1}"
                else:
                    status = "Ativo (Global)"
            choices.append(f"{i+1}: {nomes_slots[i]} - [{status}]")

        self.lista = wx.ListBox(panel, choices=choices, size=(-1, 150))
        self.lista.SetSelection(0)
        vbox.Add(self.lista, 1, wx.EXPAND | wx.ALL, 5)

        btn_sizer = wx.StdDialogButtonSizer()
        self.btn_ok = wx.Button(panel, wx.ID_OK, "Avançar (Enter)")
        self.btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Cancelar (Esc)")
        btn_sizer.AddButton(self.btn_ok)
        btn_sizer.AddButton(self.btn_cancel)
        btn_sizer.Realize()
        vbox.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        panel.SetSizer(vbox)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        wx.CallLater(100, self.lista.SetFocus)

    def get_slot(self):
        return self.lista.GetSelection()

    def on_key(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
        elif event.GetKeyCode() in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            self.EndModal(wx.ID_OK)
        else:
            event.Skip()

def _dsp_canais_do_slot(cache_slot):
    chs = cache_slot.get('chs') if isinstance(cache_slot.get('chs'), dict) else {}
    return {c: n for c, n in chs.items() if isinstance(c, int) and 0 <= c < 16}


def _dsp_mids_preview(parent_seq, slot_idx, n):
    # "mids" (0-5) pra tocar N cópias de uma Inserção multi-canal ao vivo:
    # o "home" da gaveta primeiro, depois mids de gavetas inativas.
    home = slot_idx - 1
    vc = getattr(parent_seq, 'variation_dsp_cache', {}) or {}
    ocupadas = {k - 1 for k, v in vc.items()
                if isinstance(k, int) and 1 <= k <= 6 and k != slot_idx
                and isinstance(v, dict) and v.get('active')}
    livres = [m for m in range(6) if m != home and m not in ocupadas]
    mids = ([home] if 0 <= home <= 5 else []) + livres
    return mids[:max(1, n)]


def _dsp_add_sliders_canais(dlg):
    # Um SpinCtrl por canal quando o efeito é multi-canal. Gaveta 1 (Variation
    # SYSTEM): nível de envio de cada canal (CC94). Inserção: mistura
    # seco/molhado (Dry/Wet, 0x0B) da cópia daquele canal. Fica em
    # dlg.sl_canais {canal: SpinCtrl}. Espelha o editor de Variation do Style
    # Creator.
    import wx
    dlg.sl_canais = {}
    chs = _dsp_canais_do_slot(dlg.cache)
    if len(chs) < 2:
        return
    if dlg.slot_idx == 0:
        titulo = "Nível de envio de cada canal pro efeito (0 a 127):"
        padrao = 127
    else:
        titulo = "Mistura seco/molhado de cada canal (0 = só o som seco, 127 = só o efeito):"
        _r = dlg.cache.get('ret', -1)
        padrao = _r if 0 <= _r <= 127 else 64
    dlg.scrsz.Add(wx.StaticText(dlg.scr, label=titulo), 0, wx.LEFT | wx.TOP, 10)
    for ch in sorted(chs):
        dlg.scrsz.Add(wx.StaticText(dlg.scr, label=f"Canal {ch + 1} (0 a 127):"), 0, wx.LEFT | wx.TOP, 10)
        sl = wx.SpinCtrl(dlg.scr, value=str(chs.get(ch, padrao)), min=0, max=127)
        sl.SetName(f"Canal {ch + 1}")
        dlg.scrsz.Add(sl, 0, wx.EXPAND | wx.ALL, 5)
        sl.Bind(wx.EVT_SPINCTRL, dlg.enviar_para_teclado)
        sl.Bind(wx.EVT_TEXT, dlg.enviar_para_teclado)
        dlg.sl_canais[ch] = sl


def _dsp_ler_sliders_canais(dlg):
    if not getattr(dlg, 'sl_canais', None):
        return
    chs = dlg.cache.setdefault('chs', {})
    for ch, sl in dlg.sl_canais.items():
        try:
            chs[ch] = max(0, min(127, int(sl.GetValue())))
        except Exception:
            pass
    dlg.cache['ch'] = next(iter(chs), dlg.cache.get('ch', 0x7F))


def _dsp_rotulo_canais(parent, slot_idx, canal_idx):
    # "Canal 5" ou, num efeito multi-canal, "Canais 3, 5, 8".
    v = getattr(parent, 'variation_dsp_cache', {}).get(slot_idx, {})
    chs = v.get('chs') if isinstance(v.get('chs'), dict) else {}
    canais = sorted(c for c in chs if isinstance(c, int) and 0 <= c < 16)
    if len(canais) >= 2:
        return "Canais " + ", ".join(str(c + 1) for c in canais)
    return f"Canal {canal_idx + 1}"


class SelectDSPFamilyDialog(wx.Dialog):
    def __init__(self, parent, canal_idx, variation_dsp_cache):
        super().__init__(parent, title=f"Roteamento de DSP - Canal {canal_idx + 1}", size=(420, 560))
        self.cache = variation_dsp_cache
        self.parent_seq = parent
        self.canal_idx = canal_idx
        
        # Lista compartilhada com o Style Creator (mhs_utils.VARIATION_EFEITOS_LIST) -
        # já sem as 10 famílias fabricadas (MSB 20/24/25/36/43/44/48/49/50/51)
        # que não existem de verdade no protocolo, mais os efeitos que
        # faltavam (Pitch Change, Touch Wah, Noise Gate, etc.).
        self.efeitos_list = VARIATION_EFEITOS_LIST

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        wx.StaticText(panel, label="1. Escolha a Gaveta (Slot DSP):").Wrap(-1)
        self.cb_slot = wx.Choice(panel, choices=["Variation (DSP 1)", "Insertion DSP 2", "Insertion DSP 3", "Insertion DSP 4", "Insertion DSP 5", "Insertion DSP 6", "Insertion DSP 7"])
        self.cb_slot.SetSelection(0)
        vbox.Add(self.cb_slot, 0, wx.EXPAND | wx.ALL, 5)

        # Vários canais podem passar pelo MESMO efeito. Na Gaveta 1 (Variation)
        # é via Conexão SYSTEM + CC94. Nas Gavetas de Inserção o programa faz
        # uma cópia física do efeito por canal (usa as gavetas livres em
        # seguida).
        self.lbl_canais = wx.StaticText(panel, label="1b. Canais que passam por este efeito (marque quantos quiser):")
        self.lbl_canais.Wrap(-1)
        vbox.Add(self.lbl_canais, 0, wx.LEFT | wx.TOP, 5)
        self.clb_canais = wx.CheckListBox(panel, choices=[f"Canal {i + 1}" for i in range(16)], size=(-1, 110))
        vbox.Add(self.clb_canais, 0, wx.EXPAND | wx.ALL, 5)

        wx.StaticText(panel, label="2. Escolha a Família do Efeito:").Wrap(-1)
        self.cb_msb = wx.Choice(panel, choices=[item[0] for item in self.efeitos_list])
        self.cb_msb.SetSelection(0)
        vbox.Add(self.cb_msb, 0, wx.EXPAND | wx.ALL, 5)

        wx.StaticText(panel, label="3. Variação (Preset LSB):").Wrap(-1)
        self.cb_lsb = wx.Choice(panel, choices=nomes_presets(self.efeitos_list[0][1]))
        self.cb_lsb.SetSelection(0)
        vbox.Add(self.cb_lsb, 0, wx.EXPAND | wx.ALL, 5)

        self.btn_remover = wx.Button(panel, wx.ID_ANY, "Remover TODOS os DSP deste Canal")
        vbox.Add(self.btn_remover, 0, wx.EXPAND | wx.ALL, 5)

        btn_sizer = wx.StdDialogButtonSizer()
        self.btn_ok = wx.Button(panel, wx.ID_OK, "Avançar para Edição (Enter)")
        self.btn_cancel = wx.Button(panel, wx.ID_CANCEL, "Cancelar (Esc)")
        btn_sizer.AddButton(self.btn_ok)
        btn_sizer.AddButton(self.btn_cancel)
        btn_sizer.Realize()
        vbox.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        panel.SetSizer(vbox)

        self.cb_slot.Bind(wx.EVT_CHOICE, self.on_slot_change)
        self.cb_msb.Bind(wx.EVT_CHOICE, self.on_msb_change)
        self.btn_remover.Bind(wx.EVT_BUTTON, self.on_remover)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)

        # Carrega o estado se já existir
        self.on_slot_change(None)
        wx.CallLater(100, self.cb_slot.SetFocus)

    def on_msb_change(self, event):
        # Cada família tem seus próprios presets nomeados - troca a lista do
        # Preset pra corresponder à família recém-escolhida.
        msb_sel = self.cb_msb.GetSelection()
        msb_val = self.efeitos_list[msb_sel][1] if msb_sel != wx.NOT_FOUND else 0
        self.cb_lsb.Set(nomes_presets(msb_val))
        self.cb_lsb.SetSelection(0)
        if event is not None:
            event.Skip()

    def on_slot_change(self, event):
        slot = self.cb_slot.GetSelection()
        if slot in self.cache:
            msb_idx = self.cache[slot].get('msb_idx', 0)
            lsb_idx = self.cache[slot].get('lsb_idx', 0)
            self.cb_msb.SetSelection(msb_idx)
            msb_val = self.efeitos_list[msb_idx][1] if msb_idx < len(self.efeitos_list) else 0
            self.cb_lsb.Set(nomes_presets(msb_val))
            self.cb_lsb.SetSelection(lsb_idx if 0 <= lsb_idx < self.cb_lsb.GetCount() else wx.NOT_FOUND)

            # Avisa o NVDA
            try:
                from mhs_utils import falar_status
                nome_efeito = self.efeitos_list[msb_idx][0]
                falar_status(f"Gaveta {slot + 1} contém: {nome_efeito}", imediato=True)
            except: pass

        # Lista de canais: vale pra qualquer gaveta agora.
        self.clb_canais.Enable(True)
        self.lbl_canais.Enable(True)
        for i in range(self.clb_canais.GetCount()):
            self.clb_canais.Check(i, False)
        vslot = self.cache.get(slot, {})
        chs = vslot.get('chs') if isinstance(vslot.get('chs'), dict) else None
        marcados = set(chs.keys()) if chs else {self.canal_idx}
        # Inserção: se OUTRAS gavetas ativas têm o MESMO efeito (mesmo tipo e
        # preset), pré-marca os canais delas também - assim dá pra reeditar o
        # grupo de uma vez depois de reabrir o arquivo.
        if slot != 0 and vslot.get('active'):
            alvo = (vslot.get('msb_idx', 0), vslot.get('lsb_idx', 0))
            for k, ov in self.cache.items():
                if not (isinstance(k, int) and 1 <= k <= 6 and k != slot):
                    continue
                if not (isinstance(ov, dict) and ov.get('active')):
                    continue
                if (ov.get('msb_idx', 0), ov.get('lsb_idx', 0)) != alvo:
                    continue
                och = ov.get('chs') if isinstance(ov.get('chs'), dict) else {}
                marcados.update(och.keys() or ([ov['ch']] if isinstance(ov.get('ch'), int) and 0 <= ov.get('ch', 99) < 16 else []))
        for c in marcados:
            if 0 <= c < self.clb_canais.GetCount():
                self.clb_canais.Check(c, True)

    def get_valores(self):
        slot = self.cb_slot.GetSelection()
        msb_val = self.efeitos_list[self.cb_msb.GetSelection()][1]
        canais = [i for i in range(self.clb_canais.GetCount()) if self.clb_canais.IsChecked(i)]
        if not canais:
            canais = [self.canal_idx]
        return slot, self.cb_msb.GetSelection(), msb_val, self.cb_lsb.GetSelection(), canais

    def on_remover(self, event):
        import wx
        from mhs_utils import falar_status

        def usa_canal(k, v):
            if not (isinstance(v, dict) and v.get('active')):
                return False
            chs = v.get('chs') if isinstance(v.get('chs'), dict) else {}
            if chs:
                return self.canal_idx in chs
            return v.get('ch') == self.canal_idx

        alvos = [k for k, v in self.cache.items() if usa_canal(k, v)]
        if not alvos:
            falar_status(f"O canal {self.canal_idx + 1} não tem nenhum DSP para remover.", imediato=True)
            return
        dlg = wx.MessageDialog(
            self,
            f"Remover TODOS os {len(alvos)} efeito(s) DSP do canal {self.canal_idx + 1}? "
            f"Eles saem do arquivo. Dá pra desfazer com Ctrl+Z.",
            "Remover DSP do Canal", wx.YES_NO | wx.ICON_WARNING)
        resp = dlg.ShowModal()
        dlg.Destroy()
        if resp == wx.ID_YES:
            self.EndModal(wx.ID_DELETE)

    def on_key(self, event):
        import wx
        if event.GetKeyCode() == wx.WXK_ESCAPE: self.EndModal(wx.ID_CANCEL)
        elif event.GetKeyCode() in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            if self.FindFocus() is self.btn_remover:
                self.on_remover(None)
            else:
                self.EndModal(wx.ID_OK)
        else: event.Skip()

class DelayDSPEditor(wx.Dialog):
    def __init__(self, parent, canal_idx, slot_idx, msb_val, msb_idx, lsb_idx, nomes_parametros):
        super().__init__(parent, title=f"Editor de DELAY - {_dsp_rotulo_canais(parent, slot_idx, canal_idx)} (Gaveta {slot_idx + 1})", size=(450, 750))
        self.parent_seq = parent
        self.canal_idx = canal_idx
        self.slot_idx = slot_idx
        self.msb_val = msb_val

        self.cache = self.parent_seq.variation_dsp_cache[slot_idx]
        _upd = {'active': True, 'msb_idx': msb_idx, 'lsb_idx': lsb_idx}
        _chs_atual = self.cache.get('chs') if isinstance(self.cache.get('chs'), dict) else {}
        if slot_idx != 0 and not _chs_atual:
            _upd['ch'] = canal_idx   # multi-canal (chs) não é sobrescrito
        self.cache.update(_upd)
        
        self.long_params_indices = {5: [0, 1, 2, 3], 6: [0, 1, 2, 3], 7: [0, 2, 5, 6], 8: [0, 1]}.get(msb_val, [])

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        self.scr = wx.ScrolledWindow(panel, style=wx.VSCROLL)
        self.scr.SetScrollRate(0, 20)
        self.scrsz = wx.BoxSizer(wx.VERTICAL)

        # Preset aqui dentro também, além do passo anterior - assim dá pra
        # ir trocando e já ouvir na hora, sem precisar voltar pra tela de
        # seleção toda vez (igual ao editor de Variation do Style Creator).
        self.scrsz.Add(wx.StaticText(self.scr, label="Preset (Variação):"), 0, wx.LEFT | wx.TOP, 10)
        self.cb_lsb = wx.Choice(self.scr, choices=nomes_presets(msb_val))
        self.cb_lsb.SetName("Preset")
        self.lsb_original = lsb_idx
        self.cb_lsb.SetSelection(lsb_idx if 0 <= lsb_idx < self.cb_lsb.GetCount() else wx.NOT_FOUND)
        self.scrsz.Add(self.cb_lsb, 0, wx.EXPAND | wx.ALL, 5)
        self.cb_lsb.Bind(wx.EVT_CHOICE, self.on_preset_mudou)

        self.modulos = []
        parametros_salvos = self.cache.get('p', [-1]*16)

        maximos_msb = DSP_PARAM_MAX.get(msb_val, {})
        for i in range(16):
            is_long = i in self.long_params_indices
            # Alguns parâmetros são uma lista curta de opções com nome (ex:
            # "Input Select: L, R, L&R") - o Data List documenta o valor
            # máximo real, então o slider para no último nome.
            limite = 7150 if is_long else maximos_msb.get(i, 127)
            nome_real = nomes_parametros[i] if i < len(nomes_parametros) else f"Parâmetro Oculto {i+1}"
            rotulo = f"{nome_real} (0 a {limite}ms):" if is_long else f"{nome_real} (0 a {limite}):"

            lbl = wx.StaticText(self.scr, label=rotulo)
            self.scrsz.Add(lbl, 0, wx.LEFT|wx.TOP, 10)

            sl = wx.SpinCtrl(self.scr, value=str(parametros_salvos[i]), min=-1, max=limite)
            sl.SetName(nome_real)
            sl._opcoes_dsp = None if is_long else DSP_PARAM_OPTIONS.get(msb_val, {}).get(i)
            self.scrsz.Add(sl, 0, wx.EXPAND | wx.ALL, 5)
            self.modulos.append(sl)

            sl.Bind(wx.EVT_SPINCTRL, self.enviar_para_teclado)
            sl.Bind(wx.EVT_TEXT, self.enviar_para_teclado)

        rotulo_ret = "Return Level (Volume Global):" if slot_idx == 0 else "Dry/Wet Global da Gaveta (Param 10 - 0x0B):"
        self.scrsz.Add(wx.StaticText(self.scr, label=rotulo_ret), 0, wx.LEFT | wx.TOP, 10)
        self.sl_ret = wx.SpinCtrl(self.scr, value=str(self.cache.get('ret', -1)), min=-1, max=127)
        self.sl_ret.SetName("Dry/Wet Global")
        self.scrsz.Add(self.sl_ret, 0, wx.EXPAND | wx.ALL, 5)
        self.sl_ret.Bind(wx.EVT_SPINCTRL, self.enviar_para_teclado)

        _dsp_add_sliders_canais(self)

        self.scr.SetSizer(self.scrsz)
        vbox.Add(self.scr, 1, wx.EXPAND | wx.ALL, 5)

        btn_ok = wx.Button(panel, wx.ID_OK, "Fechar e Manter")
        vbox.Add(btn_ok, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        panel.SetSizer(vbox)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        wx.CallLater(100, self.cb_lsb.SetFocus)
        self.enviar_para_teclado(None)

    def on_preset_mudou(self, event):
        for sl in self.modulos:
            if sl is not None:
                sl.SetValue("-1")
        self.enviar_para_teclado(None)

    def enviar_para_teclado(self, event):
        import mido, time
        if self.sl_ret: self.cache['ret'] = self.sl_ret.GetValue()
        p_list = [self.modulos[i].GetValue() for i in range(16)]
        self.cache['p'] = p_list
        sel_lsb = self.cb_lsb.GetSelection()
        self.cache['lsb_idx'] = sel_lsb if sel_lsb != wx.NOT_FOUND else self.lsb_original
        _dsp_ler_sliders_canais(self)

        # Parâmetro de lista de opções (Device, Speaker Type, Input Mode...)
        # mudado pelas setinhas/mouse (fora do on_key, que já fala sozinho) -
        # fala o NOME da opção pro NVDA em vez de só o número.
        if event is not None:
            obj_evt = event.GetEventObject()
            opc_evt = getattr(obj_evt, '_opcoes_dsp', None)
            if opc_evt:
                falar_status(_rotulo_valor_dsp(obj_evt.GetName(), obj_evt.GetValue(), opc_evt), imediato=True)

        if not getattr(self.parent_seq, 'output', None): return

        msgs = []
        part_val = 0x7F if self.msb_val == 0 else self.canal_idx
        lsb_val = self.cache['lsb_idx']
        ret_val = self.cache.get('ret', -1)
        chs = _dsp_canais_do_slot(self.cache)

        if self.slot_idx == 0:
            if len(chs) >= 2:
                msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x5A, 0x01, 0xF7])
                msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x5B, 0x7F, 0xF7])
            else:
                msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x5B, part_val, 0xF7])
            msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x40, self.msb_val, lsb_val, 0xF7])

            # Manda os dois endereços de Return (0x56 e o Parameter 10 em
            # 0x54 de 2 bytes) - mesma dupla-escrita usada em
            # consolidar_projeto/enviar_variation_dsp_completo, já que os
            # testes em hardware não confirmaram um endereço único.
            if ret_val != -1:
                msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x56, ret_val, 0xF7])
                msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x54, 0x00, ret_val, 0xF7])

            offsets_var_2bytes = [0x42, 0x44, 0x46, 0x48, 0x4A, 0x4C, 0x4E, 0x50, 0x52, 0x54]
            offsets_var_1byte  = [0x70, 0x71, 0x72, 0x73, 0x74, 0x75]
            for i in range(16):
                if p_list[i] != -1:
                    if i == 9 and ret_val != -1:
                        continue
                    if i < 10: msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, offsets_var_2bytes[i], p_list[i] // 128, p_list[i] % 128, 0xF7])
                    else: msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, offsets_var_1byte[i-10], p_list[i] & 0x7F, 0xF7])
            if len(chs) >= 2:
                for c_env, niv_env in chs.items():
                    msgs.append([0xB0 + c_env, 94, max(0, min(127, int(niv_env)))])
        else:
            # Inserção: 1 cópia física por canal marcado (cada uma na sua
            # "mid"), pra dar pra ouvir os N canais ao vivo. A mistura
            # seco/molhado de cada cópia vem do slider do canal (senão o
            # Dry/Wet global).
            alvos = list(chs.items()) if len(chs) >= 2 else [(self.canal_idx if self.msb_val != 0 else 0x7F, ret_val)]
            mids = _dsp_mids_preview(self.parent_seq, self.slot_idx, len(alvos))
            for (canal_ins, nivel), nn in zip(alvos, mids):
                dw = nivel if (isinstance(nivel, int) and 0 <= nivel <= 127) else ret_val
                msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x03, nn, 0x0C, canal_ins, 0xF7])
                msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x03, nn, 0x00, self.msb_val, lsb_val, 0xF7])
                if dw != -1:
                    msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x03, nn, 0x0B, dw, 0xF7])
                for i in range(16):
                    if p_list[i] != -1:
                        msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x03, nn, 0x30 + (i * 2), p_list[i] // 128, p_list[i] % 128, 0xF7])

        for m in msgs:
            try:
                self.parent_seq.output.send(mido.Message.from_bytes(m))
                if len(m) >= 7 and m[6] in [0x40, 0x00]: time.sleep(0.05)
            except: pass

    def refrescar(self):
        # Chamado (via wx.CallAfter) quando o teclado termina uma rajada de
        # SysEx com esta tela aberta - self.cache é o MESMO dicionário de
        # self.parent_seq.variation_dsp_cache[slot_idx] (referência direta,
        # não cópia), então a captura em segundo plano (on_midi_in) já
        # atualizou os valores sozinha - só falta atualizar os SpinCtrl na
        # tela pra refletir, sem reenviar nada de volta pro teclado.
        p_list = self.cache.get('p', [-1] * 16)
        for i, sl in enumerate(self.modulos):
            if sl is None:
                continue
            novo = p_list[i] if i < len(p_list) else -1
            if sl.GetValue() != novo:
                sl.SetValue(novo)
        if getattr(self, 'sl_ret', None) is not None:
            novo_ret = self.cache.get('ret', 64)
            if self.sl_ret.GetValue() != novo_ret:
                self.sl_ret.SetValue(novo_ret)

    def on_key(self, event):
        import wx
        code = event.GetKeyCode()
        ctrl = event.ControlDown()
        shift = event.ShiftDown()
        alt = event.AltDown()
        obj = self.FindFocus()

        if code in [wx.WXK_SPACE, 32]:
            if ctrl and not alt and not shift: getattr(self.parent_seq, 'toggle_pausa', lambda x: None)(None); return
            elif not ctrl and not alt and not shift: getattr(self.parent_seq, 'toggle_reproducao', lambda x: None)(None); return

        if code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]: self.EndModal(wx.ID_OK); return
        if code == wx.WXK_ESCAPE: self.EndModal(wx.ID_CANCEL); return

        if isinstance(obj, wx.SpinCtrl):
            val, max_v, min_v = obj.GetValue(), obj.GetMax(), obj.GetMin()
            mudou = False
            
            if code == wx.WXK_HOME: val = max_v; mudou = True
            elif code == wx.WXK_END: val = min_v; mudou = True
            elif code in [wx.WXK_PAGEUP, wx.WXK_NUMPAD_PAGEUP]:
                val = min(max_v, val + (100 if max_v > 127 else 10)); mudou = True
            elif code in [wx.WXK_PAGEDOWN, wx.WXK_NUMPAD_PAGEDOWN]:
                val = max(min_v, val - (100 if max_v > 127 else 10)); mudou = True
                
            if mudou:
                obj.SetValue(val)
                self.enviar_para_teclado(None)
                try:
                    from mhs_utils import falar_status
                    falar_status(_rotulo_valor_dsp(obj.GetName(), val, getattr(obj, '_opcoes_dsp', None)), imediato=True)
                except: pass
                return

        event.Skip()

class StandardDSPEditor(wx.Dialog):
    def __init__(self, parent, canal_idx, slot_idx, msb_val, msb_idx, lsb_idx, nomes_parametros):
        super().__init__(parent, title=f"Editor Padrão - {_dsp_rotulo_canais(parent, slot_idx, canal_idx)} (Gaveta {slot_idx + 1})", size=(450, 750))
        self.parent_seq = parent
        self.canal_idx = canal_idx
        self.slot_idx = slot_idx
        self.msb_val = msb_val

        self.cache = self.parent_seq.variation_dsp_cache[slot_idx]
        _upd = {'active': True, 'msb_idx': msb_idx, 'lsb_idx': lsb_idx}
        _chs_atual = self.cache.get('chs') if isinstance(self.cache.get('chs'), dict) else {}
        if slot_idx != 0 and not _chs_atual:
            _upd['ch'] = canal_idx   # multi-canal (chs) não é sobrescrito
        self.cache.update(_upd)
        
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        self.scr = wx.ScrolledWindow(panel, style=wx.VSCROLL)
        self.scr.SetScrollRate(0, 20)
        self.scrsz = wx.BoxSizer(wx.VERTICAL)

        # Preset aqui dentro também, além do passo anterior - assim dá pra
        # ir trocando e já ouvir na hora, sem precisar voltar pra tela de
        # seleção toda vez (igual ao editor de Variation do Style Creator).
        self.scrsz.Add(wx.StaticText(self.scr, label="Preset (Variação):"), 0, wx.LEFT | wx.TOP, 10)
        self.cb_lsb = wx.Choice(self.scr, choices=nomes_presets(msb_val))
        self.cb_lsb.SetName("Preset")
        self.lsb_original = lsb_idx
        self.cb_lsb.SetSelection(lsb_idx if 0 <= lsb_idx < self.cb_lsb.GetCount() else wx.NOT_FOUND)
        self.scrsz.Add(self.cb_lsb, 0, wx.EXPAND | wx.ALL, 5)
        self.cb_lsb.Bind(wx.EVT_CHOICE, self.on_preset_mudou)

        self.modulos = []
        parametros_salvos = self.cache.get('p', [-1]*16)
        maximos_msb = DSP_PARAM_MAX.get(msb_val, {})

        for i in range(16):
            if i < len(nomes_parametros):
                # Alguns parâmetros são uma lista curta de opções com nome
                # (ex: "Device: Transistor, Vintage Tube, Dist1, Dist2, Fuzz")
                # - o Data List documenta o valor máximo real, então o slider
                # para no último nome em vez de rolar até 127 à toa.
                max_i = maximos_msb.get(i, 127)
                lbl = wx.StaticText(self.scr, label=f"{nomes_parametros[i]} (0 a {max_i}):")
                self.scrsz.Add(lbl, 0, wx.LEFT|wx.TOP, 10)

                sl = wx.SpinCtrl(self.scr, value=str(parametros_salvos[i]), min=-1, max=max_i)
                sl.SetName(nomes_parametros[i])
                sl._opcoes_dsp = DSP_PARAM_OPTIONS.get(msb_val, {}).get(i)
                self.scrsz.Add(sl, 0, wx.EXPAND | wx.ALL, 5)
                self.modulos.append(sl)

                sl.Bind(wx.EVT_SPINCTRL, self.enviar_para_teclado)
                sl.Bind(wx.EVT_TEXT, self.enviar_para_teclado)
            else:
                self.modulos.append(None)

        # Bug real do Michel ("Tão só.mid", canal 3, Gaveta de Inserção com
        # Auto Wah, 1 canal só usando o efeito): esta tela só tinha o
        # controle de Dry/Wet (Return Level) pra Gaveta 1 (Variation,
        # slot_idx == 0) - uma gaveta de INSERÇÃO com um único canal não
        # tinha NENHUM controle de Dry/Wet (nem pra ver, nem pra reenviar),
        # já que _dsp_add_sliders_canais só cria sliders por canal quando
        # há 2+ canais no efeito. Resultado: abrir a tela mandava de novo o
        # Tipo do efeito (43 10 4C 03 nn 00 ...) sem NUNCA reforçar o
        # Dry/Wet salvo (0x0B) - o teclado real reseta o Dry/Wet pro padrão
        # de fábrica ao trocar de Tipo, e como não reenviávamos o valor
        # certo, o som mudava na hora. O DelayDSPEditor (usado pelas
        # famílias de delay/eco) já tinha isso certo - Dry/Wet sempre
        # visível e sempre reenviado, não só com 2+ canais; replicado aqui.
        rotulo_ret = "Return Level (Volume Global):" if slot_idx == 0 else "Dry/Wet Global da Gaveta (Param 10 - 0x0B):"
        self.scrsz.Add(wx.StaticText(self.scr, label=rotulo_ret), 0, wx.LEFT | wx.TOP, 10)
        if slot_idx == 0:
            self.sl_ret = wx.SpinCtrl(self.scr, value=str(self.cache.get('ret', 64)), min=0, max=127)
            self.sl_ret.SetName("Return Level")
        else:
            self.sl_ret = wx.SpinCtrl(self.scr, value=str(self.cache.get('ret', -1)), min=-1, max=127)
            self.sl_ret.SetName("Dry/Wet Global")
        self.scrsz.Add(self.sl_ret, 0, wx.EXPAND | wx.ALL, 5)
        self.sl_ret.Bind(wx.EVT_SPINCTRL, self.enviar_para_teclado)

        _dsp_add_sliders_canais(self)

        self.scr.SetSizer(self.scrsz)
        vbox.Add(self.scr, 1, wx.EXPAND | wx.ALL, 5)

        btn_ok = wx.Button(panel, wx.ID_OK, "Fechar e Manter")
        vbox.Add(btn_ok, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        panel.SetSizer(vbox)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)

        wx.CallLater(100, self.cb_lsb.SetFocus)
        self.enviar_para_teclado(None)

    def on_preset_mudou(self, event):
        for sl in self.modulos:
            if sl is not None:
                sl.SetValue("-1")
        self.enviar_para_teclado(None)

    def enviar_para_teclado(self, event):
        import mido
        import time

        if self.sl_ret: self.cache['ret'] = self.sl_ret.GetValue()
        p_list = []
        for i in range(16):
            p_list.append(self.modulos[i].GetValue() if self.modulos[i] else -1)
        self.cache['p'] = p_list
        sel_lsb = self.cb_lsb.GetSelection()
        self.cache['lsb_idx'] = sel_lsb if sel_lsb != wx.NOT_FOUND else self.lsb_original
        _dsp_ler_sliders_canais(self)

        # Parâmetro de lista de opções (Device, Speaker Type, Input Mode...)
        # mudado pelas setinhas/mouse (fora do on_key, que já fala sozinho) -
        # fala o NOME da opção pro NVDA em vez de só o número.
        if event is not None:
            obj_evt = event.GetEventObject()
            opc_evt = getattr(obj_evt, '_opcoes_dsp', None)
            if opc_evt:
                falar_status(_rotulo_valor_dsp(obj_evt.GetName(), obj_evt.GetValue(), opc_evt), imediato=True)

        if not getattr(self.parent_seq, 'output', None): return

        msgs = []
        part_val = 0x7F if self.msb_val == 0 else self.canal_idx
        lsb_val = self.cache['lsb_idx']
        chs = _dsp_canais_do_slot(self.cache)

        if self.slot_idx == 0:
            ret_val = self.cache.get('ret', 64)
            if len(chs) >= 2:
                # Vários canais -> Conexão SYSTEM + CC94 por canal.
                msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x5A, 0x01, 0xF7])
                msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x5B, 0x7F, 0xF7])
            else:
                msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x5B, part_val, 0xF7])
            msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x40, self.msb_val, lsb_val, 0xF7])
            # Manda os dois endereços de Return (0x56 e o Parameter 10 em
            # 0x54 de 2 bytes) - mesma dupla-escrita usada nos outros
            # pontos de gravação (ver DelayDSPEditor/consolidar_projeto).
            msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x56, ret_val, 0xF7])
            msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x54, 0x00, ret_val, 0xF7])
            offsets_var_2bytes = [0x42, 0x44, 0x46, 0x48, 0x4A, 0x4C, 0x4E, 0x50, 0x52, 0x54]
            offsets_var_1byte  = [0x70, 0x71, 0x72, 0x73, 0x74, 0x75]
            for i in range(16):
                if p_list[i] != -1:
                    if i == 9:
                        continue
                    if i < 10: msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, offsets_var_2bytes[i], 0x00, p_list[i] & 0x7F, 0xF7])
                    else: msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, offsets_var_1byte[i-10], p_list[i] & 0x7F, 0xF7])
            if len(chs) >= 2:
                for c_env, niv_env in chs.items():
                    msgs.append([0xB0 + c_env, 94, max(0, min(127, int(niv_env)))])
        else:
            # Params 11-16 do efeito de Inserção XG ficam em 0x20-0x25.
            offsets_ins_1b = [0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25]
            ret_val = self.cache.get('ret', -1)
            # 1 cópia física por canal marcado (cada uma na sua "mid"), pra
            # ouvir os N canais ao vivo. A mistura seco/molhado (índice 9 /
            # 0x0B) de cada cópia vem do slider do canal quando há 2+ canais
            # (ver _dsp_add_sliders_canais), senão do Dry/Wet Global
            # (self.sl_ret) - COM 1 canal só isso já cai direto em ret_val.
            alvos = list(chs.items()) if len(chs) >= 2 else [(self.canal_idx if self.msb_val != 0 else 0x7F, ret_val)]
            mids = _dsp_mids_preview(self.parent_seq, self.slot_idx, len(alvos))
            for (canal_ins, nivel), nn in zip(alvos, mids):
                dw = nivel if (isinstance(nivel, int) and 0 <= nivel <= 127) else ret_val
                msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x03, nn, 0x0C, canal_ins, 0xF7])
                msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x03, nn, 0x00, self.msb_val, lsb_val, 0xF7])
                for i in range(16):
                    if p_list[i] != -1:
                        if i == 9 and len(chs) >= 2:
                            continue  # o Dry/Wet do canal manda no índice 9
                        msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x03, nn, offsets_ins_1b[i], p_list[i] & 0x7F, 0xF7])
                # Bug real do Michel: isto exigia 2+ canais pra reenviar o
                # Dry/Wet - com 1 canal só (o caso mais comum), o Dry/Wet
                # NUNCA era reforçado ao reabrir a tela. Como o Tipo do
                # efeito (mensagem logo acima) é reenviado incondicionalmente
                # sempre que a tela abre, e o teclado real reseta o Dry/Wet
                # da gaveta pro padrão de fábrica ao receber uma troca de
                # Tipo (mesmo pro MESMO tipo já ativo), o som mudava na hora
                # só de reabrir - sem essa condição, o valor certo nunca
                # chegava a ser reenviado depois.
                if dw != -1:
                    msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x03, nn, 0x0B, dw & 0x7F, 0xF7])

        for m in msgs:
            try:
                self.parent_seq.output.send(mido.Message.from_bytes(m))
                if len(m) >= 7 and m[6] in [0x40, 0x00]: time.sleep(0.05)
            except: pass

    def refrescar(self):
        # Ver o comentário do mesmo método no DelayDSPEditor - self.cache é
        # referência direta a variation_dsp_cache[slot_idx], já atualizado
        # pela captura em segundo plano; só falta refletir na tela.
        p_list = self.cache.get('p', [-1] * 16)
        for i, sl in enumerate(self.modulos):
            if sl is None:
                continue
            novo = p_list[i] if i < len(p_list) else -1
            if sl.GetValue() != novo:
                sl.SetValue(novo)
        if getattr(self, 'sl_ret', None) is not None:
            novo_ret = self.cache.get('ret', 64)
            if self.sl_ret.GetValue() != novo_ret:
                self.sl_ret.SetValue(novo_ret)

    def on_key(self, event):
        import wx
        code = event.GetKeyCode()
        ctrl = event.ControlDown()
        shift = event.ShiftDown()
        alt = event.AltDown()
        
        obj = self.FindFocus()

        # --- 1. COMANDOS GLOBAIS ---
        if code in [wx.WXK_SPACE, 32]:
            if ctrl and not alt and not shift:
                getattr(self.parent_seq, 'toggle_pausa', lambda x: None)(None)
                return
            elif not ctrl and not alt and not shift:
                getattr(self.parent_seq, 'toggle_reproducao', lambda x: None)(None)
                return

        if code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            self.EndModal(wx.ID_OK)
            return
            
        if code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return

        # --- 2. COMANDOS DE ACESSIBILIDADE PARA OS VALORES ---
        if isinstance(obj, wx.SpinCtrl):
            val = obj.GetValue()
            max_v = obj.GetMax()
            min_v = obj.GetMin() # Que é -1 (Fábrica)
            mudou = False
            
            if code == wx.WXK_HOME: 
                val = max_v
                mudou = True
            elif code == wx.WXK_END: 
                val = min_v
                mudou = True
            elif code in [wx.WXK_PAGEUP, wx.WXK_NUMPAD_PAGEUP]:
                passo = 100 if max_v > 127 else 10
                val = min(max_v, val + passo)
                mudou = True
            elif code in [wx.WXK_PAGEDOWN, wx.WXK_NUMPAD_PAGEDOWN]:
                passo = 100 if max_v > 127 else 10
                val = max(min_v, val - passo)
                mudou = True
                
            if mudou:
                obj.SetValue(val)
                self.enviar_para_teclado(None)
                try:
                    from mhs_utils import falar_status
                    falar_status(_rotulo_valor_dsp(obj.GetName(), val, getattr(obj, '_opcoes_dsp', None)), imediato=True)
                except: pass
                return

        event.Skip()
class PreRollDialog(wx.Dialog):
    def __init__(self, parent, compassos_atuais):
        super().__init__(parent, title="Configurar Pré-roll (Contagem de Gravação)", size=(350, 180))
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        lbl = wx.StaticText(self, label="Compassos de espera antes de iniciar a gravação:")
        sizer.Add(lbl, 0, wx.ALL, 10)
        
        self.sp_compassos = wx.SpinCtrl(self, value=str(compassos_atuais), min=0, max=16)
        self.sp_compassos.SetToolTip("Digite 0 para gravação instantânea ou o número de compassos para espera.")
        sizer.Add(self.sp_compassos, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 15)
        
        self.SetSizer(sizer)
        wx.CallLater(100, self.sp_compassos.SetFocus)
        
    def get_valores(self):
        return self.sp_compassos.GetValue()

class PasteRepeatDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="Colar Repetido (Paste Repeat)", size=(350, 280))
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        sz_rep = wx.BoxSizer(wx.HORIZONTAL)
        sz_rep.Add(wx.StaticText(self, label="Número de repetições:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.sp_repeats = wx.SpinCtrl(self, value="1", min=1, max=999)
        sz_rep.Add(self.sp_repeats, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(sz_rep, 0, wx.EXPAND | wx.ALL, 5)
        
        box_mode = wx.StaticBox(self, label="Modo de Repetição")
        sz_mode = wx.StaticBoxSizer(box_mode, wx.VERTICAL)
        
        self.rb_gap = wx.RadioButton(self, label="Sem espaços (No gaps) - Fim de um, começo do outro", style=wx.RB_GROUP)
        self.rb_sec = wx.RadioButton(self, label="Intervalo fixo em Segundos")
        self.rb_beat = wx.RadioButton(self, label="Intervalo fixo em Beats (Tempo Musical)")
        
        sz_mode.Add(self.rb_gap, 0, wx.ALL, 5)
        
        sz_sec = wx.BoxSizer(wx.HORIZONTAL)
        sz_sec.Add(self.rb_sec, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.txt_sec = wx.TextCtrl(self, value="1.00")
        sz_sec.Add(self.txt_sec, 1, wx.EXPAND | wx.ALL, 5)
        sz_mode.Add(sz_sec, 0, wx.EXPAND)
        
        sz_beat = wx.BoxSizer(wx.HORIZONTAL)
        sz_beat.Add(self.rb_beat, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        
        self.beat_choices = [
            ("1/1 (Semibreve)", 1920),
            ("1/2 (Mínima)", 960),
            ("1/2T (Mínima Tercina)", 640),
            ("1/4 (Semínima)", 480),
            ("1/4D (Semínima Pontuada)", 720),
            ("1/4T (Semínima Tercina)", 320),
            ("1/8 (Colcheia)", 240),
            ("1/8D (Colcheia Pontuada)", 360),
            ("1/8T (Colcheia Tercina)", 160),
            ("1/16 (Semicolcheia)", 120),
            ("1/16D (Semicolcheia Pontuada)", 180),
            ("1/16T (Semicolcheia Tercina)", 80)
        ]
        
        self.cb_beats = wx.ComboBox(self, choices=[c[0] for c in self.beat_choices], style=wx.CB_READONLY)
        self.cb_beats.SetSelection(3)
        sz_beat.Add(self.cb_beats, 1, wx.EXPAND | wx.ALL, 5)
        sz_mode.Add(sz_beat, 0, wx.EXPAND)
        
        sizer.Add(sz_mode, 0, wx.EXPAND | wx.ALL, 10)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        
        self.SetSizer(sizer)
        wx.CallLater(100, self.sp_repeats.SetFocus)
        
    def get_valores(self):
        modo = 0
        if self.rb_sec.GetValue(): modo = 1
        elif self.rb_beat.GetValue(): modo = 2
        
        try: secs = float(self.txt_sec.GetValue().replace(',', '.'))
        except: secs = 1.0
        
        ticks_base = self.beat_choices[self.cb_beats.GetSelection()][1]
        
        return self.sp_repeats.GetValue(), modo, secs, ticks_base

# --- PRESETS DE BATERIA (rufos/desenhos prontos) ---
# Trazido do MHS Style Creator, a pedido do Michel - mesmo catálogo, mesma
# lógica. Notas GM/XG padrão de bateria - mesma numeração em qualquer
# teclado GM/XG (não depende do Drum Setup do canal).
NOTA_CAIXA_AC = 38     # Acoustic Snare
NOTA_CAIXA_EL = 40     # Electric Snare
NOTA_CRASH_1 = 49      # Crash Cymbal 1
NOTA_CRASH_2 = 57      # Crash Cymbal 2
NOTA_CHINESE = 52      # Chinese Cymbal
NOTA_SPLASH = 55       # Splash Cymbal
NOTA_RIDE_1 = 51       # Ride Cymbal 1
NOTA_RIDE_BELL = 53    # Ride Bell
NOTA_RIDE_2 = 59       # Ride Cymbal 2
NOTA_HIHAT_FECHADO = 42
NOTA_HIHAT_PEDAL = 44
NOTA_HIHAT_ABERTO = 46
NOTA_TOM_GRAVE_1 = 41  # Low Floor Tom
NOTA_TOM_GRAVE_2 = 43  # High Floor Tom
NOTA_TOM_MEDIO_1 = 45  # Low Tom
NOTA_TOM_MEDIO_2 = 47  # Low-Mid Tom
NOTA_TOM_AGUDO_1 = 48  # Hi-Mid Tom
NOTA_TOM_AGUDO_2 = 50  # High Tom

def _rufo(nota, duracao_beats, subdivisao_ticks, vel_inicial, vel_final, nota_alternada=None, curva='linear'):
    # Gera um rufo/roll: uma sequência de batidas igualmente espaçadas
    # (subdivisao_ticks, na escala de 480 ticks por tempo), com velocity
    # variando em RAMPA de vel_inicial até vel_final ao longo da duração -
    # é assim que se faz o "começa bem baixinho e vai aumentando até bater
    # no máximo" pedido pelo Michel, só invertendo vel_inicial/vel_final
    # pra decrescendo.
    # `curva='exponencial'`: a variação de velocity acelera em vez de ser
    # constante (fica mais "natural"/dramática).
    # `nota_alternada`: se dado, alterna entre `nota` e ela a cada batida.
    total_ticks = int(round(480 * duracao_beats))
    n = max(2, int(round(total_ticks / subdivisao_ticks)))
    eventos = []
    for i in range(n):
        t = int(round(i * total_ticks / n))
        frac = i / max(1, n - 1)
        if curva == 'exponencial':
            frac = frac ** 2
        v = max(1, min(127, int(round(vel_inicial + (vel_final - vel_inicial) * frac))))
        nt = nota if (nota_alternada is None or i % 2 == 0) else nota_alternada
        eventos.append((t, nt, v))
    return eventos

def _rufo_acelerando(nota, duracao_beats, subdivisao_inicial_ticks, subdivisao_final_ticks, vel_inicial, vel_final, nota_alternada=None):
    # Rufo onde a DENSIDADE das batidas também muda ao longo do tempo -
    # começa espaçado e vai "acelerando" (ou o contrário), tipo um rufo
    # militar/de tambor de verdade em vez de subdivisão fixa.
    total_ticks = int(round(480 * duracao_beats))
    eventos = []
    t = 0.0
    i = 0
    while t < total_ticks:
        frac = t / max(1, total_ticks)
        subdiv = subdivisao_inicial_ticks + (subdivisao_final_ticks - subdivisao_inicial_ticks) * frac
        v = max(1, min(127, int(round(vel_inicial + (vel_final - vel_inicial) * frac))))
        nt = nota if (nota_alternada is None or i % 2 == 0) else nota_alternada
        eventos.append((int(round(t)), nt, v))
        t += max(5.0, subdiv)
        i += 1
    return eventos

def _rufo_ciclo(notas, duracao_beats, subdivisao_ticks, vel_inicial, vel_final):
    # Igual ao _rufo, mas girando por uma LISTA de notas em ciclo (ex.: os
    # 6 toms em sequência) em vez de só alternar entre 2.
    total_ticks = int(round(480 * duracao_beats))
    n = max(2, int(round(total_ticks / subdivisao_ticks)))
    eventos = []
    for i in range(n):
        t = int(round(i * total_ticks / n))
        frac = i / max(1, n - 1)
        v = max(1, min(127, int(round(vel_inicial + (vel_final - vel_inicial) * frac))))
        nt = notas[i % len(notas)]
        eventos.append((t, nt, v))
    return eventos

def _virada_toms(duracao_beats, notas_em_ordem, vel_inicial=95, vel_final=118):
    # Virada clássica de toms - uma batida por tom da lista, igualmente
    # espaçada ao longo da duração, com crescendo leve de velocity.
    total_ticks = int(round(480 * duracao_beats))
    n = len(notas_em_ordem)
    eventos = []
    for i, nota in enumerate(notas_em_ordem):
        t = int(round(i * total_ticks / n))
        frac = i / max(1, n - 1)
        v = max(1, min(127, int(round(vel_inicial + (vel_final - vel_inicial) * frac))))
        eventos.append((t, nota, v))
    return eventos

# Cada preset: (nome, categoria, duração em tempos/beats, eventos)
# eventos = lista de (offset_ticks_a_480_por_tempo, nota_midi, velocity)
BATERIA_PRESETS = [
    # --- Rufos de Caixa ---
    ("Rufo de Caixa Curto - 1/2 tempo", "Rufos de Caixa", 0.5,
        _rufo(NOTA_CAIXA_AC, 0.5, 40, 85, 127)),
    ("Rufo de Caixa - 1 tempo", "Rufos de Caixa", 1,
        _rufo(NOTA_CAIXA_AC, 1, 60, 70, 122)),
    ("Rufo de Caixa - 2 tempos", "Rufos de Caixa", 2,
        _rufo(NOTA_CAIXA_AC, 2, 60, 60, 124)),
    ("Rufo de Caixa - 3 tempos", "Rufos de Caixa", 3,
        _rufo(NOTA_CAIXA_AC, 3, 60, 55, 126)),
    ("Rufo de Caixa Longo - 4 tempos", "Rufos de Caixa", 4,
        _rufo(NOTA_CAIXA_AC, 4, 60, 45, 127)),
    ("Rufo de Caixa Dupla (Acústica/Elétrica) - 1 tempo", "Rufos de Caixa", 1,
        _rufo(NOTA_CAIXA_AC, 1, 60, 70, 120, nota_alternada=NOTA_CAIXA_EL)),
    ("Rufo de Caixa Dupla (Acústica/Elétrica) - 2 tempos", "Rufos de Caixa", 2,
        _rufo(NOTA_CAIXA_AC, 2, 60, 65, 124, nota_alternada=NOTA_CAIXA_EL)),
    ("Rufo de Caixa Curva Natural - 2 tempos", "Rufos de Caixa", 2,
        _rufo(NOTA_CAIXA_AC, 2, 60, 55, 127, curva='exponencial')),
    ("Rufo de Caixa Curva Natural - 4 tempos", "Rufos de Caixa", 4,
        _rufo(NOTA_CAIXA_AC, 4, 60, 40, 127, curva='exponencial')),
    ("Rufo de Caixa Militar Acelerando - 2 tempos", "Rufos de Caixa", 2,
        _rufo_acelerando(NOTA_CAIXA_AC, 2, 150, 30, 60, 127)),
    ("Rufo de Caixa Militar Acelerando - 4 tempos", "Rufos de Caixa", 4,
        _rufo_acelerando(NOTA_CAIXA_AC, 4, 180, 25, 50, 127)),
    # --- Rufos de Prato ---
    ("Rufo de Prato Crescendo - 1 tempo", "Rufos de Prato", 1,
        _rufo(NOTA_CRASH_1, 1, 60, 30, 127)),
    ("Rufo de Prato Crescendo - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_CRASH_1, 2, 60, 25, 127)),
    ("Rufo de Prato Crescendo - 3 tempos", "Rufos de Prato", 3,
        _rufo(NOTA_CRASH_1, 3, 60, 20, 127)),
    ("Rufo de Prato Crescendo Longo - 4 tempos", "Rufos de Prato", 4,
        _rufo(NOTA_CRASH_1, 4, 60, 15, 127)),
    ("Rufo de Prato Chinês Crescendo - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_CHINESE, 2, 60, 25, 127)),
    ("Rufo Duplo de Pratos (Crash/Chinês) Crescendo - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_CRASH_1, 2, 60, 25, 127, nota_alternada=NOTA_CHINESE)),
    ("Rufo de Prato Decrescendo (Máximo ao Silêncio) - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_CRASH_1, 2, 60, 127, 20)),
    ("Rufo de Prato Curva Natural - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_CRASH_1, 2, 60, 20, 127, curva='exponencial')),
    ("Rufo de Prato Curva Natural Longo - 4 tempos", "Rufos de Prato", 4,
        _rufo(NOTA_CRASH_1, 4, 60, 10, 127, curva='exponencial')),
    ("Rufo de Prato Splash Crescendo - 1 tempo", "Rufos de Prato", 1,
        _rufo(NOTA_SPLASH, 1, 60, 35, 127)),
    ("Rufo de Prato Acelerando - 3 tempos", "Rufos de Prato", 3,
        _rufo_acelerando(NOTA_CRASH_1, 3, 160, 40, 30, 127, nota_alternada=NOTA_CHINESE)),
    ("Rufo de Prato (Ride 1) Crescendo - 1 tempo", "Rufos de Prato", 1,
        _rufo(NOTA_RIDE_1, 1, 60, 30, 127)),
    ("Rufo de Prato (Ride 1) Crescendo - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_RIDE_1, 2, 60, 25, 127)),
    ("Rufo de Prato (Ride 1) Curva Natural - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_RIDE_1, 2, 60, 20, 127, curva='exponencial')),
    ("Rufo de Prato (Crash 2) Crescendo - 1 tempo", "Rufos de Prato", 1,
        _rufo(NOTA_CRASH_2, 1, 60, 30, 127)),
    ("Rufo de Prato (Crash 2) Crescendo - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_CRASH_2, 2, 60, 25, 127)),
    ("Rufo de Prato (Crash 2) Curva Natural - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_CRASH_2, 2, 60, 20, 127, curva='exponencial')),
    ("Rufo de Prato (Crash 2) Decrescendo - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_CRASH_2, 2, 60, 127, 20)),
    ("Rufo de Prato Chinês Curva Natural - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_CHINESE, 2, 60, 20, 127, curva='exponencial')),
    ("Rufo de Prato Chinês Decrescendo - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_CHINESE, 2, 60, 127, 20)),
    ("Rufo de Prato Splash - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_SPLASH, 2, 60, 30, 127)),
    ("Rufo de Prato Splash Curva Natural - 1 tempo", "Rufos de Prato", 1,
        _rufo(NOTA_SPLASH, 1, 60, 30, 127, curva='exponencial')),
    ("Rufo Intercalado (Crash 1 / Crash 2) - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_CRASH_1, 2, 60, 30, 127, nota_alternada=NOTA_CRASH_2)),
    ("Rufo Intercalado (Crash 1 / Splash) - 1 tempo", "Rufos de Prato", 1,
        _rufo(NOTA_CRASH_1, 1, 60, 40, 122, nota_alternada=NOTA_SPLASH)),
    ("Rufo Intercalado (Ride 1 / Chinês) - 2 tempos", "Rufos de Prato", 2,
        _rufo(NOTA_RIDE_1, 2, 60, 35, 124, nota_alternada=NOTA_CHINESE)),
    # --- Rufos de Tom ---
    ("Rufo de Tom Grave - 1 tempo", "Rufos de Tom", 1,
        _rufo(NOTA_TOM_GRAVE_1, 1, 80, 70, 122)),
    ("Rufo de Tom Médio - 1 tempo", "Rufos de Tom", 1,
        _rufo(NOTA_TOM_MEDIO_1, 1, 80, 70, 122)),
    ("Rufo de Tom Agudo - 1 tempo", "Rufos de Tom", 1,
        _rufo(NOTA_TOM_AGUDO_2, 1, 80, 70, 122)),
    ("Rufo de Toms Alternado (Grave/Agudo) - 2 tempos", "Rufos de Tom", 2,
        _rufo(NOTA_TOM_GRAVE_1, 2, 80, 65, 124, nota_alternada=NOTA_TOM_AGUDO_2)),
    ("Rufo de Toms Alternado Curva Natural - 3 tempos", "Rufos de Tom", 3,
        _rufo(NOTA_TOM_GRAVE_2, 3, 80, 50, 127, nota_alternada=NOTA_TOM_AGUDO_1, curva='exponencial')),
    ("Rufo de Tom Grave 2 - 1 tempo", "Rufos de Tom", 1,
        _rufo(NOTA_TOM_GRAVE_2, 1, 80, 70, 122)),
    ("Rufo de Tom Médio 2 - 1 tempo", "Rufos de Tom", 1,
        _rufo(NOTA_TOM_MEDIO_2, 1, 80, 70, 122)),
    ("Rufo de Tom Agudo 1 - 1 tempo", "Rufos de Tom", 1,
        _rufo(NOTA_TOM_AGUDO_1, 1, 80, 70, 122)),
    ("Rufo de Toms Alternado (Grave 1 / Grave 2) - 2 tempos", "Rufos de Tom", 2,
        _rufo(NOTA_TOM_GRAVE_1, 2, 80, 65, 124, nota_alternada=NOTA_TOM_GRAVE_2)),
    ("Rufo de Toms Alternado (Médio 1 / Médio 2) - 2 tempos", "Rufos de Tom", 2,
        _rufo(NOTA_TOM_MEDIO_1, 2, 80, 65, 124, nota_alternada=NOTA_TOM_MEDIO_2)),
    ("Rufo de Toms Alternado (Agudo 1 / Agudo 2) - 2 tempos", "Rufos de Tom", 2,
        _rufo(NOTA_TOM_AGUDO_1, 2, 80, 65, 124, nota_alternada=NOTA_TOM_AGUDO_2)),
    ("Rufo de Toms Decrescendo (Agudo) - 2 tempos", "Rufos de Tom", 2,
        _rufo(NOTA_TOM_AGUDO_2, 2, 80, 127, 30)),
    ("Rufo Giratório de Toms (Todos os 6) - 2 tempos", "Rufos de Tom", 2,
        _rufo_ciclo([NOTA_TOM_GRAVE_1, NOTA_TOM_GRAVE_2, NOTA_TOM_MEDIO_1, NOTA_TOM_MEDIO_2, NOTA_TOM_AGUDO_1, NOTA_TOM_AGUDO_2], 2, 60, 60, 124)),
    ("Rufo Giratório de Toms (Todos os 6) - 4 tempos", "Rufos de Tom", 4,
        _rufo_ciclo([NOTA_TOM_GRAVE_1, NOTA_TOM_GRAVE_2, NOTA_TOM_MEDIO_1, NOTA_TOM_MEDIO_2, NOTA_TOM_AGUDO_1, NOTA_TOM_AGUDO_2], 4, 60, 50, 127)),
    # --- Viradas de Tom (fill clássico descendo/subindo) ---
    ("Virada de Toms Descendo - 1 tempo", "Viradas de Tom", 1,
        _virada_toms(1, [NOTA_TOM_AGUDO_2, NOTA_TOM_AGUDO_1, NOTA_TOM_MEDIO_2, NOTA_TOM_MEDIO_1, NOTA_TOM_GRAVE_2, NOTA_TOM_GRAVE_1])),
    ("Virada de Toms Descendo com Prato Final - 2 tempos", "Viradas de Tom", 2,
        _virada_toms(1.75, [NOTA_TOM_AGUDO_2, NOTA_TOM_AGUDO_2, NOTA_TOM_AGUDO_1, NOTA_TOM_AGUDO_1, NOTA_TOM_MEDIO_2, NOTA_TOM_MEDIO_2, NOTA_TOM_MEDIO_1, NOTA_TOM_MEDIO_1, NOTA_TOM_GRAVE_2, NOTA_TOM_GRAVE_2, NOTA_TOM_GRAVE_1, NOTA_TOM_GRAVE_1])
        + [(1920, NOTA_CRASH_1, 127)]),
    ("Virada de Toms Subindo - 1 tempo", "Viradas de Tom", 1,
        _virada_toms(1, [NOTA_TOM_GRAVE_1, NOTA_TOM_GRAVE_2, NOTA_TOM_MEDIO_1, NOTA_TOM_MEDIO_2, NOTA_TOM_AGUDO_1, NOTA_TOM_AGUDO_2])),
    ("Virada de Toms Longa Descendo com Prato Final - 4 tempos", "Viradas de Tom", 4,
        _virada_toms(3.75, [NOTA_TOM_AGUDO_2, NOTA_TOM_AGUDO_1, NOTA_TOM_MEDIO_2, NOTA_TOM_MEDIO_1, NOTA_TOM_GRAVE_2, NOTA_TOM_GRAVE_1] * 3)
        + [(1920, NOTA_CRASH_2, 127)]),

    # --- Brincadeiras de Hi-Hat ---
    ("Brincadeira de Hi-Hat (Aberto/Fechado) - 1 tempo", "Brincadeiras de Hi-Hat", 1, [
        (0, NOTA_HIHAT_FECHADO, 90), (120, NOTA_HIHAT_FECHADO, 75), (240, NOTA_HIHAT_ABERTO, 100), (360, NOTA_HIHAT_PEDAL, 80),
    ]),
    ("Brincadeira de Hi-Hat (Aberto/Fechado) - 2 tempos", "Brincadeiras de Hi-Hat", 2, [
        (0, NOTA_HIHAT_FECHADO, 90), (120, NOTA_HIHAT_FECHADO, 75), (240, NOTA_HIHAT_FECHADO, 90), (360, NOTA_HIHAT_ABERTO, 105),
        (480, NOTA_HIHAT_PEDAL, 80), (600, NOTA_HIHAT_FECHADO, 90), (720, NOTA_HIHAT_ABERTO, 100), (840, NOTA_HIHAT_PEDAL, 80),
    ]),

    # --- Brincadeiras de Prato (Ride/Bell/Ride 2) ---
    ("Brincadeira de Prato - 1 tempo", "Brincadeiras de Prato", 1, [
        (0, NOTA_RIDE_1, 100), (120, NOTA_RIDE_BELL, 90), (240, NOTA_RIDE_1, 100), (360, NOTA_RIDE_2, 95),
    ]),
    ("Brincadeira de Prato - 2 tempos", "Brincadeiras de Prato", 2, [
        (0, NOTA_RIDE_1, 100), (120, NOTA_RIDE_BELL, 88), (240, NOTA_RIDE_1, 100), (360, NOTA_RIDE_BELL, 92),
        (480, NOTA_RIDE_2, 96), (600, NOTA_RIDE_1, 100), (720, NOTA_RIDE_BELL, 90), (840, NOTA_RIDE_2, 100),
    ]),
    ("Brincadeira de Prato Sincopada - 2 tempos", "Brincadeiras de Prato", 2, [
        (0, NOTA_RIDE_1, 100), (160, NOTA_RIDE_BELL, 85), (320, NOTA_RIDE_2, 95), (400, NOTA_RIDE_BELL, 80),
        (480, NOTA_RIDE_1, 100), (720, NOTA_RIDE_BELL, 90), (880, NOTA_RIDE_2, 100),
    ]),
    ("Brincadeira de Prato - 3 tempos", "Brincadeiras de Prato", 3, [
        (0, NOTA_RIDE_1, 100), (120, NOTA_RIDE_BELL, 88), (240, NOTA_RIDE_1, 100), (360, NOTA_RIDE_BELL, 90),
        (480, NOTA_RIDE_2, 96), (600, NOTA_RIDE_1, 100), (720, NOTA_RIDE_BELL, 88), (840, NOTA_RIDE_1, 100),
        (960, NOTA_RIDE_BELL, 92), (1080, NOTA_RIDE_2, 100),
    ]),
    ("Brincadeira de Prato Longa - 4 tempos", "Brincadeiras de Prato", 4, [
        (0, NOTA_RIDE_1, 100), (120, NOTA_RIDE_BELL, 85), (240, NOTA_RIDE_1, 100), (360, NOTA_RIDE_BELL, 88),
        (480, NOTA_RIDE_2, 92), (600, NOTA_RIDE_1, 100), (720, NOTA_RIDE_BELL, 85), (840, NOTA_RIDE_2, 96),
        (960, NOTA_RIDE_1, 100), (1080, NOTA_RIDE_BELL, 88), (1200, NOTA_RIDE_1, 100), (1320, NOTA_RIDE_BELL, 90),
        (1440, NOTA_RIDE_2, 100), (1560, NOTA_RIDE_1, 100), (1680, NOTA_RIDE_BELL, 92), (1800, NOTA_RIDE_2, 110),
    ]),

    # --- Combinados (Caixa + Prato + Toms, fill "completo") ---
    ("Fill Completo (Caixa + Prato) - 2 tempos", "Combinados", 2,
        _rufo(NOTA_CAIXA_AC, 1.5, 60, 60, 122) + [(720, NOTA_CRASH_1, 127)]),
    ("Fill Completo (Caixa + Prato) - 4 tempos", "Combinados", 4,
        _rufo(NOTA_CAIXA_AC, 3.5, 60, 50, 125) + [(1680, NOTA_CRASH_1, 127)]),
    ("Fill Completo (Caixa + Toms + Prato) - 2 tempos", "Combinados", 2,
        _rufo(NOTA_CAIXA_AC, 1, 60, 65, 122)
        + [(t + 480, n, v) for t, n, v in _virada_toms(0.75, [NOTA_TOM_AGUDO_2, NOTA_TOM_MEDIO_2, NOTA_TOM_MEDIO_1, NOTA_TOM_GRAVE_1], vel_inicial=100, vel_final=120)]
        + [(840, NOTA_CRASH_1, 127)]),
    ("Fill Completo (Caixa + Toms + Prato) - 4 tempos", "Combinados", 4,
        _rufo(NOTA_CAIXA_AC, 2, 60, 55, 120)
        + [(t + 960, n, v) for t, n, v in _virada_toms(1, [NOTA_TOM_AGUDO_2, NOTA_TOM_AGUDO_1, NOTA_TOM_MEDIO_2, NOTA_TOM_MEDIO_1, NOTA_TOM_GRAVE_2, NOTA_TOM_GRAVE_1], vel_inicial=95, vel_final=122)]
        + [(1920, NOTA_CRASH_1, 127)]),
    ("Fill Completo Acelerando (Caixa Militar + Prato) - 4 tempos", "Combinados", 4,
        _rufo_acelerando(NOTA_CAIXA_AC, 3.75, 160, 30, 45, 125)
        + [(1920, NOTA_CRASH_2, 127)]),
]

def _spec_simples(nota, subdiv, vel_ini, nota_alt=None):
    return lambda duracao: _rufo(nota, duracao, subdiv, vel_ini, 127, nota_alternada=nota_alt)

def _spec_ciclo(notas, subdiv, vel_ini):
    return lambda duracao: _rufo_ciclo(notas, duracao, subdiv, vel_ini, 127)

# Cada rufo "Rápido"/"Super Rápido" (incluindo intercalados e o giratório
# de toms) ganha automaticamente as versões de 1, 2 e 4 tempos.
_RUFOS_RAPIDOS_SPEC = [
    ("Rufo de Caixa Rápido", "Rufos de Caixa", _spec_simples(NOTA_CAIXA_AC, 30, 45)),
    ("Rufo de Caixa Super Rápido", "Rufos de Caixa", _spec_simples(NOTA_CAIXA_AC, 20, 60)),
    ("Rufo de Caixa Rápido Intercalado (Acústica/Elétrica)", "Rufos de Caixa", _spec_simples(NOTA_CAIXA_AC, 30, 50, NOTA_CAIXA_EL)),
    ("Rufo de Caixa Super Rápido Intercalado (Acústica/Elétrica)", "Rufos de Caixa", _spec_simples(NOTA_CAIXA_AC, 20, 60, NOTA_CAIXA_EL)),

    ("Rufo de Prato Rápido (Crash 1)", "Rufos de Prato", _spec_simples(NOTA_CRASH_1, 30, 40)),
    ("Rufo de Prato Super Rápido (Crash 1)", "Rufos de Prato", _spec_simples(NOTA_CRASH_1, 20, 55)),
    ("Rufo de Prato Rápido (Chinês)", "Rufos de Prato", _spec_simples(NOTA_CHINESE, 30, 40)),
    ("Rufo de Prato Super Rápido (Chinês)", "Rufos de Prato", _spec_simples(NOTA_CHINESE, 20, 55)),
    ("Rufo de Prato Rápido (Ride 1)", "Rufos de Prato", _spec_simples(NOTA_RIDE_1, 30, 40)),
    ("Rufo de Prato Rápido (Crash 2)", "Rufos de Prato", _spec_simples(NOTA_CRASH_2, 30, 40)),
    ("Rufo de Prato Super Rápido (Crash 2)", "Rufos de Prato", _spec_simples(NOTA_CRASH_2, 20, 55)),
    ("Rufo de Prato Rápido (Splash)", "Rufos de Prato", _spec_simples(NOTA_SPLASH, 30, 45)),
    ("Rufo de Prato Rápido Intercalado (Crash 1 / Crash 2)", "Rufos de Prato", _spec_simples(NOTA_CRASH_1, 30, 45, NOTA_CRASH_2)),
    ("Rufo de Prato Super Rápido Intercalado (Crash 1 / Crash 2)", "Rufos de Prato", _spec_simples(NOTA_CRASH_1, 20, 60, NOTA_CRASH_2)),
    ("Rufo de Prato Rápido Intercalado (Ride 1 / Chinês)", "Rufos de Prato", _spec_simples(NOTA_RIDE_1, 30, 45, NOTA_CHINESE)),
    ("Rufo de Prato Super Rápido Intercalado (Crash 1 / Splash)", "Rufos de Prato", _spec_simples(NOTA_CRASH_1, 20, 55, NOTA_SPLASH)),

    ("Rufo de Toms Rápido (Grave)", "Rufos de Tom", _spec_simples(NOTA_TOM_GRAVE_1, 40, 55)),
    ("Rufo de Toms Super Rápido (Grave)", "Rufos de Tom", _spec_simples(NOTA_TOM_GRAVE_1, 30, 60)),
    ("Rufo de Toms Rápido (Médio)", "Rufos de Tom", _spec_simples(NOTA_TOM_MEDIO_1, 40, 55)),
    ("Rufo de Toms Super Rápido (Médio)", "Rufos de Tom", _spec_simples(NOTA_TOM_MEDIO_1, 30, 60)),
    ("Rufo de Toms Rápido (Agudo)", "Rufos de Tom", _spec_simples(NOTA_TOM_AGUDO_2, 40, 55)),
    ("Rufo de Toms Super Rápido (Agudo)", "Rufos de Tom", _spec_simples(NOTA_TOM_AGUDO_2, 30, 60)),
    ("Rufo de Toms Rápido Intercalado (Grave/Agudo)", "Rufos de Tom", _spec_simples(NOTA_TOM_GRAVE_1, 40, 50, NOTA_TOM_AGUDO_2)),
    ("Rufo de Toms Super Rápido Intercalado (Grave/Agudo)", "Rufos de Tom", _spec_simples(NOTA_TOM_GRAVE_1, 30, 60, NOTA_TOM_AGUDO_2)),
    ("Rufo de Toms Rápido Intercalado (Médio 1 / Médio 2)", "Rufos de Tom", _spec_simples(NOTA_TOM_MEDIO_1, 40, 50, NOTA_TOM_MEDIO_2)),
    ("Rufo Giratório de Toms Rápido (Todos os 6)", "Rufos de Tom",
        _spec_ciclo([NOTA_TOM_GRAVE_1, NOTA_TOM_GRAVE_2, NOTA_TOM_MEDIO_1, NOTA_TOM_MEDIO_2, NOTA_TOM_AGUDO_1, NOTA_TOM_AGUDO_2], 40, 60)),
    ("Rufo Giratório de Toms Super Rápido (Todos os 6)", "Rufos de Tom",
        _spec_ciclo([NOTA_TOM_GRAVE_1, NOTA_TOM_GRAVE_2, NOTA_TOM_MEDIO_1, NOTA_TOM_MEDIO_2, NOTA_TOM_AGUDO_1, NOTA_TOM_AGUDO_2], 30, 70)),
]

def _gerar_variantes_rapidas():
    novos = []
    for nome_base, categoria, gerador in _RUFOS_RAPIDOS_SPEC:
        for duracao in (1, 2, 4):
            tempo_str = f"{duracao} tempo" + ("" if duracao == 1 else "s")
            novos.append((f"{nome_base} - {tempo_str}", categoria, duracao, gerador(duracao)))
    return novos

BATERIA_PRESETS += _gerar_variantes_rapidas()

BATERIA_CATEGORIAS = ["Todos"] + sorted(set(p[1] for p in BATERIA_PRESETS), key=lambda c: [i for i, p in enumerate(BATERIA_PRESETS) if p[1] == c][0])


class MidiEffectsDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="Efeitos MIDI Offline (Arpejo, Delay e Strum/Harpa)", size=(450, 520))
        self.parent = parent
        self.restaurado = False
        
        # --- BACKUP PARA O PREVIEW ---
        self.backup_midi = self.parent.clone_midi_rapido(self.parent.midi_file)
        
        self.grids = [
            ("Semínima (1/4)", 480), ("Semínima Tercina (1/4T)", 320),
            ("Colcheia (1/8)", 240), ("Colcheia Tercina (1/8T)", 160),
            ("Semicolcheia (1/16)", 120), ("Semicolcheia Tercina (1/16T)", 80),
            ("Fusa (1/32)", 60), ("Fusa Tercina (1/32T)", 40), ("Semifusa (1/64)", 30)
        ]
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        aviso = wx.StaticText(self, label="Selecione um trecho (I / O) antes de aplicar!")
        main_sizer.Add(aviso, 0, wx.ALL | wx.ALIGN_CENTER, 10)
        
        self.notebook = wx.Notebook(self)
        
        # --- TAB 1: ARPEJADOR ---
        self.tab_arp = wx.Panel(self.notebook)
        sz_arp = wx.BoxSizer(wx.VERTICAL)
        
        sz_arp.Add(wx.StaticText(self.tab_arp, label="Resolução do Arpejo:"), 0, wx.ALL, 5)
        self.cb_arp_grid = wx.ComboBox(self.tab_arp, value=self.grids[4][0], choices=[g[0] for g in self.grids], style=wx.CB_READONLY)
        self.cb_arp_grid.SetSelection(4)
        sz_arp.Add(self.cb_arp_grid, 0, wx.EXPAND | wx.ALL, 5)
        
        sz_arp.Add(wx.StaticText(self.tab_arp, label="Direção:"), 0, wx.ALL, 5)
        self.cb_arp_dir = wx.ComboBox(self.tab_arp, choices=["Acima (Up)", "Abaixo (Down)", "Alternado (Up/Down)", "Ordem Tocada (As Played)", "Aleatório (Random)"], style=wx.CB_READONLY)
        self.cb_arp_dir.SetSelection(0)
        sz_arp.Add(self.cb_arp_dir, 0, wx.EXPAND | wx.ALL, 5)
        
        sz_arp.Add(wx.StaticText(self.tab_arp, label="Oitavas (1 a 10):"), 0, wx.ALL, 5)
        self.sp_arp_oct = wx.SpinCtrl(self.tab_arp, value="1", min=1, max=10)
        sz_arp.Add(self.sp_arp_oct, 0, wx.EXPAND | wx.ALL, 5)
        
        sz_arp.Add(wx.StaticText(self.tab_arp, label="Duração da Nota / Gate (%):"), 0, wx.ALL, 5)
        self.sp_arp_gate = wx.SpinCtrl(self.tab_arp, value="80", min=10, max=100)
        sz_arp.Add(self.sp_arp_gate, 0, wx.EXPAND | wx.ALL, 5)
        
        self.tab_arp.SetSizer(sz_arp)
        
        # --- TAB 2: DELAY ---
        self.tab_del = wx.Panel(self.notebook)
        sz_del = wx.BoxSizer(wx.VERTICAL)
        
        sz_del.Add(wx.StaticText(self.tab_del, label="Resolução do Eco (Intervalo):"), 0, wx.ALL, 5)
        self.cb_del_grid = wx.ComboBox(self.tab_del, value=self.grids[4][0], choices=[g[0] for g in self.grids], style=wx.CB_READONLY)
        self.cb_del_grid.SetSelection(4)
        sz_del.Add(self.cb_del_grid, 0, wx.EXPAND | wx.ALL, 5)
        
        sz_del.Add(wx.StaticText(self.tab_del, label="Repetições (Ecos):"), 0, wx.ALL, 5)
        self.sp_del_rep = wx.SpinCtrl(self.tab_del, value="3", min=1, max=20)
        sz_del.Add(self.sp_del_rep, 0, wx.EXPAND | wx.ALL, 5)
        
        sz_del.Add(wx.StaticText(self.tab_del, label="Decaimento de Velocity (% por repetição):"), 0, wx.ALL, 5)
        self.sp_del_dec = wx.SpinCtrl(self.tab_del, value="75", min=10, max=100)
        sz_del.Add(self.sp_del_dec, 0, wx.EXPAND | wx.ALL, 5)
        
        self.tab_del.SetSizer(sz_del)
        
        # --- TAB 3: HARPA / STRUM (NOVO) ---
        self.tab_harp = wx.Panel(self.notebook)
        sz_harp = wx.BoxSizer(wx.VERTICAL)
        
        sz_harp.Add(wx.StaticText(self.tab_harp, label="Direção do Arrastão:"), 0, wx.ALL, 5)
        self.cb_harp_dir = wx.ComboBox(self.tab_harp, choices=["Subindo (Grave para Agudo)", "Descendo (Agudo para Grave)", "Vai e Volta (Sobe e Desce)"], style=wx.CB_READONLY)
        self.cb_harp_dir.SetSelection(0)
        sz_harp.Add(self.cb_harp_dir, 0, wx.EXPAND | wx.ALL, 5)
        
        sz_harp.Add(wx.StaticText(self.tab_harp, label="Velocidade da Palhetada/Dedilhado:"), 0, wx.ALL, 5)
        self.estilos_harp = [
            ("Strum Hiper Rápido (Flamenco)", 8),
            ("Strum Rápido (Violão Base)", 15),
            ("Dedilhado Médio (Piano Roll)", 30),
            ("Harpa Lenta (Cascata Mágica)", 60),
            ("Sincronizado na Resolução do Grid Abaixo", 0)
        ]
        self.cb_harp_estilo = wx.ComboBox(self.tab_harp, choices=[e[0] for e in self.estilos_harp], style=wx.CB_READONLY)
        self.cb_harp_estilo.SetSelection(1) # Padrão: Violão
        sz_harp.Add(self.cb_harp_estilo, 0, wx.EXPAND | wx.ALL, 5)
        
        sz_harp.Add(wx.StaticText(self.tab_harp, label="Resolução do Grid (Apenas se sincronizado):"), 0, wx.ALL, 5)
        self.cb_harp_grid = wx.ComboBox(self.tab_harp, value=self.grids[6][0], choices=[g[0] for g in self.grids], style=wx.CB_READONLY)
        self.cb_harp_grid.SetSelection(6) # Fusa por padrão para harpas longas
        sz_harp.Add(self.cb_harp_grid, 0, wx.EXPAND | wx.ALL, 5)
        
        sz_harp.Add(wx.StaticText(self.tab_harp, label="Extensão do Acorde (Clonar em Oitavas):"), 0, wx.ALL, 5)
        self.sp_harp_oct = wx.SpinCtrl(self.tab_harp, value="1", min=1, max=4)
        sz_harp.Add(self.sp_harp_oct, 0, wx.EXPAND | wx.ALL, 5)
        
        self.tab_harp.SetSizer(sz_harp)

        # --- TAB 4: BATERIA (PRESETS) (NOVO, trazido do MHS Style Creator) ---
        # Desenhos prontos de bateria pra INSERIR no canal em foco -
        # diferente das outras 3 abas (que transformam notas já existentes
        # no trecho marcado). SOBREPÕE o que já está tocando no canal, não
        # apaga (ver tratamento de 'bateria_preset' em aplicar_efeito_midi).
        self.tab_bat = wx.Panel(self.notebook)
        sz_bat = wx.BoxSizer(wx.VERTICAL)
        sz_bat.Add(wx.StaticText(self.tab_bat, label="Categoria:"), 0, wx.ALL, 5)
        self.cb_bat_cat = wx.ComboBox(self.tab_bat, value=BATERIA_CATEGORIAS[0], choices=BATERIA_CATEGORIAS, style=wx.CB_READONLY)
        self.cb_bat_cat.SetSelection(0)
        sz_bat.Add(self.cb_bat_cat, 0, wx.EXPAND | wx.ALL, 5)
        sz_bat.Add(wx.StaticText(self.tab_bat, label="Desenho (Seta Cima/Baixo escolhe e já ouve sozinho; Espaço toca o trecho com o desenho aplicado):"), 0, wx.ALL, 5)
        self.list_bat = wx.ListBox(self.tab_bat, style=wx.LB_SINGLE)
        sz_bat.Add(self.list_bat, 1, wx.EXPAND | wx.ALL, 5)
        self.tab_bat.SetSizer(sz_bat)
        self._bateria_indices = []
        self._popular_lista_bateria()

        # --- ADICIONA AS ABAS ---
        self.notebook.AddPage(self.tab_arp, "Arpejador")
        self.notebook.AddPage(self.tab_del, "MIDI Delay")
        self.notebook.AddPage(self.tab_harp, "Harpa / Strum")
        self.notebook.AddPage(self.tab_bat, "Bateria (Presets)")

        main_sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 5)
        
        self.btn_play = wx.Button(self, label="Ouvir Preview (Espaço: Play/Stop, CTRL+Espaço: Pausa)")
        main_sizer.Add(self.btn_play, 0, wx.EXPAND | wx.ALL, 10)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        main_sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        
        self.SetSizer(main_sizer)
        
        # --- BINDS ---
        self.btn_play.Bind(wx.EVT_BUTTON, self.on_play_pause)
        
        self.cb_arp_grid.Bind(wx.EVT_COMBOBOX, self.on_change)
        self.cb_arp_dir.Bind(wx.EVT_COMBOBOX, self.on_change)
        self.sp_arp_oct.Bind(wx.EVT_SPINCTRL, self.on_change)
        self.sp_arp_gate.Bind(wx.EVT_SPINCTRL, self.on_change)
        
        self.cb_del_grid.Bind(wx.EVT_COMBOBOX, self.on_change)
        self.sp_del_rep.Bind(wx.EVT_SPINCTRL, self.on_change)
        self.sp_del_dec.Bind(wx.EVT_SPINCTRL, self.on_change)
        
        self.cb_harp_dir.Bind(wx.EVT_COMBOBOX, self.on_change)
        self.cb_harp_estilo.Bind(wx.EVT_COMBOBOX, self.on_change)
        self.cb_harp_grid.Bind(wx.EVT_COMBOBOX, self.on_change)
        self.sp_harp_oct.Bind(wx.EVT_SPINCTRL, self.on_change)

        self.cb_bat_cat.Bind(wx.EVT_COMBOBOX, self.on_bat_categoria_change)
        self.list_bat.Bind(wx.EVT_LISTBOX, self.on_bat_preset_change)

        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_tab_change)
        
        self.Bind(wx.EVT_BUTTON, self.on_btn_click)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        
        wx.CallLater(100, self.cb_arp_grid.SetFocus)
        wx.CallLater(200, self.aplicar_preview)
        
    def on_change(self, event):
        self.aplicar_preview()
        event.Skip()

    def _popular_lista_bateria(self):
        # Reconstrói a lista de presets filtrada pela categoria escolhida -
        # `self._bateria_indices[i]` guarda o índice REAL em BATERIA_PRESETS
        # pra cada linha `i` da lista filtrada (get_valores usa isso).
        cat = self.cb_bat_cat.GetStringSelection() or "Todos"
        self._bateria_indices = [i for i, p in enumerate(BATERIA_PRESETS) if cat == "Todos" or p[1] == cat]
        rotulos = []
        for i in self._bateria_indices:
            nome, categoria, duracao, _ = BATERIA_PRESETS[i]
            tempo_str = f"{duracao:g} tempo" + ("" if duracao == 1 else "s")
            rotulos.append(f"{nome} ({tempo_str})")
        self.list_bat.Set(rotulos)
        if rotulos:
            self.list_bat.SetSelection(0)

    def on_bat_categoria_change(self, event):
        self._popular_lista_bateria()
        self.on_bat_preset_change(event)

    def on_bat_preset_change(self, event):
        # Seta Cima/Baixo na lista: toca o DESENHO SOZINHO, na hora, direto
        # pela porta MIDI - só pra ouvir rapidinho qual é qual, sem precisar
        # de Play. O Espaço continua tocando o trecho de verdade já com o
        # desenho aplicado por cima (aplicar_preview/on_change).
        sel = self.list_bat.GetSelection()
        if sel != wx.NOT_FOUND and self._bateria_indices:
            self.tocar_preview_isolado_bateria(self._bateria_indices[sel])
        self.on_change(event)

    def tocar_preview_isolado_bateria(self, preset_idx):
        porta = getattr(self.parent, 'output', None)
        if not porta or not (0 <= preset_idx < len(BATERIA_PRESETS)):
            return
        # Token em vez de cancelar Timers um a um: se o Michel passar rápido
        # por vários presets, cada nova chamada invalida os note_on/note_off
        # ainda pendentes da anterior.
        self._bat_preview_token = getattr(self, '_bat_preview_token', 0) + 1
        meu_token = self._bat_preview_token
        _, _, _, eventos_preset = BATERIA_PRESETS[preset_idx]
        midi_file = getattr(self.parent, 'midi_file', None)
        tpb = getattr(midi_file, 'ticks_per_beat', 480) if midi_file else 480
        tempo_us = getattr(self.parent, 'current_tempo', 500000) or 500000
        escala = tpb / 480.0
        seg_por_tick = (tempo_us / 1000000.0) / max(1, tpb)
        ch = self.parent.canal_atual
        gate_ticks = max(1, int(round(30 * escala)))

        def _enviar(msg, token):
            if token != self._bat_preview_token:
                return
            try:
                porta.send(msg)
            except Exception:
                pass

        for offset480, nota, vel in eventos_preset:
            t_ticks = int(round(offset480 * escala))
            atraso_on = t_ticks * seg_por_tick
            atraso_off = (t_ticks + gate_ticks) * seg_por_tick
            msg_on = mido.Message('note_on', channel=ch, note=nota, velocity=vel)
            msg_off = mido.Message('note_off', channel=ch, note=nota, velocity=0)
            threading.Timer(atraso_on, _enviar, args=(msg_on, meu_token)).start()
            threading.Timer(atraso_off, _enviar, args=(msg_off, meu_token)).start()

    def on_play_pause(self, event):
        self.parent.toggle_reproducao(None)
        
    def on_btn_click(self, event):
        if event.GetId() == wx.ID_OK:
            self.restaurar_original()
            self.EndModal(wx.ID_OK)
        elif event.GetId() == wx.ID_CANCEL:
            self.restaurar_original()
            self.EndModal(wx.ID_CANCEL)
        else:
            event.Skip()
            
    def on_close(self, event):
        self.restaurar_original()
        event.Skip()
        
    def restaurar_original(self):
        if self.restaurado: return
        self.restaurado = True
        
        was_playing = self.parent.tocando
        play_time = self.parent.current_playback_time
        
        if self.parent.tocando:
            self.parent.tocando = False
            self.parent.all_notes_off()
            import time
            time.sleep(0.05)
            
        self.parent.midi_file = self.parent.clone_midi_rapido(self.backup_midi)
        self.parent.ler_midi_memoria(reset_canais=False)
        self.parent.current_playback_time = play_time
        self.parent.last_start_time = play_time
        self.parent.seek_flag = True
        
        if was_playing:
            self.parent.tocando = True
            import threading
            threading.Thread(target=self.parent.play_thread, daemon=True).start()
            
    def aplicar_preview(self):
        tipo, params = self.get_valores()
        self.parent.aplicar_efeito_midi(tipo, params, is_preview=True, backup_midi=self.backup_midi)

    def on_tab_change(self, event):
        sel = self.notebook.GetSelection()
        self.aplicar_preview() 
        try:
            from mhs_utils import falar_status
            falar_status(self.notebook.GetPageText(sel), imediato=True)
        except: pass
        event.Skip()

    def get_valores(self):
        tab = self.notebook.GetSelection()
        params = {}
        if tab == 0:
            tipo = "arpejo"
            params['grid'] = self.grids[self.cb_arp_grid.GetSelection()][1]
            params['direction'] = self.cb_arp_dir.GetSelection()
            params['octaves'] = self.sp_arp_oct.GetValue()
            params['gate'] = self.sp_arp_gate.GetValue()
        elif tab == 1:
            tipo = "delay"
            params['grid'] = self.grids[self.cb_del_grid.GetSelection()][1]
            params['repeats'] = self.sp_del_rep.GetValue()
            params['decay'] = self.sp_del_dec.GetValue()
        elif tab == 2:
            tipo = "harpa"
            estilo_val = self.estilos_harp[self.cb_harp_estilo.GetSelection()][1]
            grid_val = self.grids[self.cb_harp_grid.GetSelection()][1]

            params['direction'] = self.cb_harp_dir.GetSelection()
            params['delay_ticks'] = estilo_val if estilo_val > 0 else grid_val
            params['octaves'] = self.sp_harp_oct.GetValue()
        else:
            tipo = "bateria_preset"
            sel = self.list_bat.GetSelection()
            params['preset_idx'] = self._bateria_indices[sel] if sel != wx.NOT_FOUND and self._bateria_indices else None

        return tipo, params

    def on_key(self, event):
        import wx
        code = event.GetKeyCode()
        ctrl = event.ControlDown()
        if code in [wx.WXK_SPACE, 32]:
            if ctrl: self.parent.toggle_pausa(None)
            else: self.parent.toggle_reproducao(None)
            return
        elif code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            self.restaurar_original()
            self.EndModal(wx.ID_OK)
            return
        elif code == wx.WXK_ESCAPE:
            self.restaurar_original()
            self.EndModal(wx.ID_CANCEL)
            return
        elif code in [wx.WXK_TAB, ord('\t')] and ctrl:
            total = self.notebook.GetPageCount()
            current = self.notebook.GetSelection()
            next_page = (current - 1) % total if event.ShiftDown() else (current + 1) % total
            self.notebook.SetSelection(next_page)
            return
        else:
            event.Skip()
class FadeDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="Fade In / Fade Out (Expression)", size=(380, 250))
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        lbl_info = wx.StaticText(self, label="O Fade utilizará o CC 11 (Expression) para preservar\no volume principal (CC 7) da sua mixagem.")
        sizer.Add(lbl_info, 0, wx.ALL | wx.ALIGN_CENTER, 10)
        
        self.radio_box = wx.RadioBox(self, label="Tipo de Fade:", choices=["Fade In (0 ao Máximo)", "Fade Out (Máximo ao 0)"], majorDimension=1, style=wx.RA_SPECIFY_COLS)
        self.radio_box.SetSelection(1)
        sizer.Add(self.radio_box, 0, wx.EXPAND | wx.ALL, 10)
        
        self.chk_todos = wx.CheckBox(self, label="Aplicar Master Fade (Em todos os canais)")
        self.chk_todos.SetValue(True)
        sizer.Add(self.chk_todos, 0, wx.ALL, 10)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        
        self.SetSizer(sizer)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        
        wx.CallLater(100, self.radio_box.SetFocus)
        
    def get_valores(self):
        return self.radio_box.GetSelection(), self.chk_todos.GetValue()

    def on_key(self, event):
        code = event.GetKeyCode()
        if code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            self.EndModal(wx.ID_OK)
        elif code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
        else:
            event.Skip()

class ClonarConfigCanalDialog(wx.Dialog):
    def __init__(self, parent, canal_origem):
        super().__init__(parent, title="Clonar Configurações", size=(350, 180))
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        lbl = wx.StaticText(self, label=f"Copiar TUDO do Canal {canal_origem + 1} para o canal:")
        sizer.Add(lbl, 0, wx.ALL, 10)
        
        opcoes = [f"Canal {i + 1}" for i in range(16)]
        self.cb_canal = wx.ComboBox(self, choices=opcoes, style=wx.CB_READONLY)
        # Já deixa o próximo canal pré-selecionado por comodidade
        self.cb_canal.SetSelection((canal_origem + 1) % 16)
        sizer.Add(self.cb_canal, 0, wx.EXPAND | wx.ALL, 10)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        
        self.SetSizer(sizer)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        
        # O wx já foi importado no início do arquivo mhs_dialogs.py, então basta chamar direto!
        wx.CallLater(100, self.cb_canal.SetFocus)
        
    def get_canal_alvo(self):
        return self.cb_canal.GetSelection()

    def on_key(self, event):
        import wx
        code = event.GetKeyCode()
        if code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            self.EndModal(wx.ID_OK)
        elif code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
        else:
            event.Skip()