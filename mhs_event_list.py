import wx
import mido
import threading
import copy
from mhs_utils import falar_status, get_nome_nota, get_cc_name

# --- DICIONÁRIO COMPLETO DE CONTROL CHANGES (Formatado para busca por letra) ---
CC_DICT = {
    0: "Bank Select MSB", 1: "Modulation", 2: "Breath Controller", 4: "Foot Controller",
    5: "Portamento Time", 6: "Data Entry MSB", 7: "Volume", 8: "Balance", 10: "Pan",
    11: "Expression", 12: "Effect Control 1", 13: "Effect Control 2", 64: "Sustain Pedal",
    65: "Portamento On/Off", 66: "Sostenuto", 67: "Soft Pedal", 68: "Legato", 69: "Hold 2",
    70: "Sound Variation", 71: "Sound Resonance", 72: "Release Time", 73: "Attack Time",
    74: "Cutoff", 75: "Decay Time", 76: "Vibrato Rate", 77: "Vibrato Depth", 78: "Vibrato Delay",
    84: "Portamento Control", 91: "Reverb", 92: "Tremolo", 93: "Chorus", 94: "Celeste",
    95: "Phaser", 98: "NRPN LSB", 99: "NRPN MSB", 100: "RPN LSB", 101: "RPN MSB",
    120: "All Sound Off", 121: "Reset All Controllers", 122: "Local Control", 123: "All Notes Off"
}
CC_CHOICES = [f"{CC_DICT.get(i, 'Control ' + str(i))}, {i}" for i in range(128)]

# =====================================================================
# CAIXAS DE EDIÇÃO PROFISSIONAIS (SpinCtrl e ComboBox)
# =====================================================================
class EdicaoNotaDialog(wx.Dialog):
    def __init__(self, parent, nota_val=60, vel_val=100, dur_val=240, b=0, p=0, is_insert=False):
        titulo = "Inserir Nota / Peça" if is_insert else "Editar Nota / Peça"
        super().__init__(parent, title=titulo, size=(400, 300))
        self.parent_list = parent 
        self.b = b
        self.p = p
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.lbl_nota = wx.StaticText(self, label="Nota/Peça:")
        sizer.Add(self.lbl_nota, 0, wx.ALL, 5)
        
        self.sp_nota = wx.SpinCtrl(self, value=str(nota_val), min=0, max=127)
        sizer.Add(self.sp_nota, 0, wx.EXPAND | wx.ALL, 5)
        
        lbl_vel = wx.StaticText(self, label="Velocity:")
        sizer.Add(lbl_vel, 0, wx.ALL, 5)
        
        self.sp_vel = wx.SpinCtrl(self, value=str(vel_val), min=1, max=127)
        sizer.Add(self.sp_vel, 0, wx.EXPAND | wx.ALL, 5)
        
        lbl_dur = wx.StaticText(self, label="Duração (Ticks):")
        sizer.Add(lbl_dur, 0, wx.ALL, 5)
        
        self.sp_dur = wx.SpinCtrl(self, value=str(dur_val), min=1, max=3840)
        sizer.Add(self.sp_dur, 0, wx.EXPAND | wx.ALL, 5)
        
        self.sp_nota.Bind(wx.EVT_SPINCTRL, self.on_update)
        self.sp_vel.Bind(wx.EVT_SPINCTRL, self.on_update)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)
        
        self.atualizar_label(falar=False)
        wx.CallLater(100, self.sp_nota.SetFocus)

    def atualizar_label(self, falar=True):
        val = self.sp_nota.GetValue()
        nome = self.parent_list.get_nome_nota_ou_peca(val, self.b, self.p)
        if self.parent_list.is_drum_channel():
            txt = f"Peça: {nome} ({val})"
        else:
            txt = f"Nota: {nome} ({val})"
            
        self.lbl_nota.SetLabel(txt)
        if falar:
            falar_status(nome, imediato=True)

    def play_preview(self):
        if getattr(self.parent_list.parent, 'output', None):
            self.parent_list.matar_nota_preview()
            msg = mido.Message(
                'note_on', 
                channel=self.parent_list.canal_idx, 
                note=self.sp_nota.GetValue(), 
                velocity=self.sp_vel.GetValue()
            )
            self.parent_list.preview_note = msg
            self.parent_list.parent.output.send(msg)
            self.parent_list.preview_timer = threading.Timer(0.3, self.parent_list.matar_nota_preview)
            self.parent_list.preview_timer.start()
        
    def on_update(self, event):
        self.atualizar_label(falar=True)
        self.play_preview()
            
    def get_values(self):
        return self.sp_nota.GetValue(), self.sp_vel.GetValue(), self.sp_dur.GetValue()

class VirtualEventList(wx.ListCtrl):
    def __init__(self, parent, dialog_ref):
        super().__init__(parent, style=wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_NO_HEADER)
        self.dialog_ref = dialog_ref
        self.InsertColumn(0, "Evento", width=2000)

    def OnGetItemText(self, item, column):
        if 0 <= item < len(self.dialog_ref.display_events):
            ev = self.dialog_ref.display_events[item]
            return self.dialog_ref.gerar_fala_curta(ev)
        return ""
class EdicaoCCDialog(wx.Dialog):
    def __init__(self, parent, cc_val=0, val_val=0, tick_val=0, is_insert=False):
        titulo = "Inserir Control Change" if is_insert else "Editar Control Change"
        super().__init__(parent, title=titulo, size=(400, 300))
        self.parent_list = parent
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        lbl_cc = wx.StaticText(self, label="Control Change (Digite a letra ou use setas):")
        sizer.Add(lbl_cc, 0, wx.ALL, 5)
        
        self.cb_cc = wx.ComboBox(self, value=CC_CHOICES[cc_val], choices=CC_CHOICES, style=wx.CB_READONLY)
        self.cb_cc.SetSelection(cc_val)
        sizer.Add(self.cb_cc, 0, wx.EXPAND | wx.ALL, 5)
        
        lbl_val = wx.StaticText(self, label="Valor (0 a 127):")
        sizer.Add(lbl_val, 0, wx.ALL, 5)
        
        self.sp_val = wx.SpinCtrl(self, value=str(val_val), min=0, max=127)
        sizer.Add(self.sp_val, 0, wx.EXPAND | wx.ALL, 5)

        lbl_tick = wx.StaticText(self, label="Posição Exata (Tick):")
        sizer.Add(lbl_tick, 0, wx.ALL, 5)
        
        self.sp_tick = wx.SpinCtrl(self, value=str(tick_val), min=0, max=9999999)
        sizer.Add(self.sp_tick, 0, wx.EXPAND | wx.ALL, 5)
        
        self.cb_cc.Bind(wx.EVT_COMBOBOX, self.on_cc_change)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)
        wx.CallLater(100, self.cb_cc.SetFocus)
        
    def on_cc_change(self, event):
        falar_status(self.cb_cc.GetValue(), imediato=True)
            
    def get_values(self):
        return self.cb_cc.GetSelection(), self.sp_val.GetValue(), self.sp_tick.GetValue()
class EdicaoPCDialog(wx.Dialog):
    def __init__(self, parent, bank_val=0, patch_val=0, tick_val=0, is_insert=False):
        titulo = "Inserir Program Change" if is_insert else "Editar Program Change"
        super().__init__(parent, title=titulo, size=(400, 300))
        self.parent_list = parent
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        lbl_bank = wx.StaticText(self, label="Banco (Bank 0-16384):")
        sizer.Add(lbl_bank, 0, wx.ALL, 5)
        
        self.sp_bank = wx.SpinCtrl(self, value=str(bank_val), min=0, max=16384)
        sizer.Add(self.sp_bank, 0, wx.EXPAND | wx.ALL, 5)
        
        self.lbl_patch = wx.StaticText(self, label="Patch:")
        sizer.Add(self.lbl_patch, 0, wx.ALL, 5)
        
        self.sp_patch = wx.SpinCtrl(self, value=str(patch_val), min=0, max=127)
        sizer.Add(self.sp_patch, 0, wx.EXPAND | wx.ALL, 5)

        lbl_tick = wx.StaticText(self, label="Posição Exata (Tick):")
        sizer.Add(lbl_tick, 0, wx.ALL, 5)
        
        self.sp_tick = wx.SpinCtrl(self, value=str(tick_val), min=0, max=9999999)
        sizer.Add(self.sp_tick, 0, wx.EXPAND | wx.ALL, 5)
        
        self.sp_bank.Bind(wx.EVT_SPINCTRL, self.on_update)
        self.sp_patch.Bind(wx.EVT_SPINCTRL, self.on_update)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)
        
        self.atualizar_label(falar=False)
        wx.CallLater(100, self.sp_bank.SetFocus)
        
    def atualizar_label(self, falar=True):
        b_val = self.sp_bank.GetValue()
        p_val = self.sp_patch.GetValue()
        nome_pc = f"Program {p_val}"
        
        if hasattr(self.parent_list.parent, 'instrument_names'):
            nome_pc = self.parent_list.parent.instrument_names.get(b_val, {}).get(p_val, nome_pc)
            
        self.lbl_patch.SetLabel(f"Patch: {nome_pc}")
        if falar:
            falar_status(nome_pc, imediato=True)
        
    def on_update(self, event):
        self.atualizar_label(falar=True)
            
    def get_values(self):
        return self.sp_bank.GetValue(), self.sp_patch.GetValue(), self.sp_tick.GetValue()
class EventListDialog(wx.Dialog):
    def __init__(self, parent, canais_alvo):
        # Aceita um único canal ou vários!
        self.canais_alvo = set(canais_alvo) if isinstance(canais_alvo, (set, list)) else {canais_alvo}
        self.canal_idx = list(self.canais_alvo)[0] # Mantém para não quebrar janelas filhas
        
        titulo = f"Event List - {len(self.canais_alvo)} canais" if len(self.canais_alvo) > 1 else f"Event List - Canal {self.canal_idx+1}"
        super().__init__(parent, title=titulo, size=(600, 400), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        
        self.parent = parent
        self.preview_note = None
        self.preview_timer = None
        self.is_anchored = True # GATILHO: Começa ancorado no cursor atual!
        self.last_playback_idx = 0
        self.modified = False
        self.needs_audio_rebuild = False 
        
        if getattr(self.parent, 'midi_file', None):
            self.backup_global_midi = self.parent.clone_midi_rapido(self.parent.midi_file)
        
        self.undo_stack = []
        self.selected_indices = set()
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.dummy_focus = wx.Panel(self, size=(0, 0), style=wx.WANTS_CHARS)
        sizer.Add(self.dummy_focus, 0, wx.ALL, 0)
        
        self.list_box = VirtualEventList(self, self)
        sizer.Add(self.list_box, 1, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(sizer)
        
        self.tempo_map = []
        self.build_tempo_map()
        self.load_events()
        
        self.sync_to_playback_time()
        self.current_idx = self.last_playback_idx
        self.reconstruir_lista_visual()
        
        self.list_box.Bind(wx.EVT_SET_FOCUS, lambda e: self.dummy_focus.SetFocus())
        self.dummy_focus.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        
        wx.CallAfter(self.dummy_focus.SetFocus)
        wx.CallLater(1000, self.falar_primeira_nota)
    def registrar_undo(self):
        # Apenas bate a foto interna pro Ctrl+Z daqui de dentro da tela!
        if not hasattr(self, 'undo_stack'):
            self.undo_stack = []
            
        # OTIMIZAÇÃO EXTREMA: Salva o estado num piscar de olhos sem congelar o leitor de telas
        self.undo_stack.append(self.parent.clone_midi_rapido(self.parent.midi_file))
        
        if len(self.undo_stack) > 30: 
            self.undo_stack.pop(0)
    def is_drum_channel(self):
        if hasattr(self.parent, 'canais') and self.canal_idx in self.parent.canais:
            if self.parent.canais[self.canal_idx].get("IsDrum", False):
                return True
        return self.canal_idx == 9

    def get_current_bank_patch_at_time(self, target_time=None):
        b = -1
        p = -1
        
        if target_time is not None:
            temp_b_msb = 0
            temp_b_lsb = 0
            for ev in self.display_events:
                ev_time = ev['start'] if ev['type'] == 'note' else ev['time']
                
                if ev_time > target_time:
                    break
                    
                if ev['type'] == 'control_change':
                    if ev['msg'].control == 0:
                        temp_b_msb = ev['msg'].value
                    elif ev['msg'].control == 32:
                        temp_b_lsb = ev['msg'].value
                elif ev['type'] == 'program_change':
                    b = (temp_b_msb * 128) + temp_b_lsb
                    p = ev['msg'].program
                    
        if p == -1:
            if hasattr(self.parent, 'overrides') and self.canal_idx in self.parent.overrides:
                ov = self.parent.overrides[self.canal_idx]
                if "Bank" in ov:
                    b = ov["Bank"]
                if "Patch" in ov:
                    p = ov["Patch"]
                    
            if p == -1 and hasattr(self.parent, 'canais') and self.canal_idx in self.parent.canais:
                b = self.parent.canais[self.canal_idx].get("Bank", 0)
                p = self.parent.canais[self.canal_idx].get("Patch", 0)
                
        return max(0, b), max(0, p)

    def get_nome_nota_ou_peca(self, nota_val, b=None, p=None):
        if b is None or p is None:
            b, p = self.get_current_bank_patch_at_time()
            
        if hasattr(self.parent, 'key_names'):
            kn = self.parent.key_names
            if isinstance(kn, dict):
                if b in kn and isinstance(kn[b], dict) and p in kn[b] and nota_val in kn[b][p]:
                    return kn[b][p][nota_val]
                if (b, p) in kn and nota_val in kn[(b, p)]:
                    return kn[(b, p)][nota_val]
                    
        if self.is_drum_channel():
            bateras = {
                13: "Surdo Mute", 14: "Surdo Open", 15: "Hi Q", 16: "Whip Slap", 17: "Scratch Push", 18: "Scratch Pull", 
                19: "Finger Snap", 20: "Click Noise", 21: "Metronome Click", 22: "Metronome Bell", 23: "Seq Click L", 24: "Seq Click H", 
                25: "Brush Tap", 26: "Brush Swirl L", 27: "Brush Slap", 28: "Brush Tap Swirl", 29: "Snare Roll", 30: "Castanet", 
                31: "Snare L", 32: "Sticks", 33: "Bass Drum L", 34: "Open Rim Shot", 35: "Acoustic Bass Drum", 36: "Bass Drum 1", 
                37: "Side Stick", 38: "Acoustic Snare", 39: "Hand Clap", 40: "Electric Snare", 41: "Low Floor Tom", 42: "Closed Hi Hat", 
                43: "High Floor Tom", 44: "Pedal Hi-Hat", 45: "Low Tom", 46: "Open Hi-Hat", 47: "Low-Mid Tom", 48: "Hi-Mid Tom", 
                49: "Crash Cymbal 1", 50: "High Tom", 51: "Ride Cymbal 1", 52: "Chinese Cymbal", 53: "Ride Bell", 54: "Tambourine", 
                55: "Splash Cymbal", 56: "Cowbell", 57: "Crash Cymbal 2", 58: "Vibraslap", 59: "Ride Cymbal 2", 60: "Hi Bongo",
                61: "Low Bongo", 62: "Mute Conga", 63: "Open Conga", 64: "Low Conga", 65: "High Timbale", 66: "Low Timbale",
                67: "High Agogo", 68: "Low Agogo", 69: "Cabasa", 70: "Maracas", 71: "Short Whistle", 72: "Long Whistle",
                73: "Short Guiro", 74: "Long Guiro", 75: "Claves", 76: "Hi Wood Block", 77: "Low Wood Block", 78: "Mute Cuica",
                79: "Open Cuica", 80: "Mute Triangle", 81: "Open Triangle", 82: "Shaker", 83: "Jingle Bell", 84: "Belltree",
                85: "Castanet", 86: "Mute Surdo", 87: "Open Surdo"
            }
            return bateras.get(nota_val, f"Peça {nota_val}")
            
        return get_nome_nota(nota_val)
        
    def falar_primeira_nota(self):
        if self.display_events:
            fala = self.gerar_fala_curta(self.display_events[self.current_idx])
            falar_status(fala, imediato=True)

    def build_tempo_map(self):
        self.tempo_map = []
        tpb = max(1, getattr(self.parent.midi_file, 'ticks_per_beat', 480))
        current_tempo = 500000
        self.tempo_map.append((0, 0.0, current_tempo))
        if not getattr(self.parent, 'midi_file', None):
            return
            
        # OTIMIZAÇÃO: Busca o tempo separadamente por track. Nada de merge_tracks travando a janela!
        tempos = []
        for track in self.parent.midi_file.tracks:
            abs_t = 0
            for msg in track:
                abs_t += msg.time
                if msg.type == 'set_tempo':
                    tempos.append((abs_t, msg.tempo))
        tempos.sort(key=lambda x: x[0])
        
        abs_ticks = 0
        abs_sec = 0.0
        
        for t_tick, t_val in tempos:
            if t_tick > abs_ticks:
                diff_ticks = t_tick - abs_ticks
                abs_sec += (diff_ticks * current_tempo) / (tpb * 1000000.0)
                abs_ticks = t_tick
            current_tempo = t_val
            self.tempo_map.append((abs_ticks, abs_sec, current_tempo))
    def tick_to_sec(self, target_tick):
        tpb = max(1, getattr(self.parent.midi_file, 'ticks_per_beat', 480))
        last_tempo_ev = self.tempo_map[0]
        for tm in self.tempo_map:
            if tm[0] <= target_tick:
                last_tempo_ev = tm
            else:
                break
        base_tick, base_sec, tempo = last_tempo_ev
        diff_ticks = max(0, target_tick - base_tick)
        return base_sec + mido.tick2second(diff_ticks, tpb, tempo)

    def get_tempo_at_tick(self, target_tick):
        last_tempo = 500000
        for tm in self.tempo_map:
            if tm[0] <= target_tick:
                last_tempo = tm[2]
            else:
                break
        return last_tempo

    def load_events(self):
        self.tracks_abs, self.all_display_events = [], []
        self.pistas_do_canal = set()
        self.original_lens = {} 
        
        if not hasattr(self, 'active_filter'): self.active_filter = 1
        if not getattr(self.parent, 'midi_file', None): return
        
        default_b = 0
        default_p = 0
        if hasattr(self.parent, 'overrides') and self.canal_idx in self.parent.overrides:
            ov = self.parent.overrides[self.canal_idx]
            if "Bank" in ov: default_b = ov["Bank"]
            if "Patch" in ov: default_p = ov["Patch"]
        elif hasattr(self.parent, 'canais') and self.canal_idx in self.parent.canais:
            default_b = self.parent.canais[self.canal_idx].get("Bank", 0)
            default_p = self.parent.canais[self.canal_idx].get("Patch", 0)
            
        tpb = max(1, getattr(self.parent.midi_file, 'ticks_per_beat', 480))
        tempo_events = []
        for track in self.parent.midi_file.tracks:
            abs_tick = 0
            for msg in track:
                abs_tick += msg.time
                if msg.type == 'set_tempo':
                    tempo_events.append((abs_tick, msg.tempo))
        tempo_events.sort(key=lambda x: x[0])
        
        for t_idx, track in enumerate(self.parent.midi_file.tracks):
            abs_time, events, active_notes = 0, [], {}
            temp_b_msb, temp_b_lsb = 0, 0
            current_b = default_b
            current_p = default_p
            has_our_channel = False
            
            for msg in track:
                abs_time += msg.time
                
                # --- BUSCA EM MÚLTIPLOS CANAIS ---
                if getattr(msg, 'channel', None) in self.canais_alvo:
                    has_our_channel = True
                    if msg.type == 'control_change':
                        if msg.control == 0: temp_b_msb = msg.value
                        elif msg.control == 32: temp_b_lsb = msg.value
                    elif msg.type == 'program_change':
                        current_b = (temp_b_msb * 128) + temp_b_lsb
                        current_p = msg.program
                
                if msg.type == 'note_on' and msg.velocity > 0:
                    ev = {'type': 'note', 'start': abs_time, 'end': abs_time, 'msg_on': msg, 'msg_off': None, 'track': t_idx, 'bank': current_b, 'patch': current_p}
                    events.append(ev)
                    active_notes[(getattr(msg, 'channel', None), msg.note)] = ev
                elif msg.type == 'note_off' or (msg.type == 'note_on' and getattr(msg, 'velocity', 0) == 0):
                    key = (getattr(msg, 'channel', None), getattr(msg, 'note', None))
                    if key in active_notes:
                        active_notes[key]['end'] = abs_time
                        active_notes[key]['msg_off'] = msg
                        del active_notes[key]
                    else:
                        ev = {'type': 'note_off', 'time': abs_time, 'msg': msg, 'track': t_idx}
                        events.append(ev)
                else:
                    ev = {'type': getattr(msg, 'type', 'unknown'), 'time': abs_time, 'msg': msg, 'track': t_idx, 'bank': current_b, 'patch': current_p}
                    events.append(ev)
                    
            if has_our_channel:
                self.pistas_do_canal.add(t_idx)
                
            self.tracks_abs.append(events)
            self.original_lens[t_idx] = len(events)

        raw_display = []
        for t_events in self.tracks_abs:
            for ev in t_events:
                msg = ev.get('msg_on') if ev['type'] == 'note' else ev.get('msg')
                # --- EXIBE TODOS OS CANAIS ALVO ---
                if msg and getattr(msg, 'channel', None) in self.canais_alvo:
                    if getattr(msg, 'type', '') in ['note_on', 'control_change', 'program_change', 'pitchwheel']:
                        raw_display.append(ev)
                        
        raw_display.sort(key=lambda x: x['start'] if x['type'] == 'note' else x['time'])
        
        curr_tempo_idx = 0
        curr_tempo = 500000
        curr_tick_anchor = 0
        curr_sec_anchor = 0.0
        tempo_div = 1000000.0 * tpb
        
        for ev in raw_display:
            abs_t = ev['start'] if ev['type'] == 'note' else ev.get('time', 0)
            
            while curr_tempo_idx < len(tempo_events) and tempo_events[curr_tempo_idx][0] <= abs_t:
                t_tick, t_val = tempo_events[curr_tempo_idx]
                if t_tick > curr_tick_anchor:
                    curr_sec_anchor += (t_tick - curr_tick_anchor) * float(curr_tempo) / tempo_div
                    curr_tick_anchor = t_tick
                curr_tempo = t_val
                curr_tempo_idx += 1
                
            ev['abs_sec'] = curr_sec_anchor + (abs_t - curr_tick_anchor) * float(curr_tempo) / tempo_div
            self.all_display_events.append(ev)

        self.apply_filter(falar=False)
    def apply_filter(self, falar=True):
        if not hasattr(self, 'active_filter'):
            self.active_filter = 1
            
        indice_salvo = getattr(self, 'current_idx', 0)
        
        target_sec = 0.0
        if hasattr(self, 'display_events') and self.display_events and 0 <= indice_salvo < len(self.display_events):
            target_sec = self.display_events[indice_salvo].get('abs_sec', 0.0)
            
        self.display_events = []
        for ev in self.all_display_events:
            if self.active_filter == 1: self.display_events.append(ev)
            elif self.active_filter == 2 and ev['type'] == 'note': self.display_events.append(ev)
            elif self.active_filter == 3 and ev['type'] == 'control_change': self.display_events.append(ev)
            elif self.active_filter == 4 and ev['type'] == 'program_change': self.display_events.append(ev)
            elif self.active_filter == 5 and ev['type'] == 'pitchwheel': self.display_events.append(ev)
            
        self.selected_indices.clear()
        
        if not falar:
            if self.display_events:
                self.current_idx = max(0, min(indice_salvo, len(self.display_events) - 1))
            else:
                self.current_idx = 0
        else:
            best_idx = 0
            min_diff = 999999.0
            for i, ev in enumerate(self.display_events):
                diff = abs(ev.get('abs_sec', 0.0) - target_sec)
                if diff < min_diff:
                    min_diff = diff
                    best_idx = i
            self.current_idx = best_idx if self.display_events else 0
            
        self.reconstruir_lista_visual()
        
        if falar:
            nomes = {1: "Todos", 2: "Notas", 3: "Control Changes", 4: "Program Changes", 5: "Pitch Wheel"}
            from mhs_utils import falar_status
            falar_status(f"Filtro: {nomes.get(self.active_filter, '')}. {len(self.display_events)} itens.", imediato=True)
    def sync_to_playback_time(self):
        if not self.display_events:
            return
        pt = getattr(self.parent, 'current_playback_time', 0.0)
        for i, ev in enumerate(self.display_events):
            if ev.get('abs_sec', 0.0) >= pt - 0.001:
                self.last_playback_idx = i
                break
        else:
            self.last_playback_idx = len(self.display_events) - 1
        self.is_anchored = True

    def gerar_fala_curta(self, ev):
        msg = ev.get('msg_on') if ev['type'] == 'note' else ev['msg']
        ch = getattr(msg, 'channel', 0)
        prefix = f"C {ch+1} " if len(self.canais_alvo) > 1 else ""
        
        if ev['type'] == 'note':
            b = ev.get('bank', 0)
            p = ev.get('patch', 0)
            nome = self.get_nome_nota_ou_peca(msg.note, b, p)
            if self.is_drum_channel():
                return f"{prefix}{nome}"
            return f"{prefix}Nota {nome}"
            
        elif msg.type == 'control_change':
            nome_cc = CC_DICT.get(msg.control, f"Control {msg.control}")
            return f"{prefix}{nome_cc}, valor {msg.value}"
            
        elif msg.type == 'program_change':
            ev_time = ev['time']
            b, p = self.get_current_bank_patch_at_time(ev_time)
            nome_pc = f"Program {msg.program}"
            if hasattr(self.parent, 'instrument_names'):
                nome_pc = self.parent.instrument_names.get(b, {}).get(msg.program, nome_pc)
            return f"{prefix}PC Banco {b} Patch {nome_pc}"
            
        elif msg.type == 'pitchwheel':
            return f"{prefix}Pitch {msg.pitch}"
            
        return f"{prefix}{msg.type}"
    def reconstruir_lista_visual(self):
        self.list_box.SetItemCount(len(self.display_events))
        self.list_box.Refresh()
        self.atualizar_foco_visual()
    def atualizar_foco_visual(self):
        if not self.display_events: return
        self.list_box.Freeze()
        
        total = self.list_box.GetItemCount()
        selecionados = len(self.selected_indices)
        
        if selecionados == 0:
            self.list_box.SetItemState(-1, 0, wx.LIST_STATE_SELECTED)
        elif selecionados == total:
            self.list_box.SetItemState(-1, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)
        elif selecionados < 50:
            self.list_box.SetItemState(-1, 0, wx.LIST_STATE_SELECTED)
            for idx in self.selected_indices:
                if 0 <= idx < total:
                    self.list_box.SetItemState(idx, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)
        else:
            self.list_box.SetItemState(-1, 0, wx.LIST_STATE_SELECTED)
            
        if 0 <= self.current_idx < total:
            self.list_box.SetItemState(self.current_idx, wx.LIST_STATE_FOCUSED | wx.LIST_STATE_SELECTED, wx.LIST_STATE_FOCUSED | wx.LIST_STATE_SELECTED)
            self.list_box.EnsureVisible(self.current_idx)
            
        self.list_box.Thaw()
    def speak_and_preview(self):
        if not self.display_events:
            return
            
        ev = self.display_events[self.current_idx]
        msg = ev.get('msg_on') if ev['type'] == 'note' else ev['msg']
        
        falar_status(self.gerar_fala_curta(ev), imediato=True)
        
        if ev['type'] == 'note': 
            self.tocar_nota_exata(msg, ev['start'], ev['end'])
        
        target_time = max(0.0, ev.get('abs_sec', 0.0) - 0.001)
        if getattr(self.parent, 'tocando', False): 
            self.parent.all_notes_off()
            
        self.parent.current_playback_time = target_time
        self.parent.last_start_time = target_time 
        self.parent.seek_flag = True

    def rebuild_final_midi(self):
        try:
            if not hasattr(self, 'pistas_do_canal'):
                self.pistas_do_canal = set(range(len(self.tracks_abs)))
                
            for i, t_events in enumerate(self.tracks_abs):
                # OTIMIZAÇÃO: Se a pista não tem o nosso canal, e o número de notas não mudou, PULA!
                if i not in self.pistas_do_canal:
                    if hasattr(self, 'original_lens') and len(t_events) == self.original_lens.get(i, -1):
                        continue 
                        
                flat = []
                for ev in t_events:
                    if ev['type'] == 'note':
                        flat.append([ev['start'], ev['msg_on']])
                        if ev.get('msg_off'):
                            flat.append([ev['end'], ev['msg_off']])
                    else:
                        flat.append([ev.get('time', 0), ev.get('msg')])
                
                # OTIMIZAÇÃO: Prioridade construída rápido para ordenar sem congelar o wxPython
                for idx_item, item in enumerate(flat):
                    m = item[1]
                    is_off = 0 if m and (m.type == 'note_off' or (m.type == 'note_on' and getattr(m, 'velocity', 0) == 0)) else 1
                    item.append(is_off)

                flat_indexed = [(item[0], item[2], idx, item[1]) for idx, item in enumerate(flat)]
                # OTIMIZAÇÃO: itemgetter é mais rápido que lambda aqui
                from operator import itemgetter
                flat_indexed.sort(key=itemgetter(0, 1, 2))

                import mido
                new_track = mido.MidiTrack()
                last_t = 0
                
                for t, _, idx, m in flat_indexed:
                    if not m: continue
                    delta = max(0, int(round(t - last_t)))
                    # OTIMIZAÇÃO DA MUTAÇÃO: Acaba com as instâncias cópias
                    m.time = delta
                    new_track.append(m)
                    last_t = t
                    
                if i < len(self.parent.midi_file.tracks):
                    self.parent.midi_file.tracks[i] = new_track
                
            self.parent.dirty = True
        except Exception as e:
            from mhs_utils import falar_status
            falar_status(f"Erro invisível evitado: {e}", imediato=True)
    def handle_midi_in(self, in_msg):
        if in_msg.type not in ['note_on', 'note_off']:
            return

        if not self.display_events:
            if getattr(self.parent, 'output', None): 
                self.parent.output.send(in_msg.copy(channel=self.canal_idx))
            return
            
        ev = self.display_events[self.current_idx]
        
        if ev['type'] == 'note' and in_msg.type == 'note_on' and in_msg.velocity > 0:
            self.registrar_undo()
            
            old_msg_on = ev['msg_on']
            new_note = in_msg.note
            new_vel = in_msg.velocity
            
            ev['msg_on'] = old_msg_on.copy(note=new_note, velocity=new_vel)
            if ev['msg_off']: 
                ev['msg_off'] = ev['msg_off'].copy(note=new_note)
                
            self.modified = True
            self.needs_audio_rebuild = True
            
            if 0 <= self.current_idx < len(self.display_events):
                self.list_box.RefreshItem(self.current_idx)
            self.atualizar_foco_visual()
            
            b = ev.get('bank', 0)
            p = ev.get('patch', 0)
            nome = self.get_nome_nota_ou_peca(new_note, b, p)
            falar_status(f"Substituído: {nome}", imediato=True)
            self.tocar_nota_exata(ev['msg_on'], ev['start'], ev['end'])
        else:
            if getattr(self.parent, 'output', None):
                self.parent.output.send(in_msg.copy(channel=self.canal_idx))
    def get_selected_events(self):
        if self.selected_indices:
            return [self.display_events[i] for i in sorted(self.selected_indices)]
        return [self.display_events[self.current_idx]]

    def copiar_evento(self):
        evs = self.get_selected_events()
        if not evs:
            return
            
        self.parent.event_clipboard = []
        source_tpb = max(1, getattr(self.parent.midi_file, 'ticks_per_beat', 480))
        first_ticks = evs[0]['start'] if evs[0]['type'] == 'note' else evs[0]['time']
        
        for ev in evs:
            ev_ticks = ev['start'] if ev['type'] == 'note' else ev['time']
            offset = ev_ticks - first_ticks
            
            # Tira uma cópia idêntica e profunda do dicionário nativo do evento
            clonado = copy.deepcopy(ev)
            clonado['tick_offset'] = offset
            clonado['source_tpb'] = source_tpb
            self.parent.event_clipboard.append(clonado)
                
        from mhs_utils import falar_status
        falar_status(f"{len(evs)} eventos copiados.", imediato=True)
    def recortar_evento(self):
        from mhs_utils import falar_status
        self.copiar_evento()
        self.registrar_undo() 
        evs = self.get_selected_events()
        
        for ev in evs:
            if ev in self.tracks_abs[ev['track']]:
                self.tracks_abs[ev['track']].remove(ev)
                
        self.selected_indices.clear()
        self.modified = True
        self.needs_audio_rebuild = True
        
        falar_status(f"{len(evs)} eventos recortados.", imediato=True)
        self.rebuild_final_midi()
        self.load_events()
        
        # --- TRAVA DE SEGURANÇA DO CURSOR ---
        # Garante que o NVDA não trave se a lista ficar vazia após o recorte
        if not self.display_events:
            self.current_idx = 0
            self.reconstruir_lista_visual()
            return
            
        self.current_idx = max(0, min(self.current_idx, len(self.display_events) - 1))
        self.reconstruir_lista_visual()
        self.speak_and_preview()
    def colar_evento(self):
        from mhs_utils import falar_status
        if not getattr(self.parent, 'event_clipboard', None):
            falar_status("Área de transferência vazia.", imediato=True)
            return
            
        self.registrar_undo()
        
        if getattr(self, 'is_anchored', False) or not self.display_events:
            abs_sec = getattr(self.parent, 'current_playback_time', 0.0)
            base_paste_ticks = self.parent.get_tick_at_sec(abs_sec) if hasattr(self.parent, 'get_tick_at_sec') else 0
        else:
            ev_foco = self.display_events[self.current_idx]
            base_paste_ticks = ev_foco['start'] if ev_foco['type'] == 'note' else ev_foco['time']

        ch_alvo = self.canal_idx 

        track_destino = 0
        if getattr(self.parent, 'midi_file', None):
            for t_idx, track in enumerate(self.parent.midi_file.tracks):
                if any(getattr(m, 'channel', None) == ch_alvo for m in track):
                    track_destino = t_idx
                    break

        dest_tpb = max(1, getattr(self.parent.midi_file, 'ticks_per_beat', 480))
        
        for item in self.parent.event_clipboard:
            scale = dest_tpb / float(item.get('source_tpb', dest_tpb))
            scaled_offset = int(round(item['tick_offset'] * scale))
            paste_ticks = base_paste_ticks + scaled_offset
            
            if item['type'] == 'note':
                dur_original = item['end'] - item['start']
                dur_scaled = int(round(dur_original * scale))
                
                msg_on = item['msg_on'].copy(channel=ch_alvo)
                msg_off = item['msg_off'].copy(channel=ch_alvo) if item.get('msg_off') else None
                if not msg_off:
                    import mido
                    msg_off = mido.Message('note_off', channel=ch_alvo, note=msg_on.note, velocity=0)
                    
                b, p = self.get_current_bank_patch_at_time(paste_ticks)
                
                new_ev = {
                    'type': 'note',
                    'start': paste_ticks,
                    'end': paste_ticks + dur_scaled,
                    'msg_on': msg_on,
                    'msg_off': msg_off,
                    'track': track_destino,
                    'bank': b,
                    'patch': p
                }
                self.tracks_abs[track_destino].append(new_ev)
            else:
                msg = item['msg'].copy(channel=ch_alvo) if hasattr(item['msg'], 'channel') else item['msg'].copy()
                new_ev = {
                    'type': item['type'],
                    'time': paste_ticks,
                    'msg': msg,
                    'track': track_destino
                }
                self.tracks_abs[track_destino].append(new_ev)
        
        self.modified = True
        self.needs_audio_rebuild = True
        falar_status("Colado.", imediato=True)
        self.rebuild_final_midi()
        self.load_events()
        self.reconstruir_lista_visual()
        self.speak_and_preview()
    def duplicar_evento(self, flam=False):
        if not self.display_events:
            return
            
        self.registrar_undo()
        self.modified = True
        self.needs_audio_rebuild = True
        
        delay_sec = 0.040 if flam else 0.0
        tpb = max(1, getattr(self.parent.midi_file, 'ticks_per_beat', 480))
        
        ev = self.display_events[self.current_idx]
        msg = ev.get('msg_on') if ev['type'] == 'note' else ev['msg']
        
        abs_ticks = ev['start'] if ev['type'] == 'note' else ev['time']
        local_tempo = self.get_tempo_at_tick(abs_ticks)
        bpm_dur = local_tempo / 1000000.0
        delay_ticks = int(round((delay_sec / bpm_dur) * tpb))

        new_start_ticks = abs_ticks + delay_ticks
        
        if ev['type'] == 'note':
            dur_ticks = ev['end'] - ev['start']
            new_end_ticks = new_start_ticks + dur_ticks
            
            msg_on = ev['msg_on'].copy()
            if ev['msg_off']:
                msg_off = ev['msg_off'].copy()
            else:
                msg_off = mido.Message('note_off', channel=msg_on.channel, note=msg_on.note, velocity=0)
            
            new_ev = {'type': 'note', 'start': new_start_ticks, 'end': new_end_ticks, 'msg_on': msg_on, 'msg_off': msg_off, 'track': ev['track'], 'bank': ev.get('bank', 0), 'patch': ev.get('patch', 0)}
            self.tracks_abs[ev['track']].append(new_ev)
        else:
            new_ev = {'type': ev['type'], 'time': new_start_ticks, 'msg': msg.copy(), 'track': ev['track']}
            self.tracks_abs[ev['track']].append(new_ev)
            
        if flam:
            falar_status("Flam gerado.", imediato=True)
        else:
            falar_status("Evento duplicado.", imediato=True)
        
        self.rebuild_final_midi()
        self.load_events()
        self.reconstruir_lista_visual()
        
        self.current_idx = min(self.current_idx + 1, len(self.display_events) - 1)
        self.atualizar_foco_visual()
        self.speak_and_preview()

    def achatar_notas_um_tick(self):
        # 'T' de Tick - reduz a DURAÇÃO de nota(s) pro mínimo possível (1
        # tick), sem mexer no início, no pitch nem na velocity. Pedido do
        # Michel pra bateria/percussão: como esses instrumentos costumam
        # ser samples de um tiro só, o note_off praticamente não importa
        # pro som terminar - deixar cada batida com 1 tick só limpa a
        # lista de eventos e evita nota "comprida" à toa arrastando note_
        # off por cima de outras batidas. Mesmo critério de alvo do 'S'
        # (Substituir): seleção múltipla > trecho marcado (Início/Fim) >
        # todas as notas da lista visível.
        if not self.display_events:
            return
        t_start = getattr(self.parent, 'time_selection_start', None)
        t_end = getattr(self.parent, 'time_selection_end', None)
        if len(self.selected_indices) > 1:
            evs_target = self.get_selected_events()
        elif t_start is not None and t_end is not None:
            t_min = min(t_start, t_end)
            t_max = max(t_start, t_end)
            evs_target = [e for e in self.display_events if t_min - 0.001 <= e.get('abs_sec', 0.0) <= t_max + 0.001]
        else:
            evs_target = self.display_events
        notas = [e for e in evs_target if e['type'] == 'note']
        if not notas:
            falar_status("Nenhuma nota pra achatar.", imediato=True)
            return
        self.registrar_undo()
        for e in notas:
            e['end'] = e['start'] + 1
        self.modified = True
        self.needs_audio_rebuild = True
        falar_status(f"{len(notas)} nota(s) achatada(s) pra 1 tick.", imediato=True)
        self.rebuild_final_midi()
        self.load_events()
        self.reconstruir_lista_visual()
        self.speak_and_preview()

    def insert_event(self):
        # --- A MÁGICA DA ÂNCORA ---
        # Verifica se o usuário usou os atalhos de navegação no tempo
        if getattr(self, 'is_anchored', False) or not self.display_events:
            abs_sec = getattr(self.parent, 'current_playback_time', 0.0)
            base_ticks = self.parent.get_tick_at_sec(abs_sec) if hasattr(self.parent, 'get_tick_at_sec') else 0
        else:
            ev_foco = self.display_events[self.current_idx]
            base_ticks = ev_foco['start'] if ev_foco['type'] == 'note' else ev_foco['time']
            abs_sec = ev_foco.get('abs_sec', 0.0)

        b, p = self.get_current_bank_patch_at_time(base_ticks)
        dlg = wx.SingleChoiceDialog(self, "Tipo de Evento:", "Inserir", ["Nota", "Control Change (CC)", "Program Change (PC)"])
        
        if dlg.ShowModal() == wx.ID_OK:
            sel_idx = dlg.GetSelection()
            track_destino = 0
            if getattr(self.parent, 'midi_file', None):
                for t_idx, track in enumerate(self.parent.midi_file.tracks):
                    if any(getattr(m, 'channel', None) == self.canal_idx for m in track):
                        track_destino = t_idx
                        break

            new_ev_list = []
            import mido
            
            if sel_idx == 0:
                dlg_nota = EdicaoNotaDialog(self, 60, 100, 240, b, p, is_insert=True)
                if dlg_nota.ShowModal() == wx.ID_OK:
                    nota, vel, dur_ticks = dlg_nota.get_values()
                    msg = mido.Message('note_on', channel=self.canal_idx, note=nota, velocity=vel)
                    msg_off = mido.Message('note_off', channel=self.canal_idx, note=nota, velocity=0)
                    new_ev_list.append({'type': 'note', 'start': base_ticks, 'end': base_ticks + dur_ticks, 'msg_on': msg, 'msg_off': msg_off, 'track': track_destino, 'abs_sec': abs_sec, 'bank': b, 'patch': p})
                dlg_nota.Destroy()
                
            elif sel_idx == 1:
                # O Erro Antigo Morava Aqui: Faltava passar o tick_val e ler a variável t_new
                dlg_cc = EdicaoCCDialog(self, 0, 0, tick_val=base_ticks, is_insert=True)
                if dlg_cc.ShowModal() == wx.ID_OK:
                    cc, val, t_new = dlg_cc.get_values()
                    sec_new = self.tick_to_sec(t_new) if hasattr(self, 'tick_to_sec') else abs_sec
                    msg = mido.Message('control_change', channel=self.canal_idx, control=cc, value=val)
                    new_ev_list.append({'type': 'control_change', 'time': t_new, 'msg': msg, 'track': track_destino, 'abs_sec': sec_new})
                dlg_cc.Destroy()
                
            elif sel_idx == 2:
                # O Erro Antigo Morava Aqui: Faltava passar o tick_val e ler a variável t_new
                dlg_pc = EdicaoPCDialog(self, b, p, tick_val=base_ticks, is_insert=True)
                if dlg_pc.ShowModal() == wx.ID_OK:
                    bank, patch, t_new = dlg_pc.get_values()
                    sec_new = self.tick_to_sec(t_new) if hasattr(self, 'tick_to_sec') else abs_sec
                    msg_pc = mido.Message('program_change', channel=self.canal_idx, program=patch)
                    msg_msb = mido.Message('control_change', channel=self.canal_idx, control=0, value=bank // 128)
                    msg_lsb = mido.Message('control_change', channel=self.canal_idx, control=32, value=bank % 128)
                    
                    new_ev_list.append({'type': 'control_change', 'time': t_new, 'msg': msg_msb, 'track': track_destino, 'abs_sec': sec_new})
                    new_ev_list.append({'type': 'control_change', 'time': t_new, 'msg': msg_lsb, 'track': track_destino, 'abs_sec': sec_new})
                    new_ev_list.append({'type': 'program_change', 'time': t_new, 'msg': msg_pc, 'track': track_destino, 'abs_sec': sec_new})
                dlg_pc.Destroy()

            if new_ev_list:
                self.registrar_undo()
                self.modified = True
                self.needs_audio_rebuild = True
                for ev in new_ev_list:
                    self.tracks_abs[track_destino].append(ev)
                
                from mhs_utils import falar_status
                falar_status("Evento inserido na posição exata.", imediato=True)
                
                self.rebuild_final_midi()
                self.load_events()
                self.reconstruir_lista_visual()
                
                # Foca no novo evento recém criado!
                if self.display_events:
                    self.current_idx = min(self.current_idx + 1, len(self.display_events) - 1)
                    self.atualizar_foco_visual()
                    self.speak_and_preview()
                
        dlg.Destroy()
        wx.CallAfter(self.dummy_focus.SetFocus)

    # =====================================================================
    # O CÉREBRO DOS TECLADOS
    # =====================================================================
    def on_key(self, event):
        import wx
        from mhs_utils import falar_status
        code = event.GetKeyCode()
        ctrl = event.ControlDown()
        shift = event.ShiftDown()
        alt = event.AltDown()

        if code in [ord('W'), ord('w')] and not (ctrl or alt or shift):
            self.parent.current_playback_time = 0.0
            self.parent.last_start_time = 0.0
            self.parent.seek_flag = True
            self.current_idx = 0
            self.is_anchored = True
            if self.display_events:
                self.atualizar_foco_visual()
            falar_status("Início da música", imediato=True)
            return

        if code == wx.WXK_INSERT or (code in [ord('I'), ord('i')] and ctrl):
            if hasattr(self, 'insert_event'): self.insert_event()
            return
        
        if code in [ord('V'), ord('v')] and ctrl and not shift and not alt:
            if hasattr(self, 'colar_evento'): self.colar_evento()
            return
            
        if code in [wx.WXK_SPACE, 32] and not shift and not alt:
            if ctrl:
                if hasattr(self.parent, 'toggle_pausa'): self.parent.toggle_pausa(None)
            else:
                was_playing = getattr(self.parent, 'tocando', False)
                if was_playing and hasattr(self.parent, 'toggle_reproducao'):
                    self.parent.toggle_reproducao(None)
                    import time
                    time.sleep(0.05) 
                if getattr(self, 'needs_audio_rebuild', False):
                    self.rebuild_final_midi()
                    try:
                        play_time = getattr(self.parent, 'current_playback_time', 0.0)
                        self.parent.ler_midi_memoria(reset_canais=False)
                        self.parent.current_playback_time = play_time
                        self.parent.seek_flag = True
                    except: pass
                    self.needs_audio_rebuild = False
                if not was_playing and hasattr(self.parent, 'toggle_reproducao'): 
                    self.parent.toggle_reproducao(None)
            if hasattr(self, 'sync_to_playback_time'):
                wx.CallAfter(self.sync_to_playback_time)
            return

        if code == wx.WXK_ESCAPE:
            if shift:
                self.selected_indices.clear()
                self.parent.time_selection_start = None
                self.parent.time_selection_end = None
                self.non_contiguous_mode = False
                self.atualizar_foco_visual()
                from mhs_utils import falar_status
                falar_status("Seleções canceladas.", imediato=True)
                return
            try:
                was_playing = getattr(self.parent, 'tocando', False)
                if was_playing and hasattr(self.parent, 'toggle_reproducao'):
                    self.parent.toggle_reproducao(None)
                    import time
                    time.sleep(0.05)
                if getattr(self, 'modified', False) or getattr(self, 'needs_audio_rebuild', False):
                    from mhs_utils import falar_status
                    falar_status("Salvando alterações...", imediato=True)
                    if hasattr(self.parent, 'salvar_estado_desfazer') and hasattr(self, 'backup_global_midi'):
                        current_midi = self.parent.midi_file
                        self.parent.midi_file = self.backup_global_midi
                        self.parent.salvar_estado_desfazer()
                        self.parent.midi_file = current_midi
                    self.rebuild_final_midi()
                    try:
                        play_time = getattr(self.parent, 'current_playback_time', 0.0)
                        self.parent.ler_midi_memoria(reset_canais=False)
                        self.parent.current_playback_time = play_time
                        self.parent.seek_flag = True
                    except: pass
            except: pass
            finally:
                self.EndModal(wx.ID_CANCEL)
            return

        if code in [ord('1'), ord('2'), ord('3'), ord('4'), ord('5')] and not (ctrl or alt or shift):
            self.active_filter = code - ord('0')
            if hasattr(self, 'apply_filter'): self.apply_filter(falar=True)
            return

        if not self.display_events:
            event.Skip()
            return

        if code in [ord('Z'), ord('z')] and ctrl and not shift and not alt:
            if hasattr(self, 'undo_stack') and self.undo_stack:
                self.parent.midi_file = self.undo_stack.pop()
                self.parent.dirty = True
                self.load_events()
                try:
                    play_time = getattr(self.parent, 'current_playback_time', 0.0)
                    self.parent.ler_midi_memoria(reset_canais=False)
                    self.parent.current_playback_time = play_time
                    self.parent.seek_flag = True
                except: pass
                self.needs_audio_rebuild = False
                if self.display_events:
                    self.current_idx = min(self.current_idx, len(self.display_events) - 1)
                self.reconstruir_lista_visual()
                self.speak_and_preview()
                falar_status("Desfeito passo interno.", imediato=True)
            else:
                falar_status("Nada para desfazer no Event List.", imediato=True)
            return

        if code in [ord('Q'), ord('q')] and ctrl and not shift and not alt:
            try:
                from mhs_dialogs import QuantizeProDialog
                dlg = QuantizeProDialog(self)
                if dlg.ShowModal() == wx.ID_OK:
                    self.registrar_undo()
                    grid_ticks, forca = dlg.get_values()
                    t_start = getattr(self.parent, 'time_selection_start', None)
                    t_end = getattr(self.parent, 'time_selection_end', None)
                    if len(self.selected_indices) > 1:
                        evs_target = self.get_selected_events()
                    elif t_start is not None and t_end is not None:
                        t_min = min(t_start, t_end)
                        t_max = max(t_start, t_end)
                        evs_target = [e for e in self.display_events if t_min - 0.001 <= e.get('abs_sec', 0.0) <= t_max + 0.001]
                    else:
                        evs_target = self.display_events
                    count = 0
                    for ev in evs_target:
                        if ev['type'] == 'note':
                            start_tick = ev['start']
                            closest_grid = round(start_tick / grid_ticks) * grid_ticks
                            diff = closest_grid - start_tick
                            move_ticks = int(round(diff * (forca / 100.0)))
                            if move_ticks != 0:
                                dur = ev['end'] - ev['start']
                                ev['start'] += move_ticks
                                ev['end'] = ev['start'] + dur
                                count += 1
                    self.modified = True
                    self.needs_audio_rebuild = True
                    falar_status(f"{count} notas quantizadas.", imediato=True)
                    self.rebuild_final_midi()
                    self.load_events()
                    self.reconstruir_lista_visual()
                    self.speak_and_preview()
                if hasattr(self, 'matar_nota_preview'): self.matar_nota_preview()
                if hasattr(self, 'preview_is_playing'): self.preview_is_playing = False
                dlg.Destroy()
            except Exception as e:
                falar_status(f"Erro na quantização: {e}", imediato=True)
            wx.CallAfter(self.dummy_focus.SetFocus)
            return

        if code in [ord('E'), ord('e')] and ctrl and shift and not alt:
            if hasattr(self, 'abrir_selecao_eventos'): self.abrir_selecao_eventos()
            return

        if code in [ord('I'), ord('i')] and not (ctrl or alt or shift):
            if getattr(self, 'is_anchored', False):
                self.parent.time_selection_start = self.parent.current_playback_time
            else:
                ev = self.display_events[self.current_idx]
                self.parent.time_selection_start = ev.get('abs_sec', 0.0)
            if self.parent.time_selection_end is None or self.parent.time_selection_end <= self.parent.time_selection_start:
                self.parent.time_selection_end = self.parent.time_selection_start + 0.1
            txt = self.parent._obter_str_compasso(self.parent.time_selection_start)
            falar_status(f"Início marcado: {txt}", imediato=True)
            return

        if code in [ord('O'), ord('o')] and not (ctrl or alt or shift):
            if getattr(self, 'is_anchored', False):
                self.parent.time_selection_end = self.parent.current_playback_time
            else:
                ev = self.display_events[self.current_idx]
                self.parent.time_selection_end = ev.get('abs_sec', 0.0)
            if self.parent.time_selection_start is None or self.parent.time_selection_start >= self.parent.time_selection_end:
                self.parent.time_selection_start = 0.0
            txt = self.parent._obter_str_compasso(self.parent.time_selection_end)
            falar_status(f"Fim marcado: {txt}", imediato=True)
            return

        if code in [ord('A'), ord('a')] and ctrl and not shift and not alt:
            self.selected_indices = set(range(len(self.display_events)))
            self.atualizar_foco_visual()
            falar_status("Todos os eventos selecionados", imediato=True)
            return

        if code in [ord('A'), ord('a')] and shift and not ctrl and not alt:
            ev_ref = self.display_events[self.current_idx]
            ref_type = ev_ref['type']
            t_start = getattr(self.parent, 'time_selection_start', None)
            t_end = getattr(self.parent, 'time_selection_end', None)
            has_time_sel = (t_start is not None and t_end is not None)
            if has_time_sel:
                t_min = min(t_start, t_end) - 0.001
                t_max = max(t_start, t_end) + 0.001
            has_item_sel = len(self.selected_indices) > 1
            search_pool = self.selected_indices.copy() if has_item_sel else set(range(len(self.display_events)))
            
            self.selected_indices.clear()
            count = 0
            for i in search_pool:
                ev = self.display_events[i]
                if not has_item_sel and has_time_sel:
                    if not (t_min <= ev.get('abs_sec', 0.0) <= t_max): continue
                match = False
                if ev['type'] == ref_type:
                    if ref_type == 'note':
                        if ev['msg_on'].note == ev_ref['msg_on'].note: match = True
                    elif ref_type == 'control_change':
                        if ev['msg'].control == ev_ref['msg'].control: match = True
                    else: match = True 
                if match:
                    self.selected_indices.add(i)
                    count += 1
            self.atualizar_foco_visual()
            if has_item_sel: falar_status(f"{count} notas iguais na seleção.", imediato=True)
            elif has_time_sel: falar_status(f"{count} notas iguais no trecho.", imediato=True)
            else: falar_status(f"{count} notas iguais na pista.", imediato=True)
            return

        if code in [wx.WXK_SPACE, 32] and shift and not ctrl and not alt:
            if not getattr(self, 'non_contiguous_mode', False):
                self.non_contiguous_mode = True
                self.selected_indices.add(self.current_idx)
                falar_status("Modo seleção não contínua ativada. Selecionado.", imediato=True)
            else:
                if self.current_idx in self.selected_indices:
                    self.selected_indices.remove(self.current_idx)
                    falar_status("Removido", imediato=True)
                else:
                    self.selected_indices.add(self.current_idx)
                    falar_status("Selecionado", imediato=True)
            self.atualizar_foco_visual()
            return

        if code in [ord('S'), ord('s')] and not (ctrl or alt or shift):
            try:
                from mhs_dialogs import SubstituirNotasDialog
                old_note = 60
                old_vel = 100
                if self.display_events:
                    ev = self.display_events[self.current_idx]
                    if ev['type'] == 'note':
                        old_note = ev['msg_on'].note
                        old_vel = ev['msg_on'].velocity
                dlg = SubstituirNotasDialog(self, old_note, old_vel)
                if dlg.ShowModal() == wx.ID_OK:
                    self.registrar_undo()
                    new_note, adj_vel, adj_dur = dlg.get_values()
                    tpb = max(1, getattr(self.parent.midi_file, 'ticks_per_beat', 480))
                    t_start = getattr(self.parent, 'time_selection_start', None)
                    t_end = getattr(self.parent, 'time_selection_end', None)
                    if len(self.selected_indices) > 1:
                        evs_target = self.get_selected_events()
                    elif t_start is not None and t_end is not None:
                        t_min = min(t_start, t_end)
                        t_max = max(t_start, t_end)
                        evs_target = [e for e in self.display_events if t_min - 0.001 <= e.get('abs_sec', 0.0) <= t_max + 0.001]
                    else:
                        evs_target = self.display_events
                    count = 0
                    for ev in evs_target:
                        if ev['type'] == 'note' and ev['msg_on'].note == old_note:
                            msg_on = ev['msg_on']
                            novo_v = max(1, min(127, msg_on.velocity + adj_vel))
                            local_tempo = self.get_tempo_at_tick(ev['start'])
                            ticks_per_ms = tpb / (local_tempo / 1000.0)
                            dur_adj_ticks = int(round(adj_dur * ticks_per_ms))
                            nova_dur = max(1, (ev['end'] - ev['start']) + dur_adj_ticks)
                            ev['msg_on'] = msg_on.copy(note=new_note, velocity=novo_v)
                            if ev['msg_off']: ev['msg_off'] = ev['msg_off'].copy(note=new_note)
                            ev['end'] = ev['start'] + nova_dur
                            count += 1
                    self.modified = True
                    self.needs_audio_rebuild = True
                    falar_status(f"{count} notas alteradas.", imediato=True)
                    self.rebuild_final_midi()
                    self.load_events()
                    self.reconstruir_lista_visual()
                    self.speak_and_preview()
                dlg.Destroy()
            except: pass
            wx.CallAfter(self.dummy_focus.SetFocus)
            return

        if code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER] and not (ctrl or alt or shift):
            ev = self.display_events[self.current_idx]
            msg = ev.get('msg_on') if ev['type'] == 'note' else ev['msg']
            ch_ev = getattr(msg, 'channel', 0)
            
            if ev['type'] == 'note':
                dur_ticks = ev['end'] - ev['start']
                b, p = ev.get('bank', 0), ev.get('patch', 0)
                dlg = EdicaoNotaDialog(self, msg.note, msg.velocity, dur_ticks, b, p, is_insert=False)
                if dlg.ShowModal() == wx.ID_OK:
                    self.registrar_undo()
                    n, v, d = dlg.get_values()
                    ev['msg_on'] = ev['msg_on'].copy(note=n, velocity=v)
                    if ev['msg_off']: ev['msg_off'] = ev['msg_off'].copy(note=n)
                    ev['end'] = ev['start'] + d
                    self.modified = True
                    self.needs_audio_rebuild = True
                    self.list_box.RefreshItem(self.current_idx)
                    self.atualizar_foco_visual()
                    self.speak_and_preview()
                dlg.Destroy()
                
            elif ev['type'] == 'control_change':
                dlg = EdicaoCCDialog(self, msg.control, msg.value, tick_val=ev['time'], is_insert=False)
                if dlg.ShowModal() == wx.ID_OK:
                    self.registrar_undo()
                    cc_new, val_new, t_new = dlg.get_values()
                    ev['msg'] = ev['msg'].copy(control=cc_new, value=val_new)
                    ev['time'] = t_new
                    self.modified = True
                    self.needs_audio_rebuild = True
                    self.rebuild_final_midi()
                    self.load_events()
                    self.reconstruir_lista_visual()
                    self.speak_and_preview()
                dlg.Destroy()
                
            elif ev['type'] == 'program_change':
                if hasattr(self, 'get_current_bank_patch_at_time'): b, p_old = self.get_current_bank_patch_at_time(ev['time'])
                else: b = 0
                dlg = EdicaoPCDialog(self, b, msg.program, tick_val=ev['time'], is_insert=False)
                if dlg.ShowModal() == wx.ID_OK:
                    self.registrar_undo()
                    b_new, p_new, t_new = dlg.get_values()
                    ev['msg'] = ev['msg'].copy(program=p_new)
                    ev['time'] = t_new
                    
                    for i in range(self.current_idx - 1, max(-1, self.current_idx - 15), -1):
                        prev_ev = self.display_events[i]
                        if prev_ev['type'] == 'control_change' and getattr(prev_ev['msg'], 'channel', None) == ch_ev:
                            if prev_ev['msg'].control == 0: 
                                prev_ev['msg'] = prev_ev['msg'].copy(value=b_new // 128)
                                prev_ev['time'] = t_new
                            elif prev_ev['msg'].control == 32: 
                                prev_ev['msg'] = prev_ev['msg'].copy(value=b_new % 128)
                                prev_ev['time'] = t_new
                    try:
                        main_win = getattr(self, 'parent', self.GetParent())
                        if ch_ev is not None and hasattr(main_win, 'canais'):
                            main_win.canais[ch_ev]["Patch"] = p_new
                            main_win.canais[ch_ev]["Bank"] = b_new
                    except: pass
                    
                    self.modified = True
                    self.needs_audio_rebuild = True
                    self.rebuild_final_midi()
                    self.load_events()
                    self.reconstruir_lista_visual()
                    self.speak_and_preview()
                dlg.Destroy()
            wx.CallAfter(self.dummy_focus.SetFocus)
            return

        if code in [wx.WXK_UP, wx.WXK_DOWN, wx.WXK_PAGEUP, wx.WXK_PAGEDOWN] and not (ctrl or alt):
            if shift:
                if not getattr(self, 'non_contiguous_mode', False): self.selected_indices.add(self.current_idx)
            else:
                self.selected_indices.clear()
                self.non_contiguous_mode = False

            if self.is_anchored:
                if code == wx.WXK_DOWN: self.current_idx = getattr(self, 'last_playback_idx', self.current_idx)
                elif code == wx.WXK_UP: self.current_idx = max(0, getattr(self, 'last_playback_idx', self.current_idx) - 1)
                elif code == wx.WXK_PAGEUP: self.current_idx = max(0, getattr(self, 'last_playback_idx', self.current_idx) - 10)
                elif code == wx.WXK_PAGEDOWN: self.current_idx = min(len(self.display_events) - 1, getattr(self, 'last_playback_idx', self.current_idx) + 10)
                self.is_anchored = False
            else:
                if code == wx.WXK_UP: self.current_idx = max(0, self.current_idx - 1)
                elif code == wx.WXK_DOWN: self.current_idx = min(len(self.display_events) - 1, self.current_idx + 1)
                elif code == wx.WXK_PAGEUP: self.current_idx = max(0, self.current_idx - 10)
                elif code == wx.WXK_PAGEDOWN: self.current_idx = min(len(self.display_events) - 1, self.current_idx + 10)

            if shift:
                if not getattr(self, 'non_contiguous_mode', False): self.selected_indices.add(self.current_idx)

            self.atualizar_foco_visual()
            self.speak_and_preview()
            if shift:
                if not getattr(self, 'non_contiguous_mode', False): 
                    falar_status("Selecionado", imediato=False)
            return  

        if code == wx.WXK_HOME and not alt:
            if shift and not ctrl:
                for i in range(self.current_idx + 1):
                    self.selected_indices.add(i)
                self.current_idx = 0
                self.atualizar_foco_visual()
                self.speak_and_preview()
                falar_status("Selecionado até o início", imediato=False)
                return
                
            if not shift: 
                self.selected_indices.clear()
                self.non_contiguous_mode = False
            
            if ctrl:
                # Ctrl+Home: primeiro evento de NOTA da lista (se a lista
                # filtrada não tiver nenhuma nota, cai no primeiro evento).
                self.current_idx = 0
                for i_ev, ev in enumerate(self.display_events):
                    if ev.get('type') == 'note':
                        self.current_idx = i_ev
                        break
                self.atualizar_foco_visual()
                self.speak_and_preview()
                falar_status("Primeiro evento de nota", imediato=False)
            else:
                t_start = getattr(self.parent, 'time_selection_start', None)
                if t_start is not None and self.display_events:
                    for i, ev in enumerate(self.display_events):
                        if ev.get('abs_sec', 0.0) >= t_start - 0.001:
                            self.current_idx = i
                            break
                    self.atualizar_foco_visual()
                    self.speak_and_preview()
                    falar_status("Ir para Marca de Início", imediato=False)
                else:
                    self.current_idx = 0
                    self.atualizar_foco_visual()
                    self.speak_and_preview()
            return

        if code == wx.WXK_END and not alt:
            if shift and not ctrl:
                if self.display_events:
                    for i in range(self.current_idx, len(self.display_events)):
                        self.selected_indices.add(i)
                    self.current_idx = len(self.display_events) - 1
                    self.atualizar_foco_visual()
                    self.speak_and_preview()
                    falar_status("Selecionado até o fim", imediato=False)
                return
                
            if not shift: 
                self.selected_indices.clear()
                self.non_contiguous_mode = False
            
            if ctrl:
                # Ctrl+End: último evento da lista (de qualquer tipo).
                if self.display_events: self.current_idx = len(self.display_events) - 1
                self.atualizar_foco_visual()
                self.speak_and_preview()
                falar_status("Último evento da lista", imediato=False)
            else:
                t_end = getattr(self.parent, 'time_selection_end', None)
                if t_end is not None and self.display_events:
                    best_idx = len(self.display_events) - 1
                    for i, ev in enumerate(self.display_events):
                        if ev.get('abs_sec', 0.0) > t_end + 0.001:
                            best_idx = max(0, i - 1)
                            break
                    self.current_idx = best_idx
                    self.atualizar_foco_visual()
                    self.speak_and_preview()
                    falar_status("Ir para Marca de Fim", imediato=False)
                else:
                    if self.display_events: self.current_idx = len(self.display_events) - 1
                    self.atualizar_foco_visual()
                    self.speak_and_preview()
            return

        if code in [wx.WXK_LEFT, wx.WXK_RIGHT]:
            evs = self.get_selected_events()
            sign = -1 if code == wx.WXK_LEFT else 1
            
            ev_foco = self.display_events[self.current_idx]
            tipo_foco = ev_foco['type']
            mudanca_str = ""
            
            for ev in evs:
                if ev['type'] != tipo_foco: continue 
                if ev['type'] == 'note':
                    if not ctrl and not alt and not shift:
                        nova_nota = max(0, min(127, ev['msg_on'].note + sign))
                        ev['msg_on'] = ev['msg_on'].copy(note=nova_nota)
                        if ev['msg_off']: ev['msg_off'] = ev['msg_off'].copy(note=nova_nota)
                        if ev == ev_foco:
                            nome = self.get_nome_nota_ou_peca(nova_nota, ev.get('bank',0), ev.get('patch',0))
                            mudanca_str = f"Nota {nome}"
                    elif ctrl and not alt and not shift:
                        nova_nota = max(0, min(127, ev['msg_on'].note + (sign * 12)))
                        ev['msg_on'] = ev['msg_on'].copy(note=nova_nota)
                        if ev['msg_off']: ev['msg_off'] = ev['msg_off'].copy(note=nova_nota)
                        if ev == ev_foco:
                            nome = self.get_nome_nota_ou_peca(nova_nota, ev.get('bank',0), ev.get('patch',0))
                            mudanca_str = f"Oitava {nome}"
                    elif shift and not ctrl and not alt:
                        novo_vel = max(1, min(127, ev['msg_on'].velocity + sign))
                        ev['msg_on'] = ev['msg_on'].copy(velocity=novo_vel)
                        if ev == ev_foco: mudanca_str = f"Velocity {novo_vel}"
                    elif ctrl and shift and not alt:
                        novo_vel = max(1, min(127, ev['msg_on'].velocity + (sign * 10)))
                        ev['msg_on'] = ev['msg_on'].copy(velocity=novo_vel)
                        if ev == ev_foco: mudanca_str = f"Velocity {novo_vel}"
                    elif alt and not ctrl and not shift:
                        dur = max(1, (ev['end'] - ev['start']) + sign)
                        ev['end'] = ev['start'] + dur
                        if ev == ev_foco: mudanca_str = f"Duração {dur} ticks"
                    elif ctrl and alt and not shift:
                        dur = max(1, (ev['end'] - ev['start']) + (sign * 5))
                        ev['end'] = ev['start'] + dur
                        if ev == ev_foco: mudanca_str = f"Duração {dur} ticks"
                    elif shift and alt and not ctrl:
                        dur = ev['end'] - ev['start']
                        ev['start'] = max(0, ev['start'] + sign)
                        ev['end'] = ev['start'] + dur
                        if hasattr(self, 'tick_to_sec'): ev['abs_sec'] = self.tick_to_sec(ev['start'])
                        if ev == ev_foco: mudanca_str = f"Atrasado {-sign} tick" if sign < 0 else f"Adiantado {sign} tick"
                    elif ctrl and shift and alt:
                        dur = ev['end'] - ev['start']
                        ev['start'] = max(0, ev['start'] + (sign * 5))
                        ev['end'] = ev['start'] + dur
                        if hasattr(self, 'tick_to_sec'): ev['abs_sec'] = self.tick_to_sec(ev['start'])
                        if ev == ev_foco: mudanca_str = f"Atrasado {-sign * 5} ticks" if sign < 0 else f"Adiantado {sign * 5} ticks"
                elif ev['type'] == 'control_change':
                    if not ctrl and not alt and not shift:
                        novo_cc = max(0, min(127, ev['msg'].control + sign))
                        ev['msg'] = ev['msg'].copy(control=novo_cc)
                        try:
                            from mhs_event_list import CC_DICT
                            nome_cc = CC_DICT.get(novo_cc, str(novo_cc))
                        except:
                            nome_cc = str(novo_cc)
                        if ev == ev_foco: mudanca_str = f"CC {nome_cc}"
                    elif ctrl and not alt and not shift:
                        novo_val = max(0, min(127, ev['msg'].value + sign))
                        ev['msg'] = ev['msg'].copy(value=novo_val)
                        if ev == ev_foco: mudanca_str = f"Valor {novo_val}"
                elif ev['type'] == 'program_change':
                    if not ctrl and not alt and not shift:
                        ev['bank'] = max(0, min(16384, ev.get('bank', 0) + sign))
                        if ev == ev_foco: mudanca_str = f"Banco {ev['bank']}"
                    elif ctrl and not alt and not shift:
                        novo_p = max(0, min(127, ev['msg'].program + sign))
                        ev['msg'] = ev['msg'].copy(program=novo_p)
                        if ev == ev_foco: mudanca_str = f"Patch {novo_p}"
                elif ev['type'] == 'pitchwheel':
                    if not ctrl and not alt and not shift:
                        novo_val = max(-8192, min(8191, ev['msg'].pitch + (sign * 100)))
                        ev['msg'] = ev['msg'].copy(pitch=novo_val)
                        if ev == ev_foco: mudanca_str = f"Pitch {novo_val}"

            if mudanca_str:
                self.modified = True
                self.needs_audio_rebuild = True
                if len(self.selected_indices) > 50:
                    self.list_box.Refresh() 
                else:
                    self.list_box.Freeze()
                    for idx in self.selected_indices:
                        if 0 <= idx < self.list_box.GetItemCount(): self.list_box.RefreshItem(idx)
                    if 0 <= self.current_idx < self.list_box.GetItemCount(): self.list_box.RefreshItem(self.current_idx)
                    self.list_box.Thaw()
                    
                self.atualizar_foco_visual()
                falar_status(mudanca_str, imediato=True)
                if tipo_foco == 'note':
                    if getattr(self.parent, 'output', None):
                        if hasattr(self, 'matar_nota_preview'): self.matar_nota_preview()
                        msg_on = ev_foco['msg_on']
                        msg_play = msg_on.copy(channel=msg_on.channel, note=msg_on.note, velocity=msg_on.velocity)
                        self.preview_note = msg_play
                        try: self.parent.output.send(msg_play)
                        except: pass
                        import threading
                        if getattr(self, 'preview_timer', None): self.preview_timer.cancel()
                        dur_sec = 0.3
                        if hasattr(self, 'tick_to_sec'):
                            try: dur_sec = self.tick_to_sec(ev_foco['end']) - self.tick_to_sec(ev_foco['start'])
                            except: pass
                        dur_preview = min(0.4, max(0.05, dur_sec))
                        self.preview_timer = threading.Timer(dur_preview, getattr(self, 'matar_nota_preview', lambda: None))
                        self.preview_timer.start()
            return

        if code in [wx.WXK_DELETE, wx.WXK_BACK, wx.WXK_NUMPAD_DELETE]:
            indice_salvo = self.current_idx
            evs = self.get_selected_events()
            self.registrar_undo()
            for ev in evs:
                if ev in self.tracks_abs[ev['track']]: self.tracks_abs[ev['track']].remove(ev)
            self.selected_indices.clear()
            self.modified = True
            self.needs_audio_rebuild = True
            falar_status("Apagado.", imediato=True)
            self.rebuild_final_midi()
            self.load_events()
            if not self.display_events:
                self.current_idx = 0
                self.reconstruir_lista_visual()
                return
            self.current_idx = max(0, min(indice_salvo, len(self.display_events) - 1))
            self.reconstruir_lista_visual()
            self.speak_and_preview()
            return

        if code in [ord('D'), ord('d')] and not (ctrl or alt or shift):
            if hasattr(self, 'duplicar_evento'): self.duplicar_evento(flam=False)
            return
        if code in [ord('F'), ord('f')] and not (ctrl or alt or shift):
            if hasattr(self, 'duplicar_evento'): self.duplicar_evento(flam=True)
            return
        if code in [ord('T'), ord('t')] and not (ctrl or alt or shift):
            if hasattr(self, 'achatar_notas_um_tick'): self.achatar_notas_um_tick()
            return
        if code in [ord('C'), ord('c')] and ctrl and not shift and not alt:
            if hasattr(self, 'copiar_evento'): self.copiar_evento()
            return
        if code in [ord('X'), ord('x')] and ctrl and not shift and not alt:
            if hasattr(self, 'recortar_evento'): self.recortar_evento()
            return

        event.Skip()
    def play_quantize_preview(self, grid_ticks, forca):
        self.preview_is_playing = False
        import time
        time.sleep(0.02) 
        
        self.preview_is_playing = True
        import threading
        t = threading.Thread(target=self._tocar_preview_quantize, args=(grid_ticks, forca))
        t.daemon = True
        t.start()
        try:
            from mhs_utils import falar_status
            falar_status("Tocando preview quantizado...", imediato=True)
        except:
            pass
    def _tocar_preview_quantize(self, grid_ticks, forca):
        import time
        import mido
        
        t_start = getattr(self.parent, 'time_selection_start', None)
        t_end = getattr(self.parent, 'time_selection_end', None)
        
        if len(self.selected_indices) > 1:
            evs_target = self.get_selected_events()
        elif t_start is not None and t_end is not None:
            t_min = min(t_start, t_end)
            t_max = max(t_start, t_end)
            evs_target = [e for e in self.display_events if t_min - 0.001 <= e.get('abs_sec', 0.0) <= t_max + 0.001]
        else:
            evs_target = self.display_events
            
        if not evs_target:
            self.preview_is_playing = False
            return
            
        cursor_tick = 0
        if hasattr(self, 'display_events') and self.display_events:
            ev_cursor = self.display_events[self.current_idx]
            cursor_tick = ev_cursor.get('start', ev_cursor.get('time', 0))
            
        preview_events = []
        for ev in evs_target:
            if ev['type'] == 'note':
                st = ev['start']
                if st >= cursor_tick:
                    closest = round(st / grid_ticks) * grid_ticks
                    diff = closest - st
                    move = int(round(diff * (forca / 100.0)))
                    new_start = max(0, st + move)
                    dur = ev['end'] - ev['start']
                    
                    # Usa a função nativa do Event List para pegar o tempo perfeito!
                    sec_on = self.tick_to_sec(new_start)
                    sec_off = self.tick_to_sec(new_start + dur)
                    
                    preview_events.append({'sec': sec_on, 'type': 'on', 'msg': ev['msg_on']})
                    preview_events.append({'sec': sec_off, 'type': 'off', 'msg': ev['msg_on']})
                
        if not preview_events:
            self.preview_is_playing = False
            return
            
        preview_events.sort(key=lambda x: x['sec'])
        
        start_real_time = time.time()
        first_event_sec = preview_events[0]['sec']
        
        for p_ev in preview_events:
            if not getattr(self, 'preview_is_playing', False):
                break
                
            # Calcula a hora exata de tocar essa nota baseada no relógio real
            target_real_time = start_real_time + (p_ev['sec'] - first_event_sec)
            
            # Sleep fragmentado: dorme piscando os olhos para ouvir o comando de STOP na hora!
            while True:
                if not getattr(self, 'preview_is_playing', False):
                    break
                now = time.time()
                wait_time = target_real_time - now
                if wait_time <= 0.001:
                    break
                time.sleep(min(0.01, wait_time))
                
            if not getattr(self, 'preview_is_playing', False):
                break
                
            try:
                if p_ev['type'] == 'on':
                    self.parent.output.send(p_ev['msg'])
                else:
                    msg_off = mido.Message('note_off', channel=p_ev['msg'].channel, note=p_ev['msg'].note, velocity=0)
                    self.parent.output.send(msg_off)
            except:
                pass
                
        self.preview_is_playing = False
        if hasattr(self.parent, 'all_notes_off'):
            self.parent.all_notes_off()
    def abrir_selecao_eventos(self):
        try:
            import wx
            dlg = SelecaoAvancadaDialog(self)
            if dlg.ShowModal() == wx.ID_OK:
                count = dlg.aplicar_selecao()
                self.atualizar_foco_visual()
                from mhs_utils import falar_status
                if count > 0:
                    falar_status(f"Filtro aplicado. {count} eventos selecionados.", imediato=True)
                else:
                    falar_status("Nenhum evento corresponde aos critérios.", imediato=True)
            dlg.Destroy()
        except Exception as e:
            from mhs_utils import falar_status
            falar_status(f"Erro ao abrir seleção: {e}", imediato=True)
            
        import wx
        wx.CallAfter(self.dummy_focus.SetFocus)
    def matar_nota_preview(self):
        # 1. Cancela o timer com segurança
        if getattr(self, 'preview_timer', None):
            self.preview_timer.cancel()
            self.preview_timer = None
            
        # 2. Desliga a nota presa fisicamente
        if getattr(self, 'preview_note', None) and getattr(self.parent, 'output', None):
            try:
                import mido
                msg_off = mido.Message('note_off', channel=self.preview_note.channel, note=self.preview_note.note, velocity=0)
                self.parent.output.send(msg_off)
            except Exception:
                pass
            self.preview_note = None

    def tocar_nota_exata(self, msg, start_tick, end_tick):
        if msg.type == 'note_on' and msg.velocity > 0 and getattr(self.parent, 'output', None):
            # Mata qualquer nota que esteja tocando antes de disparar a nova (Evita o engasgo)
            self.matar_nota_preview()
            
            self.preview_note = msg
            try:
                self.parent.output.send(msg)
            except:
                pass
            
            # Calcula a duração original da nota
            try:
                dur_sec = self.tick_to_sec(end_tick) - self.tick_to_sec(start_tick)
            except:
                dur_sec = 0.3
                
            # Trava o preview num máximo de 0.4s para evitar que notas longas embolem a navegação
            dur_preview = min(0.4, max(0.05, dur_sec))
            
            import threading
            self.preview_timer = threading.Timer(dur_preview, self.matar_nota_preview)
            self.preview_timer.start()
class EventListQuantizeDialog(wx.Dialog):
    def __init__(self, parent_list):
        super().__init__(parent_list, title="Quantizar (Event List)", size=(400, 250))
        self.parent_list = parent_list
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.grids = [
            ("Semínima (1/4)", 480),
            ("Semínima Tercina (1/4T)", 320),
            ("Semínima Pontuada (1/4D)", 720),
            ("Colcheia (1/8)", 240),
            ("Colcheia Tercina (1/8T)", 160),
            ("Colcheia Pontuada (1/8D)", 360),
            ("Semicolcheia (1/16)", 120),
            ("Semicolcheia Tercina (1/16T)", 80),
            ("Semicolcheia Pontuada (1/16D)", 180),
            ("Fusa (1/32)", 60),
            ("Fusa Tercina (1/32T)", 40),
            ("Fusa Pontuada (1/32D)", 90),
            ("Semifusa (1/64)", 30),
            ("Semifusa Tercina (1/64T)", 20),
            ("Semifusa Pontuada (1/64D)", 45)
        ]
        
        lbl_grid = wx.StaticText(self, label="Grade de Quantização:")
        sizer.Add(lbl_grid, 0, wx.ALL, 5)
        self.cb_grid = wx.ComboBox(self, value=self.grids[6][0], choices=[g[0] for g in self.grids], style=wx.CB_READONLY)
        self.cb_grid.SetSelection(6)
        sizer.Add(self.cb_grid, 0, wx.EXPAND | wx.ALL, 5)
        
        lbl_forca = wx.StaticText(self, label="Força (%):")
        sizer.Add(lbl_forca, 0, wx.ALL, 5)
        self.sp_forca = wx.SpinCtrl(self, value="100", min=1, max=100)
        sizer.Add(self.sp_forca, 0, wx.EXPAND | wx.ALL, 5)
        
        lbl_preview = wx.StaticText(self, label="Pressione ESPAÇO para Ouvir/Parar o Preview")
        sizer.Add(lbl_preview, 0, wx.ALL | wx.ALIGN_CENTER, 10)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)
        
        self.cb_grid.Bind(wx.EVT_COMBOBOX, self.on_change)
        self.sp_forca.Bind(wx.EVT_SPINCTRL, self.on_change)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        
        wx.CallLater(100, self.cb_grid.SetFocus)
        
    def on_change(self, event):
        obj = event.GetEventObject()
        if obj == self.cb_grid:
            falar_status(self.cb_grid.GetValue(), imediato=True)
        event.Skip()
        
    def get_values(self):
        base_grid = self.grids[self.cb_grid.GetSelection()][1]
        tpb = 480
        try:
            tpb = max(1, getattr(self.parent_list.parent.midi_file, 'ticks_per_beat', 480))
        except:
            pass
        grid_ticks = int(round(base_grid * (tpb / 480.0)))
        return grid_ticks, self.sp_forca.GetValue()

    def on_key(self, event):
        code = event.GetKeyCode()
        if code in [wx.WXK_SPACE, 32]:
            if getattr(self.parent_list, 'preview_is_playing', False):
                self.parent_list.preview_is_playing = False
                if hasattr(self.parent_list.parent, 'all_notes_off'):
                    self.parent_list.parent.all_notes_off()
                falar_status("Preview parado.", imediato=True)
            else:
                grid, forca = self.get_values()
                if hasattr(self.parent_list, 'play_quantize_preview'):
                    self.parent_list.play_quantize_preview(grid, forca)
            return
            
        if code == wx.WXK_ESCAPE:
            if hasattr(self.parent_list, 'matar_nota_preview'):
                self.parent_list.matar_nota_preview()
            self.parent_list.preview_is_playing = False
            if hasattr(self.parent_list.parent, 'all_notes_off'):
                self.parent_list.parent.all_notes_off()
            self.EndModal(wx.ID_CANCEL)
            return
            
        event.Skip()

class SelecaoAvancadaDialog(wx.Dialog):
    def __init__(self, parent_list):
        super().__init__(parent_list, title="Seleção Avançada de Eventos", size=(450, 550))
        self.parent_list = parent_list
        
        self.b_ref = 0
        self.p_ref = 0
        if self.parent_list.display_events:
            if 0 <= self.parent_list.current_idx < len(self.parent_list.display_events):
                ev_ref = self.parent_list.display_events[self.parent_list.current_idx]
                self.b_ref = ev_ref.get('bank', 0)
                self.p_ref = ev_ref.get('patch', 0)
        
        self.notas_lista = []
        for i in range(128):
            nome = self.parent_list.get_nome_nota_ou_peca(i, self.b_ref, self.p_ref)
            self.notas_lista.append(f"{i} - {nome}")
            
        self.cc_lista = []
        for i in range(128):
            nome_cc = "Control Change"
            try:
                from mhs_event_list import CC_DICT
                nome_cc = CC_DICT.get(i, "Control Change")
            except:
                pass
            self.cc_lista.append(f"{i} - {nome_cc}")
            
        self.padrao_lista = [str(i) for i in range(128)]
            
        sz = wx.BoxSizer(wx.VERTICAL)
        
        lbl_tipo = wx.StaticText(self, label="1. Tipo de Evento:")
        sz.Add(lbl_tipo, 0, wx.ALL, 5)
        self.cb_tipo = wx.ComboBox(self, choices=["Notas", "Control Change", "Program Change", "Pitch Wheel", "Todos"], style=wx.CB_READONLY)
        self.cb_tipo.SetSelection(0)
        sz.Add(self.cb_tipo, 0, wx.EXPAND | wx.ALL, 5)
        
        self.chk_num = wx.CheckBox(self, label="2. Filtrar por Número (Nota ou CC)")
        sz.Add(self.chk_num, 0, wx.ALL, 5)
        
        lbl_nota_min = wx.StaticText(self, label="Número Mínimo:")
        sz.Add(lbl_nota_min, 0, wx.LEFT | wx.RIGHT, 15)
        self.cb_val_min = wx.ComboBox(self, choices=self.notas_lista, style=wx.CB_READONLY)
        self.cb_val_min.SetSelection(0)
        sz.Add(self.cb_val_min, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 15)
        
        lbl_nota_max = wx.StaticText(self, label="Número Máximo:")
        sz.Add(lbl_nota_max, 0, wx.LEFT | wx.RIGHT, 15)
        self.cb_val_max = wx.ComboBox(self, choices=self.notas_lista, style=wx.CB_READONLY)
        self.cb_val_max.SetSelection(127)
        sz.Add(self.cb_val_max, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 15)
        
        self.chk_val = wx.CheckBox(self, label="3. Filtrar por Força (Velocity ou Valor)")
        sz.Add(self.chk_val, 0, wx.ALL, 5)
        
        lbl_vel_min = wx.StaticText(self, label="Valor Mínimo:")
        sz.Add(lbl_vel_min, 0, wx.LEFT | wx.RIGHT, 15)
        self.sp_vel_min = wx.SpinCtrl(self, value="0", min=-8192, max=8191)
        sz.Add(self.sp_vel_min, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 15)
        
        lbl_vel_max = wx.StaticText(self, label="Valor Máximo:")
        sz.Add(lbl_vel_max, 0, wx.LEFT | wx.RIGHT, 15)
        self.sp_vel_max = wx.SpinCtrl(self, value="127", min=-8192, max=8191)
        sz.Add(self.sp_vel_max, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 15)
        
        lbl_escopo = wx.StaticText(self, label="4. Escopo de Tempo:")
        sz.Add(lbl_escopo, 0, wx.ALL, 5)
        self.cb_escopo = wx.ComboBox(self, choices=["Pista Toda", "Apenas no Trecho Selecionado (I/O)"], style=wx.CB_READONLY)
        self.cb_escopo.SetSelection(0)
        sz.Add(self.cb_escopo, 0, wx.EXPAND | wx.ALL, 5)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sz.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        
        self.SetSizer(sz)
        
        self.cb_tipo.Bind(wx.EVT_COMBOBOX, self.on_tipo_change)
        self.chk_num.Bind(wx.EVT_CHECKBOX, self.on_check_falar)
        self.chk_val.Bind(wx.EVT_CHECKBOX, self.on_check_falar)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        
        self.cb_val_min.Bind(wx.EVT_COMBOBOX, self.on_preview_min)
        self.cb_val_max.Bind(wx.EVT_COMBOBOX, self.on_preview_max)
        self.cb_val_min.Bind(wx.EVT_TEXT, self.on_preview_min)
        self.cb_val_max.Bind(wx.EVT_TEXT, self.on_preview_max)
        
        self.sp_vel_min.Bind(wx.EVT_SPINCTRL, self.on_preview_min)
        self.sp_vel_max.Bind(wx.EVT_SPINCTRL, self.on_preview_max)
        self.sp_vel_min.Bind(wx.EVT_TEXT, self.on_preview_min)
        self.sp_vel_max.Bind(wx.EVT_TEXT, self.on_preview_max)
        
        # O wx já foi importado no início do arquivo mhs_dialogs.py, então basta chamar direto!
        wx.CallLater(100, self.cb_tipo.SetFocus)

    def obter_nota_por_texto(self, combo):
        txt = combo.GetValue()
        if txt and " - " in txt:
            try:
                return int(txt.split(" - ")[0])
            except:
                pass
        sel = combo.GetSelection()
        if sel != wx.NOT_FOUND:
            return sel
        return 0

    def _get_nota_preview(self, is_min):
        if self.chk_num.GetValue():
            # Se o filtro por nota tá ativo, usa a nota selecionada na caixa correspondente
            if is_min:
                return self.obter_nota_por_texto(self.cb_val_min)
            else:
                return self.obter_nota_por_texto(self.cb_val_max)
        else:
            # Se não tá filtrando nota, toca a nota em que o cursor está focado no Event List!
            if self.parent_list.display_events and 0 <= self.parent_list.current_idx < len(self.parent_list.display_events):
                ev = self.parent_list.display_events[self.parent_list.current_idx]
                if ev['type'] == 'note':
                    return ev['msg_on'].note
            return 60 # C4 padrão caso não tenha nota focada

    def on_preview_min(self, event):
        event.Skip()
        nota = self._get_nota_preview(is_min=True)
        vel = self.sp_vel_min.GetValue()
        self.tocar_preview(nota, vel)

    def on_preview_max(self, event):
        event.Skip()
        nota = self._get_nota_preview(is_min=False)
        vel = self.sp_vel_max.GetValue()
        self.tocar_preview(nota, vel)
        
    def tocar_preview(self, nota, vel):
        if self.cb_tipo.GetSelection() != 0:
            return
            
        nota = max(0, min(127, nota))
        # Removemos a trava do 60! MegaVoices precisam de valores exatos para testar as camadas!
        # Usamos 1 como mínimo pois velocidade 0 no protocolo MIDI silencia a nota (Note Off)
        vel_preview = max(1, min(127, vel))
        
        if getattr(self.parent_list.parent, 'output', None):
            import mido
            import threading
            self.parent_list.matar_nota_preview()
            msg = mido.Message('note_on', channel=self.parent_list.canal_idx, note=nota, velocity=vel_preview)
            self.parent_list.preview_note = msg
            try:
                self.parent_list.parent.output.send(msg)
                self.parent_list.preview_timer = threading.Timer(0.3, self.parent_list.matar_nota_preview)
                self.parent_list.preview_timer.start()
            except:
                pass

    def on_check_falar(self, event):
        obj = event.GetEventObject()
        estado = "Marcado" if obj.GetValue() else "Desmarcado"
        from mhs_utils import falar_status
        falar_status(f"{estado}", imediato=True)
        event.Skip()
        
    def on_tipo_change(self, event):
        sel = self.cb_tipo.GetSelection()
        if sel == 0:
            self.cb_val_min.Set(self.notas_lista)
            self.cb_val_max.Set(self.notas_lista)
        elif sel == 1:
            self.cb_val_min.Set(self.cc_lista)
            self.cb_val_max.Set(self.cc_lista)
        else:
            self.cb_val_min.Set(self.padrao_lista)
            self.cb_val_max.Set(self.padrao_lista)
            
        self.cb_val_min.SetSelection(0)
        self.cb_val_max.SetSelection(127)
        
        from mhs_utils import falar_status
        falar_status(self.cb_tipo.GetValue(), imediato=True)
        event.Skip()
        
    def on_key(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
        else:
            event.Skip()
            
    def aplicar_selecao(self):
        tipo_sel = self.cb_tipo.GetSelection()
        usar_num = self.chk_num.GetValue()
        usar_val = self.chk_val.GetValue()
        
        n_min = self.cb_val_min.GetSelection()
        n_max = self.cb_val_max.GetSelection()
        if n_min > n_max:
            n_min, n_max = n_max, n_min
            
        v_min = self.sp_vel_min.GetValue()
        v_max = self.sp_vel_max.GetValue()
        if v_min > v_max:
            v_min, v_max = v_max, v_min
            
        escopo = self.cb_escopo.GetSelection()
        
        t_start = getattr(self.parent_list.parent, 'time_selection_start', None)
        t_end = getattr(self.parent_list.parent, 'time_selection_end', None)
        
        # Correção adicional: Respeitar a opção "Pista Toda" e não prender no trecho antigo
        if escopo == 1: 
            t_min = min(t_start, t_end) - 0.001 if (t_start is not None and t_end is not None) else 0.0
            t_max = max(t_start, t_end) + 0.001 if (t_start is not None and t_end is not None) else float('inf')
        else:
            t_min = 0.0
            t_max = float('inf')
        
        self.parent_list.selected_indices.clear()
        count = 0
        
        for i, ev in enumerate(self.parent_list.display_events):
            if escopo == 1:
                if not (t_min <= ev.get('abs_sec', 0.0) <= t_max):
                    continue
                    
            if tipo_sel == 1 and ev['type'] != 'control_change': continue
            if tipo_sel == 2 and ev['type'] != 'note': continue
            if tipo_sel == 3 and ev['type'] != 'program_change': continue
            if tipo_sel == 4 and ev['type'] != 'pitchwheel': continue
            
            passa_num = True
            if usar_num:
                num_ev = ev['msg_on'].note if ev['type'] == 'note' else (ev['msg'].control if ev['type'] == 'control_change' else (ev['msg'].program if ev['type'] == 'program_change' else 0))
                passa_num = (n_min <= num_ev <= n_max)
                
            passa_val = True
            if usar_val:
                val_ev = ev['msg_on'].velocity if ev['type'] == 'note' else (ev['msg'].value if ev['type'] == 'control_change' else (ev['msg'].program if ev['type'] == 'program_change' else (ev['msg'].pitch if ev['type'] == 'pitchwheel' else 0)))
                passa_val = (v_min <= val_ev <= v_max)
                
            if passa_num and passa_val:
                self.parent_list.selected_indices.add(i)
                count += 1
                
        return count