import wx
import mido
import mido.backends.rtmidi
import threading
import json
import os
import re
import sys
import time
import copy
import ctypes
import ctypes.wintypes

# --- IMPORTANDO OS NOSSOS MODULOS ---
from mhs_utils import (
    falar_status, CONFIG_FILE, get_cc_name,
    REV_MSB_LIST, CHO_MSB_LIST, VARIATION_EFEITOS_LIST, DSP_PARAM_NAMES,
    OFFSETS_VAR_2BYTES, OFFSETS_VAR_1BYTE, OFFSETS_REV_PARAMS, OFFSETS_CHO_PARAMS,
    REV_PARAM_INDEX, CHO_PARAM_INDEX, DRUM_NRPN_MSBS,
    detune_combinar, detune_separar, achar_porta_certa, verificar_nova_versao, verificar_nova_versao_detalhado,
    copiar_com_tempo
)
from mhs_dialogs import (
    VelocityControlDialog, RippleEditingDialog,
    TimeSignatureDialog, EnvelopeCCDialog, TempoEnvelopeDialog,
    QuantizacaoOfflineDialog, QuantizacaoRealTimeDialog,
    HumanizarDialog, PreferenciasDialog, DrumSetupDialog,
    PropriedadesCanalDialog, MidiRouterDialog, SysExEditorDialog,
    QuantizeProDialog, SysExListDialog, ChangelogDialog, oferecer_atualizacao
)
from mhs_event_list import EventListDialog

# Número da versão do app - um lugar só pra atualizar a cada release (título
# da janela e a checagem de atualizações). Mesmo padrão do MHS Style Creator.
VERSAO_APP = "4.5.1"

# Nome do repositório no GitHub (github.com/MHS-Softwares/<REPO_GITHUB>) -
# usado por verificar_atualizacoes_ao_iniciar / PreferenciasDialog pra
# consultar a Release mais recente e comparar com VERSAO_APP.
REPO_GITHUB = "MHS-MIDI-Sequencer"

# Texto da tela de Changelog (ver mostrar_changelog_se_necessario) - mesmo
# padrão do MHS Style Creator: embutido no código (não lido de um .txt
# separado) porque é a PRIMEIRA coisa que o usuário vê depois de atualizar,
# e não pode depender de um arquivo externo que talvez não tenha sido
# empacotado junto no instalador. A cada nova versão, acrescente uma
# entrada nova aqui.
MENSAGEM_APOIO = (
    "\n\n---\n\n"
    "Se este programa está ajudando você no seu trabalho, considere uma coisa:\n\n"
    "Ele é feito, do zero, por um músico cego - pensado pra funcionar 100% por "
    "teclado e leitor de tela, sem depender de enxergar nada na tela. Cada "
    "correção e cada recurso novo sai de muitas horas de trabalho voluntário, "
    "pensando em você e em outros músicos com deficiência visual que também "
    "precisam de uma ferramenta assim.\n\n"
    "Se puder, considere fazer uma contribuição via Pix ou PayPal, de "
    "qualquer valor - é um jeito simples de reconhecer esse trabalho e "
    "ajudar a mantê-lo vivo, sempre recebendo correções e novidades.\n\n"
    "Chave Pix / PayPal (e-mail): michel.teclado@gmail.com\n"
    "Destinatário: Michel Henrique da Silva\n\n"
    "Qualquer valor já faz muita diferença. Muito obrigado por usar o MHS "
    "MIDI Sequencer!"
)

CHANGELOG_TEXTS = {
    "4.5.1": (
        "- Corrigido: depois de baixar a atualização pela janela de "
        "atualização, ao responder Sim em \"Deseja instalar agora?\" o "
        "programa fechava mas o instalador não abria (o arquivo ficava "
        "só na pasta Downloads). Agora o instalador abre de verdade. "
        "Se você recusar fechar o programa (por exemplo no \"salvar "
        "antes de sair\"), nada é instalado, como antes."
        "\n\n- Mesmo defeito achado pelo Gabriel Schuck "
        "(@gabrielschuck) no MHS Style Creator."
    ),
    "4.5": (
        "- Corrigido: o instalador baixado pela janela de atualização "
        "agora é salvo na pasta Downloads que o Windows informa, e não "
        "numa pasta Downloads presumida dentro da pasta do usuário. Se "
        "você mudou o local da pasta Downloads (OneDrive, outra "
        "partição, outro disco), o arquivo antes ia parar num lugar onde "
        "você não procurava e a instalação não abria; agora vai para a "
        "sua pasta Downloads de verdade."
    ),
    "4.4": (
        "- Novo: a janela de atualização agora baixa o instalador da "
        "nova versão direto por ela, sem abrir página nenhuma. O botão "
        "\"Baixar e instalar\" avisa o progresso por voz, confere a "
        "integridade do arquivo e, ao terminar, pergunta se você quer "
        "instalar agora (o programa pergunta se quer salvar o que "
        "estiver aberto, fecha e abre o instalador). Se preferir não "
        "instalar na hora, o arquivo fica na sua pasta Downloads.\n\n"
        "- Mais rápido: abrir um MIDI ficou cerca de 35% mais rápido, "
        "salvar/consolidar o projeto ficou quase 3 vezes mais rápido, e o "
        "Desfazer (e o preview dos efeitos) ficou cerca de 7 vezes mais "
        "rápido num MIDI grande - o programa fazia validações repetidas, "
        "mensagem por mensagem, que não eram necessárias."
    ),
    "4.3": (
        "- Corrigido: em Efeitos MIDI (Ctrl+K), aba \"Bateria (Presets)\", "
        "o desenho escolhido soava certinho no preview, mas ao confirmar "
        "com Enter não entrava no MIDI (erro interno silencioso). Agora o "
        "preset de bateria é aplicado de verdade no trecho marcado.\n\n"
        "- Novo: botão \"Baixar da Internet...\" na aba Instrument "
        "Definitions das Preferências (Ctrl+P). O programa procura no site "
        "jososoft.dk a lista de teclados Yamaha que têm arquivo .ins "
        "disponível e mostra pra você escolher o seu (dá pra digitar o nome "
        "pra ir direto). É só apertar Enter, ou dar Tab até o botão Baixar: "
        "o programa baixa, avisa tudo por voz, salva numa pasta chamada "
        "\"Ins files\" ao lado do programa e já deixa o arquivo escolhido "
        "como instrumento - só falta clicar em Aplicar ou Fechar."
    ),
    "4.2": (
        "- Corrigido um bug no Drum Setup, aba \"Montagem de Kit\": só de "
        "ajustar o Banco/Patch/Peça Doadora de UMA peça (mesmo sem clicar "
        "\"Aplicar Mapeamento\") já podia desfazer, no teclado real, a "
        "afinação de QUALQUER OUTRA peça já confirmada antes nesse mesmo "
        "canal (ex.: montar a Caixa, aplicar, e só de mexer nos controles "
        "do Bumbo em seguida, a Caixa \"voltava\" pro kit padrão). Causa: "
        "a pré-audição do kit doador reseleciona o Banco/Patch do canal "
        "duas vezes (pra tocar e pra voltar), e isso reseta a afinação "
        "por nota inteira no teclado real - sem reaplicar depois o que já "
        "tinha sido confirmado. Os dados nunca se perdiam (por isso "
        "reabrir a tela sempre mostrava tudo certo), só o SOM ao vivo "
        "ficava errado até fechar e reabrir a tela de novo."
    ),
    "4.1": (
        "- Novo: aba \"Atualizações\" em Preferências (Ctrl+P) - caixa de "
        "marcação \"Verificar atualizações automaticamente ao iniciar o "
        "programa\" (ligada por padrão) e um botão \"Procurar Atualizações "
        "Agora\", disponível sempre. Ao achar uma versão mais nova "
        "publicada no GitHub, pergunta se quer abrir a página de "
        "download.\n\n"
        "- Novo: menu Ajuda, com \"Novidades desta Versão...\" (reabre esta "
        "mesma tela sob demanda) e \"Ir para a Página do Projeto\" (abre o "
        "repositório no GitHub no navegador)."
    ),
}

# --- Tradução dos CC/NRPN de forma de onda que o teclado manda junto com o
# timbre para o endereço equivalente do Multi Part (SysEx 43 10 4C 08 nn XX).
# Assim tudo cai no MESMO lugar (canais[ch]["VoiceCreator"]) e volta igual ao
# salvar. NOTA: a conferir no Data List do PSR-SX600 / no hardware do Michel.
## Endereços conferidos byte a byte contra o Data List oficial do
# PSR-SX600 (MIDI Parameter Change table, MULTI PART - página 65): a
# tabela antiga apontava pros endereços ERRADOS (0x20/0x21/0x60/0x61/
# 0x63/0x64/0x66 - que na verdade são "MW LFO Depth"/lixo fora da lista
# de parâmetros do Voice Creator), fazendo o CC76 (Vibrato Rate) que o
# teclado manda sozinho ao trocar de timbre escrever por engano em "MW
# LFO PMOD Depth" (0x20) em vez de "Vibrato Rate" (0x15) de verdade -
# isso é o que causava o timbre "distorcido" ao salvar/reabrir (o
# 0x20=valor do CC ficava gravado, disparando vibrato excessivo pela roda
# de modulação sem o Michel ter mexido nisso).
CC_SOUND_PARA_MULTIPART = {
    74: 0x18,  # Brightness  -> Filter Cutoff Frequency
    71: 0x19,  # Harmonic    -> Filter Resonance
    73: 0x1A,  # Attack Time -> EG Attack Time
    75: 0x1B,  # Decay Time  -> EG Decay Time
    72: 0x1C,  # Release Time-> EG Release Time
    76: 0x15,  # Vibrato Rate
    77: 0x16,  # Vibrato Depth
    78: 0x17,  # Vibrato Delay
}
NRPN_SOUND_PARA_MULTIPART = {
    (0x01, 0x08): 0x15,  # Vibrato Rate
    (0x01, 0x09): 0x16,  # Vibrato Depth
    (0x01, 0x0A): 0x17,  # Vibrato Delay
    (0x01, 0x20): 0x18,  # Filter Cutoff Frequency
    (0x01, 0x21): 0x19,  # Filter Resonance
    (0x01, 0x63): 0x1A,  # EG Attack Time
    (0x01, 0x64): 0x1B,  # EG Decay Time
    (0x01, 0x66): 0x1C,  # EG Release Time
}
# Endereços Multi Part que NÃO vão pro dict VoiceCreator (já têm dono no
# modelo, ou não são parâmetro de voz de verdade). Conferido contra o Data
# List oficial (MULTI PART, pág. 65): 0x00=Element Reserve (gerência interna
# de polifonia, não é "editar o timbre"); 0x04-0x07=Rcv Channel/Mono-Poly
# Mode/Key Assign/Part Mode (configuração de PARTE, não de SOM); 0x0A é o
# 2º byte do Detune - nunca vira uma entrada própria (ver detune_combinar/
# detune_separar - o valor combinado mora só na chave 0x09); 0x14=Variation
# Send Level (é o envio pro efeito de Inserção/Variation, já tratado à parte
# pelo sistema de DSP - não é parâmetro de voz); 0x30-0x3F=flags "Rcv X
# OFF/ON" (o que a parte ACEITA receber, não o SOM da voz em si).
MULTIPART_ADDR_RESERVADOS = {
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x0A, 0x0B, 0x0E, 0x12,
    0x13, 0x14, 0x72, 0x73,
} | set(range(0x30, 0x40))


class VoiceCreatorDialog(wx.Dialog):
    def __init__(self, parent, canal_idx, valores_atuais):
        super().__init__(parent, title=f"Voice Creator (Synth Pro) - Canal {canal_idx + 1}", size=(450, 750))
        self.parent_seq = parent
        self.canal_idx = canal_idx
        import copy
        self.valores = copy.deepcopy(valores_atuais)
        self.modulos = {}
        
        # A lista oficial da Síntese XG corrigida! Conferida parâmetro a
        # parâmetro contra o Data List oficial (MULTI PART, pág. 65) - 7
        # que faltavam foram acrescentados (0x0C/0x0D/0x0F/0x10/0x26/0x27/
        # 0x28) e o Detune (0x09) deixou de ser 2 sliders soltos ("Coarse"/
        # "Fine" 0-127 cada, formato errado) e virou 1 slider só com o valor
        # JÁ COMBINADO (ver detune_combinar/detune_separar em mhs_utils.py -
        # o Data List mostra que é 1 parâmetro de 2 bytes, cada um limitado a
        # um nibble 0x00-0x0F, não 2 parâmetros independentes de 0-127).
        self.parametros = [
            (0x08, "Note Shift (Transposição Fina)", 0, 127, 64),
            (0x09, "Detune (Desafinação Fina - 128=Centro)", 0, 255, 128),
            (0x0C, "Velocity Sense Depth (Sensib. de Toque no Volume)", 0, 127, 64),
            (0x0D, "Velocity Sense Offset (Sensib. de Toque - Piso)", 0, 127, 64),
            (0x0F, "Note Limit Low (Nota Mínima da Tessitura)", 0, 127, 0),
            (0x10, "Note Limit High (Nota Máxima da Tessitura)", 0, 127, 127),
            (0x11, "Dry Level (Amplitude)", 0, 127, 127),
            (0x15, "Vibrato Rate (LFO Velocidade)", 0, 127, 64),
            (0x16, "Vibrato Depth (LFO Intensidade)", 0, 127, 64),
            (0x17, "Vibrato Delay (LFO Atraso)", 0, 127, 64),
            (0x18, "Filter Cutoff (Frequência - Brilho)", 0, 127, 64),
            (0x19, "Filter Resonance (Ressonância - Wah)", 0, 127, 64),
            (0x1A, "EG Attack Time (Tempo de Ataque)", 0, 127, 64),
            (0x1B, "EG Decay Time (Tempo de Queda)", 0, 127, 64),
            (0x1C, "EG Release Time (Tempo de Relaxamento)", 0, 127, 64),
            (0x1D, "MW Pitch Control (Roda - Afinação)", 0, 127, 64),
            (0x1E, "MW Filter Control (Roda - Filtro)", 0, 127, 64),
            (0x1F, "MW Amplitude Control (Roda - Tremolo)", 0, 127, 64),
            (0x20, "MW LFO Pitch Depth (Roda - Vibrato)", 0, 127, 10),
            (0x21, "MW LFO Filter Depth (Roda - Wah)", 0, 127, 0),
            (0x22, "MW LFO Amp Depth (Roda - Tremolo)", 0, 127, 0),
            (0x23, "Bend Pitch Control (Alavanca Padrão)", 0, 127, 66), # 66 é +2 Semitons (0x42)!
            (0x24, "Bend Filter Control (Alavanca - Wah)", 0, 127, 64),
            (0x25, "Bend Amplitude Control (Alavanca - Vol)", 0, 127, 64),
            (0x26, "Bend LFO Pitch Depth (Alavanca - Vibrato)", 0, 127, 0),
            (0x27, "Bend LFO Filter Depth (Alavanca - Wah)", 0, 127, 0),
            (0x28, "Bend LFO Amp Depth (Alavanca - Tremolo)", 0, 127, 0),
            (0x4d, "CAT Pitch Control (Pressão de Canal - Afinação)", 0, 127, 64),
            (0x4e, "CAT Filter Control (Pressão de Canal - Filtro)", 0, 127, 64),
            (0x4f, "CAT Amplitude Control (Pressão de Canal - Volume)", 0, 127, 64),
            (0x50, "CAT LFO Pitch Depth (Pressão de Canal - Vibrato)", 0, 127, 0),
            (0x51, "CAT LFO Filter Depth (Pressão de Canal - Wah)", 0, 127, 0),
            (0x52, "CAT LFO Amp Depth (Pressão de Canal - Tremolo)", 0, 127, 0),
            (0x5a, "AC1 Pitch Control (Controle Assinável 1 - Afinação)", 0, 127, 64),
            (0x5b, "AC1 Filter Control (Controle Assinável 1 - Filtro)", 0, 127, 64),
            (0x5c, "AC1 Amplitude Control (Controle Assinável 1 - Volume)", 0, 127, 64),
            (0x5d, "AC1 LFO Pitch Depth (Controle Assinável 1 - Vibrato)", 0, 127, 0),
            (0x5e, "AC1 LFO Filter Depth (Controle Assinável 1 - Wah)", 0, 127, 0),
            (0x5f, "AC1 LFO Amp Depth (Controle Assinável 1 - Tremolo)", 0, 127, 0),
            (0x69, "Pitch EG Initial Level (Envelope de Afinação - Nível Inicial)", 0, 127, 64),
            (0x6a, "Pitch EG Attack Time (Envelope de Afinação - Ataque)", 0, 127, 64),
            (0x6b, "Pitch EG Release Level (Envelope de Afinação - Nível Final)", 0, 127, 64),
            (0x6c, "Pitch EG Release Time (Envelope de Afinação - Relaxamento)", 0, 127, 64),
            (0x6d, "Velocity Limit Low (Velocidade Mínima que Toca)", 1, 127, 1),
            (0x6e, "Velocity Limit High (Velocidade Máxima que Toca)", 1, 127, 127),
            (0x76, "EQ Bass Frequency (Frequência do Grave - 4 a 40)", 4, 40, 12),
            (0x77, "EQ Treble Frequency (Frequência do Agudo - 28 a 58)", 28, 58, 54),
        ]
        # Portamento - pedido do Michel depois de um dump real do teclado
        # dele (43 10 4C 0A 00 02 02 / ... 01, o "Modo do Portamento").
        # Switch/Time (CC 65/5) JÁ existem aqui como o campo "Porta Time"
        # (ver toggle_propriedade_direta/OnChannelListKeyDown) - só faltava
        # o Modo em si, que mora numa tabela SEPARADA do Data List oficial
        # (nn=PART NUMBER, logo depois da tabela MULTI PART) - SysEx
        # **43 1n 4C 0A pp aa vv**, bloco 0x0A, NÃO o 0x08 de sempre. Os
        # endereços 0x01-0x03 aqui não têm relação com Bank Select MSB/LSB/
        # Program Number do bloco 0x08 (mesmo valor de byte, bloco
        # diferente) - sem ambiguidade real na chave VoiceCreator porque
        # esses 3 endereços já são RESERVADOS (nunca capturados) no bloco
        # 0x08 (ver MULTIPART_ADDR_RESERVADOS).
        self.parametros_0a = [
            (0x01, "Mono Priority - Prioridade no Modo Mono (0=Última nota 1=Nota mais aguda)", 0, 1, 0),
            (0x02, "Portamento Mode - Modo do Portamento (0=Normal 1=Pitch Poly 2=Cross Fade)", 0, 2, 0),
            (0x03, "Portamento Time Mode - Modo do Tempo (0=Rate/Velocidade 1=Time/Tempo Fixo)", 0, 1, 0),
        ]
        self.parametros = self.parametros + self.parametros_0a
        self.bloco_do_param = {addr: 0x0A for addr, *_ in self.parametros_0a}

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        self.scr = wx.ScrolledWindow(panel, style=wx.VSCROLL)
        self.scr.SetScrollRate(0, 20)
        scrsz = wx.BoxSizer(wx.VERTICAL)
        
        for addr, nome, min_v, max_v, default_v in self.parametros:
            lbl = wx.StaticText(self.scr, label=f"{nome}:")
            scrsz.Add(lbl, 0, wx.LEFT|wx.TOP, 10)
            sl = wx.SpinCtrl(self.scr, value=str(self.valores.get(addr, default_v)), min=min_v, max=max_v)
            sl.SetName(nome)
            scrsz.Add(sl, 0, wx.EXPAND | wx.ALL, 5)
            self.modulos[addr] = sl
            sl.Bind(wx.EVT_SPINCTRL, self.enviar_para_teclado)
            
        self.scr.SetSizer(scrsz)
        vbox.Add(self.scr, 1, wx.EXPAND | wx.ALL, 5)
        
        btn_ok = wx.Button(panel, wx.ID_OK, "Fechar e Manter")
        vbox.Add(btn_ok, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        
        panel.SetSizer(vbox)
        wx.CallLater(100, list(self.modulos.values())[0].SetFocus)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        
    def _enviar_valor(self, addr, val):
        # Detune (0x09) é o único parâmetro combinado de 2 bytes desta lista -
        # o valor na tela é o JÁ COMBINADO (0-255), mas o teclado precisa das
        # 2 mensagens físicas separadas (0x09=nibble alto, 0x0A=nibble baixo).
        # Todo o resto é 1 endereço = 1 mensagem, como sempre foi.
        if not getattr(self.parent_seq, 'output', None):
            return
        import mido
        if addr == 0x09:
            alto, baixo = detune_separar(val)
            pares = [(0x09, alto), (0x0A, baixo)]
        else:
            pares = [(addr, val)]
        for a, v in pares:
            # Detune (0x09/0x0A) sempre vai pro bloco 0x08 - bloco_do_param
            # só tem entrada pros 3 endereços do Portamento (bloco 0x0A de
            # verdade); .get(a, 0x08) cai no padrão certo pra tudo mais.
            bloco = getattr(self, 'bloco_do_param', {}).get(a, 0x08)
            msg = [0xF0, 0x43, 0x10, 0x4C, bloco, self.canal_idx, a, v, 0xF7]
            try: self.parent_seq.output.send(mido.Message.from_bytes(msg))
            except: pass

    def enviar_para_teclado(self, event=None):
        # Se a função foi chamada por um evento de alteração, pega só quem mudou
        addr_to_send = None
        if event:
            foco = event.GetEventObject()
            for a, sl in self.modulos.items():
                if sl == foco:
                    addr_to_send = a
                    break

        if addr_to_send is not None:
            v = self.modulos[addr_to_send].GetValue()
            self.valores[addr_to_send] = v
            self._enviar_valor(addr_to_send, v)

    def get_valores(self): return self.valores

    def refrescar(self):
        # Chamado (via wx.CallAfter) quando o teclado termina uma rajada de
        # troca de timbre com esta tela aberta - self.valores foi montado
        # como uma CÓPIA em __init__ (ao contrário do editor de DSP, que
        # compartilha o cache ao vivo), então precisa reler de verdade o
        # que a captura em segundo plano (on_midi_in) já guardou no canal,
        # e atualizar cada SpinCtrl pra refletir - o mesmo feedback em
        # tempo real que o editor de DSP Variation ganhou junto.
        vc = self.parent_seq.canais[self.canal_idx].get("VoiceCreator", {})
        for addr, sl in self.modulos.items():
            if addr in vc and vc[addr] != self.valores.get(addr):
                self.valores[addr] = vc[addr]
                if sl.GetValue() != vc[addr]:
                    sl.SetValue(vc[addr])

    def on_key(self, event):
        code = event.GetKeyCode()
        if code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
        elif code in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            self.EndModal(wx.ID_OK)
        elif code in [wx.WXK_HOME, wx.WXK_END, wx.WXK_PAGEUP, wx.WXK_PAGEDOWN]:
            foco = wx.Window.FindFocus()
            if foco and isinstance(foco, wx.SpinCtrl) and foco in self.modulos.values():
                val = foco.GetValue()
                v_min, v_max = foco.GetMin(), foco.GetMax()
                passo = 6 if v_max <= 127 else 12
                if code == wx.WXK_HOME: val = v_max
                elif code == wx.WXK_END: val = v_min
                elif code == wx.WXK_PAGEUP: val = min(v_max, val + passo)
                elif code == wx.WXK_PAGEDOWN: val = max(v_min, val - passo)
                foco.SetValue(val)

                # Força o envio direto do atalho
                addr_to_send = None
                for a, sl in self.modulos.items():
                    if sl == foco:
                        addr_to_send = a
                        break
                if addr_to_send is not None:
                    self.valores[addr_to_send] = val
                    self._enviar_valor(addr_to_send, val)

                from mhs_utils import falar_status
                falar_status(str(val), imediato=True)
            else:
                event.Skip()
        else:
            event.Skip()


# --- CLASSES DE ESTADO E PAINEL (GUIAS) ---
class ProjectState:
    def __init__(self):
        import mido
        self.midi_file = mido.MidiFile(type=1)
        self.midi_file.tracks.append(mido.MidiTrack())
        self.current_midi_path = None
        self.canais = []
        self.overrides = {i: {} for i in range(16)}
        self.canais_selecionados = {0}
        self.undo_stack = []
        self.redo_stack = []
        self.recorded_events = []
        self.current_tempo = 500000
        self.dirty = False
        self.play_events = []
        self.beat_events = []
        self.current_playback_time = 0.0
        self.total_time = 0.0
        self.virtual_total_time = 3600.0
        self.last_start_time = 0.0
        self.time_selection_start = None
        self.time_selection_end = None
        self.canal_atual = 0
        self.propriedade_atual = 0
        self.ripple_mode = 0 
        self.in_vel_ctrl_on = False
        self.in_vel_min = 1
        self.in_vel_max = 127
        
        # O Áudio Guia agora é lembrado por PROJETO (arquivo-irmão
        # ".mhsaudio" ao lado do .mid - ver processar_carregamento_midi/
        # salvar_config_audio), não mais "eterno" num slot global único -
        # aquele slot único causava contaminação entre projetos diferentes
        # (o áudio de um projeto vazava pro próximo que fosse aberto).
        # Uma guia nova começa sempre sem áudio nenhum.
        self.audio_path = None
        self.audio_volume = 100
        self.audio_offset = 0.0
        
        self.dsp_cache = {
            'active': False, 'rev_msb_idx': 1, 'rev_lsb_idx': 0,
            'rev_p': [-1] * 16, 'rev_ret': 64,
            'cho_msb_idx': 1, 'cho_lsb_idx': 0,
            'cho_p': [-1] * 16, 'cho_ret': 64,
        }
        # CORREÇÃO: Cache vazio para não dar erro ao salvar novos projetos
        self.variation_dsp_cache = {}
class ProjectPanel(wx.Panel):
    def __init__(self, parent_notebook, sequencer_frame):
        super().__init__(parent_notebook, style=wx.WANTS_CHARS)
        self.sequencer = sequencer_frame
        self.Bind(wx.EVT_CHAR_HOOK, self.sequencer.on_panel_char)
        self.Bind(wx.EVT_CONTEXT_MENU, self.sequencer.abrir_propriedades_canal)
        self.info_display = wx.StaticText(self, label="MHS Sequencer .0 - Nova Guia.")
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.info_display, 0, wx.ALL, 10)
        self.SetSizer(sizer)


# --- O CÉREBRO DO SEQUENCIADOR ---

class InserirCompassosDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="Inserir Compassos em Branco", size=(350, 280))
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        sizer.Add(wx.StaticText(self, label="Quantidade de Compassos:"), 0, wx.ALL, 5)
        self.sp_qtd = wx.SpinCtrl(self, value="1", min=1, max=1000)
        sizer.Add(self.sp_qtd, 0, wx.EXPAND | wx.ALL, 5)
        
        sizer.Add(wx.StaticText(self, label="Figura (Numerador):"), 0, wx.ALL, 5)
        self.sp_num = wx.SpinCtrl(self, value="4", min=1, max=32)
        sizer.Add(self.sp_num, 0, wx.EXPAND | wx.ALL, 5)
        
        sizer.Add(wx.StaticText(self, label="Figura (Denominador):"), 0, wx.ALL, 5)
        self.sp_den = wx.SpinCtrl(self, value="4", min=1, max=32)
        sizer.Add(self.sp_den, 0, wx.EXPAND | wx.ALL, 5)
        
        btns = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)
        wx.CallLater(100, self.sp_qtd.SetFocus)
        
    def get_valores(self):
        return self.sp_qtd.GetValue(), self.sp_num.GetValue(), self.sp_den.GetValue()
# .kar (karaokê) é um arquivo MIDI padrão com a letra em eventos de texto: abre e salva igual a um .mid
WILDCARD_ABRIR_MIDI = ("MIDI e Karaokê (*.mid;*.midi;*.kar)|*.mid;*.midi;*.kar|MIDI (*.mid;*.midi)|*.mid;*.midi|"
                       "Karaokê (*.kar)|*.kar|Todos os arquivos (*.*)|*.*")
WILDCARD_SALVAR_MIDI = "MIDI (*.mid)|*.mid|Karaokê (*.kar)|*.kar"


class MidiSequencer(wx.Frame):
    # --- OTIMIZAÇÃO DE PERFORMANCE: Cache do mapa de tempos (Tick <-> Segundos) ---
    # build_time_map()/get_tempo_map() escaneavam TODAS as mensagens de TODAS as
    # tracks a cada chamada (eram chamadas dezenas de vezes por edição/arrasto).
    # Como midi_file e dirty são os ÚNICOS pontos por onde qualquer edição de
    # conteúdo passa (todo o código já depende disso para o indicador de "não
    # salvo"), transformá-los em propriedades garante que o cache é invalidado
    # automaticamente em QUALQUER lugar que edite a música, sem precisar caçar
    # cada um dos pontos de mutação no arquivo inteiro.
    @property
    def midi_file(self):
        return getattr(self, '_midi_file', None)

    @midi_file.setter
    def midi_file(self, value):
        self._midi_file = value
        self._time_map_cache = None
        self._tempo_map_cache = None

    @property
    def dirty(self):
        return getattr(self, '_dirty', False)

    @dirty.setter
    def dirty(self, value):
        self._dirty = value
        self._time_map_cache = None
        self._tempo_map_cache = None

    def __init__(self, parent, title, arquivo_inicial=None):
        super().__init__(parent, title=title, size=(800, 600))
        self.carregar_configuracoes()
        
        import pygame
        try:
            pygame.mixer.init()
        except:
            pass
            
        self.tabs_data = []
        self.current_tab_idx = -1
        self.event_clipboard = [] 
        
        self.canais = []
        self.overrides = {} 
        self.dirty = False 
        self.canal_atual = 0
        self.propriedade_atual = 0
        
        # --- LISTA ATUALIZADA: Grave e Agudo adicionados após o Pan! ---
        self.propriedades = ["Nome", "Input", "Mute", "Solo", "Arm", "Volume", "Pan", "Grave", "Agudo", "Expression", "Bank", "Patch", "Reverb", "Chorus", "Transpose", "Pitch Bend", "Mono/Poly", "Porta Time"]
        
        self.canais_selecionados = {0}
        
        self.instrument_names = {}
        self.bank_names = {}
        self.key_names = {}
        
        self.output = None
        self.output_metronomo = None
        self.midi_in = None
        self.midi_file = None
        self.current_midi_path = None
        self.active_event_list = None
        self.active_drum_setup = None

        # --- CAPTURA DE TIMBRE/DSP DO TECLADO ---
        # Quando o teclado troca de timbre, ele despeja uma rajada de CC/NRPN/
        # SysEx com todo o som (DSP de inserção, Reverb/Chorus, filtro/EG/
        # vibrato...). _captura_timbre coalesce essa rajada numa janela curta;
        # _dsp_teclado guarda a "pegada" da última rajada por canal, pra zerar
        # o que o teclado tinha configurado e agora não reenviou (senão os
        # efeitos se acumulam a cada troca). Só o caminho de MIDI-in escreve
        # em _dsp_teclado - o que é editado à mão nos editores de DSP fica de fora.
        self._captura_timbre = None
        self._captura_timer = None
        self._dsp_teclado = {'slots': {}, 'vc': {}, 'rev': set(), 'cho': set()}

        self.undo_stack = []
        self.redo_stack = []
        
        self.tocando = False
        self.metronomo_ligado = False
        self.gravando = False
        self.rt_quantize = False
        self.rt_quantize_res = 16.0
        
        self.play_events = []
        self.beat_events = [] 
        self.recorded_events = [] 
        
        self.current_tempo = 500000 
        self.current_playback_time = 0.0
        self.total_time = 0.0
        self.virtual_total_time = 3600.0 
        self.ripple_mode = 0
        
        self.in_vel_ctrl_on = False
        self.in_vel_min = 1
        self.in_vel_max = 127
        
        self.audio_path = None
        self.audio_volume = 100
        self.audio_offset = 0.0
        
        self.tap_times = []
        
        self.rotas_midi = self.config.get('rotas_midi', [
            {'active': False, 'src': '1', 'dst': '11'},
            {'active': False, 'src': 'PB', 'dst': '10'},
            {'active': False, 'src': '0', 'dst': '0'},
            {'active': False, 'src': '0', 'dst': '0'}
        ])
        
        self.msg_index = 0
        self.beat_index = 0
        self.seek_flag = False
        self.last_start_time = 0.0 

        self.time_selection_start = None
        self.time_selection_end = None
        
        self.boas_vindas_faladas = False
        
        # --- ESTADO INICIAL DA TRANSPOSIÇÃO DO MIDI IN ---
        self.midi_in_octave = 0
        self.midi_in_semitone = 0
        
        self.init_ui()
        self.setup_shortcuts()
        
        portas_entrada = self.config.get('portas_in', [])
        if not portas_entrada and self.config.get('porta_in'): 
            portas_entrada = [self.config.get('porta_in')]
            
        self.conectar_midi(portas_entrada, self.config.get('porta_out', ''))
        self.conectar_midi_metronomo()
        # Ao abrir o programa, manda Local Control Off (mesmo que o F8) -
        # assim o teclado só toca o que o programa mandar, sem o som direto
        # das teclas físicas atrapalhando os testes. Some sozinho, sem
        # precisar lembrar de apertar F8 toda vez. F8 continua funcionando
        # normalmente pra ligar/desligar na mão durante o uso.
        self.set_local_control(False)
        self.carregar_ins_ativo()
        
        self.on_nova_guia()

        # Duplo clique num .mid no Windows (ou "Abrir com") manda o caminho
        # do arquivo por linha de comando - a guia em branco que acabou de
        # abrir com on_nova_guia() já está "limpa" (sem dirty, sem path),
        # então carrega direto nela, sem criar uma 2a guia.
        if arquivo_inicial and os.path.exists(arquivo_inicial):
            wx.CallAfter(self.processar_carregamento_midi, arquivo_inicial)

        self.Bind(wx.EVT_SHOW, self.ao_mostrar_tela)
        self.Bind(wx.EVT_CLOSE, self.ao_fechar_janela)
    def save_current_tab_state(self):
        if self.current_tab_idx < 0 or self.current_tab_idx >= len(self.tabs_data): return
        state = self.tabs_data[self.current_tab_idx]
        state.midi_file = self.midi_file
        state.current_midi_path = self.current_midi_path
        state.canais = self.canais
        state.overrides = self.overrides
        state.canais_selecionados = self.canais_selecionados
        state.undo_stack = self.undo_stack
        state.redo_stack = self.redo_stack
        state.recorded_events = self.recorded_events
        state.current_tempo = self.current_tempo
        state.dirty = self.dirty
        state.play_events = self.play_events
        state.beat_events = self.beat_events
        state.current_playback_time = self.current_playback_time
        state.total_time = self.total_time
        state.virtual_total_time = self.virtual_total_time
        state.last_start_time = self.last_start_time
        state.time_selection_start = self.time_selection_start
        state.time_selection_end = self.time_selection_end
        state.canal_atual = self.canal_atual
        state.propriedade_atual = self.propriedade_atual
        state.ripple_mode = getattr(self, 'ripple_mode', 0)
        state.in_vel_ctrl_on = getattr(self, 'in_vel_ctrl_on', False)
        state.in_vel_min = getattr(self, 'in_vel_min', 1)
        state.in_vel_max = getattr(self, 'in_vel_max', 127)
        state.audio_path = getattr(self, 'audio_path', None)
        state.audio_volume = getattr(self, 'audio_volume', 100)
        state.audio_offset = getattr(self, 'audio_offset', 0.0)
        
        # --- CORREÇÃO: Salva os DOIS caches de efeitos DSP da guia atual antes de trocar ---
        import copy
        if hasattr(self, 'dsp_cache'):
            state.dsp_cache = copy.deepcopy(self.dsp_cache)
        if hasattr(self, 'variation_dsp_cache'):
            state.variation_dsp_cache = copy.deepcopy(self.variation_dsp_cache)
    def clone_midi_rapido(self, mid):
        import mido
        import copy
        new_mid = mido.MidiFile(type=mid.type)
        new_mid.ticks_per_beat = getattr(mid, 'ticks_per_beat', 480)
        # Uma cópia simples por mensagem (copy() sem argumentos, ~0,6 us) em
        # vez de copy.deepcopy das trilhas: medido num MIDI de 39 mil
        # mensagens, 32 ms contra 269 ms - e isto roda a cada "desfazer",
        # a cada preview de efeito e a cada edição na Lista de Eventos. As
        # cópias saem independentes e do mesmo tipo (MidiTrack/Message).
        new_mid.tracks = [mido.MidiTrack([m.copy() for m in trilha]) for trilha in mid.tracks]
        return new_mid
    def enviar_ambientacao_completa(self):
        if not self.output or not hasattr(self, 'dsp_cache'): return
        if not self.dsp_cache.get('active', False): return

        import mido
        import time
        c = self.dsp_cache
        rev_msb_vals = [v for _, v in REV_MSB_LIST]
        cho_msb_vals = [v for _, v in CHO_MSB_LIST]

        r_msb = rev_msb_vals[c.get('rev_msb_idx', 1)] if c.get('rev_msb_idx', 1) < len(rev_msb_vals) else 1
        c_msb = cho_msb_vals[c.get('cho_msb_idx', 1)] if c.get('cho_msb_idx', 1) < len(cho_msb_vals) else 65

        sysex_data = [
            # Removido o XG System On daqui. Ele matava o teclado de tanto reiniciar!
            [0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x00, r_msb, c.get('rev_lsb_idx', 0), 0xF7],
            [0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x0C, c.get('rev_ret', 64), 0xF7],
            [0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x20, c_msb, c.get('cho_lsb_idx', 0), 0xF7],
            [0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x2C, c.get('cho_ret', 64), 0xF7],
        ]
        rev_p = c.get('rev_p', [-1] * 16)
        for i in range(16):
            if rev_p[i] != -1:
                sysex_data.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, OFFSETS_REV_PARAMS[i], rev_p[i] & 0x7F, 0xF7])
        cho_p = c.get('cho_p', [-1] * 16)
        for i in range(16):
            if cho_p[i] != -1:
                sysex_data.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, OFFSETS_CHO_PARAMS[i], cho_p[i] & 0x7F, 0xF7])

        for data in sysex_data:
            try:
                self.output.send(mido.Message.from_bytes(data))
                # O FÔLEGO DE OURO PARA O GLOBAL: Espera o teclado alocar o Reverb e o Chorus
                if len(data) >= 7 and data[6] in [0x00, 0x20]:
                    time.sleep(0.25)
            except:
                pass
    def on_tab_changing(self, event):
        old_idx = event.GetOldSelection()
        if old_idx != wx.NOT_FOUND:
            self.save_current_tab_state()
        event.Skip()

    def on_tab_changed(self, event):
        new_idx = event.GetSelection()
        if new_idx != wx.NOT_FOUND:
            self.load_tab_state(new_idx)
            from mhs_utils import falar_status
            falar_status(f"Guia {new_idx+1}: {self.notebook.GetPageText(new_idx)}", imediato=True)
        event.Skip()


    def caminho_sidecar_audio(self, midi_path):
        # O "arquivo-irmão" do Áudio Guia: mesmo nome do .mid, extensão
        # .mhsaudio, na mesma pasta. Sem caminho de .mid (projeto ainda
        # não salvo em lugar nenhum), não tem onde guardar - devolve None.
        if not midi_path:
            return None
        base, _ext = os.path.splitext(midi_path)
        return base + ".mhsaudio"

    def salvar_config_audio(self):
        """Salva o Áudio Guia (caminho, volume, deslocamento) no arquivo-
        irmão do .mid ATUAL - cada projeto lembra só do SEU próprio áudio.
        Sem projeto salvo em disco ainda, fica só na memória desta sessão
        (não tem em qual arquivo-irmão gravar)."""
        sidecar = self.caminho_sidecar_audio(getattr(self, 'current_midi_path', None))
        if not sidecar:
            return
        try:
            import json
            caminho_audio = getattr(self, 'audio_path', None)
            if caminho_audio:
                dados = {
                    'audio_path': caminho_audio,
                    'audio_volume': getattr(self, 'audio_volume', 100),
                    'audio_offset': getattr(self, 'audio_offset', 0.0),
                }
                with open(sidecar, 'w', encoding='utf-8') as f:
                    json.dump(dados, f, indent=2, ensure_ascii=False)
            elif os.path.exists(sidecar):
                # Sem áudio nenhum configurado - não deixa um arquivo-
                # irmão "vazio"/órfão perdido do lado do .mid.
                os.remove(sidecar)
        except Exception:
            pass

    # --- ÁUDIO GUIA: motor novo, via pygame.mixer.Sound/Channel ---
    # O pygame.mixer.music (usado antes) só toca UM arquivo de cada vez
    # via streaming, e o "start=" dele depende do parser interno do
    # SDL_mixer pra buscar a posição certa - o Michel relatou desincronia
    # toda vez que pausava/avançava/retrocedia (só tocar do zero
    # funcionava). Em vez de confiar nesse seek "escondido", a gente
    # decodifica o arquivo INTEIRO uma vez (com o próprio pygame.mixer.
    # Sound - que já sabe ler WAV/MP3/OGG/FLAC, o SDL_mixer decodifica
    # e reamostra sozinho pro formato do mixer, seja qual for o formato
    # de origem) e guarda o PCM cru em memória; qualquer posição depois
    # disso é só uma fatia desse buffer (sem redecodificar, sem depender
    # de seek nenhum do SDL_mixer). Pausar/retomar na MESMA posição usa
    # Channel.pause()/unpause() - o canal fica congelado no lugar exato,
    # sem precisar reler nem recomeçar nada.
    def _audio_reset_mixer_format(self):
        import pygame
        self._audio_decoded = None
        caminho = getattr(self, 'audio_path', None)
        if not caminho or not os.path.exists(caminho):
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            som = pygame.mixer.Sound(caminho)
            bruto = som.get_raw()
            fr, tamanho, nch = pygame.mixer.get_init()
            stride = (abs(tamanho) // 8) * max(1, nch)
            self._audio_decoded = (bruto, fr, stride)
        except Exception:
            self._audio_decoded = None

    def _audio_sound_from(self, pos_segundos):
        decodificado = getattr(self, '_audio_decoded', None)
        if not decodificado or pos_segundos < 0:
            return None
        bruto, fr, stride = decodificado
        offset_bytes = int(round(pos_segundos * fr)) * stride
        if offset_bytes >= len(bruto):
            return None
        try:
            import pygame
            return pygame.mixer.Sound(buffer=bruto[offset_bytes:])
        except Exception:
            return None

    def _audio_stop(self):
        canal = getattr(self, '_audio_channel', None)
        if canal is not None:
            try: canal.stop()
            except Exception: pass
        self._audio_channel = None
        self._audio_paused = False

    def _audio_pause(self):
        canal = getattr(self, '_audio_channel', None)
        if canal is not None:
            try:
                canal.pause()
                self._audio_paused = True
            except Exception: pass

    def _audio_unpause(self):
        canal = getattr(self, '_audio_channel', None)
        if canal is not None and getattr(self, '_audio_paused', False):
            try:
                canal.unpause()
                self._audio_paused = False
                return True
            except Exception:
                pass
        return False

    def _audio_play_from(self, pos_midi_segundos):
        """Toca o Áudio Guia a partir da posição do MIDI em segundos
        (já descontando audio_offset por dentro). Devolve True se
        realmente começou a tocar."""
        self._audio_stop()
        offset = getattr(self, 'audio_offset', 0.0)
        som = self._audio_sound_from(pos_midi_segundos - offset)
        if som is None:
            return False
        try:
            vol = 0.0 if getattr(self, 'audio_muted', False) else (getattr(self, 'audio_volume', 100) / 100.0)
            som.set_volume(vol)
            self._audio_channel = som.play()
            self._audio_paused = False
            return True
        except Exception:
            return False

    def load_tab_state(self, idx):
        if idx < 0 or idx >= len(self.tabs_data): return
        
        if hasattr(self, 'enviar_reset_fisico_teclado'):
            self.enviar_reset_fisico_teclado()
            
        state = self.tabs_data[idx]
        self.midi_file = state.midi_file
        self.current_midi_path = state.current_midi_path
        self.canais = state.canais
        self.overrides = state.overrides
        self.canais_selecionados = state.canais_selecionados
        self.undo_stack = state.undo_stack
        self.redo_stack = state.redo_stack
        self.recorded_events = state.recorded_events
        self.current_tempo = state.current_tempo
        self.dirty = state.dirty
        self.play_events = state.play_events
        self.beat_events = state.beat_events
        self.current_playback_time = state.current_playback_time
        self.total_time = state.total_time
        self.virtual_total_time = state.virtual_total_time
        self.last_start_time = state.last_start_time
        self.time_selection_start = state.time_selection_start
        self.time_selection_end = state.time_selection_end
        self.canal_atual = state.canal_atual
        self.propriedade_atual = state.propriedade_atual
        self.ripple_mode = getattr(state, 'ripple_mode', 0)
        self.in_vel_ctrl_on = getattr(state, 'in_vel_ctrl_on', False)
        self.in_vel_min = getattr(state, 'in_vel_min', 1)
        self.in_vel_max = getattr(state, 'in_vel_max', 127)
        
        self.audio_path = getattr(state, 'audio_path', None)
        self.audio_volume = getattr(state, 'audio_volume', 100)
        self.audio_offset = getattr(state, 'audio_offset', 0.0)
        
        if hasattr(self, 'get_tick_at_sec'):
            self.audio_offset_tick = self.get_tick_at_sec(max(0.0, self.audio_offset))
            
        import copy
        if hasattr(state, 'dsp_cache'):
            self.dsp_cache = copy.deepcopy(state.dsp_cache)
            if hasattr(self, 'enviar_ambientacao_completa'):
                self.enviar_ambientacao_completa()
                
        if hasattr(state, 'variation_dsp_cache'):
            self.variation_dsp_cache = copy.deepcopy(state.variation_dsp_cache)
            if hasattr(self, 'enviar_variation_dsp_completo'):
                self.enviar_variation_dsp_completo()
                
        self._audio_stop()
        try:
            self._audio_reset_mixer_format()
        except Exception:
            pass

        self.current_tab_idx = idx
        self.panel = self.notebook.GetPage(idx)
        self.info_display = self.panel.info_display
        
        self.atualizar_titulo()
        self.atualizar_status(True, silenciar=True)
    def on_nova_guia(self, event=None, titulo="Novo Projeto"):
        if self.tocando: self.toggle_reproducao(None)
        if self.current_tab_idx >= 0:
            self.save_current_tab_state()
            
        state = ProjectState()
        state.midi_file = mido.MidiFile(type=1)
        state.midi_file.tracks.append(mido.MidiTrack())
        state.canais = [self.gerar_canal_vazio(i+1) for i in range(16)]
        
        self.tabs_data.append(state)
        panel = ProjectPanel(self.notebook, self) 
        
        self.notebook.AddPage(panel, titulo, select=True)
        
        wx.CallAfter(self.ler_midi_memoria, True)
        wx.CallAfter(self.atualizar_titulo)

    def on_fechar_guia(self, event=None):
        if not self.checar_salvamento_guia(): return
        
        idx = self.current_tab_idx
        
        if len(self.tabs_data) == 1:
            self.processar_novo_midi()
            self.notebook.SetPageText(0, "Novo Projeto")
            from mhs_utils import falar_status
            falar_status("Projeto limpo.", imediato=True)
            return
            
        if self.tocando: self.toggle_reproducao(None)
        
        self.tabs_data.pop(idx)
        
        self.notebook.Unbind(wx.EVT_NOTEBOOK_PAGE_CHANGING)
        self.notebook.Unbind(wx.EVT_NOTEBOOK_PAGE_CHANGED)
        
        self.notebook.DeletePage(idx)
        
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGING, self.on_tab_changing)
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_tab_changed)
        
        new_idx = self.notebook.GetSelection()
        if new_idx != wx.NOT_FOUND:
            self.load_tab_state(new_idx)
        from mhs_utils import falar_status
        falar_status("Guia fechada.", imediato=True)

    def get_selection_bounds(self):
        if self.time_selection_start is None and self.time_selection_end is None:
            return 0.0, float('inf')
        st = self.time_selection_start if self.time_selection_start is not None else 0.0
        ed = self.time_selection_end if self.time_selection_end is not None else float('inf')
        return min(st, ed), max(st, ed)

    def on_copy(self, event):
        if not self.midi_file: return
        start_sec, end_sec = self.get_selection_bounds()
        start_tick = self.get_tick_at_sec(start_sec) if start_sec != float('inf') else 0
        end_tick = self.get_tick_at_sec(end_sec) if end_sec != float('inf') else float('inf')
        
        self.clipboard_length_ticks = max(0, end_tick - start_tick) if end_tick != float('inf') else 0
        
        if not self.canais_selecionados: return
        base_ch = min(self.canais_selecionados)
        self.event_clipboard.clear()
        
        source_tpb = max(1, getattr(self.midi_file, 'ticks_per_beat', 480))
        
        all_abs = []
        for tr in self.midi_file.tracks:
            t = 0
            for m in tr:
                t += m.time
                all_abs.append((t, m))
                
        active_notes = {}
        count = 0
        
        for t, m in all_abs:
            ch = getattr(m, 'channel', None)
            if ch in self.canais_selecionados:
                if m.type == 'note_on' and m.velocity > 0:
                    if start_tick <= t < end_tick:
                        self.event_clipboard.append({'ch_offset': ch - base_ch, 'tick_offset': t - start_tick, 'msg': m.copy(), 'source_tpb': source_tpb})
                        key = (ch, m.note)
                        active_notes[key] = active_notes.get(key, 0) + 1
                        count += 1
                elif m.type == 'note_off' or (m.type == 'note_on' and getattr(m, 'velocity', 0) == 0):
                    key = (ch, getattr(m, 'note', None))
                    if key in active_notes and active_notes[key] > 0:
                        self.event_clipboard.append({'ch_offset': ch - base_ch, 'tick_offset': t - start_tick, 'msg': m.copy(), 'source_tpb': source_tpb})
                        active_notes[key] -= 1
                else:
                    if start_tick <= t < end_tick:
                        self.event_clipboard.append({'ch_offset': ch - base_ch, 'tick_offset': t - start_tick, 'msg': m.copy(), 'source_tpb': source_tpb})
                        count += 1
                        
        from mhs_utils import falar_status
        if start_sec == 0.0 and end_sec == float('inf'):
            falar_status(f"Todo o conteudo de {len(self.canais_selecionados)} canais copiado.", imediato=True)
        else:
            falar_status(f"Trecho com {count} eventos copiado de {len(self.canais_selecionados)} canais.", imediato=True)

    def on_cut(self, event):
        self.on_copy(None)
        self.delete_time_selection(None, is_cut=True)

    def on_paste(self, event):
        from mhs_utils import falar_status
        if not hasattr(self, 'event_clipboard') or not self.event_clipboard:
            falar_status("Área de transferência vazia.", imediato=True)
            return
            
        self.save_state("Colar")
        paste_tick = self.get_tick_at_sec(self.current_playback_time)
        base_target_ch = self.canal_atual
        
        dest_tpb = max(1, getattr(self.midi_file, 'ticks_per_beat', 480))
        ripple_mode = getattr(self, 'ripple_mode', 0)
        jump_ticks = getattr(self, 'clipboard_length_ticks', 0)
        
        channel_to_track = {}
        for i, tr in enumerate(self.midi_file.tracks):
            for m in tr:
                ch = getattr(m, 'channel', None)
                if ch is not None and ch not in channel_to_track:
                    channel_to_track[ch] = i
        
        new_events_by_track = {i: [] for i in range(len(self.midi_file.tracks))}
        count = 0
        canais_afetados = set()
        
        for ev in self.event_clipboard:
            target_ch = base_target_ch + ev['ch_offset']
            if 0 <= target_ch <= 15:
                canais_afetados.add(target_ch)
                new_msg = ev['msg'].copy(channel=target_ch)
                
                source_tpb = ev.get('source_tpb', dest_tpb)
                scale = dest_tpb / float(source_tpb)
                scaled_offset = int(round(ev['tick_offset'] * scale))
                target_tick = paste_tick + scaled_offset
                
                best_track = channel_to_track.get(target_ch, 0)
                new_events_by_track[best_track].append((target_tick, new_msg))
                count += 1
                
        for i, tr in enumerate(self.midi_file.tracks):
            is_affected_ch = False
            for ch, t_idx in channel_to_track.items():
                if t_idx == i and ch in canais_afetados:
                    is_affected_ch = True
            
            needs_ripple = False
            if ripple_mode == 2 and jump_ticks > 0:
                needs_ripple = True
            elif ripple_mode == 1 and is_affected_ch and jump_ticks > 0:
                needs_ripple = True
                
            has_new_events = len(new_events_by_track[i]) > 0
            
            if not needs_ripple and not has_new_events:
                continue
                
            flat = []
            t = 0
            for m in tr:
                t += m.time
                shifted_t = t
                if needs_ripple and t >= paste_tick:
                    shifted_t = t + jump_ticks
                
                # OTIMIZAÇÃO: Pré-cálculo da prioridade de ordenação
                is_off = 0 if m.type == 'note_off' or (m.type == 'note_on' and getattr(m, 'velocity', 0) == 0) else 1
                flat.append((shifted_t, is_off, m))
                
            if has_new_events:
                for t_new, m_new in new_events_by_track[i]:
                    is_off_new = 0 if m_new.type == 'note_off' or (m_new.type == 'note_on' and getattr(m_new, 'velocity', 0) == 0) else 1
                    flat.append((t_new, is_off_new, m_new))
                
            # OTIMIZAÇÃO: Sort super rápido agora que não executa getattr repetidas vezes
            flat.sort(key=lambda x: (x[0], x[1]))
            
            import mido
            new_track = mido.MidiTrack()
            last_t = 0
            for t_ev, _, m_ev in flat:
                delta = max(0, int(round(t_ev - last_t)))
                # OTIMIZAÇÃO: Mutação direta. Pula o instanciador do mido!
                m_ev.time = delta
                new_track.append(m_ev)
                last_t = t_ev
            self.midi_file.tracks[i] = new_track
            
        self.dirty = True
        self.atualizar_titulo()
        
        was_playing = self.tocando
        if self.tocando:
            self.tocando = False
            self.all_notes_off()
            import time
            time.sleep(0.05)
            
        self.ler_midi_memoria(reset_canais=False)
        
        if jump_ticks > 0:
            novo_cursor_tick = paste_tick + jump_ticks
            self.current_playback_time = self.get_sec_at_tick(novo_cursor_tick)
            self.last_start_time = self.current_playback_time
                
        self.seek_flag = True
        
        if was_playing:
            self.tocando = True
            import threading
            threading.Thread(target=self.play_thread, daemon=True).start()
            
        if jump_ticks > 0:
            txt_pos = self._obter_str_compasso(self.current_playback_time)
            msg_ripple = " com Ripple" if ripple_mode > 0 else ""
            falar_status(f"Colado{msg_ripple}. Cursor movido para {txt_pos}.", imediato=True)
        else:
            falar_status(f"Colado {count} eventos.", imediato=True)
    def abrir_humanizar(self, event):
        from mhs_utils import falar_status
        if not self.midi_file:
            falar_status("Nenhum arquivo aberto para humanizar.")
            return
            
        from mhs_dialogs import HumanizarDialog
        dlg = HumanizarDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            dlg.aplicar_definitivo()
            falar_status("Humanização aplicada com sucesso.")
            
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
        dlg.Destroy()

    def play_humanize_preview(self, dlg):
        self.preview_is_playing = False
        import time
        time.sleep(0.02)
        
        self.preview_is_playing = True
        import threading
        t = threading.Thread(target=self._tocar_preview_humanize_global, args=(dlg,))
        t.daemon = True
        t.start()
        try:
            from mhs_utils import falar_status
            falar_status("Tocando preview ...", imediato=True)
        except: pass

    def _tocar_preview_humanize_global(self, dlg):
        import time

        # Toca a MESMA renderização já sorteada por dlg._renderizar() - nunca
        # um novo sorteio aqui. É isso que garante que o preview soe
        # igualzinho ao que será gravado quando o usuário confirmar (Enter/OK).
        preview_events = list(getattr(dlg, 'preview_eventos', []))
        if not preview_events:
            self.preview_is_playing = False
            return

        t_start_sec = getattr(self, 'time_selection_start', None)
        t_end_sec = getattr(self, 'time_selection_end', None)
        has_selection = False
        if t_start_sec is not None and t_end_sec is not None:
            if abs(t_end_sec - t_start_sec) > 0.01:
                has_selection = True

        if has_selection:
            valid_events = preview_events
        else:
            # Sem trecho selecionado: começa a partir do cursor, como antes.
            cursor_sec = getattr(self, 'current_playback_time', 0.0)
            valid_events = [ev for ev in preview_events if ev[0] >= cursor_sec]

        if not valid_events:
            self.preview_is_playing = False
            return

        # --- LOOP DE PREVIEW EM TEMPO REAL ---
        # valid_events já vem ordenado pelo horário FINAL (pós-humanização),
        # então percorrer em sequência aqui nunca "atropela" uma nota
        # seguinte - o achatamento de variação que existia antes ficou
        # resolvido na própria renderização (dlg._renderizar), não mais aqui.
        while getattr(self, 'preview_is_playing', False):
            start_real_time = time.time()
            first_event_sec = valid_events[0][0]

            for ev_sec, msg in valid_events:
                if not getattr(self, 'preview_is_playing', False): break

                target_real_time = start_real_time + (ev_sec - first_event_sec)

                while True:
                    if not getattr(self, 'preview_is_playing', False): break
                    now = time.time()
                    wait_time = target_real_time - now
                    if wait_time <= 0.001: break
                    time.sleep(min(0.01, wait_time))

                if not getattr(self, 'preview_is_playing', False): break

                if getattr(self, 'output', None):
                    try: self.output.send(msg)
                    except: pass

            if not getattr(self, 'preview_is_playing', False): break

            # Se não tem trecho selecionado, toca só uma vez
            if not has_selection: break

            time.sleep(0.5) # Pausa dramática para reiniciar o loop
            if hasattr(self, 'all_notes_off'): self.all_notes_off()

        self.preview_is_playing = False
        if hasattr(self, 'all_notes_off'): self.all_notes_off()
    def abrir_ripple_editing(self, event):
        from mhs_utils import falar_status
        dlg = RippleEditingDialog(self, self.ripple_mode)
        if dlg.ShowModal() == wx.ID_OK:
            self.ripple_mode = dlg.get_mode()
            modos = ["Desativado", "Ativado para Canais Selecionados", "Ativado para Todos os Canais"]
            falar_status(f"Ripple Editing: {modos[self.ripple_mode]}")
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
        dlg.Destroy()
        
    def abrir_velocity_control(self, event):
        from mhs_utils import falar_status
        dlg = VelocityControlDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            falar_status("Configurações de Velocity Control aplicadas.", imediato=True)
            self.dirty = True
            self.atualizar_titulo()
        else:
            dlg.restaurar()
            falar_status("Velocity Control cancelado.", imediato=True)
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
        dlg.Destroy()

    def _snapshot_undo(self, action_name):
        import copy
        return {
            "action": action_name,
            "midi_file": self.clone_midi_rapido(self.midi_file),
            "canais": [c.copy() for c in self.canais],
            "overrides": {k: v.copy() for k, v in self.overrides.items()},
            "current_tempo": self.current_tempo,
            "time_selection_start": self.time_selection_start,
            "time_selection_end": self.time_selection_end,
            "canais_selecionados": self.canais_selecionados.copy(),
            "dsp_cache": copy.deepcopy(getattr(self, 'dsp_cache', None)),
            "variation_dsp_cache": copy.deepcopy(getattr(self, 'variation_dsp_cache', None)),
        }

    def save_state(self, action_name="Ação"):
        if len(self.undo_stack) >= 50:
            self.undo_stack.pop(0)
        self.undo_stack.append(self._snapshot_undo(action_name))
        self.redo_stack.clear()
        # Contador só de subir - marca "alguma coisa mudou" pro Play não
        # reaplicar o "chase" de estado (Bank/Patch/CC/NRPN) à toa quando só
        # pausou e voltou sem editar nada no meio (ver toggle_pausa/
        # toggle_reproducao/play_thread). Não uso len(undo_stack) direto
        # porque ele tem teto de 50 (pop+append fica do mesmo tamanho).
        self._revisao_estado = getattr(self, '_revisao_estado', 0) + 1

    def undo(self, event):
        from mhs_utils import falar_status
        if not self.undo_stack:
            falar_status("Nada para desfazer.")
            return
            
        self.redo_stack.append(self._snapshot_undo("Desfazer"))

        state = self.undo_stack.pop()
        self._restore_state(state)
        falar_status(f"Desfeito: {state['action']}")

    def redo(self, event):
        from mhs_utils import falar_status
        if not self.redo_stack:
            falar_status("Nada para refazer.")
            return
            
        self.undo_stack.append(self._snapshot_undo("Refazer"))

        state = self.redo_stack.pop()
        self._restore_state(state)
        falar_status("Refeito")

    def _restore_state(self, state):
        self._revisao_estado = getattr(self, '_revisao_estado', 0) + 1
        was_playing = self.tocando
        if self.tocando:
            self.tocando = False
            self.all_notes_off()
            import time
            time.sleep(0.05)
            
        self.midi_file = self.clone_midi_rapido(state["midi_file"])
        self.canais = [c.copy() for c in state["canais"]]
        self.overrides = {k: v.copy() for k, v in state["overrides"].items()}
        self.current_tempo = state["current_tempo"]
        
        self.time_selection_start = state.get("time_selection_start")
        self.time_selection_end = state.get("time_selection_end")
        self.canais_selecionados = state.get("canais_selecionados", {self.canal_atual}).copy()

        import copy
        if state.get("dsp_cache") is not None:
            self.dsp_cache = copy.deepcopy(state["dsp_cache"])
        if state.get("variation_dsp_cache") is not None:
            self.variation_dsp_cache = copy.deepcopy(state["variation_dsp_cache"])

        self.dirty = True

        self.ler_midi_memoria(reset_canais=False)
        self.atualizar_titulo()
        self.atualizar_status(True, silenciar=True)
        
        if was_playing:
            self.tocando = True
            import threading
            threading.Thread(target=self.play_thread, daemon=True).start()

    def relatar_selecoes(self, event):
        from mhs_utils import falar_status
        mensagens = []
        
        qtd_canais = len(self.canais_selecionados)
        if qtd_canais > 1 or getattr(self, 'non_continuous_sel', False):
            canais_numeros = sorted([c + 1 for c in self.canais_selecionados])
            grupos = []
            if canais_numeros:
                inicio = canais_numeros[0]
                fim = canais_numeros[0]
                for n in canais_numeros[1:]:
                    if n == fim + 1:
                        fim = n
                    else:
                        if inicio == fim:
                            grupos.append(str(inicio))
                        else:
                            grupos.append(f"{inicio} ao {fim}")
                        inicio = n
                        fim = n
                if inicio == fim:
                    grupos.append(str(inicio))
                else:
                    grupos.append(f"{inicio} ao {fim}")
            canais_str = ", ".join(grupos)
            mensagens.append(f"{qtd_canais} canais selecionados: {canais_str}")
            
        if getattr(self, 'time_selection_start', None) is not None and getattr(self, 'time_selection_end', None) is not None:
            st_sec = min(self.time_selection_start, self.time_selection_end)
            ed_sec = max(self.time_selection_start, self.time_selection_end)
            if abs(ed_sec - st_sec) > 0.01:
                st_tick = self.get_tick_at_sec(st_sec)
                ed_tick = self.get_tick_at_sec(ed_sec)
                
                tpb = max(1, getattr(self.midi_file, 'ticks_per_beat', 480))
                
                # OTIMIZAÇÃO: Busca o Time Signature sem merge_tracks!
                ts_map = []
                for track in self.midi_file.tracks:
                    abs_t = 0
                    for msg in track:
                        abs_t += msg.time
                        if msg.type == 'time_signature':
                            ts_map.append((abs_t, msg.numerator, msg.denominator))
                ts_map.sort(key=lambda x: x[0])
                if not ts_map:
                    ts_map.append((0, 4, 4))
                    
                def get_bar_beat(target_tick):
                    current_bar = 1
                    current_tick = 0
                    num, den = 4, 4
                    for tm_tick, tm_num, tm_den in ts_map:
                        if tm_tick > target_tick: break
                        ticks_por_compasso = (tpb * 4.0 / tm_den) * tm_num
                        diff = tm_tick - current_tick
                        current_bar += int(diff // ticks_por_compasso)
                        current_tick = tm_tick
                        num, den = tm_num, tm_den
                    ticks_por_compasso = (tpb * 4.0 / den) * num
                    ticks_por_beat = tpb * 4.0 / den
                    diff = target_tick - current_tick
                    current_bar += int(diff // ticks_por_compasso)
                    beat = int((diff % ticks_por_compasso) // ticks_por_beat) + 1
                    return f"compasso {current_bar}, beat {beat}"

                st_str = get_bar_beat(st_tick)
                ed_str = get_bar_beat(ed_tick)
                mensagens.append(f"Trecho marcado do {st_str} ao {ed_str}")
                
        if not mensagens:
            falar_status("Nenhuma seleção ativa no momento.", imediato=True)
        else:
            falar_status(". E . ".join(mensagens), imediato=True)
    def processar_roteamento(self, msg):
        routed_msgs = []
        matched = False
        
        for rota in self.rotas_midi:
            if not rota.get('active', False): continue
            src = rota['src']
            dst = rota['dst']
            
            is_match = False
            if src == 'PB' and msg.type == 'pitchwheel': is_match = True
            elif src != 'PB' and msg.type == 'control_change' and msg.control == int(src): is_match = True
            
            if is_match:
                matched = True
                val = msg.pitch if msg.type == 'pitchwheel' else msg.value
                import mido
                if dst == 'PB':
                    if msg.type == 'control_change':
                        pitch_val = int(round((val / 127.0) * 16383 - 8192))
                        routed_msgs.append(msg.copy(type='pitchwheel', pitch=pitch_val))
                    else:
                        routed_msgs.append(msg)
                else:
                    dst_cc = int(dst)
                    if msg.type == 'pitchwheel':
                        cc_val = int(round((val + 8192) / 16383.0 * 127))
                        routed_msgs.append(mido.Message('control_change', channel=msg.channel, control=dst_cc, value=cc_val, time=msg.time))
                    else:
                        routed_msgs.append(msg.copy(control=dst_cc))
                        
        if not matched:
            return [msg]
        return routed_msgs

    def on_midi_in(self, msg):
        if getattr(self, '_log_midi_in', False):
            try:
                with open(getattr(self, '_midi_log_path', 'midi_in_log.txt'), 'a', encoding='utf-8') as _f:
                    _f.write(str(msg) + "\n")
            except Exception:
                pass

        # --- A CIRURGIA: TRANSPOSIÇÃO DO INPUT EM TEMPO REAL ---
        if msg.type in ['note_on', 'note_off']:
            oct_shift = getattr(self, 'midi_in_octave', 0) * 12
            semi_shift = getattr(self, 'midi_in_semitone', 0)
            total_shift = oct_shift + semi_shift
            if total_shift != 0:
                nova_nota = max(0, min(127, msg.note + total_shift))
                msg = msg.copy(note=nova_nota)

        if getattr(self, 'active_event_list', None) is not None:
            if msg.type in ['note_on', 'note_off']:
                import wx
                wx.CallAfter(self.active_event_list.handle_midi_in, msg)
            return
            
        if getattr(self, 'active_drum_setup', None) is not None:
            if msg.type in ['note_on', 'note_off', 'polytouch']:
                import wx
                wx.CallAfter(self.active_drum_setup.handle_midi_in, msg)
            return
            
        # Rastreador de Canal para SysEx Cegos (Como Tipos de DSP)
        if msg.type in ['note_on', 'note_off', 'control_change', 'pitchwheel', 'program_change', 'aftertouch', 'polytouch']:
            self._ultimo_raw_ch = getattr(msg, 'channel', 0)

        if msg.type == 'sysex':
            d = list(msg.data)
            if len(d) >= 7 and tuple(d[0:4]) == (67, 126, 1, 0):
                micros = (d[4] * 16384) + (d[5] * 128) + d[6]
                if micros > 0:
                    novo_bpm = int(round(60000000.0 / micros))
                    import wx
                    wx.CallAfter(self.processar_tempo_hardware, novo_bpm)
                return

            # --- ANTENA INTELIGENTE DE EFEITOS DSP YAMAHA XG ---
            if len(d) >= 7 and tuple(d[0:3]) == (0x43, 0x10, 0x4C):
                high = d[3]
                mid = d[4]
                param = d[5]
                
                # --- 1. CANAL ALVO: SEMPRE o canal em foco (decisão do Michel) ---
                # Toda a captura de timbre/DSP que chega pela MIDI IN vai pro
                # canal selecionado na tela, sem depender de Arm/Input - "se eu
                # estiver em outro canal, converte pro canal selecionado".
                ch_idx_in_data = -1
                if high == 0x08:  # Multi Part - o canal mora em d[4]
                    ch_idx_in_data = 4
                elif high == 0x02 and mid == 0x01 and param == 0x5B and len(d) >= 7 and d[6] != 0x7F:
                    ch_idx_in_data = 6
                elif high == 0x03 and param == 0x0C and len(d) >= 7 and d[6] != 0x7F:
                    ch_idx_in_data = 6

                novo_ch = self.canal_atual
                if 0 <= novo_ch < 16 and ch_idx_in_data != -1:
                    d[ch_idx_in_data] = novo_ch
                    msg = msg.copy(data=d)
                    if high == 0x08:
                        mid = novo_ch

                # Qualquer SysEx de DSP do teclado abre/renova a janela de
                # captura de rajada de troca de timbre.
                self._cap_tocar(novo_ch)


                # --- 2. ATUALIZAÇÃO DO CACHE E ROTEAMENTO FORÇADO ---
                # Reverb e Chorus Global
                if high == 0x02 and mid == 0x01:
                    if not hasattr(self, 'dsp_cache'):
                        self.dsp_cache = {
                            'active': False, 'rev_msb_idx': 1, 'rev_lsb_idx': 0,
                            'rev_p': [-1] * 16, 'rev_ret': 64,
                            'cho_msb_idx': 1, 'cho_lsb_idx': 0,
                            'cho_p': [-1] * 16, 'cho_ret': 64,
                        }

                    c = self.dsp_cache
                    rev_msb_vals = [v for _, v in REV_MSB_LIST]
                    cho_msb_vals = [v for _, v in CHO_MSB_LIST]

                    if param == 0x00 and len(d) >= 8:
                        c['active'] = True
                        if d[6] in rev_msb_vals: c['rev_msb_idx'] = rev_msb_vals.index(d[6])
                        c['rev_lsb_idx'] = d[7]
                    elif param == 0x0C:
                        c['active'] = True
                        c['rev_ret'] = d[6]
                    elif param in REV_PARAM_INDEX:
                        c['active'] = True
                        c['rev_p'][REV_PARAM_INDEX[param]] = d[6]
                    elif param == 0x20 and len(d) >= 8:
                        c['active'] = True
                        if d[6] in cho_msb_vals: c['cho_msb_idx'] = cho_msb_vals.index(d[6])
                        c['cho_lsb_idx'] = d[7]
                    elif param == 0x2C:
                        c['active'] = True
                        c['cho_ret'] = d[6]
                    elif param in CHO_PARAM_INDEX:
                        c['active'] = True
                        c['cho_p'][CHO_PARAM_INDEX[param]] = d[6]

                # DSP Variation e Insertion (Gavetas)
                slot_idx = None
                if high == 0x02 and mid == 0x01:
                    slot_idx = 0
                elif high == 0x03:
                    cap_rm = getattr(self, '_captura_timbre', None)
                    if cap_rm is not None:
                        # O número da gaveta que o teclado escolheu (mid) não tem
                        # relação com as gavetas que o ARQUIVO já usa. Se ela já
                        # for de OUTRO canal, remapeia pra gaveta do canal em
                        # foco (ou a 1ª livre) - senão o timbre novo atropela o
                        # DSP de outro canal.
                        remap = cap_rm.setdefault('slot_remap', {})
                        if mid not in remap:
                            kb_slot = mid + 1
                            v_kb = self.variation_dsp_cache.get(kb_slot)
                            colide = (isinstance(v_kb, dict) and v_kb.get('active')
                                      and v_kb.get('ch') not in (self.canal_atual, 127, None))
                            remap[mid] = self._escolher_slot_dsp(self.canal_atual) if colide else kb_slot
                        slot_idx = remap[mid]
                    else:
                        slot_idx = mid + 1

                if slot_idx is not None:
                    if not hasattr(self, 'variation_dsp_cache'):
                        self.variation_dsp_cache = {}
                    if slot_idx not in self.variation_dsp_cache:
                        self.variation_dsp_cache[slot_idx] = {'active': False, 'ch': 127, 'msb_idx': 0, 'lsb_idx': 0, 'ret': -1, 'p': [-1]*16, 'timestamp': 0}
                    
                    v = self.variation_dsp_cache[slot_idx]

                    # Captura de rajada: quando o timbre novo REDEFINE o tipo de
                    # efeito dessa gaveta (endereço 0x40 no slot 0 / 0x00 nos
                    # demais), limpa os params do timbre ANTERIOR antes de
                    # aplicar os novos - senão vão se acumulando a cada troca.
                    cap = getattr(self, '_captura_timbre', None)
                    _tipo_efeito = len(d) >= 8 and ((param == 0x40 and slot_idx == 0) or (param == 0x00 and slot_idx > 0))
                    if cap and _tipo_efeito and slot_idx not in cap['visto']['slots']:
                        v['p'] = [-1] * 16
                        v['ret'] = -1
                    if cap:
                        cap['visto']['slots'].add(slot_idx)

                    # Identifica se o teclado mandou desligar o efeito (Bypass ou Desconectar)
                    is_bypass = False
                    if (param == 0x5B or param == 0x0C) and len(d) >= 7 and d[6] == 0x7F:
                        is_bypass = True
                    if (param == 0x40 or param == 0x00) and len(d) >= 8 and d[6] == 0x00:
                        is_bypass = True
                        
                    if is_bypass:
                        v['active'] = False
                    else:
                        v['active'] = True
                        import time
                        now = time.time()
                        v['timestamp'] = now
                        
                        if novo_ch is not None:
                            v['ch'] = novo_ch
                            # O canal roteado do teclado (5B na Variation, 0C na
                            # Inserção) entra em 'chs' pra ficar coerente com o
                            # modelo multi-canal.
                            if param in (0x5B, 0x0C) and d[6] != 0x7F:
                                v.setdefault('chs', {})[novo_ch] = v.get('chs', {}).get(novo_ch, 127)

                            # --- A FAXINA PROATIVA (O EXTERMINADOR DE GAVETAS ABANDONADAS) ---
                            # Se o Yamaha alocou uma nova gaveta pro canal, destruímos as gavetas órfãs antigas enviando o comando físico de desligar!
                            for k_old, v_old in self.variation_dsp_cache.items():
                                if k_old != slot_idx and isinstance(v_old, dict) and v_old.get('ch') == novo_ch:
                                    if now - v_old.get('timestamp', 0) > 0.5:
                                        v_old['active'] = False
                                        if getattr(self, 'output', None):
                                            try:
                                                import mido
                                                if k_old == 0:
                                                    msg_off = mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x5B, 0x7F, 0xF7])
                                                else:
                                                    msg_off = mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x03, k_old - 1, 0x0C, 0x7F, 0xF7])
                                                self.output.send(msg_off)
                                                if self.gravando:
                                                    self.recorded_events.append((self.current_playback_time, msg_off.copy()))
                                            except: pass
                            
                    dsp_msb_vals = [v for _, v in VARIATION_EFEITOS_LIST]
                    offsets_var_2bytes = [0x42, 0x44, 0x46, 0x48, 0x4A, 0x4C, 0x4E, 0x50, 0x52, 0x54]
                    offsets_var_1byte  = [0x70, 0x71, 0x72, 0x73, 0x74, 0x75]
                    # Params 1-10 do efeito de Inserção XG ficam em 0x02-0x0B;
                    # os params 11-16 ficam em 0x20-0x25 (não em 0x0D-0x12, que
                    # são as sensibilidades de controlador). Efeitos como o 95
                    # (Amp Simulator) usam os 16, e o teclado despeja isso na
                    # troca de timbre.
                    offsets_ins_1b     = [0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25]

                    if param == 0x40 and slot_idx == 0 and len(d) >= 8:
                        if d[6] in dsp_msb_vals: v['msb_idx'] = dsp_msb_vals.index(d[6])
                        v['lsb_idx'] = d[7]
                    elif param == 0x00 and slot_idx > 0 and len(d) >= 8:
                        if d[6] in dsp_msb_vals: v['msb_idx'] = dsp_msb_vals.index(d[6])
                        v['lsb_idx'] = d[7]
                    elif param == 0x0B and slot_idx > 0 and len(d) >= 7:
                        v['ret'] = d[6]
                    elif param == 0x54 and slot_idx == 0 and len(d) >= 8:
                        v['p'][9] = (d[6] * 128) + d[7]
                    elif param == 0x56 and slot_idx == 0 and len(d) >= 7:
                        v['ret'] = d[6]
                    elif param in offsets_var_2bytes and slot_idx == 0 and len(d) >= 8:
                        idx_p = offsets_var_2bytes.index(param)
                        v['p'][idx_p] = (d[6] * 128) + d[7]
                    elif param in offsets_var_1byte and slot_idx == 0 and len(d) >= 7:
                        idx_p = offsets_var_1byte.index(param) + 10
                        v['p'][idx_p] = d[6]
                    elif slot_idx > 0 and len(d) >= 8 and 0x30 <= param <= 0x4E:
                        idx_p = (param - 0x30) // 2
                        if idx_p < 16: v['p'][idx_p] = (d[6] * 128) + d[7]
                    elif slot_idx > 0 and param in offsets_ins_1b and len(d) >= 7:
                        idx_p = offsets_ins_1b.index(param)
                        v['p'][idx_p] = d[6]
                        
                    # --- INJEÇÃO DE ROTEAMENTO FORÇADO ---
                    if param == 0x00 and not is_bypass and novo_ch is not None and getattr(self, 'output', None):
                        import mido
                        if slot_idx == 0:
                            assign_syx = [0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x5B, novo_ch, 0xF7]
                        else:
                            assign_syx = [0xF0, 0x43, 0x10, 0x4C, 0x03, slot_idx - 1, 0x0C, novo_ch, 0xF7]
                        try:
                            msg_assign = mido.Message.from_bytes(assign_syx)
                            self.output.send(msg_assign)
                            if self.gravando:
                                self.recorded_events.append((self.current_playback_time, msg_assign.copy()))
                        except: pass

                # --- MULTI PART (forma de onda: filtro, EG, vibrato, EQ...) ---
                # O teclado despeja esses SysEx junto com o timbre. Antes eles
                # só eram ecoados e sumiam ao salvar; agora entram no modelo,
                # tudo no canal em foco.
                if high == 0x08 and 0 <= novo_ch < 16 and len(d) >= 7:
                    addr_mp, val_mp = d[5], d[6]
                    c_alvo = self.canais[novo_ch]
                    if addr_mp == 0x0E:
                        c_alvo["Pan"] = val_mp
                    elif addr_mp == 0x12:
                        c_alvo["Chorus"] = val_mp
                    elif addr_mp == 0x13:
                        c_alvo["Reverb"] = val_mp
                    elif addr_mp == 0x72:
                        c_alvo["Grave"] = val_mp
                    elif addr_mp == 0x73:
                        c_alvo["Agudo"] = val_mp
                    elif addr_mp in (0x09, 0x0A):
                        # Detune: 2 bytes separados no fio (cada um só um
                        # nibble), 1 valor combinado só no modelo - ver
                        # detune_combinar/detune_separar em mhs_utils.py.
                        if not hasattr(self, '_detune_nibbles'):
                            self._detune_nibbles = {i: [0x08, 0x00] for i in range(16)}
                        par = self._detune_nibbles.setdefault(novo_ch, [0x08, 0x00])
                        if addr_mp == 0x09: par[0] = val_mp & 0x0F
                        else: par[1] = val_mp & 0x0F
                        c_alvo.setdefault("VoiceCreator", {})[0x09] = detune_combinar(par[0], par[1])
                        cap = getattr(self, '_captura_timbre', None)
                        if cap:
                            cap['visto']['vc'].add(0x09)
                    elif addr_mp not in MULTIPART_ADDR_RESERVADOS:
                        # Volume (0x0B) e outros reservados ficam de fora
                        # (Volume/Expression não entram no modelo, por decisão
                        # do Michel).
                        c_alvo.setdefault("VoiceCreator", {})[addr_mp] = val_mp
                        cap = getattr(self, '_captura_timbre', None)
                        if cap:
                            cap['visto']['vc'].add(addr_mp)
                    self.dirty = True
                elif high == 0x0A and 0 <= novo_ch < 16 and len(d) >= 7:
                    # Portamento (Mono Priority/Modo/Modo do Tempo) - bloco
                    # SEPARADO 0x0A, não o 0x08 de sempre (ver comentário
                    # perto de self.parametros_0a em VoiceCreatorDialog).
                    addr_mp, val_mp = d[5], d[6]
                    if addr_mp in (0x01, 0x02, 0x03):
                        c_alvo = self.canais[novo_ch]
                        c_alvo.setdefault("VoiceCreator", {})[addr_mp] = val_mp
                        cap = getattr(self, '_captura_timbre', None)
                        if cap:
                            cap['visto']['vc'].add(addr_mp)
                        self.dirty = True

            if getattr(self, 'output', None):
                try:
                    self.output.send(msg)
                except:
                    pass

            if self.gravando:
                self.recorded_events.append((self.current_playback_time, msg.copy()))
            return

        if not hasattr(self, '_in_msb'): self._in_msb = {i: 0 for i in range(16)}
        if not hasattr(self, '_in_lsb'): self._in_lsb = {i: 0 for i in range(16)}

        # Captura de timbre/DSP: Program Change e CCs de forma de onda (71-78,
        # NRPN 01 xx) do teclado vão SEMPRE pro canal em foco, fora da lógica
        # de Arm/Input. Abre/renova a janela de rajada de troca de timbre.
        if msg.type in ('program_change', 'control_change'):
            self._captura_voz_hardware(msg)

        if getattr(self, 'esperando_nota', False):
            is_valid_trigger = False
            if msg.type == 'note_on' and msg.velocity > 0:
                is_valid_trigger = True
            elif msg.type in ['control_change', 'pitchwheel']:
                is_valid_trigger = True
                
            if is_valid_trigger:
                self.esperando_nota = False
                self.gravando = True 
                import wx
                wx.CallAfter(self.atualizar_titulo)
                if not self.tocando:
                    wx.CallAfter(self.toggle_reproducao, None)

        if msg.type in ['note_on', 'note_off', 'control_change', 'pitchwheel', 'program_change', 'aftertouch', 'polytouch']:
            msgs_to_process = self.processar_roteamento(msg)
            
            for r_msg in msgs_to_process:
                if not getattr(r_msg, 'is_meta', False):
                    raw_ch = getattr(r_msg, 'channel', None)
                    hw_in_ch = (raw_ch + 1) if raw_ch is not None else 1
                    
                    alvos_armados = [i for i in range(16) if self.canais[i]["Arm"]]
                    if alvos_armados:
                        alvos_validos = [i for i in alvos_armados if self.canais[i].get("Input", 1) == hw_in_ch]
                    else:
                        if self.canais[self.canal_atual].get("Input", 1) == hw_in_ch:
                            alvos_validos = [self.canal_atual]
                        else:
                            alvos_validos = []
                        
                    if not alvos_validos:
                        continue
                        
                    if raw_ch is not None and 0 <= raw_ch < 16:
                        mudou_prop_tela = False
                        for ch_idx in alvos_validos:
                            mudou_neste = False
                            
                            if r_msg.type == 'program_change':
                                self.canais[ch_idx]["Patch"] = r_msg.program
                                self.overrides[ch_idx]["Patch"] = r_msg.program
                                mudou_neste = True
                                b = self.canais[ch_idx]["Bank"]
                                nome_p = self.instrument_names.get(b, {}).get(r_msg.program, f"P {r_msg.program}")
                                from mhs_utils import falar_status
                                falar_status(f"{nome_p}", imediato=True)
                                
                                # --- A FAXINA NO PROGRAM CHANGE PARA O HARDWARE ---
                                if hasattr(self, 'variation_dsp_cache'):
                                    import time
                                    now = time.time()
                                    for slot_k, v in self.variation_dsp_cache.items():
                                        if isinstance(v, dict):
                                            is_owner = (v.get('ch') == ch_idx) or (ch_idx == 0 and v.get('ch') in [127, 0x7F])
                                            if is_owner and (now - v.get('timestamp', 0) > 0.5):
                                                v['active'] = False
                                                # Envia comando de morte definitivo pro Teclado
                                                if getattr(self, 'output', None):
                                                    try:
                                                        import mido
                                                        if slot_k == 0:
                                                            msg_off = mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x5B, 0x7F, 0xF7])
                                                        else:
                                                            msg_off = mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x03, slot_k - 1, 0x0C, 0x7F, 0xF7])
                                                        self.output.send(msg_off)
                                                        if self.gravando:
                                                            self.recorded_events.append((self.current_playback_time, msg_off.copy()))
                                                    except: pass
                                
                            elif r_msg.type == 'control_change':
                                if r_msg.control == 0:  
                                    self._in_msb[raw_ch] = r_msg.value
                                    novo_banco = (self._in_msb[raw_ch] * 128) + self._in_lsb.get(raw_ch, 0)
                                    self.canais[ch_idx]["Bank"] = novo_banco
                                    self.overrides[ch_idx]["Bank"] = novo_banco
                                    mudou_neste = True
                                    nome_b = self.bank_names.get(novo_banco, f"Banco {novo_banco}")
                                    from mhs_utils import falar_status
                                    falar_status(f"{nome_b}", imediato=True)
                                elif r_msg.control == 32: 
                                    self._in_lsb[raw_ch] = r_msg.value
                                    novo_banco = (self._in_msb.get(raw_ch, 0) * 128) + self._in_lsb[raw_ch]
                                    self.canais[ch_idx]["Bank"] = novo_banco
                                    self.overrides[ch_idx]["Bank"] = novo_banco
                                    mudou_neste = True
                                elif r_msg.control == 94:
                                    # "Variation Send Level" - este canal manda
                                    # sinal pro efeito da Gaveta 1 (Variation).
                                    if not hasattr(self, 'variation_dsp_cache'):
                                        self.variation_dsp_cache = {}
                                    v0 = self.variation_dsp_cache.setdefault(
                                        0, {'active': False, 'ch': 0x7F, 'msb_idx': 0, 'lsb_idx': 0, 'ret': -1, 'p': [-1] * 16, 'chs': {}})
                                    if r_msg.value > 0:
                                        v0.setdefault('chs', {})[ch_idx] = r_msg.value
                                        v0['active'] = True
                                    else:
                                        v0.get('chs', {}).pop(ch_idx, None)
                                    mudou_neste = True
                                else:
                                    prop_map = {7: "Volume", 10: "Pan", 11: "Expression", 91: "Reverb", 93: "Chorus"}
                                    if r_msg.control in prop_map:
                                        # Durante uma troca de timbre, Volume (7)
                                        # e Expression (11) só passam pro
                                        # sintetizador, não entram no modelo/
                                        # arquivo (decisão do Michel).
                                        if getattr(self, '_captura_timbre', None) and r_msg.control in (7, 11):
                                            pass
                                        else:
                                            self.canais[ch_idx][prop_map[r_msg.control]] = r_msg.value
                                            mudou_neste = True
                            
                            if mudou_neste:
                                self.dirty = True
                                if self.canal_atual == ch_idx: mudou_prop_tela = True
                        if mudou_prop_tela: 
                            import wx
                            wx.CallAfter(self.atualizar_status, True, True)

                    # Durante uma troca de timbre, o Volume (CC7) e a Expression
                    # (CC11) que o timbre carrega NÃO passam pro sintetizador -
                    # senão o som muda de volume até o Play. O
                    # _finalizar_captura_timbre reafirma o valor da coluna logo
                    # depois.
                    if (getattr(self, '_captura_timbre', None) and not getattr(r_msg, 'is_meta', False)
                            and r_msg.type == 'control_change' and r_msg.control in (7, 11)):
                        continue

                    msg_to_send = r_msg
                    if self.in_vel_ctrl_on and msg_to_send.type == 'note_on' and msg_to_send.velocity > 0:
                        new_vel = int(round(self.in_vel_min + (msg_to_send.velocity - 1) * (self.in_vel_max - self.in_vel_min) / 126.0))
                        msg_to_send = msg_to_send.copy(velocity=max(1, min(127, new_vel)))

                    for ch in alvos_validos:
                        msg_mapped = msg_to_send.copy(channel=ch)
                        if self.output: self.output.send(msg_mapped)
                        if self.gravando and self.canais[ch]["Arm"]:
                            self.recorded_events.append((self.current_playback_time, msg_mapped))

    # ================= CAPTURA DE TIMBRE/DSP DO TECLADO =================
    def _escolher_slot_dsp(self, ch):
        # Gaveta de Inserção (1..6) pra onde mandar o DSP do timbre novo desse
        # canal: a que ele já usa, senão a primeira livre.
        vc = getattr(self, 'variation_dsp_cache', {})
        for k in range(1, 7):
            v = vc.get(k)
            if isinstance(v, dict) and v.get('active') and v.get('ch') == ch:
                return k
        for k in range(1, 7):
            v = vc.get(k)
            if not isinstance(v, dict) or not v.get('active'):
                return k
        return 1

    def _cap_tocar(self, ch):
        # Thread do rtmidi: abre ou renova a janela de coalescência da rajada
        # de troca de timbre para o canal `ch`. A "pegada" da rajada anterior
        # (prev) é fotografada só na abertura; `visto` acumula o que a rajada
        # atual traz. O fecho (com reset do que não voltou) roda na GUI.
        import time
        if not hasattr(self, '_dsp_teclado'):
            self._dsp_teclado = {'slots': {}, 'vc': {}}
        cap = getattr(self, '_captura_timbre', None)
        if cap is None or cap.get('ch') != ch:
            self._captura_timbre = {
                'ch': ch,
                'visto': {'slots': set(), 'vc': set()},
                'prev': {
                    'slots': set(self._dsp_teclado['slots'].get(ch, set())),
                    'vc': set(self._dsp_teclado['vc'].get(ch, set())),
                },
            }
            import wx
            wx.CallAfter(self._cap_agendar_fecho)
        self._captura_timbre['ate'] = time.time() + 0.45

    def _cap_agendar_fecho(self):
        import wx
        if getattr(self, '_captura_timer', None):
            try: self._captura_timer.Stop()
            except Exception: pass
        self._captura_timer = wx.CallLater(500, self._cap_verificar_fecho)

    def _cap_verificar_fecho(self):
        import time, wx
        cap = getattr(self, '_captura_timbre', None)
        if not cap:
            return
        if time.time() < cap.get('ate', 0):
            self._captura_timer = wx.CallLater(150, self._cap_verificar_fecho)
            return
        self._finalizar_captura_timbre()

    def _finalizar_captura_timbre(self):
        # GUI thread. Zera as gavetas/endereços que o teclado tinha configurado
        # antes e a rajada atual não reenviou - pra os efeitos não acumularem.
        cap = getattr(self, '_captura_timbre', None)
        self._captura_timbre = None
        self._captura_timer = None
        if not cap:
            return
        import mido
        ch = cap['ch']
        visto = cap['visto']
        prev = cap['prev']

        if hasattr(self, 'variation_dsp_cache'):
            for slot in prev['slots'] - visto['slots']:
                v = self.variation_dsp_cache.get(slot)
                if isinstance(v, dict) and v.get('ch') == ch:
                    v['active'] = False
                    v['p'] = [-1] * 16
                    v['ret'] = -1
                    if getattr(self, 'output', None):
                        try:
                            if slot == 0:
                                off = mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x5B, 0x7F, 0xF7])
                            else:
                                off = mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x03, slot - 1, 0x0C, 0x7F, 0xF7])
                            self.output.send(off)
                        except Exception:
                            pass

        # Se o teclado alocou gaveta(s) nova(s) pra esse canal, desliga
        # qualquer OUTRA gaveta que ainda aponte pro mesmo canal (uma do
        # arquivo, do timbre anterior) - senão o canal fica com dois efeitos
        # de inserção sobrepostos.
        if visto['slots'] and hasattr(self, 'variation_dsp_cache'):
            for k, ov in list(self.variation_dsp_cache.items()):
                if (isinstance(ov, dict) and k not in visto['slots']
                        and ov.get('ch') == ch and ov.get('active')):
                    ov['active'] = False

        if 0 <= ch < len(self.canais):
            vc = self.canais[ch].get("VoiceCreator", {})
            for addr in prev['vc'] - visto['vc']:
                vc.pop(addr, None)

        if not hasattr(self, '_dsp_teclado'):
            self._dsp_teclado = {'slots': {}, 'vc': {}}
        self._dsp_teclado['slots'][ch] = set(visto['slots'])
        self._dsp_teclado['vc'][ch] = set(visto['vc'])

        # Reafirma o Volume (CC7) e a Expression (CC11) da COLUNA pro
        # sintetizador - o timbre novo trouxe os valores dele, mas quem manda é
        # a mixagem da tela.
        if getattr(self, 'output', None) and 0 <= ch < len(self.canais):
            c = self.canais[ch]
            try:
                self.output.send(mido.Message('control_change', channel=ch, control=7, value=int(c.get("Volume", 100))))
                self.output.send(mido.Message('control_change', channel=ch, control=11, value=int(c.get("Expression", 127))))
            except Exception:
                pass

        self.dirty = True
        import wx
        wx.CallAfter(self.atualizar_status, True, True)
        for attr in ('active_dsp_editor', 'active_voice_creator'):
            ed = getattr(self, attr, None)
            if ed is not None and hasattr(ed, 'refrescar'):
                try: wx.CallAfter(ed.refrescar)
                except Exception: pass

    def _captura_voz_hardware(self, msg):
        # Thread do rtmidi. PC + CCs de forma de onda (71-78) + NRPN (01 xx) que
        # o teclado manda na troca de timbre → sempre pro canal em foco.
        ch = self.canal_atual
        if not (0 <= ch < len(self.canais)):
            return
        c = self.canais[ch]
        hw = getattr(msg, 'channel', 0)

        if msg.type == 'program_change':
            self._cap_tocar(ch)
            c["Patch"] = msg.program
            self.overrides.setdefault(ch, {})["Patch"] = msg.program
            self.dirty = True
            return

        # control_change
        cc, val = msg.control, msg.value

        if cc in (0, 32):
            self._cap_tocar(ch)
            if not hasattr(self, '_in_msb'): self._in_msb = {i: 0 for i in range(16)}
            if not hasattr(self, '_in_lsb'): self._in_lsb = {i: 0 for i in range(16)}
            if cc == 0: self._in_msb[hw] = val
            else: self._in_lsb[hw] = val
            banco = (self._in_msb.get(hw, 0) * 128) + self._in_lsb.get(hw, 0)
            c["Bank"] = banco
            self.overrides.setdefault(ch, {})["Bank"] = banco
            self.dirty = True
            return

        if cc in (10, 91, 93):
            c[{10: "Pan", 91: "Reverb", 93: "Chorus"}[cc]] = val
            self.dirty = True
            return

        # Sound Controllers → endereço Multi Part equivalente no VoiceCreator
        if cc in CC_SOUND_PARA_MULTIPART:
            addr = CC_SOUND_PARA_MULTIPART[cc]
            c.setdefault("VoiceCreator", {})[addr] = val
            self.dirty = True
            cap = getattr(self, '_captura_timbre', None)
            if cap: cap['visto']['vc'].add(addr)
            return

        # NRPN: CC99=MSB, CC98=LSB, CC6=data MSB (CC38=data LSB, ignorado)
        if cc in (99, 98, 6, 38):
            if not hasattr(self, '_nrpn_in'):
                self._nrpn_in = {}
            st = self._nrpn_in.setdefault(hw, {'msb': None, 'lsb': None})
            if cc == 99: st['msb'] = val
            elif cc == 98: st['lsb'] = val
            elif cc == 6 and st['msb'] is not None and st['lsb'] is not None:
                addr = NRPN_SOUND_PARA_MULTIPART.get((st['msb'], st['lsb']))
                if addr is not None:
                    c.setdefault("VoiceCreator", {})[addr] = val
                    self.dirty = True
                    cap = getattr(self, '_captura_timbre', None)
                    if cap: cap['visto']['vc'].add(addr)
            return

    def on_toggle_midi_log(self, event):
        # Liga/desliga um log de TUDO que chega pela MIDI IN (inclusive SysEx),
        # pra capturar a rajada de troca de timbre do teclado. Grava em
        # midi_in_log.txt na pasta do programa.
        import os, time
        from mhs_utils import falar_status, BASE_DIR
        self._log_midi_in = not getattr(self, '_log_midi_in', False)
        if self._log_midi_in:
            self._midi_log_path = os.path.join(BASE_DIR, "midi_in_log.txt")
            try:
                with open(self._midi_log_path, 'w', encoding='utf-8') as f:
                    f.write("# Log de MIDI de entrada - " + time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
                falar_status("Registro de MIDI de entrada ligado. Mude o timbre no teclado e "
                             "depois desligue este item. O arquivo midi_in_log.txt fica na pasta do programa.",
                             imediato=True)
            except Exception:
                self._log_midi_in = False
                falar_status("Não consegui criar o arquivo de log.", imediato=True)
        else:
            falar_status("Registro de MIDI de entrada desligado.", imediato=True)

    def processar_tempo_hardware(self, novo_bpm):
        # --- FILTRO ANTI-SPAM: O NVDA SÓ FALA SE O NÚMERO MUDAR ---
        if getattr(self, '_ultimo_bpm_falado', None) == novo_bpm:
            return # Se for repetido, corta o mal pela raiz e fica mudo!

        self._ultimo_bpm_falado = novo_bpm

        from mhs_utils import falar_status
        falar_status(str(novo_bpm), imediato=True)

        current_bpm = int(round(60000000.0 / getattr(self, 'current_tempo', 500000)))
        if novo_bpm == current_bpm:
            return

        # Mesma troca de andamento AO VIVO do Tap Tempo (ver do_tap_tempo)
        # - nunca mais precisa do truque de "multiplicador"
        # (target_live_bpm/live_multiplier): aquele truque nunca travava a
        # thread de Play, mas também nunca mexia em play_events/
        # beat_events de verdade - então o Áudio Guia (que sempre toca na
        # velocidade real) ia saindo do sincronismo enquanto o
        # multiplicador ficasse diferente de 1.0. Trocando o andamento de
        # verdade (protegido por _pausar_leitura_eventos) o Áudio Guia
        # fica sempre sincronizado, tocando ou parado, sem nenhuma pausa
        # perceptível.
        self._pausar_leitura_eventos = True
        try:
            self._definir_bpm_global(novo_bpm)
            self.dirty = True
            self.ler_midi_memoria(reset_canais=False)
            self.seek_flag = False

            self.msg_index = len(self.play_events)
            for i, ev in enumerate(self.play_events):
                if ev[0] >= self.current_playback_time:
                    self.msg_index = i
                    break
            self.beat_index = len(self.beat_events)
            for i, (b_time, is_d) in enumerate(self.beat_events):
                if b_time >= self.current_playback_time:
                    self.beat_index = i
                    break
        finally:
            self._pausar_leitura_eventos = False

    def obter_mapa_tempos(self):
        """ Varre a Trilha Mestre e mapeia o momento exato em segundos de cada Envelope de Tempo """
        import mido
        if not getattr(self, 'midi_file', None) or not self.midi_file.tracks: return []
        tpb = self.midi_file.ticks_per_beat
        tempos = []
        abs_tick = 0
        current_tempo = 500000 # Começa no padrão de 120 BPM
        current_sec = 0.0
        
        for msg in self.midi_file.tracks[0]:
            if msg.time > 0:
                current_sec += mido.tick2second(msg.time, tpb, current_tempo)
                abs_tick += msg.time
            if msg.type == 'set_tempo':
                current_tempo = msg.tempo
                bpm = round(mido.tempo2bpm(msg.tempo), 2)
                tempos.append({'tick': abs_tick, 'sec': current_sec, 'bpm': bpm, 'msg': msg})
        return tempos

    def apagar_envelope_tempo_atual(self):
        """ Apaga fisicamente a automação de tempo que estiver embaixo do cursor """
        mapa = self.obter_mapa_tempos()
        if not mapa: return False
        
        cur_sec = self.current_playback_time
        margem = 0.05
        alvo = None
        
        for t in mapa:
            if abs(t['sec'] - cur_sec) <= margem:
                alvo = t
                break
                
        if not alvo: return False # Não achou envelope de tempo aqui

        # Antes só travava se o tempo estivesse EXATAMENTE no tick 0 - mas
        # `garantir_cabecalho_xg` insere o "XG System On" bem no início da
        # Trilha Mestre e empurra 120 ticks de "fôlego" pro PRÓXIMO evento
        # (pra o teclado real conseguir processar) - isso desloca o único
        # set_tempo do projeto pro tick 120, não mais o tick 0. A trava
        # exigia os dois (`tick==0` E ser o único) - um projeto editado
        # (com o cabeçalho XG já inserido) deixava de ser reconhecido como
        # "o único BPM do projeto" só por causa desse deslocamento, e o
        # Backspace apagava de verdade, jogando a música toda de volta pro
        # padrão de 120 BPM (achado pelo Michel comparando um .mid nunca
        # salvo pelo programa, ainda no tick 0, com o "Sonho de Amor.mid",
        # já com o cabeçalho e por isso no tick 120). Ser o ÚNICO tempo do
        # projeto (não importa o tick exato) já basta pra ser "o BPM
        # principal" - não tem "envelope" nenhum pra apagar aqui.
        # Exceção: um único tempo que NÃO está no começo da música (depois do
        # "fôlego" do cabeçalho XG, tick 120) não é o BPM principal e sim um
        # "envelope" solto - ex.: TA9506SeAcontecer.mid, com o único set_tempo
        # no beat 4 do 1º compasso. Esse pode ser apagado (a música volta ao
        # 120 BPM padrão até o Michel definir o andamento geral, Ctrl+Shift+T).
        if len(mapa) == 1 and alvo['tick'] <= 120:
            from mhs_utils import falar_status
            falar_status("Impossível apagar. Este é o único BPM do projeto. Para mudar o andamento geral, use Ctrl+Shift+T.", imediato=True)
            return True
            
        track_0 = self.midi_file.tracks[0]
        idx_to_remove = -1
        for i, msg in enumerate(track_0):
            if msg == alvo['msg']:
                idx_to_remove = i
                break
                
        if idx_to_remove != -1:
            msg_removida = track_0.pop(idx_to_remove)
            # Acopla a duração do evento apagado no próximo evento para não descincronizar a música!
            if idx_to_remove < len(track_0):
                track_0[idx_to_remove] = copiar_com_tempo(track_0[idx_to_remove], track_0[idx_to_remove].time + msg_removida.time)
                
            self.dirty = True
            self.atualizar_titulo()
            self.ler_midi_memoria(reset_canais=False)
            
            from mhs_utils import falar_status
            if not self.obter_mapa_tempos():
                falar_status(f"Envelope de {alvo['bpm']} BPM apagado. A música voltou ao andamento padrão de 120 BPM. Use Ctrl+Shift+T para definir o andamento geral.", imediato=True)
            else:
                falar_status(f"Envelope de {alvo['bpm']} BPM apagado.", imediato=True)
            return True
            
        return False



    def obter_mapa_compassos(self):
        """ Varre a Trilha Mestre e mapeia o momento exato de cada Mudança de Compasso (Time Signature) """
        import mido
        if not getattr(self, 'midi_file', None) or not self.midi_file.tracks: return []
        tpb = getattr(self.midi_file, 'ticks_per_beat', 480)
        compassos = []
        abs_tick = 0
        current_tempo = 500000 
        current_sec = 0.0
        
        for msg in self.midi_file.tracks[0]:
            if msg.time > 0:
                current_sec += mido.tick2second(msg.time, tpb, current_tempo)
                abs_tick += msg.time
            if msg.type == 'set_tempo':
                current_tempo = msg.tempo
            elif msg.type == 'time_signature':
                compassos.append({'tick': abs_tick, 'sec': current_sec, 'num': msg.numerator, 'den': msg.denominator, 'msg': msg})
        return compassos

    def navegar_formula_compasso(self, direcao):
        """ Navega para a próxima (1) ou anterior (-1) Fórmula de Compasso """
        self.foco_inteligente = 'compasso'
        mapa = self.obter_mapa_compassos()
        if not mapa:
            from mhs_utils import falar_status
            falar_status("Nenhuma mudança de compasso encontrada neste projeto.", imediato=True)
            return
            
        cur_sec = getattr(self, 'current_playback_time', 0.0)
        margem = 0.05 
        alvo = None
        
        if direcao == 1: # Próximo
            for c in mapa:
                if c['sec'] > cur_sec + margem:
                    alvo = c
                    break
        else: # Anterior
            for c in reversed(mapa):
                if c['sec'] < cur_sec - margem:
                    alvo = c
                    break
                    
        if alvo:
            self.current_playback_time = alvo['sec']
            self.last_start_time = alvo['sec']
            self.seek_flag = True
            str_pos = self.format_time(alvo['sec']) if hasattr(self, 'format_time') else f"{alvo['sec']:.1f}s"
            
            from mhs_utils import falar_status
            falar_status(f"Fórmula: {alvo['num']} por {alvo['den']}. {str_pos}", imediato=True)
            
            if getattr(self, 'tocando', False):
                self.tocando = False
                self.all_notes_off()
                import time; time.sleep(0.05)
                self.tocando = True
                import threading
                threading.Thread(target=self.play_thread, daemon=True).start()
        else:
            from mhs_utils import falar_status
            falar_status("Fim das mudanças de compasso." if direcao == 1 else "Início das mudanças de compasso.", imediato=True)

    def navegar_envelope_tempo(self, direcao):
        """ Navega para o próximo (1) ou anterior (-1) Envelope de Tempo """
        self.foco_inteligente = 'tempo'
        mapa = self.obter_mapa_tempos()
        if not mapa:
            from mhs_utils import falar_status
            falar_status("Nenhum envelope de tempo dinâmico encontrado.", imediato=True)
            return
            
        cur_sec = self.current_playback_time
        margem = 0.05 # 50 milissegundos de margem
        alvo = None
        
        if direcao == 1: # Próximo
            for t in mapa:
                if t['sec'] > cur_sec + margem:
                    alvo = t
                    break
        else: # Anterior
            for t in reversed(mapa):
                if t['sec'] < cur_sec - margem:
                    alvo = t
                    break
                    
        if alvo:
            self.current_playback_time = alvo['sec']
            self.last_start_time = alvo['sec']
            self.seek_flag = True
            str_pos = self.format_time(alvo['sec']) if hasattr(self, 'format_time') else f"{alvo['sec']:.1f}s"
            
            from mhs_utils import falar_status
            falar_status(f"Envelope de tempo: {alvo['bpm']} BPM. {str_pos}", imediato=True)
            
            if self.tocando:
                self.tocando = False
                self.all_notes_off()
                import time; time.sleep(0.05)
                self.tocando = True
                import threading
                threading.Thread(target=self.play_thread, daemon=True).start()
        else:
            from mhs_utils import falar_status
            falar_status("Fim dos envelopes." if direcao == 1 else "Início dos envelopes.", imediato=True)
    def editar_envelope_tempo_atual(self, event=None):
        """ Shift+T: edita o andamento do Envelope de Tempo em foco (o que estiver
        embaixo do cursor - navegue até ele com Shift+Ç / Shift+^). Troca só o
        valor daquele set_tempo, no mesmo tick; os outros envelopes ficam. """
        from mhs_utils import falar_status
        if not getattr(self, 'midi_file', None) or not self.midi_file.tracks:
            falar_status("Nenhum projeto aberto.", imediato=True)
            return
        mapa = self.obter_mapa_tempos()
        cur_sec = self.current_playback_time
        alvo = None
        for t in mapa:
            if abs(t['sec'] - cur_sec) <= 0.05:
                alvo = t
                break
        if not alvo:
            falar_status("O cursor não está sobre um envelope de tempo. Use Shift+Ç ou Shift+^ para navegar até um.", imediato=True)
            return
        self.foco_inteligente = 'tempo'
        try:
            from mhs_dialogs import PreciseTempoDialog
        except ImportError:
            falar_status("Erro: Tela de BPM não encontrada no arquivo de diálogos.", imediato=True)
            return
        dlg = PreciseTempoDialog(self, float(alvo['bpm']))
        dlg.SetTitle(f"Alterar BPM do Envelope de Tempo ({alvo['bpm']} BPM)")
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
            return
        novo_bpm = max(10.0, min(500.0, float(dlg.get_bpm())))
        dlg.Destroy()
        novo_micros = int(round(60000000.0 / novo_bpm))

        track_0 = self.midi_file.tracks[0]
        idx = next((i for i, m in enumerate(track_0) if m is alvo['msg']), -1)
        if idx == -1:
            idx = next((i for i, m in enumerate(track_0) if m == alvo['msg']), -1)
        if idx == -1:
            falar_status("Não achei esse envelope de tempo no arquivo.", imediato=True)
            return
        self.save_state("Editar Envelope de Tempo")
        track_0[idx] = track_0[idx].copy(tempo=novo_micros)

        # Mesma troca de andamento sem parar a reprodução do Tempo Preciso/Tap
        self._pausar_leitura_eventos = True
        try:
            self.dirty = True
            self.ler_midi_memoria(reset_canais=False)
            self.seek_flag = False
            self.msg_index = len(self.play_events)
            for i, ev in enumerate(self.play_events):
                if ev[0] >= self.current_playback_time:
                    self.msg_index = i
                    break
            self.beat_index = len(self.beat_events)
            for i, (b_time, is_d) in enumerate(self.beat_events):
                if b_time >= self.current_playback_time:
                    self.beat_index = i
                    break
        finally:
            self._pausar_leitura_eventos = False
        self.atualizar_titulo()
        if getattr(self, 'tocando', False):
            self.seek_flag = True
        falar_status(f"Envelope de tempo alterado de {alvo['bpm']} para {novo_bpm:g} BPM.", imediato=True)
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())

    def apagar_formula_compasso_atual(self):
        """ Apaga a Fórmula de Compasso (Time Signature) que estiver embaixo do cursor """
        import mido
        if not getattr(self, 'midi_file', None) or not self.midi_file.tracks: return False
        
        track_0 = self.midi_file.tracks[0]
        tpb = getattr(self.midi_file, 'ticks_per_beat', 480)
        cur_pos = getattr(self, 'current_playback_time', 0.0)
        margem = 0.05 # 50ms de margem de colisão
        
        current_tempo = 500000
        current_sec = 0.0
        
        alvo_idx = -1
        msg_removida = None
        
        for i, msg in enumerate(track_0):
            if msg.time > 0:
                current_sec += mido.tick2second(msg.time, tpb, current_tempo)
            if msg.type == 'set_tempo':
                current_tempo = msg.tempo
                
            if msg.type == 'time_signature':
                if abs(current_sec - cur_pos) <= margem:
                    alvo_idx = i
                    msg_removida = msg
                    break
                    
        if alvo_idx != -1:
            # Proteção: Evita apagar se for a ÚNICA figura de compasso do projeto inteiro
            tot_ts = sum(1 for m in track_0 if m.type == 'time_signature')
            if current_sec < 0.01 and tot_ts <= 1:
                from mhs_utils import falar_status
                falar_status("Impossível apagar. Esta é a única figura de compasso do projeto.", imediato=True)
                return True # Retorna True para avisar que a tecla foi tratada (só não foi apagada)
                
            # Remove a mensagem da trilha
            track_0.pop(alvo_idx)
            
            # Repassa o tempo delta da figura apagada para o próximo evento (Para não engolir o tempo da música!)
            if alvo_idx < len(track_0):
                track_0[alvo_idx] = copiar_com_tempo(track_0[alvo_idx], track_0[alvo_idx].time + msg_removida.time)
                
            self.dirty = True
            self.atualizar_titulo()
            self.ler_midi_memoria(reset_canais=False)
            
            from mhs_utils import falar_status
            falar_status(f"Figura de compasso {msg_removida.numerator} por {msg_removida.denominator} removida.", imediato=True)
            return True
            
        return False
    def on_delete_inteligente(self, event):
        """ Roteador do botão Delete/Backspace para decidir o que apagar """
        t_start = getattr(self, 'time_selection_start', None)
        t_end = getattr(self, 'time_selection_end', None)
        
        # Só usa a inteligência se NÃO houver trecho (I/O) selecionado
        if t_start is None or t_end is None or abs(t_start - t_end) < 0.01:
            
            foco = getattr(self, 'foco_inteligente', None)
            
            # 1. Tenta apagar mudança de compasso APENAS se o usuário estiver navegando nelas
            if foco == 'compasso':
                if hasattr(self, 'apagar_formula_compasso_atual') and self.apagar_formula_compasso_atual():
                    return
            
            # 2. Tenta apagar envelope de tempo APENAS se o usuário estiver navegando neles
            elif foco == 'tempo':
                if hasattr(self, 'apagar_envelope_tempo_atual') and self.apagar_envelope_tempo_atual():
                    return 
                
        # Se não apagou controles especiais (ou se não estava com o foco neles), faz a exclusão normal
        if hasattr(self, 'delete_time_selection'):
            self.delete_time_selection(event)
        else:
            event.Skip()
    def atualizar_titulo(self):
        nome = os.path.basename(self.current_midi_path) if self.current_midi_path else "Novo Projeto"
        marca = "*" if self.dirty else ""
        
        if getattr(self, 'esperando_nota', False):
            grav = " [AGUARDANDO MIDI...]"
        elif self.gravando:
            grav = " [GRAVANDO]"
        else:
            grav = ""
        
        if hasattr(self, 'notebook') and self.current_tab_idx >= 0:
            self.notebook.SetPageText(self.current_tab_idx, f"{marca}{nome}")
            
        self.SetTitle(f"{marca}{nome}{grav} - MHS MIDI Sequencer {VERSAO_APP}")

    def checar_salvamento_guia(self):
        if not self.dirty:
            return True
            
        nome = self.notebook.GetPageText(self.current_tab_idx)
        dlg = wx.MessageDialog(self, f"A guia '{nome}' tem alterações não salvas. Deseja salvar agora?", "MHS MIDI Sequencer", wx.YES_NO | wx.CANCEL | wx.ICON_WARNING)
        dlg.SetYesNoCancelLabels("&Sim", "&Não", "&Cancelar")
        res = dlg.ShowModal()
        dlg.Destroy()
        
        if res == wx.ID_YES:
            if self.current_midi_path:
                try:
                    self.salvar_midi(self.current_midi_path)
                    return True
                except:
                    return False
            else:
                wx.CallAfter(self.on_save_as_midi, None)
                return False
        elif res == wx.ID_CANCEL:
            return False
            
        return True

    def ao_fechar_janela(self, event):
        self.save_current_tab_state()
        
        for i, state in enumerate(self.tabs_data):
            if state.dirty:
                self.notebook.SetSelection(i)
                self.notebook.Update()
                if not self.checar_salvamento_guia():
                    if event.CanVeto():
                        event.Veto()
                    return
                    
        # --- Fecha TODAS as múltiplas entradas MIDI com segurança ---
        if hasattr(self, 'midi_inputs'):
            for p in self.midi_inputs:
                try: p.close()
                except: pass
                
        # Ao fechar o programa, devolve o Local Control Ligado - senão o
        # teclado fica mudo nas teclas físicas até alguém lembrar de
        # apertar F8 de novo. Precisa ser antes de fechar a porta.
        self.set_local_control(True)
        if self.output: self.output.close()
        event.Skip()
    def ao_mostrar_tela(self, event):
        if event.IsShown():
            wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
            from mhs_utils import falar_status
            if not getattr(self, 'boas_vindas_faladas', False):
                wx.CallLater(1000, lambda: falar_status("Bem vindo ao MHS Midi Sequencer! Boas produções!", imediato=True))
                wx.CallLater(4500, lambda: self.atualizar_status(True)) 
                self.boas_vindas_faladas = True
            else:
                wx.CallLater(600, lambda: self.atualizar_status(True))
                
        event.Skip()

    def enviar_xg_param(self, ch, prop, val):
        import mido
        if not self.output: return
        # Mapeamento oficial dos endereços do Multi Part da Yamaha XG!
        addr_map = {"Volume": 0x0B, "Pan": 0x0E, "Reverb": 0x13, "Chorus": 0x12, "Grave": 0x72, "Agudo": 0x73}
        if prop in addr_map:
            msg = [0xF0, 0x43, 0x10, 0x4C, 0x08, ch, addr_map[prop], val, 0xF7]
            try:
                self.output.send(mido.Message.from_bytes(msg))
            except: pass
    def enviar_midi_param(self, prop, val, canal=None, is_playback=False):
        import mido
        import time
        ch = canal if canal is not None else self.canal_atual
        
        if not is_playback:
            self.overrides[ch][prop] = val
            if prop == "Patch" and "Bank" not in self.overrides[ch]:
                self.overrides[ch]["Bank"] = self.canais[ch]["Bank"]
            elif prop == "Bank" and "Patch" not in self.overrides[ch]:
                self.overrides[ch]["Patch"] = self.canais[ch]["Patch"]
            
            self.dirty = True
            self.atualizar_titulo()
            
        if not self.output or prop == "Transpose" or prop == "Nome": return
        
        try:
            if prop == "Bank":
                if self.config.get('padrao_midi', 'XG') == 'GM' and ch == 9: return
                msb, lsb = val // 128, val % 128
                self.output.send(mido.Message('control_change', channel=ch, control=0, value=msb))
                self.output.send(mido.Message('control_change', channel=ch, control=32, value=lsb))
                if not is_playback:
                    time.sleep(0.01)
                
                # --- A MÁGICA RECUPERADA AQUI ---
                # O teclado precisa de um "empurrão" (Program Change) para engolir o novo banco na hora!
                patch_atual = self.overrides.get(ch, {}).get("Patch", self.canais[ch].get("Patch", 0))
                self.output.send(mido.Message('program_change', channel=ch, program=patch_atual))
                
            elif prop == "Patch":
                self.output.send(mido.Message('program_change', channel=ch, program=val))
                
            elif prop == "Pitch Bend":
                self.output.send(mido.Message('control_change', channel=ch, control=101, value=0))
                self.output.send(mido.Message('control_change', channel=ch, control=100, value=0))
                self.output.send(mido.Message('control_change', channel=ch, control=6, value=val))
                
            # --- INCLUSÃO DO GRAVE E AGUDO NO ROTEAMENTO ---
            elif prop in ["Volume", "Pan", "Grave", "Agudo", "Expression", "Reverb", "Chorus", "Mono/Poly", "Porta Time"]:
                cc_map = {"Volume": 7, "Pan": 10, "Expression": 11, "Reverb": 91, "Chorus": 93, "Porta Time": 5}
                if prop in cc_map:
                    self.output.send(mido.Message('control_change', channel=ch, control=cc_map[prop], value=val))
                if prop == "Porta Time":
                    self.output.send(mido.Message('control_change', channel=ch, control=65, value=127 if val > 0 else 0))
                elif prop == "Mono/Poly":
                    self.output.send(mido.Message('control_change', channel=ch, control=127 if val else 126, value=0 if val else 1))
                if prop not in ["Mono/Poly", "Porta Time"]:
                    self.enviar_xg_param(ch, prop, val)
        except: pass
    def carregar_configuracoes(self):
        self.config = {'porta_in': '', 'porta_out': '', 'arquivos_ins': [], 'ins_selecionado': 0, 'ins_instrumento': '', 'recentes': []}
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f: 
                    dados_salvos = json.load(f)
                    self.config.update(dados_salvos)
        except Exception:
            pass
            
        self.config.setdefault('padrao_midi', 'XG')
        self.config.setdefault('verificar_atualizacoes', True)
        self.config.setdefault('metro_note_down', 22)
        self.config.setdefault('metro_vel_down', 100)
        self.config.setdefault('metro_note_beat', 21)
        self.config.setdefault('metro_vel_beat', 100)
        self.config.setdefault('metro_out', '')
        self.config.setdefault('metro_volume', 100)

        try:
            buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(None, 13, None, 0, buf) 
            pasta_musicas = buf.value
        except Exception:
            pasta_musicas = os.path.join(os.path.expanduser('~'), 'Music')

        pasta_mhs = os.path.join(pasta_musicas, "MHS MIDI Sequencer")
        
        try:
            if not os.path.exists(pasta_mhs):
                os.makedirs(pasta_mhs)
        except:
            pasta_mhs = pasta_musicas

        if 'pasta_abrir' not in self.config or not self.config['pasta_abrir']:
            self.config['pasta_abrir'] = pasta_mhs
        if 'pasta_salvar' not in self.config or not self.config['pasta_salvar']:
            self.config['pasta_salvar'] = pasta_mhs

        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except: pass

    def carregar_ins_ativo(self):
        idx = self.config.get('ins_selecionado', 0)
        arquivos = self.config.get('arquivos_ins', [])
        if idx is not None and idx < len(arquivos) and os.path.exists(arquivos[idx]):
            self.parse_ins_file(arquivos[idx])

    def parse_ins_file(self, path):
        self.instrument_names = {}
        self.bank_names = {}
        self.key_names = {} 
        self.controller_names = {} 
        
        try:
            with open(path, 'r', encoding='latin-1') as f:
                sections = {}
                current_section = None
                for line in f:
                    line = line.strip()
                    if not line or line.startswith(';'): continue
                    
                    sec_match = re.match(r'^\[(.*)\]$', line)
                    if sec_match:
                        current_section = sec_match.group(1).strip()
                        if current_section not in sections:
                            sections[current_section] = {}
                        continue
                    
                    if current_section and '=' in line:
                        parts = line.split('=', 1)
                        if len(parts) == 2:
                            sections[current_section][parts[0].strip()] = parts[1].strip()

            instrument_target = self.config.get('ins_instrumento')
            if not instrument_target or instrument_target not in sections:
                for sec_name, items in sections.items():
                    if any('patch[' in k.lower() for k in items.keys()):
                        instrument_target = sec_name
                        break
            
            if instrument_target and instrument_target in sections:
                patch_lists = {}
                control_lists = {} 
                
                for key, val in sections[instrument_target].items():
                    key_lower = key.lower()
                    
                    patch_match = re.search(r'patch\[\s*(\d+)\s*\]', key_lower)
                    if patch_match:
                        bank_num = int(patch_match.group(1))
                        patch_lists[bank_num] = val
                        self.bank_names[bank_num] = val
                        continue
                    
                    control_match = re.search(r'control\[\s*(\d+)\s*\]', key_lower)
                    if control_match:
                        bank_num = int(control_match.group(1))
                        control_lists[bank_num] = val
                        continue
                            
                    key_match = re.search(r'key\[\s*(\d+)\s*,\s*(\d+)\s*\]', key_lower)
                    if key_match:
                        bank_num = int(key_match.group(1))
                        patch_num = int(key_match.group(2))
                        if val in sections:
                            if (bank_num, patch_num) not in self.key_names:
                                self.key_names[(bank_num, patch_num)] = {}
                            for k_note, v_name in sections[val].items():
                                if k_note.isdigit():
                                    self.key_names[(bank_num, patch_num)][int(k_note)] = v_name
                            
                for bank_num, list_name in patch_lists.items():
                    self.instrument_names[bank_num] = {}
                    if list_name in sections:
                        for k, v in sections[list_name].items():
                            if k.isdigit():
                                self.instrument_names[bank_num][int(k)] = v
                
                for bank_num, list_name in control_lists.items():
                    self.controller_names[bank_num] = {}
                    if list_name in sections:
                        for k, v in sections[list_name].items():
                            if k.isdigit():
                                self.controller_names[bank_num][int(k)] = v

        except Exception as e:
            pass

    def gerar_canal_vazio(self, num):
        banco_inicial = 16256 if num == 10 else 0
        return {"Nome": f"Track {num}", "Input": 1, "Mute": False, "Solo": False, "Arm": False,
                "Volume": 100, "Pan": 64, "Grave": 64, "Agudo": 64, "Expression": 127, 
                "Bank": banco_inicial, "Patch": 0, "Reverb": 0, "Chorus": 0, "Transpose": 0, "Pitch Bend": 2, "Mono/Poly": True, "Porta Time": 0, "VoiceCreator": {}}
    def conectar_midi(self, portas_in_salvas, nome_porta_out):
        import mido

        # --- CONECTANDO MÚLTIPLAS ENTRADAS (MIDI IN) ---
        if not hasattr(self, 'midi_inputs'):
            self.midi_inputs = []
            
        # Fecha as conexões antigas de forma segura
        for port in self.midi_inputs:
            try: port.close()
            except: pass
        self.midi_inputs.clear()
        
        # Garante que as portas salvas sejam interpretadas como uma lista
        if isinstance(portas_in_salvas, str):
            portas_in_salvas = [portas_in_salvas] if portas_in_salvas else []

        disponiveis_in = mido.get_input_names()
        for nome_salvo in portas_in_salvas:
            porta_certa = achar_porta_certa(nome_salvo, disponiveis_in)
            if porta_certa:
                try:
                    # Abre a porta e joga pra mesma função on_midi_in!
                    novo_in = mido.open_input(porta_certa, callback=self.on_midi_in)
                    self.midi_inputs.append(novo_in)
                except: pass

        # --- CONECTANDO A SAÍDA (MIDI OUT) BLINDADA ---
        try:
            if getattr(self, 'output', None):
                self.output.close()
            
            disponiveis_out = mido.get_output_names()
            porta_out_certa = achar_porta_certa(nome_porta_out, disponiveis_out)
            
            if porta_out_certa:
                self.output = mido.open_output(porta_out_certa)
        except: pass

    def conectar_midi_metronomo(self):
        # Porta MIDI separada, só pro metrônomo (canal 10), igual ao Style
        # Creator: se não for escolhida nenhuma (config['metro_out'] vazio),
        # o clique continua saindo pela porta principal, sem mudar nada.
        import mido

        if self.output_metronomo:
            try: self.output_metronomo.close()
            except: pass
            self.output_metronomo = None

        nome_porta = self.config.get('metro_out', '')
        if not nome_porta:
            return

        try:
            porta_certa = achar_porta_certa(nome_porta, mido.get_output_names())
            if porta_certa:
                self.output_metronomo = mido.open_output(porta_certa)
                self.enviar_setup_metronomo()
        except: pass

    def enviar_setup_metronomo(self):
        # Bank 16256 (MSB 127/LSB 0), Patch 0, Reverb 0, Chorus 0 fixos, e o
        # Volume do Metrônomo configurado - tudo no canal 10 (índice 9),
        # mandado só na porta separada do metrônomo.
        porta = self.output_metronomo
        if not porta:
            return
        volume = self.config.get('metro_volume', 100)
        bank = 16256
        try:
            porta.send(mido.Message('control_change', channel=9, control=0, value=bank // 128))
            porta.send(mido.Message('control_change', channel=9, control=32, value=bank % 128))
            porta.send(mido.Message('program_change', channel=9, program=0))
            porta.send(mido.Message('control_change', channel=9, control=7, value=volume))
            porta.send(mido.Message('control_change', channel=9, control=91, value=0))
            porta.send(mido.Message('control_change', channel=9, control=93, value=0))
        except: pass

    def update_recent_menu(self):
        for item in self.recent_menu.GetMenuItems():
            self.recent_menu.DestroyItem(item)
            
        recentes = self.config.get('recentes', [])
        self.recent_mappings = {}
        
        if not recentes:
            item = self.recent_menu.Append(wx.ID_ANY, "Vazio")
            item.Enable(False)
        else:
            for i, path in enumerate(recentes):
                m_id = 3000 + i
                self.recent_mappings[m_id] = path
                item = self.recent_menu.Append(m_id, f"{i+1} - {os.path.basename(path)}")
                self.Bind(wx.EVT_MENU, self.on_open_recent, item)

    def add_to_recent(self, path):
        recentes = self.config.get('recentes', [])
        if path in recentes:
            recentes.remove(path)
        recentes.insert(0, path)
        recentes = recentes[:10]
        self.config['recentes'] = recentes
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except: pass
        wx.CallAfter(self.update_recent_menu)

    def init_ui(self):
        self.notebook = wx.Notebook(self)
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGING, self.on_tab_changing)
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_tab_changed)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.notebook, 1, wx.EXPAND)
        self.SetSizer(sizer)
        
        menubar = wx.MenuBar()
        f_menu = wx.Menu()
        new_item = f_menu.Append(wx.ID_NEW, "Novo\tCtrl+N")
        nova_guia_item = f_menu.Append(wx.ID_ANY, "Nova Guia\tCtrl+Shift+N")
        fechar_guia_item = f_menu.Append(wx.ID_ANY, "Fechar Guia\tCtrl+F4")
        load_item = f_menu.Append(wx.ID_OPEN, "Carregar MIDI\tCtrl+O")
        self.recent_menu = wx.Menu()
        f_menu.AppendSubMenu(self.recent_menu, "Arquivos &Recentes")
        save_item = f_menu.Append(wx.ID_SAVE, "Salvar\tCtrl+S")
        save_as_item = f_menu.Append(wx.ID_SAVEAS, "Salvar como...\tCtrl+Shift+S")
        
        edit_menu = wx.Menu()
        undo_item = edit_menu.Append(wx.ID_UNDO, "Desfazer\tCtrl+Z")
        sel_all_item = edit_menu.Append(134, "Selecionar Todos os Canais\tCtrl+A")
        clone_cfg_item = edit_menu.Append(148, "Clonar Configurações do Canal para...\tCtrl+L")
        edit_menu.AppendSeparator()
        redo_item = edit_menu.Append(wx.ID_REDO, "Refazer\tCtrl+Shift+Z")
        ev_list_item = edit_menu.Append(150, "Event List (Lista de Eventos)...\tCtrl+E")
        del_sel_item = edit_menu.Append(160, "Apagar Seleção de Tempo\tDel")
        
        transp_menu = wx.Menu()
        play_item = transp_menu.Append(105, "Reproduzir / Parar\tSpace")
        pause_item = transp_menu.Append(106, "Pausar / Retomar\tCtrl+Space")
        rec_item = transp_menu.Append(116, "Gravar\tR")
        rec_sync_item = transp_menu.Append(137, "Gravar (Aguardar Nota)\tCtrl+R")
        mark_in_item = transp_menu.Append(161, "Marcar Início da Seleção (IN)\tI")
        mark_out_item = transp_menu.Append(162, "Marcar Fim da Seleção (OUT)\tO")
        transp_menu.AppendSeparator()
        transp_menu.Append(260, "Panic (Desligar Notas Presas)\tF3")
        transp_menu.Append(261, "Reset Geral do Teclado\tCtrl+F3")
        
        tool_menu = wx.Menu()
        audio_guia_item = tool_menu.Append(165, "Áudio Guia / Playback...\tCtrl+G")
        tool_menu.Append(243, "Mutar Áudio Guia\tCtrl+Alt+M")
        tool_menu.Append(244, "Adiantar Áudio Guia (1ms)\tAlt+Shift+Left")
        tool_menu.Append(245, "Atrasar Áudio Guia (1ms)\tAlt+Shift+Right")
        tool_menu.Append(246, "Adiantar Áudio Guia (5ms)\tCtrl+Alt+Shift+Left")
        tool_menu.Append(247, "Atrasar Áudio Guia (5ms)\tCtrl+Alt+Shift+Right")
        tool_menu.AppendSeparator()
        
        ripple_item = tool_menu.Append(127, "Ripple Editing...\tCtrl+Shift+P")
        metro_item = tool_menu.Append(117, "Metrônomo\tCtrl+M")
        bpm_item = tool_menu.Append(120, "Envelope de Tempo (BPM)...\tShift+C")
        env_cc_item = tool_menu.Append(125, "Envelope de Automação de CC...\tShift+E")
        fade_item = tool_menu.Append(144, "Fade In / Fade Out (Expression)...\tCtrl+Shift+F")
        ts_item = tool_menu.Append(126, "Figura de Compasso (Time Signature)...\tCtrl+Shift+M")
        inc_bpm = tool_menu.Append(121, "Aumentar Tempo (+1)\tCtrl++")
        dec_bpm = tool_menu.Append(122, "Diminuir Tempo (-1)\tCtrl+-")
        quant_off_item = tool_menu.Append(140, "Quantização Offline...\tCtrl+Q")
        quant_rt_item = tool_menu.Append(141, "Quantização Tempo Real (Input)...\tQ")
        humanize_item = tool_menu.Append(142, "Humanizar...\tH")
        fx_midi_item = tool_menu.Append(143, "Efeitos MIDI Offline (Arpejo, Delay, Harpa, Bateria)...\tCtrl+K")
        drum_setup_item = tool_menu.Append(198, "Drum Setup Yamaha XG...\tCtrl+D")
        
        o_menu = wx.Menu()
        sysex_item = o_menu.Append(136, "Editor de SysEx Raiz...\tCtrl+Shift+Y")
        sysex_list_item = o_menu.Append(138, "Gerenciador de SysEx Existentes...\tCtrl+Shift+X")
        vc_item = o_menu.Append(147, "Voice Creator (Edição de Timbre)...\tCtrl+T")
        vel_ctrl_item = o_menu.Append(128, "Velocity Midi Control...\tCtrl+Shift+V")
        midi_conv_item = o_menu.Append(129, "Conversor MIDI (Midi Convert to CC)...\tCtrl+Shift+C")
        dsp_item = o_menu.Append(145, "Efeitos DSP Globais (Reverb e Chorus)...\tCtrl+Shift+D")
        dsp_insert_item = o_menu.Append(146, "Efeito de Inserção DSP (Variation) do Canal...\tCtrl+Shift+I")
        local_ctrl_item = o_menu.Append(194, "Som Local do Teclado (Local Control)\tF8")
        # ID 248 (não 241!) - o 241 já era usado por aumentar_vol_audio (Ctrl+
        # Alt+Seta Cima, junto com 242/243/244-247 do Áudio Guia). Os dois
        # binds em cima do MESMO id faziam o wx só chamar o último (aumentar_
        # vol_audio) - "Registrar MIDI de Entrada" nunca rodava de verdade,
        # por isso o midi_in_log.txt nunca era criado (achado quando o Michel
        # reportou "marco, mudo o timbre, desmarco" e o arquivo não aparecia).
        self.item_log_midi = o_menu.AppendCheckItem(248, "Registrar MIDI de Entrada (arquivo de log)")
        pref_item = o_menu.Append(wx.ID_PREFERENCES, "Preferências\tCtrl+P")
        
        menubar.Append(f_menu, "Arquivo")
        menubar.Append(edit_menu, "Editar")
        menubar.Append(transp_menu, "Transporte")
        menubar.Append(tool_menu, "Ferramentas")
        voz_menu = wx.Menu()
        voz_menu.Append(330, "Importar Voz (.vce, .drm, .mgv, .sar, .liv) para o Canal Atual...")
        voz_menu.Append(331, "Exportar Voz do Canal Atual (.vce, .drm, .mgv, .sar, .liv)...")
        menubar.Append(voz_menu, "Vozes")
        menubar.Append(o_menu, "Opções")

        ajuda_menu = wx.Menu()
        ajuda_menu.Append(360, "&Novidades desta Versão...")
        ajuda_menu.Append(361, "&Ir para a Página do Projeto")
        self.Bind(wx.EVT_MENU, self.OnMostrarNovidades, id=360)
        self.Bind(wx.EVT_MENU, self.OnAbrirPaginaProjeto, id=361)
        menubar.Append(ajuda_menu, "Aj&uda")

        self.SetMenuBar(menubar)
        
        self.Bind(wx.EVT_MENU, self.on_new_midi, id=wx.ID_NEW)
        self.Bind(wx.EVT_MENU, self.on_nova_guia, id=181)
        self.Bind(wx.EVT_MENU, self.on_fechar_guia, id=180)
        self.Bind(wx.EVT_MENU, self.on_load_midi, id=wx.ID_OPEN)
        self.Bind(wx.EVT_MENU, self.on_save_midi, id=wx.ID_SAVE)
        self.Bind(wx.EVT_MENU, self.on_save_as_midi, id=wx.ID_SAVEAS)
        self.Bind(wx.EVT_MENU, self.undo, id=wx.ID_UNDO)
        self.Bind(wx.EVT_MENU, self.redo, id=wx.ID_REDO)
        self.Bind(wx.EVT_MENU, self.selecionar_todos_canais, id=134)
        self.Bind(wx.EVT_MENU, self.abrir_clonar_config, id=148)
        self.Bind(wx.EVT_MENU, self.abrir_event_list, id=150)
        self.Bind(wx.EVT_MENU, self.delete_time_selection, id=160)
        self.Bind(wx.EVT_MENU, self.toggle_reproducao, id=105)
        self.Bind(wx.EVT_MENU, self.toggle_pausa, id=106)
        self.Bind(wx.EVT_MENU, self.toggle_gravacao, id=116)
        self.Bind(wx.EVT_MENU, self.toggle_gravacao_espera, id=137)
        self.Bind(wx.EVT_MENU, self.mark_selection_start, id=161)
        self.Bind(wx.EVT_MENU, self.mark_selection_end, id=162)
        self.Bind(wx.EVT_MENU, self.abrir_audio_guia, id=165)
        self.Bind(wx.EVT_MENU, self.abrir_ripple_editing, id=127)
        self.Bind(wx.EVT_MENU, self.toggle_metronomo, id=117)
        self.Bind(wx.EVT_MENU, self.abrir_envelope_tempo, id=120)
        self.Bind(wx.EVT_MENU, self.abrir_envelope_cc, id=125)
        self.Bind(wx.EVT_MENU, self.abrir_fade, id=144)
        self.Bind(wx.EVT_MENU, self.abrir_time_signature, id=126)
        self.Bind(wx.EVT_MENU, lambda e: self.change_tempo(amount=1), id=121)
        self.Bind(wx.EVT_MENU, lambda e: self.change_tempo(amount=-1), id=122)
        self.Bind(wx.EVT_MENU, self.abrir_quantizacao_offline, id=140)
        self.Bind(wx.EVT_MENU, self.abrir_quantizacao_realtime, id=141)
        self.Bind(wx.EVT_MENU, self.abrir_humanizar, id=142)
        self.Bind(wx.EVT_MENU, self.abrir_efeitos_midi, id=143)
        self.Bind(wx.EVT_MENU, self.abrir_drum_setup, id=198)
        self.Bind(wx.EVT_MENU, self.abrir_editor_sysex, id=136)
        self.Bind(wx.EVT_MENU, self.abrir_lista_sysex, id=138)
        self.Bind(wx.EVT_MENU, self.abrir_voice_creator, id=147)
        self.Bind(wx.EVT_MENU, self.abrir_velocity_control, id=128)
        self.Bind(wx.EVT_MENU, self.abrir_conversor_midi, id=129)
        self.Bind(wx.EVT_MENU, self.abrir_efeitos_globais, id=145)
        self.Bind(wx.EVT_MENU, self.abrir_variation_dsp, id=146)
        self.Bind(wx.EVT_MENU, self.toggle_local_control, id=194)
        self.Bind(wx.EVT_MENU, self.on_toggle_midi_log, id=248)
        self.Bind(wx.EVT_MENU, self.abrir_preferencias, id=wx.ID_PREFERENCES)
        
        self.Bind(wx.EVT_MENU, lambda e: self.ajustar_offset_audio(-0.001), id=244)
        self.Bind(wx.EVT_MENU, lambda e: self.ajustar_offset_audio(0.001), id=245)
        self.Bind(wx.EVT_MENU, lambda e: self.ajustar_offset_audio(-0.005), id=246)
        self.Bind(wx.EVT_MENU, lambda e: self.ajustar_offset_audio(0.005), id=247)
        self.Bind(wx.EVT_MENU, self.mutar_audio, id=243)
        self.Bind(wx.EVT_MENU, self.acao_panic, id=260)
        self.Bind(wx.EVT_MENU, self.reset_geral_teclado, id=261)
        self.Bind(wx.EVT_MENU, self.importar_voz_canal, id=330)
        self.Bind(wx.EVT_MENU, self.exportar_voz_canal, id=331)
        
        self.update_recent_menu()
    def on_panel_char(self, event):
        code = event.GetKeyCode()
        ctrl = event.ControlDown()
        alt = event.AltDown()
        shift = event.ShiftDown()

        if code in [ord('M'), ord('m')] and ctrl and alt and not shift:
            self.mutar_audio(None)
            return

        if alt and shift and not ctrl:
            if code == wx.WXK_LEFT:
                self.ajustar_offset_audio(-0.001)
                return
            elif code == wx.WXK_RIGHT:
                self.ajustar_offset_audio(0.001)
                return

        if ctrl and alt and shift:
            if code == wx.WXK_LEFT:
                self.ajustar_offset_audio(-0.005)
                return
            elif code == wx.WXK_RIGHT:
                self.ajustar_offset_audio(0.005)
                return

        if code in [ord('C'), ord('c'), ord('E'), ord('e')] and not (ctrl or alt or shift):
            return
        event.Skip()

    def acao_panic(self, event):
        self.all_notes_off()
        from mhs_utils import falar_status
        falar_status("Panic. Todas as notas desligadas.", imediato=True)

    def reset_geral_teclado(self, event):
        self.enviar_reset_fisico_teclado()
        from mhs_utils import falar_status
        falar_status("Reset Geral enviado! O teclado foi completamente zerado.", imediato=True)
    def setup_shortcuts(self):
        entries = [
            (wx.ACCEL_NORMAL, wx.WXK_UP, 101), (wx.ACCEL_NORMAL, wx.WXK_DOWN, 102),
            (wx.ACCEL_NORMAL, wx.WXK_LEFT, 103), (wx.ACCEL_NORMAL, wx.WXK_RIGHT, 104),
            (wx.ACCEL_NORMAL, wx.WXK_SPACE, 105), (wx.ACCEL_CTRL, wx.WXK_SPACE, 106),
            (wx.ACCEL_NORMAL, wx.WXK_RETURN, 107), (wx.ACCEL_NORMAL, ord('+'), 108),
            (wx.ACCEL_NORMAL, ord('-'), 109), (wx.ACCEL_NORMAL, wx.WXK_PAGEUP, 110),
            (wx.ACCEL_NORMAL, wx.WXK_PAGEDOWN, 111), (wx.ACCEL_CTRL, wx.WXK_PAGEUP, 112),
            (wx.ACCEL_CTRL, wx.WXK_PAGEDOWN, 113), (wx.ACCEL_CTRL, wx.WXK_HOME, 114),
            (wx.ACCEL_NORMAL, ord('W'), 114), (wx.ACCEL_CTRL, wx.WXK_END, 115),
            (wx.ACCEL_NORMAL, ord('R'), 116), (wx.ACCEL_CTRL, ord('R'), 137),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('R'), 139),
            (wx.ACCEL_CTRL, ord('M'), 117), (wx.ACCEL_NORMAL, wx.WXK_TAB, 118),
            (wx.ACCEL_SHIFT, wx.WXK_TAB, 118), (wx.ACCEL_NORMAL, wx.WXK_F2, 193),
            (wx.ACCEL_NORMAL, wx.WXK_F3, 260),
            (wx.ACCEL_CTRL, wx.WXK_F3, 261),
            (wx.ACCEL_NORMAL, wx.WXK_F5, 195), (wx.ACCEL_NORMAL, wx.WXK_F6, 196),
            (wx.ACCEL_NORMAL, wx.WXK_F7, 197), (wx.ACCEL_NORMAL, wx.WXK_F8, 194),
            (wx.ACCEL_SHIFT, wx.WXK_UP, 131), (wx.ACCEL_SHIFT, wx.WXK_DOWN, 132),
            (wx.ACCEL_SHIFT, wx.WXK_SPACE, 133), (wx.ACCEL_SHIFT, wx.WXK_ESCAPE, 170),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, wx.WXK_SPACE, 250),
            (wx.ACCEL_CTRL | wx.ACCEL_ALT, wx.WXK_UP, 241),
            (wx.ACCEL_CTRL | wx.ACCEL_ALT, wx.WXK_DOWN, 242),
            (wx.ACCEL_CTRL | wx.ACCEL_ALT, ord('M'), 243),
            (wx.ACCEL_ALT, wx.WXK_F5, 225), (wx.ACCEL_ALT, wx.WXK_F6, 226), (wx.ACCEL_ALT, wx.WXK_F7, 227),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, wx.WXK_F5, 215), (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, wx.WXK_F6, 216), (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, wx.WXK_F7, 217),
            (wx.ACCEL_SHIFT, ord('C'), 120), (wx.ACCEL_SHIFT, ord('E'), 125),
            
            # --- ATALHOS DE ENVELOPE DE TEMPO (BPM) ---
            (wx.ACCEL_SHIFT, 199, 340), # Shift + Ç (Anterior)
            (wx.ACCEL_SHIFT, 231, 340), # Shift + ç (Anterior minúsculo)
            (wx.ACCEL_SHIFT, 94, 341),  # Shift + ^ (Próximo)
            (wx.ACCEL_SHIFT, 126, 341), # Shift + ~ (Próximo)

            # --- ATALHOS DE FÓRMULA DE COMPASSO (Time Signature) ---
            (wx.ACCEL_CTRL, 199, 342), # Ctrl + Ç (Anterior)
            (wx.ACCEL_CTRL, 231, 342), # Ctrl + ç (Anterior minúsculo)
            (wx.ACCEL_CTRL, 94, 343),  # Ctrl + ^ (Próximo)
            (wx.ACCEL_CTRL, 126, 343), # Ctrl + ~ (Próximo)
            
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('F'), 144),
            (wx.ACCEL_CTRL, ord('L'), 148), 
            (wx.ACCEL_CTRL, ord('A'), 134), (wx.ACCEL_CTRL, ord('Z'), wx.ID_UNDO),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('Z'), wx.ID_REDO), (wx.ACCEL_CTRL, ord('E'), 150),
            (wx.ACCEL_NORMAL, wx.WXK_DELETE, 160), (wx.ACCEL_NORMAL, wx.WXK_BACK, 160), 
            (wx.ACCEL_NORMAL, ord('I'), 161),
            (wx.ACCEL_NORMAL, ord('O'), 162), (wx.ACCEL_NORMAL, wx.WXK_HOME, 163),
            (wx.ACCEL_NORMAL, wx.WXK_END, 164), (wx.ACCEL_CTRL, ord('G'), 165),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('T'), 230), (wx.ACCEL_CTRL, wx.WXK_F4, 180),
            (wx.ACCEL_CTRL, ord('W'), 180), (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('N'), 181),
            (wx.ACCEL_CTRL, ord('C'), wx.ID_COPY), (wx.ACCEL_CTRL, ord('X'), wx.ID_CUT),
            (wx.ACCEL_CTRL, ord('V'), wx.ID_PASTE), (wx.ACCEL_SHIFT, ord('V'), 251),
            (wx.ACCEL_CTRL, ord('F'), 265),
            (wx.ACCEL_CTRL, ord('D'), 198), (wx.ACCEL_NORMAL, wx.WXK_MENU, 199),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('X'), 138), (wx.ACCEL_CTRL, ord('T'), 147), (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('I'), 146),
            (wx.ACCEL_CTRL, wx.WXK_UP, 280), (wx.ACCEL_CTRL, wx.WXK_DOWN, 281),
            (wx.ACCEL_CTRL, wx.WXK_LEFT, 282), (wx.ACCEL_CTRL, wx.WXK_RIGHT, 283),
            (wx.ACCEL_SHIFT, ord('M'), 290),
            
            # --- ATALHOS DO NUDGE (Andar com o MIDI) ---
            (wx.ACCEL_NORMAL, ord(','), 310), (wx.ACCEL_SHIFT, ord(','), 311),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord(','), 312), (wx.ACCEL_ALT, ord(','), 313),
            (wx.ACCEL_CTRL | wx.ACCEL_ALT, ord(','), 314),
            (wx.ACCEL_NORMAL, ord('.'), 320), (wx.ACCEL_SHIFT, ord('.'), 321),
            (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('.'), 322), (wx.ACCEL_ALT, ord('.'), 323),
            (wx.ACCEL_CTRL | wx.ACCEL_ALT, ord('.'), 324),

            # --- TAP TEMPO (mesma tecla T já usada dentro do Áudio Guia,
            # agora também funciona na tela principal) ---
            (wx.ACCEL_NORMAL, ord('T'), 350), (wx.ACCEL_SHIFT, ord('T'), 351)
        ]
        self.SetAcceleratorTable(wx.AcceleratorTable(entries))
        
        self.Bind(wx.EVT_MENU, self.navegar_canais, id=101, id2=102)
        self.Bind(wx.EVT_MENU, self.navegar_canais_shift, id=131, id2=132)
        self.Bind(wx.EVT_MENU, self.toggle_selecao_canal, id=133)
        self.Bind(wx.EVT_MENU, self.limpar_selecoes, id=170)
        self.Bind(wx.EVT_MENU, self.relatar_selecoes, id=250)
        self.Bind(wx.EVT_MENU, self.navegar_propriedades, id=103, id2=104)
        self.Bind(wx.EVT_MENU, self.acao_enter, id=107)
        self.Bind(wx.EVT_MENU, self.alterar_valor, id=108, id2=109)
        self.Bind(wx.EVT_MENU, self.renomear_canal, id=193)
        self.Bind(wx.EVT_MENU, getattr(self, 'on_f3_panic', lambda x: None), id=260)
        self.Bind(wx.EVT_MENU, getattr(self, 'on_ctrl_f3_reset', lambda x: None), id=261)
        self.Bind(wx.EVT_MENU, self.toggle_gravacao, id=116)
        self.Bind(wx.EVT_MENU, self.toggle_gravacao_espera, id=137)
        self.Bind(wx.EVT_MENU, getattr(self, 'abrir_preroll', lambda x: None), id=139)
        self.Bind(wx.EVT_MENU, self.toggle_metronomo, id=117)
        self.Bind(wx.EVT_MENU, self.repetir_status_tab, id=118)
        self.Bind(wx.EVT_MENU, lambda e: self.toggle_propriedade_direta("Mute"), id=195)
        self.Bind(wx.EVT_MENU, lambda e: self.toggle_propriedade_direta("Solo"), id=196)
        self.Bind(wx.EVT_MENU, lambda e: self.toggle_propriedade_direta("Arm"), id=197)
        self.Bind(wx.EVT_MENU, self.aumentar_vol_audio, id=241)
        self.Bind(wx.EVT_MENU, self.diminuir_vol_audio, id=242)
        self.Bind(wx.EVT_MENU, self.mutar_audio, id=243)
        self.Bind(wx.EVT_MENU, lambda e: self.contar_estado("Mute", "mutados"), id=215)
        self.Bind(wx.EVT_MENU, lambda e: self.contar_estado("Solo", "solados"), id=216)
        self.Bind(wx.EVT_MENU, lambda e: self.contar_estado("Arm", "armados"), id=217)
        self.Bind(wx.EVT_MENU, lambda e: self.limpar_estado("Mute", "mutes desligados"), id=225)
        self.Bind(wx.EVT_MENU, lambda e: self.limpar_estado("Solo", "solos desligados"), id=226)
        self.Bind(wx.EVT_MENU, lambda e: self.limpar_estado("Arm", "desarmados"), id=227)
        self.Bind(wx.EVT_MENU, self.toggle_local_control, id=194)
        self.Bind(wx.EVT_MENU, getattr(self, 'abrir_envelope_tempo', lambda x: None), id=120)
        self.Bind(wx.EVT_MENU, getattr(self, 'abrir_envelope_cc', lambda x: None), id=125)
        self.Bind(wx.EVT_MENU, getattr(self, 'abrir_fade', lambda x: None), id=144)
        self.Bind(wx.EVT_MENU, getattr(self, 'abrir_clonar_config', lambda x: None), id=148)
        self.Bind(wx.EVT_MENU, self.selecionar_todos_canais, id=134)
        self.Bind(wx.EVT_MENU, getattr(self, 'abrir_event_list', lambda x: None), id=150)
        
        # O Roteamento Dinâmico do Backspace e Delete
        self.Bind(wx.EVT_MENU, getattr(self, 'on_delete_inteligente', lambda x: None), id=160)
        
        self.Bind(wx.EVT_MENU, getattr(self, 'mark_selection_start', lambda x: None), id=161)
        self.Bind(wx.EVT_MENU, getattr(self, 'mark_selection_end', lambda x: None), id=162)
        self.Bind(wx.EVT_MENU, getattr(self, 'ir_para_inicio_selecao', lambda x: None), id=163)
        self.Bind(wx.EVT_MENU, getattr(self, 'ir_para_fim_selecao', lambda x: None), id=164)
        self.Bind(wx.EVT_MENU, getattr(self, 'abrir_audio_guia', lambda x: None), id=165)
        self.Bind(wx.EVT_MENU, getattr(self, 'abrir_tempo_preciso', lambda x: None), id=230)
        self.Bind(wx.EVT_MENU, self.on_fechar_guia, id=180)
        self.Bind(wx.EVT_MENU, getattr(self, 'on_nova_guia', lambda x: None), id=181)
        self.Bind(wx.EVT_MENU, self.on_copy, id=wx.ID_COPY)
        self.Bind(wx.EVT_MENU, getattr(self, 'on_cut', lambda x: None), id=wx.ID_CUT)
        self.Bind(wx.EVT_MENU, self.on_paste, id=wx.ID_PASTE)
        self.Bind(wx.EVT_MENU, getattr(self, 'on_paste_repeat', lambda x: None), id=251)
        self.Bind(wx.EVT_MENU, getattr(self, 'on_ir_para_compasso', lambda x: None), id=265)
        self.Bind(wx.EVT_MENU, getattr(self, 'abrir_drum_setup', lambda x: None), id=198)
        self.Bind(wx.EVT_MENU, getattr(self, 'abrir_propriedades_canal', lambda x: None), id=199)
        self.Bind(wx.EVT_MENU, getattr(self, 'transpor_midi_in', lambda x: None), id=280, id2=283)
        
        # --- BINDS DO NUDGE (Trás e Frente) ---
        self.Bind(wx.EVT_MENU, lambda e: self.mover_midi_tempo(-1, False, False, False), id=310)
        self.Bind(wx.EVT_MENU, lambda e: self.mover_midi_tempo(-1, False, True, False), id=311)
        self.Bind(wx.EVT_MENU, lambda e: self.mover_amo_midi_tempo(-1, True, True, False), id=312)
        self.Bind(wx.EVT_MENU, lambda e: self.mover_midi_tempo(-1, False, False, True), id=313)
        self.Bind(wx.EVT_MENU, lambda e: self.mover_midi_tempo(-1, True, False, True), id=314)
        
        self.Bind(wx.EVT_MENU, lambda e: self.mover_midi_tempo(1, False, False, False), id=320)
        self.Bind(wx.EVT_MENU, lambda e: self.mover_midi_tempo(1, False, True, False), id=321)
        self.Bind(wx.EVT_MENU, lambda e: self.mover_midi_tempo(1, True, True, False), id=322)
        self.Bind(wx.EVT_MENU, lambda e: self.mover_midi_tempo(1, False, False, True), id=323)
        self.Bind(wx.EVT_MENU, lambda e: self.mover_midi_tempo(1, True, False, True), id=324)

        # --- Binds dos Envelopes de Tempo e Compasso ---
        self.Bind(wx.EVT_MENU, lambda e: getattr(self, 'navegar_envelope_tempo', lambda x: None)(-1), id=340)
        self.Bind(wx.EVT_MENU, self.editar_envelope_tempo_atual, id=351)
        self.Bind(wx.EVT_MENU, lambda e: getattr(self, 'navegar_envelope_tempo', lambda x: None)(1), id=341)
        
        self.Bind(wx.EVT_MENU, lambda e: getattr(self, 'navegar_formula_compasso', lambda x: None)(-1), id=342)
        self.Bind(wx.EVT_MENU, lambda e: getattr(self, 'navegar_formula_compasso', lambda x: None)(1), id=343)

        for i in range(110, 116):
            self.Bind(wx.EVT_MENU, getattr(self, 'buscar_posicao', lambda x: None), id=i)
            
        self.Bind(wx.EVT_MENU, getattr(self, 'abrir_inserir_compassos', lambda x: None), id=290)
        self.Bind(wx.EVT_MENU, self.do_tap_tempo, id=350)
    def on_f3_panic(self, event):
        if hasattr(self, 'all_notes_off'):
            self.all_notes_off()
        from mhs_utils import falar_status
        falar_status("Notas desligadas", imediato=True)

    def on_ctrl_f3_reset(self, event):
        if getattr(self, 'output', None):
            import mido
            import time
            try:
                self.output.send(mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x00, 0x00, 0x7E, 0x00, 0xF7]))
                time.sleep(0.05)
            except: pass
            
            if hasattr(self, 'all_notes_off'):
                self.all_notes_off()
                
        from mhs_utils import falar_status
        falar_status("Teclado resetado", imediato=True)
    def on_next_tab(self, event):
        total = self.notebook.GetPageCount()
        if total > 1:
            current = self.notebook.GetSelection()
            next_page = (current + 1) % total
            self.notebook.SetSelection(next_page)

    def on_prev_tab(self, event):
        total = self.notebook.GetPageCount()
        if total > 1:
            current = self.notebook.GetSelection()
            next_page = (current - 1) % total
            self.notebook.SetSelection(next_page)

    def toggle_propriedade_direta(self, prop):
        from mhs_utils import falar_status
        alvos = self.canais_selecionados if self.canal_atual in self.canais_selecionados else {self.canal_atual}
        novo_estado = not self.canais[self.canal_atual][prop]
        
        for ch in alvos:
            self.canais[ch][prop] = novo_estado
            if prop == "Mute" and novo_estado:
                self.all_notes_off(ch)
            elif prop == "Solo" and novo_estado:
                for i in range(16):
                    if i not in alvos:
                        self.all_notes_off(i)
                        
        self.dirty = True
        self.atualizar_titulo()
        
        estado_str = "Ligado" if novo_estado else "Desligado"
        if len(alvos) > 1:
            falar_status(f"{prop} {estado_str} em {len(alvos)} canais", imediato=True)
        else:
            falar_status(f"Canal {self.canal_atual + 1} {prop} {estado_str}", imediato=True)
            
        self.atualizar_status(silenciar=True)

    def abrir_conversor_midi(self, event):
        from mhs_dialogs import MidiRouterDialog
        from mhs_utils import falar_status
        dlg = MidiRouterDialog(self, self.rotas_midi)
        if dlg.ShowModal() == wx.ID_OK:
            self.rotas_midi = dlg.get_valores()
            self.config['rotas_midi'] = self.rotas_midi
            try:
                with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=4, ensure_ascii=False)
            except: pass
            falar_status("Rotas MIDI atualizadas.", imediato=True)
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
        dlg.Destroy()

    def abrir_time_signature(self, event):
        from mhs_dialogs import TimeSignatureDialog
        dlg = TimeSignatureDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            num, den, is_local = dlg.get_valores()
            self.aplicar_time_signature(num, den, is_local)
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
        dlg.Destroy()

    def aplicar_time_signature(self, num, den, is_local):
        from mhs_utils import falar_status
        if not self.midi_file: return
        self.save_state("Figura de Compasso")
        
        target_tick = self.get_tick_at_sec(self.current_playback_time) if is_local else 0
        
        track_idx = 0
        if not self.midi_file.tracks:
            self.midi_file.tracks.append(mido.MidiTrack())
        track = self.midi_file.tracks[track_idx]
        
        abs_events = []
        current_abs = 0
        for msg in track:
            current_abs += msg.time
            abs_events.append([current_abs, msg])
            
        if not is_local:
            abs_events = [item for item in abs_events if item[1].type != 'time_signature']
        else:
            abs_events = [item for item in abs_events if not (item[1].type == 'time_signature' and item[0] == target_tick)]
            
        ts_msg = mido.MetaMessage('time_signature', numerator=num, denominator=den, clocks_per_click=24, notated_32nd_notes_per_beat=8)
        abs_events.append([target_tick, ts_msg])
        abs_events.sort(key=lambda x: x[0])
        
        new_track = mido.MidiTrack()
        last_tick = 0
        for tick, msg in abs_events:
            delta = max(0, tick - last_tick)
            new_track.append(copiar_com_tempo(msg, delta))
            last_tick = tick
            
        self.midi_file.tracks[track_idx] = new_track
        self.dirty = True
        self.atualizar_titulo()
        
        was_playing = self.tocando
        if self.tocando:
            self.tocando = False
            self.all_notes_off()
            time.sleep(0.05)
            
        self.ler_midi_memoria(reset_canais=False)
        self.seek_flag = True
        if was_playing:
            self.tocando = True
            threading.Thread(target=self.play_thread, daemon=True).start()
            
        local_str = "no cursor" if is_local else "global"
        falar_status(f"Figura de compasso {num} por {den} aplicada {local_str}.", imediato=True)

    def abrir_drum_setup(self, event):
        from mhs_utils import falar_status
        from mhs_dialogs import DrumSetupDialog
        if not self.midi_file: return
        falar_status(f"Abrindo Yamaha XG Drum Setup para Canal {self.canal_atual + 1}")
        dlg = DrumSetupDialog(self, self.canal_atual)
        self.active_drum_setup = dlg 
        try:
            if dlg.ShowModal() == wx.ID_OK:
                drum_params, custom_maps, drum_params_nrpn = dlg.get_values()
                self.aplicar_drum_setup(drum_params, custom_maps, drum_params_nrpn)
        finally:
            # Essa é a chave de ouro que destrava o seu teclado para voltar a gravar!
            self.active_drum_setup = None
            wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
            dlg.Destroy()
    def aplicar_drum_setup(self, drum_params, custom_maps, drum_params_nrpn=None):
        from mhs_utils import falar_status
        self.save_state("Drum Setup XG")
        ch = self.canal_atual
        
        # Guarda na memória RAM oficial da pista
        self.canais[ch]["DrumParams"] = drum_params
        self.canais[ch]["CustomDrumMap"] = custom_maps
        self.canais[ch]["DrumParamsNRPN"] = drum_params_nrpn or {}

        self.dirty = True
        self.atualizar_titulo()
        
        # Consolida tudo escrevendo fisicamente no arquivo MIDI!
        self.consolidar_projeto()
        
        was_playing = self.tocando
        if self.tocando:
            self.tocando = False
            self.all_notes_off()
            import time
            time.sleep(0.05)
            
        self.ler_midi_memoria(reset_canais=False)
        self.seek_flag = True
        if was_playing:
            self.tocando = True
            import threading
            threading.Thread(target=self.play_thread, daemon=True).start()
            
        falar_status("Drum Setup aplicado 100% via SysEx.", imediato=True)
    def abrir_event_list(self, event):
        if not self.midi_file:
            self.processar_novo_midi()
            
        pre_state = {
            "action": "Edições no Event List",
            "midi_file": self.clone_midi_rapido(self.midi_file),
            "canais": [c.copy() for c in self.canais],
            "overrides": {k: v.copy() for k, v in self.overrides.items()},
            "current_tempo": self.current_tempo,
            "time_selection_start": self.time_selection_start,
            "time_selection_end": self.time_selection_end,
            "canais_selecionados": self.canais_selecionados.copy()
        }
            
        from mhs_utils import falar_status
        falar_status("Event List Aberto")
        
        # --- A MÁGICA ACONTECE AQUI! ---
        # Agora o Event List recebe todos os canais que você selecionou (Estilo Sonar)
        alvos = self.canais_selecionados if self.canais_selecionados else {self.canal_atual}
        from mhs_event_list import EventListDialog
        dlg = EventListDialog(self, alvos)
        
        self.active_event_list = dlg
        dlg.ShowModal()
        
        if getattr(dlg, 'modified', False):
            if len(self.undo_stack) >= 50:
                self.undo_stack.pop(0)
            self.undo_stack.append(pre_state)
            self.redo_stack.clear()
            
        self.active_event_list = None
        dlg.Destroy()
        
        self.ler_midi_memoria(reset_canais=False)
        import wx
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
        wx.CallLater(200, lambda: falar_status("Event List Fechado"))
    def repetir_status_tab(self, event):
        self.atualizar_status(falar_canal=True)

    def abrir_propriedades_canal(self, event):
        from mhs_dialogs import PropriedadesCanalDialog
        dlg = PropriedadesCanalDialog(self, self.canal_atual)
        if dlg.ShowModal() == wx.ID_OK:
            self.save_state("Edição de Propriedades")
            novos_dados = dlg.get_valores()
            canal = self.canais[self.canal_atual]
            
            parametros = ["Bank", "Patch", "Volume", "Pan", "Expression", "Reverb", "Chorus"]
            for p in parametros:
                if canal[p] != novos_dados[p]:
                    canal[p] = novos_dados[p]
                    self.enviar_midi_param(p, canal[p], self.canal_atual)
                    
            self.atualizar_status()
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
        dlg.Destroy()

    def on_load_midi(self, event):
        import wx
        pasta_inicial = self.config.get('pasta_abrir', '')
        with wx.FileDialog(self, "Abrir MIDI", defaultDir=pasta_inicial, wildcard=WILDCARD_ABRIR_MIDI, style=wx.FD_OPEN) as fd:
            if fd.ShowModal() == wx.ID_OK:
                path = fd.GetPath()
                
                # --- A BLINDAGEM DA NOVA GUIA ---
                # Se a guia atual tem um arquivo, está suja (modificada) ou tem eventos (tempo > 0),
                # criamos uma nova guia para proteger o trabalho atual!
                em_uso = self.dirty or (self.current_midi_path is not None) or (getattr(self, 'total_time', 0.0) > 0.1)
                
                if em_uso:
                    self.on_nova_guia(titulo="Carregando...")
                    
                wx.CallAfter(self.processar_carregamento_midi, path)

    def on_open_recent(self, event):
        import wx
        import os
        m_id = event.GetId()
        if m_id in getattr(self, 'recent_mappings', {}):
            path = self.recent_mappings[m_id]
            if os.path.exists(path):
                
                # --- A MESMA BLINDAGEM PARA OS ARQUIVOS RECENTES ---
                em_uso = self.dirty or (self.current_midi_path is not None) or (getattr(self, 'total_time', 0.0) > 0.1)
                
                if em_uso:
                    self.on_nova_guia(titulo="Carregando...")
                    wx.CallAfter(self.processar_carregamento_midi, path)
                else:
                    self.processar_carregamento_midi(path)
            else:
                from mhs_utils import falar_status
                falar_status("Aviso: Arquivo não encontrado no disco.", imediato=True)

    def on_new_midi(self, event):
        import wx
        # O Ctrl+N continua corretíssimo: pede para salvar antes de limpar a tela atual
        if not self.checar_salvamento_guia(): return
        wx.CallAfter(self.processar_novo_midi)

    def processar_carregamento_midi(self, path):
        if self.tocando:
            self.tocando = False
            self.gravando = False
            self.all_notes_off()
            import time
            time.sleep(0.1)
            
        try:
            self.current_midi_path = path
            self.midi_file = mido.MidiFile(path)

            # Áudio Guia deste projeto: procura o arquivo-irmão ".mhsaudio"
            # ao lado do .mid (ver caminho_sidecar_audio/salvar_config_audio).
            # Achou e o áudio referenciado ainda existe -> carrega sozinho.
            # Não achou -> segue sem áudio nenhum (não herda de outro
            # projeto que porventura estivesse aberto antes).
            self.audio_path = None
            self.audio_volume = 100
            self.audio_offset = 0.0
            audio_do_sidecar = False
            sidecar = self.caminho_sidecar_audio(path)
            if sidecar and os.path.exists(sidecar):
                try:
                    import json
                    with open(sidecar, 'r', encoding='utf-8') as f:
                        dados_audio = json.load(f)
                    caminho_audio = dados_audio.get('audio_path')
                    if caminho_audio and os.path.exists(caminho_audio):
                        self.audio_path = caminho_audio
                        self.audio_volume = dados_audio.get('audio_volume', 100)
                        self.audio_offset = dados_audio.get('audio_offset', 0.0)
                        audio_do_sidecar = True
                except Exception:
                    pass
            self._audio_stop()
            try:
                self._audio_reset_mixer_format()
            except Exception:
                pass

            # Cura Figuras de Compasso empilhadas de um arquivo já corrompido
            # (bug relatado: BPM alterado criou time_signatures a mais).
            self._sanear_time_signatures()
            self.overrides = {i: {} for i in range(16)}
            self.canais_selecionados = {0}
            self.dirty = False
            
            self.undo_stack.clear()
            self.redo_stack.clear()
            
            # --- A NOVA ORDEM CIRÚRGICA E DEFINITIVA ---
            
            # PASSO 1: Resgata os Efeitos (DSP) da música suja ANTES do rolo compressor passar!
            self.aplicar_sysex_ao_carregar()
            
            # PASSO 2: Suga os timbres, bancos, volumes e drum setups da música suja
            self.ler_midi_memoria(reset_canais=True) 
            
            # PASSO 3: A INTELIGÊNCIA! Agora que ele já sugou tudo, passa o Rolo Compressor pra organizar
            self.consolidar_projeto()
            
            # PASSO 4: Reconstrói o player baseado no arquivo 100% limpo e blindado
            self.ler_midi_memoria(reset_canais=False)
            
            self.atualizar_titulo()
            self.add_to_recent(path)
            
            wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
            from mhs_utils import falar_status
            falar_status("MIDI carregado, extraído e normalizado com sucesso!", imediato=True)
            
        except Exception as e:
            from mhs_utils import falar_status
            falar_status(f"Erro ao carregar: {str(e)}", imediato=True)
    def on_save_midi(self, event):
        if getattr(self, 'gravando', False):
            from mhs_utils import falar_status
            falar_status("Pare a gravação antes de salvar.", imediato=True)
            return

        # Agora usando o nome correto da variável do seu sistema!
        if not getattr(self, 'midi_file', None) or not getattr(self, 'current_midi_path', None):
            self.on_save_as_midi(event)
            return
        
        self.consolidar_projeto()
        self.garantir_cabecalho_xg() # <--- A vacina do Yamaha XG!
        
        try:
            self.midi_file.save(self.current_midi_path)
            self.dirty = False
            self.atualizar_titulo()
            self.add_to_recent(self.current_midi_path)
            from mhs_utils import falar_status
            falar_status("Projeto salvo.", imediato=True)
        except Exception as e:
            from mhs_utils import falar_status
            falar_status(f"Erro ao salvar: {e}", imediato=True)

    def on_save_as_midi(self, event):
        if not self.midi_file and not self.overrides and not self.recorded_events:
            return
            
        pasta_inicial = self.config.get('pasta_salvar', '')
        atual = getattr(self, 'current_midi_path', None) or ''
        with wx.FileDialog(self, "Salvar MIDI como", defaultDir=os.path.dirname(atual) or pasta_inicial,
                           defaultFile=os.path.basename(atual), wildcard=WILDCARD_SALVAR_MIDI,
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as fd:
            # abriu um .kar? já sugere salvar como .kar (o arquivo é o mesmo formato MIDI, só muda a extensão)
            fd.SetFilterIndex(1 if atual.lower().endswith('.kar') else 0)
            if fd.ShowModal() == wx.ID_OK:
                path = fd.GetPath()
                self.config['pasta_projetos'] = os.path.dirname(path)
                wx.CallAfter(self.processar_salvamento_midi, path)

    def processar_salvamento_midi(self, path):
        self.salvar_midi(path)
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())

    def salvar_midi(self, path):
        try:
            if self.gravando:
                self.gravando = False
                self.all_notes_off()
                
            if self.recorded_events:
                self.aplicar_gravacao()
                
            # Chama a consolidação que acabamos de arrumar
            self.consolidar_projeto()
                
            # Cria a cópia final para aplicar o Transpose apenas no arquivo físico
            novo_mid = self.clone_midi_rapido(self.midi_file)
            
            for i, track in enumerate(novo_mid.tracks):
                new_track = mido.MidiTrack()
                for msg in track:
                    ch = getattr(msg, 'channel', None)
                    if ch is not None and ch != 9 and msg.type in ['note_on', 'note_off']:
                        transp = int(self.canais[ch].get("Transpose", 0))
                        if transp != 0:
                            nova_nota = max(0, min(127, msg.note + transp))
                            msg = msg.copy(note=nova_nota)
                    new_track.append(msg)
                novo_mid.tracks[i] = new_track

            novo_mid.save(path)
            self.current_midi_path = path
            self.dirty = False
            self.atualizar_titulo()
            self.add_to_recent(path)
            # Mantém o arquivo-irmão do Áudio Guia (.mhsaudio) em dia -
            # cobre também "Salvar Como" (o áudio "acompanha" o arquivo
            # pro caminho novo).
            self.salvar_config_audio()

            from mhs_utils import falar_status
            falar_status("Arquivo salvo com sucesso!", imediato=True)
            
        except Exception as e:
            from mhs_utils import falar_status
            falar_status(f"Erro ao salvar: {str(e)}", imediato=True)
    def aplicar_chase_seguro(self):
        if not self.output: return
        
        # O dicionário ficou mais inteligente: agora rastreia o MSB e LSB do NRPN ativamente!
        estado_canais = {i: {'cc': {}, 'patch': None, 'pitchwheel': None, 'nrpn_msb': None, 'nrpn_lsb': None, 'nrpns_values': {}} for i in range(16)}

        for ev_time, msg in self.play_events:
            if ev_time >= self.current_playback_time: break
            ch = getattr(msg, 'channel', None)
            if ch is not None:
                if msg.type == 'control_change':
                    # --- A INTELIGÊNCIA DO NRPN (Filtros de Bateria e Sintetizador) ---
                    if msg.control == 99:
                        estado_canais[ch]['nrpn_msb'] = msg.value
                    elif msg.control == 98:
                        estado_canais[ch]['nrpn_lsb'] = msg.value
                    elif msg.control == 6:
                        n_msb = estado_canais[ch]['nrpn_msb']
                        n_lsb = estado_canais[ch]['nrpn_lsb']
                        if n_msb is not None and n_lsb is not None:
                            # Salva o valor final atrelado ao Parâmetro (MSB) e à Peça (LSB)
                            estado_canais[ch]['nrpns_values'][(n_msb, n_lsb)] = msg.value
                            
                    estado_canais[ch]['cc'][msg.control] = msg.value
                elif msg.type == 'program_change': 
                    estado_canais[ch]['patch'] = msg.program
                elif msg.type == 'pitchwheel': 
                    estado_canais[ch]['pitchwheel'] = msg.pitch

        import mido
        import time 
        
        for ch in range(16):
            ovr = self.overrides.get(ch, {})
            b_msb = ovr.get("Bank", estado_canais[ch]['cc'].get(0, 0) * 128) // 128 if "Bank" in ovr else estado_canais[ch]['cc'].get(0)
            b_lsb = ovr.get("Bank", estado_canais[ch]['cc'].get(32, 0)) % 128 if "Bank" in ovr else estado_canais[ch]['cc'].get(32)

            if b_msb is not None: self.output.send(mido.Message('control_change', channel=ch, control=0, value=b_msb))
            if b_lsb is not None: self.output.send(mido.Message('control_change', channel=ch, control=32, value=b_lsb))

            patch = ovr.get("Patch", estado_canais[ch].get('patch'))
            if patch is not None: self.output.send(mido.Message('program_change', channel=ch, program=patch))
            
            pitch = estado_canais[ch].get('pitchwheel')
            if pitch is not None: self.output.send(mido.Message('pitchwheel', channel=ch, pitch=pitch))

            cc_mapping = {7: "Volume", 10: "Pan", 11: "Expression", 91: "Reverb", 93: "Chorus"}
            for cc_num, prop_name in cc_mapping.items():
                val = ovr.get(prop_name, estado_canais[ch]['cc'].get(cc_num))
                if val is not None: self.output.send(mido.Message('control_change', channel=ch, control=cc_num, value=val))
                
            # --- RESTAURANDO OS NRPNS ANTES DE TOCAR ---
            # Aqui o player despeja todas as afinações e filtros de volta no teclado de uma vez!
            for (n_msb, n_lsb), n_val in estado_canais[ch]['nrpns_values'].items():
                try:
                    self.output.send(mido.Message('control_change', channel=ch, control=99, value=n_msb))
                    self.output.send(mido.Message('control_change', channel=ch, control=98, value=n_lsb))
                    self.output.send(mido.Message('control_change', channel=ch, control=6, value=n_val))
                except: pass

        # O "fôlego" de 80ms + o laço abaixo só valem a pena quando existe
        # DE VERDADE alguma configuração de bateria (SysEx ou NRPN) pra
        # reenviar - a maioria dos Play não mexe em Drum Setup nenhum, e
        # esses ~90ms fixos (aqui + o sleep(0.01) do fim) eram pagos sempre,
        # é isso que fazia a barra de espaço "atrasar" comparado ao Style
        # Creator (que só manda tudo 1x no carregamento do arquivo, nunca
        # de novo a cada Play - ver comentário em OnTogglePlay lá).
        tem_drum_setup = any(
            self.canais[ch].get("DrumParams") or self.canais[ch].get("CustomDrumMap") or self.canais[ch].get("DrumParamsNRPN")
            for ch in range(16)
        ) or getattr(self, 'active_drum_setup', None) is not None

        if tem_drum_setup:
            time.sleep(0.08) # Fôlego do teclado XG

            for ch in range(16):
                part_byte = 0x30 if ch == 9 else 0x31

                drum_params = self.canais[ch].get("DrumParams", {})
                custom_maps = self.canais[ch].get("CustomDrumMap", {})
                drum_params_nrpn = self.canais[ch].get("DrumParamsNRPN", {})

                if getattr(self, 'active_drum_setup', None) is not None and ch == self.active_drum_setup.canal_idx:
                    drum_params = self.active_drum_setup.drum_params
                    custom_maps = self.active_drum_setup.custom_maps
                    drum_params_nrpn = self.active_drum_setup.drum_params_nrpn

                # PRIMEIRO: Envia a troca de peças!
                if custom_maps:
                    for orig_note, m in custom_maps.items():
                        b = m['bank']
                        b_msb = min(127, b // 128)
                        syx_data = [0xF0, 0x43, 0x10, 0x4C, part_byte, orig_note, 0x70, b_msb, b % 128, m['patch'], m['dest_note'], 0xF7]
                        try: self.output.send(mido.Message.from_bytes(syx_data))
                        except: pass

                # SEGUNDO: Envia a Afinação, Volume, Pan, etc. para a peça que acabou de ser definida!
                if drum_params:
                    for (note, param_id), val in drum_params.items():
                        syx_data = [0xF0, 0x43, 0x10, 0x4C, part_byte, note, param_id, val, 0xF7]
                        try: self.output.send(mido.Message.from_bytes(syx_data))
                        except: pass

                # TERCEIRO: mesma coisa, mas via NRPN puro (Guia 3) - o canal já
                # vem no próprio CC, não precisa de part_byte.
                if drum_params_nrpn:
                    for (note, param_id), val in drum_params_nrpn.items():
                        for msg in (mido.Message('control_change', channel=ch, control=99, value=param_id),
                                    mido.Message('control_change', channel=ch, control=98, value=note),
                                    mido.Message('control_change', channel=ch, control=6, value=val)):
                            try: self.output.send(msg)
                            except: pass

            time.sleep(0.01)
    def play_thread(self):
        import time
        import mido
        try:
            import ctypes
            ctypes.windll.winmm.timeBeginPeriod(1)
        except:
            pass

        is_gm = (self.config.get('padrao_midi', 'XG') == 'GM')

        resume_limpo = (self.current_playback_time > 0.0 and
                         getattr(self, '_chase_dispensavel', None) == (self.current_playback_time, getattr(self, '_revisao_estado', 0)))

        if self.current_playback_time <= 0.0:
            if self.output:
                for c in range(16):
                    try:
                        self.output.send(mido.Message('control_change', channel=c, control=121, value=0))
                        self.output.send(mido.Message('control_change', channel=c, control=123, value=0))
                    except:
                        pass

                for ch in range(16):
                    b = self.canais[ch].get("Bank", 0)
                    p = self.canais[ch].get("Patch", 0)
                    try:
                        self.output.send(mido.Message('control_change', channel=ch, control=0, value=b // 128))
                        self.output.send(mido.Message('control_change', channel=ch, control=32, value=b % 128))
                        self.output.send(mido.Message('program_change', channel=ch, program=p))
                    except: pass

            for ch, params in self.overrides.items():
                for p, v in params.items():
                    self.enviar_midi_param(p, v, ch, is_playback=True)
        elif resume_limpo:
            # Tocar/Pausar (ou Parar/Tocar) voltando pro MESMO ponto sem
            # editar nada no meio - o teclado já está com Bank/Patch/CC/NRPN
            # certos (all_notes_off só tira as notas presas, não mexe nisso).
            # Pula o chase inteiro: nem o sleep de segurança, nem o
            # reenvio - é exatamente o "não zera nada" que o Style Creator
            # já tem ao pausar e voltar.
            pass
        else:
            self.aplicar_chase_seguro()

        metro_tipo = str(self.config.get('metro_tipo', 'Midi')).strip().lower()

        self.live_multiplier = getattr(self, 'live_multiplier', 1.0)
        base_bpm = int(round(60000000.0 / self.current_tempo)) if getattr(self, 'current_tempo', 500000) > 0 else 120
        
        self.msg_index = len(self.play_events)
        for i, ev in enumerate(self.play_events):
            if ev[0] >= self.current_playback_time:
                self.msg_index = i
                break
                
        self.beat_index = len(self.beat_events)
        for i, (b_time, is_d) in enumerate(self.beat_events):
            if b_time >= self.current_playback_time:
                self.beat_index = i
                break

        start_time = time.time() - (self.current_playback_time / getattr(self, 'live_multiplier', 1.0)) + 0.005

        audio_started = False
        if getattr(self, 'audio_path', None) and os.path.exists(self.audio_path):
            if resume_limpo and getattr(self, '_audio_paused', False) and self._audio_unpause():
                # Mesma posição de quando pausou, nada editado no meio -
                # o canal continua exatamente onde estava congelado
                # (Channel.pause()/unpause()) - sem reler nem recomeçar
                # o áudio, então não tem CHANCE de desincronizar.
                audio_started = True
            else:
                audio_started = self._audio_play_from(self.current_playback_time)

        # O início da thread ACIMA já fez toda a "chegada" (chase e
        # áudio) pra self.current_playback_time - um seek_flag deixado
        # ligado por quem pediu ESTA thread (toggle_pausa/toggle_
        # reproducao, ao religar) é redundante aqui: sem isso, o
        # primeiro giro do laço abaixo repetia a mesma reposição de novo
        # (parava e recomeçava o Áudio Guia, desperdiçando o
        # pause/unpause que acabou de congelar/retomar o canal certinho).
        self.seek_flag = False

        while getattr(self, 'tocando', False):
            # Troca de andamento AO VIVO (Tap Tempo - ver do_tap_tempo):
            # play_events/beat_events estão sendo reconstruídos agora
            # mesmo por baixo do pano, num outro momento (thread da UI).
            # Em vez de ler essas listas pela metade (causava o "disparo"
            # de eventos errados), só espera 1ms e tenta de novo - sem
            # parar nada, sem tocar no áudio, sem all_notes_off.
            if getattr(self, '_pausar_leitura_eventos', False):
                time.sleep(0.001)
                continue

            current_t = time.time()

            if getattr(self, 'is_prerolling', False) and self.current_playback_time >= getattr(self, 'record_start_time', 0.0):
                self.is_prerolling = False
                self.gravando = True
                import wx
                wx.CallAfter(self.atualizar_titulo)
                from mhs_utils import falar_status
                wx.CallAfter(falar_status, "Gravando Valendo!", imediato=True)
            
            if getattr(self, 'target_live_bpm', None) is not None:
                novo_mult = self.target_live_bpm / float(base_bpm)
                current_virtual = (current_t - start_time) * self.live_multiplier
                self.live_multiplier = novo_mult
                start_time = current_t - (current_virtual / self.live_multiplier)
                self.target_live_bpm = None

            if getattr(self, 'seek_flag', False):
                self._audio_stop()

                if self.current_playback_time <= 0.0:
                    if self.output:
                        for c in range(16):
                            try:
                                self.output.send(mido.Message('control_change', channel=c, control=121, value=0))
                                self.output.send(mido.Message('control_change', channel=c, control=123, value=0))
                            except: pass
                    for ch, params in self.overrides.items():
                        for p, v in params.items():
                            self.enviar_midi_param(p, v, ch, is_playback=True)
                else:
                    self.aplicar_chase_seguro()

                start_time = time.time() - (self.current_playback_time / self.live_multiplier) + 0.005

                if getattr(self, 'audio_path', None) and os.path.exists(self.audio_path):
                    audio_started = self._audio_play_from(self.current_playback_time)
                else:
                    audio_started = False

                self.msg_index = len(self.play_events)
                for i, ev in enumerate(self.play_events):
                    if ev[0] >= self.current_playback_time:
                        self.msg_index = i
                        break
                self.beat_index = len(self.beat_events)
                for i, (b_time, is_d) in enumerate(self.beat_events):
                    if b_time >= self.current_playback_time:
                        self.beat_index = i
                        break
                self.seek_flag = False
                continue

            now_virtual = (current_t - start_time) * self.live_multiplier
            self.current_playback_time = now_virtual 
            
            if not audio_started and getattr(self, 'audio_path', None) and os.path.exists(self.audio_path):
                now_real = current_t - start_time
                if now_real >= self.audio_offset:
                    audio_started = self._audio_play_from(self.current_playback_time)

            while getattr(self, 'metronomo_ligado', False) and self.beat_index < len(self.beat_events):
                b_time, is_downbeat = self.beat_events[self.beat_index]
                if now_virtual >= b_time:
                    saida_metro = self.output_metronomo or self.output
                    if metro_tipo == 'midi' and saida_metro:
                        nota_metro = self.config.get('metro_note_down', 22) if is_downbeat else self.config.get('metro_note_beat', 21)
                        vel_metro = self.config.get('metro_vel_down', 100) if is_downbeat else self.config.get('metro_vel_beat', 100)
                        try:
                            saida_metro.send(mido.Message('note_on', channel=9, note=nota_metro, velocity=vel_metro))
                            import threading
                            threading.Timer(0.05, lambda n=nota_metro, p=saida_metro: p.send(mido.Message('note_off', channel=9, note=n))).start()
                        except:
                            pass
                    self.beat_index += 1
                else:
                    break

            while self.msg_index < len(self.play_events):
                ev_time, msg = self.play_events[self.msg_index]
                if now_virtual >= ev_time:
                    self.msg_index += 1
                    
                    if getattr(msg, 'is_meta', False): 
                        if msg.type == 'set_tempo':
                            self.current_tempo = msg.tempo
                        continue

                    if msg.type == 'sysex':
                        d = msg.data
                        if len(d) >= 4 and tuple(d[0:4]) == (0x43, 0x10, 0x4C, 0x00):
                            continue
                        if len(d) == 4 and tuple(d[0:4]) == (0x7E, 0x7F, 0x09, 0x01):
                            continue
                            
                        # --- NOVO: O ESCUDO ANTI-CLONAGEM DE MIXAGEM (GRAVE, AGUDO, ETC) ---
                        # Se for um SysEx de Mixagem (0x08) e o canal tiver um override na tela, IGNORA o evento velho do arquivo!
                        if len(d) >= 7 and tuple(d[0:4]) == (0x43, 0x10, 0x4C, 0x08):
                            syx_ch = d[4]
                            syx_param = d[5]
                            if 0 <= syx_ch < 16 and syx_ch in self.overrides:
                                ovr = self.overrides[syx_ch]
                                if syx_param == 0x72 and 'Grave' in ovr: continue
                                if syx_param == 0x73 and 'Agudo' in ovr: continue
                                if syx_param in ovr.get('VoiceCreator', {}): continue
                                if syx_param == 0x01 and 'Bank' in ovr: continue
                                if syx_param == 0x02 and 'Bank' in ovr: continue
                                if syx_param == 0x03 and 'Patch' in ovr: continue
                                if syx_param == 0x0B and 'Volume' in ovr: continue
                                if syx_param == 0x0E and 'Pan' in ovr: continue
                                if syx_param == 0x13 and 'Reverb' in ovr: continue
                                if syx_param == 0x12 and 'Chorus' in ovr: continue

                        # --- O ESCUDO ANTI-DECAPITAÇÃO DE DSP ---
                        # Se for SysEx de Efeito (0x02 ou 0x03) no primeiro meio segundo da música, IGNORA!
                        # Isso confia no 'aplicar_sysex_ao_carregar' e impede o reset do processador!
                        if ev_time <= 0.5 and len(d) >= 4 and tuple(d[0:3]) == (0x43, 0x10, 0x4C) and d[3] in [0x02, 0x03]:
                            continue
                            
                        if self.output:
                            try: self.output.send(msg)
                            except: pass
                        continue
                    
                    ch = getattr(msg, 'channel', None)
                    if ch is not None:
                        if ev_time <= 0.05 and msg.type in ['program_change', 'control_change']:
                            if msg.type == 'program_change': continue
                            if msg.type == 'control_change' and msg.control in [0, 32]: continue

                        if msg.type == 'program_change' and 'Patch' in self.overrides[ch]: continue
                        if msg.type == 'control_change':
                            if msg.control in [0, 32] and 'Bank' in self.overrides[ch]: continue
                            if msg.control == 7 and 'Volume' in self.overrides[ch]: continue
                            if msg.control == 10 and 'Pan' in self.overrides[ch]: continue
                            if msg.control == 11 and 'Expression' in self.overrides[ch]: continue
                            if msg.control == 91 and 'Reverb' in self.overrides[ch]: continue
                            if msg.control == 93 and 'Chorus' in self.overrides[ch]: continue
                            if msg.control in [6, 38, 100, 101] and 'Pitch Bend' in self.overrides[ch]: continue
                            if msg.control in [5, 65] and 'Porta Time' in self.overrides[ch]: continue
                            if msg.control in [126, 127] and 'Mono/Poly' in self.overrides[ch]: continue
                        
                        if is_gm and ch == 9 and msg.type == 'control_change' and msg.control in [0, 32]:
                            continue
                        
                        if msg.type in ['note_on', 'note_off']:
                            if self.canais[ch]["Mute"]: continue
                            if any(can["Solo"] for can in self.canais) and not self.canais[ch]["Solo"]: continue
                            transp = self.canais[ch].get("Transpose", 0)
                            if transp != 0 and ch != 9:
                                msg = msg.copy(note=max(0, min(127, msg.note + transp)))
                                
                    if self.output:
                        try: self.output.send(msg)
                        except: pass
                else:
                    break
                    
            if self.msg_index < len(self.play_events):
                next_ev_time = self.play_events[self.msg_index][0]
                tempo_espera = (next_ev_time - now_virtual) / self.live_multiplier
                if tempo_espera > 0.002:
                    time.sleep(0.001)
                else:
                    pass
            else:
                time.sleep(0.002)

        try:
            import ctypes
            ctypes.windll.winmm.timeBeginPeriod(1)
        except:
            pass
        
        self.all_notes_off()
    def mark_selection_start(self, event):
        self.time_selection_start = self.current_playback_time
        if getattr(self, 'time_selection_end', None) is None or self.time_selection_end <= self.time_selection_start:
            self.time_selection_end = max(self.total_time, self.current_playback_time)
            
        str_in = self._obter_str_compasso(self.time_selection_start)
        from mhs_utils import falar_status
        falar_status(f"Marcação de Início: {str_in}", imediato=True)

    def mark_selection_end(self, event):
        self.time_selection_end = self.current_playback_time
        if getattr(self, 'time_selection_start', None) is None or self.time_selection_start >= self.time_selection_end:
            self.time_selection_start = 0.0
            
        str_out = self._obter_str_compasso(self.time_selection_end)
        from mhs_utils import falar_status
        falar_status(f"Marcação de Fim: {str_out}", imediato=True)

    def _obter_str_compasso(self, tempo_sec):
        if not getattr(self, 'midi_file', None): return f"{tempo_sec:.2f} segundos"
        target_tick = self.get_tick_at_sec(tempo_sec)
        tpb = max(1, getattr(self.midi_file, 'ticks_per_beat', 480))
        
        # OTIMIZAÇÃO: Busca o Time Signature sem juntar as trilhas
        ts_map = []
        for track in self.midi_file.tracks:
            abs_t = 0
            for msg in track:
                abs_t += msg.time
                if msg.type == 'time_signature':
                    ts_map.append((abs_t, msg.numerator, msg.denominator))
        ts_map.sort(key=lambda x: x[0])
        if not ts_map: ts_map.append((0, 4, 4))
        
        current_bar = 1
        current_tick = 0
        num, den = 4, 4
        for tm_tick, tm_num, tm_den in ts_map:
            if tm_tick > target_tick: break
            ticks_por_compasso = (tpb * 4.0 / tm_den) * tm_num
            diff = tm_tick - current_tick
            current_bar += int(diff // ticks_por_compasso)
            current_tick = tm_tick
            num, den = tm_num, tm_den
            
        ticks_por_compasso = (tpb * 4.0 / den) * num
        ticks_por_beat = tpb * 4.0 / den
        diff = target_tick - current_tick
        current_bar += int(diff // ticks_por_compasso)
        resto_compasso = diff % ticks_por_compasso
        beat = int(resto_compasso // ticks_por_beat) + 1
        ticks = int(round(resto_compasso % ticks_por_beat))
        return f"Compasso {current_bar}, beat {beat}, {ticks} ticks"
    def ir_para_inicio_selecao(self, event):
        from mhs_utils import falar_status
        if self.time_selection_start is None:
            falar_status("Nenhuma seleção de tempo ativa.", imediato=True)
            return
            
        self.all_notes_off()
        self.current_playback_time = min(self.time_selection_start, getattr(self, 'time_selection_end', self.time_selection_start))
        self.last_start_time = self.current_playback_time
        self.seek_flag = True
        
        if self.gravando or self.recorded_events:
            self.gravando = False
            self.aplicar_gravacao()
            
        falar_status(f"Início da seleção: {self.current_playback_time:.2f} segundos", imediato=True)
        
        if getattr(self, 'active_event_list', None):
            wx.CallAfter(self.active_event_list.sync_to_playback_time)

    def ir_para_fim_selecao(self, event):
        from mhs_utils import falar_status
        if self.time_selection_end is None:
            falar_status("Nenhuma seleção de tempo ativa.", imediato=True)
            return
            
        self.all_notes_off()
        self.current_playback_time = max(self.time_selection_end, getattr(self, 'time_selection_start', self.time_selection_end))
        self.last_start_time = self.current_playback_time
        self.seek_flag = True
        
        if self.gravando or self.recorded_events:
            self.gravando = False
            self.aplicar_gravacao()
            
        falar_status(f"Fim da seleção: {self.current_playback_time:.2f} segundos", imediato=True)
        
        if getattr(self, 'active_event_list', None):
            wx.CallAfter(self.active_event_list.sync_to_playback_time)



    def build_time_map(self):
        """Novo Motor Matemático: Constrói um mapa de conversão perfeito Tick <-> Segundos"""
        # OTIMIZAÇÃO: Essa função era chamada dezenas de vezes por edição (arrasto,
        # nudge, seek, status...) e escaneava a música inteira toda vez, mesmo sem
        # nada ter mudado. Agora guardamos o resultado e só recalculamos quando
        # midi_file/dirty mudam (ver propriedades no topo da classe).
        cache = getattr(self, '_time_map_cache', None)
        if cache is not None:
            return cache

        tpb = 480
        if getattr(self, 'midi_file', None):
            tpb = max(1, getattr(self.midi_file, 'ticks_per_beat', 480))

        tempos = []
        if getattr(self, 'midi_file', None):
            for track in self.midi_file.tracks:
                abs_t = 0
                for msg in track:
                    abs_t += msg.time
                    if msg.type == 'set_tempo':
                        tempos.append((abs_t, msg.tempo))
        from operator import itemgetter
        tempos.sort(key=itemgetter(0))

        mapa_limpo = []
        for t_tick, t_val in tempos:
            if mapa_limpo and mapa_limpo[-1][0] == t_tick:
                mapa_limpo[-1] = (t_tick, t_val)
            else:
                mapa_limpo.append((t_tick, t_val))

        if not mapa_limpo or mapa_limpo[0][0] > 0:
            mapa_limpo.insert(0, (0, 500000))

        anchors = []
        abs_sec = 0.0
        abs_tick = 0
        current_tempo = 500000

        for tick, tempo in mapa_limpo:
            if tick > abs_tick:
                diff_ticks = tick - abs_tick
                diff_sec = (diff_ticks * current_tempo) / (tpb * 1000000.0)
                abs_sec += diff_sec
                abs_tick = tick
            anchors.append((tick, abs_sec, tempo))
            current_tempo = tempo

        self._time_map_cache = (anchors, tpb)
        return self._time_map_cache

    def get_tempo_map(self):
        """Novo Motor Matemático: Mapeia o tempo da música sem depender de leitura de eventos delta"""
        # OTIMIZAÇÃO: mesmo princípio de cache do build_time_map (ver acima).
        cache = getattr(self, '_tempo_map_cache', None)
        if cache is not None:
            return cache

        tpb = 480
        if getattr(self, 'midi_file', None):
            tpb = max(1, getattr(self.midi_file, 'ticks_per_beat', 480))

        tempos = []
        if getattr(self, 'midi_file', None):
            for track in self.midi_file.tracks:
                abs_t = 0
                for msg in track:
                    abs_t += msg.time
                    if msg.type == 'set_tempo':
                        tempos.append((abs_t, msg.tempo))
        from operator import itemgetter
        tempos.sort(key=itemgetter(0))

        mapa_limpo = []
        for t_tick, t_val in tempos:
            if mapa_limpo and mapa_limpo[-1][0] == t_tick:
                mapa_limpo[-1] = (t_tick, t_val)
            else:
                mapa_limpo.append((t_tick, t_val))

        if not mapa_limpo or mapa_limpo[0][0] > 0:
            mapa_limpo.insert(0, (0, 500000))

        self._tempo_map_cache = (mapa_limpo, tpb)
        return self._tempo_map_cache

    def get_tick_at_sec(self, target_sec):
        if not self.midi_file: return 0
        
        # OTIMIZAÇÃO: Usa o seu próprio motor matemático instantâneo no lugar de mido.merge_tracks
        anchors, tpb = self.build_time_map()
        
        last_tick, last_sec, cur_tempo = anchors[0]
        for a_tick, a_sec, a_tempo in anchors:
            if a_sec <= target_sec:
                last_tick, last_sec, cur_tempo = a_tick, a_sec, a_tempo
            else:
                break
                
        if target_sec >= last_sec:
            diff_sec = target_sec - last_sec
            diff_ticks = (diff_sec * 1000000.0 * tpb) / cur_tempo
            return last_tick + int(round(diff_ticks))
        return 0
    def get_sec_at_tick(self, target_tick):
        """Nova função: Converte um Tick absoluto de volta para segundos precisos no mapa de tempo atual"""
        if not self.midi_file: return 0.0
        
        # OTIMIZAÇÃO: Usa o mapa rápido em vez de rodar a música toda
        anchors, tpb = self.build_time_map()
        
        last_tick, last_sec, cur_tempo = anchors[0]
        for a_tick, a_sec, a_tempo in anchors:
            if a_tick <= target_tick:
                last_tick, last_sec, cur_tempo = a_tick, a_sec, a_tempo
            else:
                break
                
        if target_tick >= last_tick:
            diff_ticks = target_tick - last_tick
            diff_sec = (diff_ticks * cur_tempo) / (tpb * 1000000.0)
            return last_sec + diff_sec
        return 0.0
    def delete_time_selection(self, event, is_cut=False):
        from mhs_utils import falar_status
        if not self.canais_selecionados: return
        
        start_sec, end_sec = self.get_selection_bounds()
        start_tick = self.get_tick_at_sec(start_sec) if start_sec != float('inf') else 0
        end_tick = self.get_tick_at_sec(end_sec) if end_sec != float('inf') else float('inf')
        
        if start_tick == end_tick:
            falar_status("Nenhum trecho selecionado.", imediato=True)
            return
        
        self.save_state("Recortar" if is_cut else "Apagar")
        eventos_apagados = 0
        shift_amount = end_tick - start_tick if end_tick != float('inf') else 0
        
        ripple_mode = getattr(self, 'ripple_mode', 0)
        
        for i, track in enumerate(self.midi_file.tracks):
            import mido
            new_track = mido.MidiTrack()
            abs_tick = 0
            
            active_notes_started_before = set()
            active_notes_to_kill = set()
            
            flat = []
            for msg in track:
                abs_tick += msg.time
                flat.append([abs_tick, msg])
                
            filtered_flat = []
            for item in flat:
                tick, msg = item
                ch = getattr(msg, 'channel', None)
                
                in_selection = (start_tick <= tick < end_tick)
                is_selected_ch = (ch is not None and ch in self.canais_selecionados)
                
                is_ripple_all = (ripple_mode == 2)
                is_ripple_sel = (ripple_mode == 1)
                
                is_affected = is_selected_ch or is_ripple_all
                
                should_shift = False
                if tick >= end_tick and end_tick != float('inf'):
                    if is_ripple_all:
                        should_shift = True
                    elif is_ripple_sel and is_selected_ch:
                        should_shift = True
                        
                if not is_affected:
                    if should_shift: item[0] = max(0, item[0] - shift_amount)
                    filtered_flat.append(item)
                    continue
                    
                if msg.type == 'note_on' and msg.velocity > 0:
                    if in_selection:
                        active_notes_to_kill.add((ch, msg.note))
                        eventos_apagados += 1
                        continue
                    elif tick < start_tick:
                        active_notes_started_before.add((ch, msg.note))
                        filtered_flat.append(item)
                    else:
                        if should_shift: item[0] = max(0, item[0] - shift_amount)
                        filtered_flat.append(item)
                        
                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                    if (ch, msg.note) in active_notes_to_kill:
                        active_notes_to_kill.discard((ch, msg.note))
                        continue 
                        
                    if in_selection and (ch, msg.note) in active_notes_started_before:
                        active_notes_started_before.discard((ch, msg.note))
                        item[0] = start_tick
                        filtered_flat.append(item)
                    else:
                        if should_shift: item[0] = max(0, item[0] - shift_amount)
                        filtered_flat.append(item)
                else:
                    if in_selection:
                        if tick == 0 and msg.type in ['set_tempo', 'time_signature', 'track_name']:
                            filtered_flat.append(item)
                        else:
                            eventos_apagados += 1
                            continue
                    else:
                        if should_shift: item[0] = max(0, item[0] - shift_amount)
                        filtered_flat.append(item)
                        
            filtered_flat.sort(key=lambda x: x[0])
            last_tick = 0
            for item in filtered_flat:
                tick, msg = item
                delta = max(0, int(round(tick - last_tick)))
                # OTIMIZAÇÃO: Mutação direta poupa alocação de memória no compilador
                msg.time = delta
                new_track.append(msg)
                last_tick = tick
                
            self.midi_file.tracks[i] = new_track
            
        self.dirty = True
        self.atualizar_titulo()
        
        if getattr(self, 'ripple_mode', 0) > 0:
            self.time_selection_end = self.time_selection_start
        
        was_playing = self.tocando
        if self.tocando:
            self.tocando = False
            self.all_notes_off()
            import time
            time.sleep(0.05)
            
        self.ler_midi_memoria(reset_canais=False)
        self.seek_flag = True
        
        if is_cut:
            falar_status(f"Recortado {eventos_apagados} eventos.", imediato=True)
        else:
            if start_sec == 0.0 and end_sec == float('inf'):
                falar_status("Todo o conteúdo foi apagado.", imediato=True)
            else:
                falar_status(f"{eventos_apagados} eventos apagados no trecho.", imediato=True)
                
        if was_playing:
            self.tocando = True
            import threading
            threading.Thread(target=self.play_thread, daemon=True).start()
    def aplicar_gravacao(self):
        if not getattr(self, 'recorded_events', []): return
        self.save_state("Gravação")
        
        was_playing = getattr(self, 'tocando', False)
        play_time = getattr(self, 'current_playback_time', 0.0)
        
        if was_playing:
            self.tocando = False
            self.all_notes_off()
            import time
            time.sleep(0.05) 
            
        import mido
        if not getattr(self, 'midi_file', None):
            self.midi_file = mido.MidiFile(type=1)
            self.midi_file.tracks.append(mido.MidiTrack())
            
        new_track = mido.MidiTrack()
        ticks_per_beat = getattr(self.midi_file, 'ticks_per_beat', 480)
        
        # OTIMIZAÇÃO VITAL: Usando a sua função build_time_map em vez de ler a música toda no merge_tracks
        anchors, tpb = self.build_time_map()
            
        def get_tick(target_sec):
            last_tick, last_sec, cur_tempo = anchors[0]
            for a_tick, a_sec, a_tempo in anchors:
                if a_sec <= target_sec:
                    last_tick, last_sec, cur_tempo = a_tick, a_sec, a_tempo
                else:
                    break
            diff_sec = target_sec - last_sec
            diff_ticks = (diff_sec * 1000000.0 * tpb) / cur_tempo
            return last_tick + int(round(diff_ticks))

        abs_ticks_list = [[get_tick(ev_t), m] for ev_t, m in self.recorded_events]
        
        if getattr(self, 'rt_quantize', False):
            grid_ticks = float(ticks_per_beat * 4.0) / float(getattr(self, 'rt_quantize_res', 16.0))
            active_notes = {}
            for item in abs_ticks_list:
                tick = item[0]
                msg = item[1]
                ch = getattr(msg, 'channel', None)
                if msg.type == 'note_on' and msg.velocity > 0:
                    snapped = int(round(tick / grid_ticks) * grid_ticks)
                    snapped = max(0, snapped)
                    offset = snapped - tick
                    item[0] = snapped
                    
                    key = (ch, msg.note)
                    if key not in active_notes:
                        active_notes[key] = []
                    active_notes[key].append(offset)
                    
                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                    key = (ch, getattr(msg, 'note', None))
                    if key in active_notes and len(active_notes[key]) > 0:
                        offset = active_notes[key].pop(0)
                        item[0] = int(max(0, tick + offset))
                        if len(active_notes[key]) == 0:
                            del active_notes[key]

        abs_ticks_list.sort(key=lambda x: (x[0], 0 if getattr(x[1], 'type', '') == 'note_off' else 1))

        last_tick = 0
        for tick, msg in abs_ticks_list:
            tick_int = int(tick) 
            new_track.append(copiar_com_tempo(msg, max(0, tick_int - last_tick)))
            last_tick = tick_int
            
        self.midi_file.tracks.append(new_track)
        self.recorded_events = []
        
        self.overrides = {i: {} for i in range(16)}
        
        if hasattr(self, 'consolidar_projeto'):
            self.consolidar_projeto()
        
        self.dirty = True
        self.atualizar_titulo()
        self.ler_midi_memoria(reset_canais=False)
        
        self.current_playback_time = play_time
        self.last_start_time = play_time
        self.seek_flag = True
        
        if was_playing:
            self.tocando = True
            import threading
            threading.Thread(target=self.play_thread, daemon=True).start()
    def toggle_metronomo(self, event):
        self.metronomo_ligado = not self.metronomo_ligado
        status = "Ligado" if self.metronomo_ligado else "Desligado"
        from mhs_utils import falar_status
        falar_status(f"Metrônomo {status}")

    def abrir_preroll(self, event):
        from mhs_dialogs import PreRollDialog
        if not hasattr(self, 'preroll_compassos'): self.preroll_compassos = 0
            
        dlg = PreRollDialog(self, self.preroll_compassos)
        if dlg.ShowModal() == wx.ID_OK:
            self.preroll_compassos = dlg.get_valores()
            from mhs_utils import falar_status
            if self.preroll_compassos > 0:
                falar_status(f"Pré-roll ativado: busca de {self.preroll_compassos} compassos.", imediato=True)
            else:
                falar_status("Pré-roll desligado.", imediato=True)
        dlg.Destroy()
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())

    def toggle_gravacao(self, event):
        self.esperando_nota = False 
        
        if getattr(self, 'is_prerolling', False):
            self.is_prerolling = False
            self.tocando = False
            self.all_notes_off()
            from mhs_utils import falar_status
            falar_status("Pré-roll cancelado.", imediato=True)
            return

        if not self.gravando:
            if not any(can["Arm"] for can in self.canais):
                from mhs_utils import falar_status
                falar_status("Arme pelo menos um canal para gravar")
                return
            
            preroll_bars = getattr(self, 'preroll_compassos', 0)
            if preroll_bars > 0:
                num = 4
                if getattr(self, 'midi_file', None):
                    for track in self.midi_file.tracks:
                        for msg in track:
                            if msg.type == 'time_signature':
                                num = msg.numerator
                                break
                                
                bpm = 60000000.0 / self.current_tempo
                sec_per_beat = 60.0 / bpm
                sec_per_bar = sec_per_beat * num
                recuo_sec = preroll_bars * sec_per_bar
                
                self.record_start_time = self.current_playback_time
                
                novo_tempo = max(0.0, self.current_playback_time - recuo_sec)
                self.current_playback_time = novo_tempo
                self.last_start_time = novo_tempo
                self.seek_flag = True
                self.is_prerolling = True 
                
                self.metronomo_ligado = True 
                
                from mhs_utils import falar_status
                falar_status(f"Pré-roll... Tocando {preroll_bars} compassos antes...", imediato=True)
                
                if not self.tocando:
                    self.tocando = True
                    import threading
                    threading.Thread(target=self.play_thread, daemon=True).start()
            else:
                self.iniciar_gravacao_real()
        else:
            self.gravando = False
            self.atualizar_titulo()
    def iniciar_gravacao_real(self):
        # --- PREPARAÇÃO DO GRAVADOR (Correção do Atraso) ---
        self.recorded_events = []
        # Puxa o TPB exato do arquivo atual (padrão 480 se não houver arquivo)
        self.record_ticks_per_beat = getattr(self.midi_file, 'ticks_per_beat', 480) if getattr(self, 'midi_file', None) else 480
        
        # --- SEU CÓDIGO ORIGINAL INTACTO ---
        self.gravando = True
        self.atualizar_titulo()
        from mhs_utils import falar_status
        falar_status("Gravando", imediato=True)
        if not self.tocando:
            self.toggle_reproducao(None)
    def _executar_preroll(self):
        from mhs_utils import falar_status
        wx.CallAfter(falar_status, f"Pré-roll... {self.preroll_compassos} compassos...", imediato=True)
        
        # Lê a assinatura de compasso para dar os estalos corretos
        num = 4
        if getattr(self, 'midi_file', None):
            for track in self.midi_file.tracks:
                for msg in track:
                    if msg.type == 'time_signature':
                        num = msg.numerator
                        break
                        
        bpm = 60000000.0 / self.current_tempo
        beat_sec = 60.0 / bpm
        
        import mido
        import time
        import threading
        
        for c in range(self.preroll_compassos):
            for b in range(num):
                # Se o usuário mandou parar no meio da contagem, aborta!
                if not getattr(self, 'is_prerolling', False): 
                    return
                
                is_downbeat = (b == 0)
                nota_metro = self.config.get('metro_note_down', 22) if is_downbeat else self.config.get('metro_note_beat', 21)
                vel_metro = self.config.get('metro_vel_down', 100) if is_downbeat else self.config.get('metro_vel_beat', 100)
                
                if self.output:
                    try:
                        self.output.send(mido.Message('note_on', channel=9, note=nota_metro, velocity=vel_metro))
                        threading.Timer(0.05, lambda n=nota_metro: getattr(self, 'output', None) and self.output.send(mido.Message('note_off', channel=9, note=n))).start()
                    except: pass
                    
                time.sleep(beat_sec)
                
        # Contagem terminou! Dispara a gravação valendo na thread principal
        if getattr(self, 'is_prerolling', False):
            self.is_prerolling = False
            wx.CallAfter(self.iniciar_gravacao_real)

    # --- IMPORTANTE: Cancelar o Pré-roll se apertar Espaço! ---
    def all_notes_off(self, ch=None):
        if not self.tocando:
            # Só pausa (nunca "stop" de verdade aqui) - all_notes_off é
            # chamado de MUITOS lugares (editar, desfazer, etc.), não só
            # de Pausar/Parar; pausar preserva a posição do Áudio Guia
            # com segurança em qualquer caso, enquanto um "stop" de
            # verdade só acontece explicitamente em toggle_reproducao.
            self._audio_pause()

        if not self.output: return
        chs = [ch] if ch is not None else range(16)
        for c in chs:
            try:
                self.output.send(mido.Message('control_change', channel=c, control=123, value=0))
                self.output.send(mido.Message('control_change', channel=c, control=64, value=0))
                self.output.send(mido.Message('control_change', channel=c, control=1, value=0))
                self.output.send(mido.Message('pitchwheel', channel=c, pitch=0))
            except: pass


    def enviar_reset_fisico_teclado(self):
        """Envia os comandos físicos de zeramento total estritamente para o hardware do teclado."""
        self.all_notes_off()
        if self.output:
            import mido
            import time
            porta_out = str(self.config.get('porta_out', '')).lower()
            padrao = self.config.get('padrao_midi', 'XG')
            
            is_ms_gs = ('microsoft' in porta_out and 'gs' in porta_out)
            
            if padrao == 'GM' and is_ms_gs:
                pass 
            else:
                try: self.output.send(mido.Message.from_bytes([0xF0, 0x7E, 0x7F, 0x09, 0x01, 0xF7]))
                except: pass
                try: 
                    self.output.send(mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x00, 0x00, 0x7E, 0x00, 0xF7]))
                    # O RESPIRO DO RESET: Sem ele, a Gaveta 1 passava batida na hora de trocar de guia!
                    time.sleep(0.25)
                except: pass
                
            for c in range(16):
                if padrao == 'GM' and is_ms_gs and c == 9:
                    continue
                try: self.output.send(mido.Message('control_change', channel=c, control=121, value=0))
                except: pass
    def atualizar_status(self, falar_canal=False, silenciar=False, apenas_valor=False, shift_held=False, event=None):
        if not hasattr(self, 'canais') or not self.canais: return
        from mhs_utils import falar_status
        
        if type(falar_canal) not in [bool, int]: falar_canal = True
        if type(silenciar) not in [bool, int]: silenciar = False
        if type(apenas_valor) not in [bool, int]: apenas_valor = False
        if type(shift_held) not in [bool, int]: shift_held = False

        c_idx = self.canal_atual
        p_idx = self.propriedade_atual
        prop = self.propriedades[p_idx]
        val = self.canais[c_idx][prop]
        
        texto_valor = str(val)
        if prop == "Bank":
            texto_valor = f"{val} - {self.bank_names.get(val, '')}"
        elif prop == "Patch":
            b = self.canais[c_idx]["Bank"]
            if b in self.instrument_names and val in self.instrument_names[b]:
                texto_valor = f"{val} - {self.instrument_names[b][val]}"
        elif prop == "Nome":
            texto_valor = val if val else "Sem Nome"
        elif prop in ["Mute", "Solo", "Arm"]:
            texto_valor = "Ligado" if val else "Desligado"
        elif prop == "Mono/Poly":
            texto_valor = "Poly" if val else "Mono"
        elif prop == "Transpose":
            texto_valor = f"+{val}" if val > 0 else str(val)

        if hasattr(self, 'info_display'):
            arm_visual = "[ARM] " if self.canais[c_idx]["Arm"] else ""
            self.info_display.SetLabel(f"{arm_visual}Canal: {c_idx + 1} | {prop}: {texto_valor}")

        if not silenciar:
            if falar_canal:
                sel_text = "Selecionado, " if (shift_held and c_idx in self.canais_selecionados and len(self.canais_selecionados) > 1) else ""
                arm_text = "armado, " if self.canais[c_idx]["Arm"] and prop != "Arm" else ""
                
                # --- A MÁGICA DA NAVEGAÇÃO LIMPA ---
                nome_canal = self.canais[c_idx].get("Nome", "")
                falar_status(f"{sel_text}{c_idx + 1} {nome_canal} {arm_text}{prop}: {texto_valor}", imediato=True)
            else:
                texto_tela = f"{prop}: {texto_valor}"
                texto_fala = texto_valor if apenas_valor else texto_tela
                falar_status(texto_fala, imediato=True)
    def abrir_preferencias(self, event):
        from mhs_dialogs import PreferenciasDialog
        dlg = PreferenciasDialog(self, self.config, VERSAO_APP, REPO_GITHUB)
        dlg.ShowModal()
        dlg.Destroy()
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())

    def mostrar_changelog_se_necessario(self):
        # Chamado só pelo bloco __main__ (via wx.CallAfter), nunca de dentro
        # do __init__ - mesmo motivo da checagem de atualização abaixo.
        # Mostra a tela de Changelog só na PRIMEIRA vez que essa versão é
        # aberta (guarda a marca em "changelog_versao_mostrada" no
        # config.json) - silencioso se não houver texto cadastrado pra essa
        # versão. Grava direto no config.json (mesmo padrão inline já usado
        # em outros pontos deste arquivo) em vez de mexer em self.config por
        # inteiro, pra nunca correr o risco de apagar outra chave.
        if self.config.get("changelog_versao_mostrada") == VERSAO_APP:
            return
        texto = CHANGELOG_TEXTS.get(VERSAO_APP)
        if texto:
            dlg = ChangelogDialog(self, VERSAO_APP, texto + MENSAGEM_APOIO)
            dlg.ShowModal()
            dlg.Destroy()
        self.config["changelog_versao_mostrada"] = VERSAO_APP
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    def OnMostrarNovidades(self, event):
        # Menu Ajuda > Novidades desta Versão - reexibe a MESMA tela de
        # Changelog sob demanda, sem mexer em "changelog_versao_mostrada".
        texto = CHANGELOG_TEXTS.get(VERSAO_APP)
        if texto:
            dlg = ChangelogDialog(self, VERSAO_APP, texto + MENSAGEM_APOIO)
            dlg.ShowModal()
            dlg.Destroy()
        else:
            falar_status("Nenhuma novidade cadastrada para esta versão.", imediato=True)

    def OnAbrirPaginaProjeto(self, event):
        import webbrowser
        webbrowser.open(f"https://github.com/MHS-Softwares/{REPO_GITHUB}")

    def verificar_atualizacoes_ao_iniciar(self):
        # Chamado só pelo bloco __main__ (via wx.CallAfter), nunca de dentro
        # do __init__ - roda em thread separada (não pode travar a abertura
        # do programa esperando resposta de rede) e só incomoda o usuário se
        # REALMENTE houver uma versão nova - silencioso em caso de falha de
        # rede ou já estar atualizado (a checagem manual, pelo botão em
        # Preferências, é que dá feedback nos dois casos).
        if not self.config.get('verificar_atualizacoes', True):
            return
        threading.Thread(target=self._verificar_atualizacao_silenciosa_thread, daemon=True).start()

    def _verificar_atualizacao_silenciosa_thread(self):
        info = verificar_nova_versao_detalhado(REPO_GITHUB, VERSAO_APP)
        if info and info['tem']:
            wx.CallAfter(self._avisar_atualizacao_disponivel, info)

    def _avisar_atualizacao_disponivel(self, info):
        # Janela de atualização: baixa o instalador direto daqui e, ao fim,
        # oferece instalar na hora (fecha o programa e abre o instalador).
        oferecer_atualizacao(self, self, "MHS MIDI Sequencer", info['versao'], VERSAO_APP, info['url_pagina'], info['instalador'])

    def navegar_canais(self, event):
        self.foco_inteligente = None # <--- Quebra o foco especial!
        eid = event.GetId()
        if eid == 101 and self.canal_atual > 0: self.canal_atual -= 1
        elif eid == 102 and self.canal_atual < 15: self.canal_atual += 1
        
        self.non_continuous_sel = False
        self.canais_selecionados = {self.canal_atual}
        self.atualizar_status(True)

    def toggle_selecao_canal(self, event):
        from mhs_utils import falar_status
        if not getattr(self, 'non_continuous_sel', False):
            self.non_continuous_sel = True
            self.canais_selecionados.add(self.canal_atual)
            falar_status(f"Seleção não contínua ativada. Canal {self.canal_atual+1} selecionado", imediato=True)
        else:
            if self.canal_atual in self.canais_selecionados:
                self.canais_selecionados.remove(self.canal_atual)
                falar_status(f"Canal {self.canal_atual+1} não selecionado", imediato=True)
            else:
                self.canais_selecionados.add(self.canal_atual)
                falar_status(f"Canal {self.canal_atual+1} selecionado", imediato=True)

    def navegar_canais_shift(self, event):
        eid = event.GetId()
        if eid == 131 and self.canal_atual > 0: self.canal_atual -= 1
        elif eid == 132 and self.canal_atual < 15: self.canal_atual += 1
        
        if getattr(self, 'non_continuous_sel', False):
            is_sel = self.canal_atual in self.canais_selecionados
            estado = "selecionado" if is_sel else "não selecionado"
            from mhs_utils import falar_status
            falar_status(f"Canal {self.canal_atual + 1} {estado}", imediato=True)
        else:
            self.canais_selecionados.add(self.canal_atual)
            self.atualizar_status(falar_canal=True, shift_held=True)

    def selecionar_todos_canais(self, event):
        from mhs_utils import falar_status
        self.canais_selecionados = set(range(16))
        falar_status("Todos os canais selecionados")
        self.atualizar_status(True, silenciar=True)

    def navegar_propriedades(self, event):
        eid = event.GetId()
        if eid == 103 and self.propriedade_atual > 0: self.propriedade_atual -= 1
        elif eid == 104 and self.propriedade_atual < len(self.propriedades)-1: self.propriedade_atual += 1
        self.atualizar_status(False)

    def acao_enter(self, event):
        self.save_state("Edição de Propriedades")
        p = self.propriedades[self.propriedade_atual]
        alvos = self.canais_selecionados if self.canal_atual in self.canais_selecionados else {self.canal_atual}
        
        if p in ["Mute", "Solo", "Arm", "Mono/Poly"]:
            novo_estado = not self.canais[self.canal_atual][p]
            for ch in alvos:
                self.canais[ch][p] = novo_estado
                if p == "Mute" and novo_estado:
                    self.all_notes_off(ch)
                elif p == "Solo" and novo_estado:
                    for i in range(16):
                        if i not in alvos:
                            self.all_notes_off(i)
                elif p == "Mono/Poly":
                    self.enviar_midi_param(p, novo_estado, ch)
                            
            self.dirty = True
            self.atualizar_titulo()
            self.atualizar_status(apenas_valor=True)
        else:
            dlg = wx.TextEntryDialog(self, f"Valor para {len(alvos)} canais:", "Editar", str(self.canais[self.canal_atual][p]))
            if dlg.ShowModal() == wx.ID_OK:
                valor_digitado = dlg.GetValue()
                
                if p == "Nome":
                    for ch in alvos:
                        self.canais[ch][p] = valor_digitado.strip()
                    self.dirty = True
                    self.atualizar_titulo()
                    self.atualizar_status(apenas_valor=True)
                else:
                    try: 
                        v = int(valor_digitado)
                        if p == "Bank": min_v, max_v = 0, 16384
                        elif p == "Transpose": min_v, max_v = -12, 12
                        elif p == "Pitch Bend": min_v, max_v = 0, 24
                        elif p == "Input": min_v, max_v = 1, 16
                        else: min_v, max_v = 0, 127
                        
                        v = max(min_v, min(max_v, v))
                        
                        for ch in alvos:
                            self.canais[ch][p] = v
                            if p not in ["Transpose", "Input"]: 
                                self.enviar_midi_param(p, v, canal=ch)
                                
                        self.atualizar_status(apenas_valor=True)
                    except Exception: 
                        pass
            
            wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
            dlg.Destroy()
    def alterar_valor(self, event=None, prop=None, dir=None):
        if prop is None:
            prop = self.propriedades[self.propriedade_atual]
        if dir is None:
            if event:
                eid = event.GetId()
                dir = 1 if eid == 108 else -1
            else:
                dir = 1

        mudou = False

        for ch in self.canais_selecionados:
            val = self.canais[ch].get(prop)
            
            if val is None:
                if prop in ["Mute", "Solo", "Arm", "Mono/Poly"]: val = False
                elif prop == "Input": val = 1
                else: val = 0
            
            novo_val = val

            if prop in ["Volume", "Pan", "Expression", "Reverb", "Chorus", "Grave", "Agudo", "Porta Time"]:
                novo_val = max(0, min(127, val + dir))
            elif prop == "Transpose":
                novo_val = max(-64, min(63, val + dir))
            elif prop == "Pitch Bend":
                novo_val = max(0, min(24, val + dir))
            elif prop == "Input":
                novo_val = max(1, min(16, val + dir))
            elif prop in ["Mute", "Solo", "Arm", "Mono/Poly"]:
                novo_val = not val
                
            elif prop == "Bank":
                # O Piloto Automático Limpo
                if hasattr(self, 'bank_names') and self.bank_names:
                    # Lê as chaves garantindo que a matemática funcione
                    bancos_disponiveis = sorted([int(k) for k in self.bank_names.keys()])
                    if val in bancos_disponiveis:
                        idx = bancos_disponiveis.index(val)
                        novo_idx = max(0, min(len(bancos_disponiveis) - 1, idx + dir))
                        novo_val = bancos_disponiveis[novo_idx]
                    else:
                        if dir > 0:
                            maiores = [b for b in bancos_disponiveis if b > val]
                            novo_val = maiores[0] if maiores else bancos_disponiveis[-1]
                        else:
                            menores = [b for b in bancos_disponiveis if b < val]
                            novo_val = menores[-1] if menores else bancos_disponiveis[0]
                else:
                    novo_val = max(0, min(16383, val + dir))
                    
            elif prop == "Patch":
                banco_atual = self.canais[ch].get("Bank", 0)
                inst_dict = {}
                if hasattr(self, 'instrument_names'):
                    inst_dict = self.instrument_names.get(banco_atual) or self.instrument_names.get(str(banco_atual)) or {}
                    
                if inst_dict:
                    patchs_disponiveis = sorted([int(k) for k in inst_dict.keys()])
                    if val in patchs_disponiveis:
                        idx = patchs_disponiveis.index(val)
                        novo_idx = max(0, min(len(patchs_disponiveis) - 1, idx + dir))
                        novo_val = patchs_disponiveis[novo_idx]
                    else:
                        if dir > 0:
                            maiores = [p for p in patchs_disponiveis if p > val]
                            novo_val = maiores[0] if maiores else patchs_disponiveis[-1]
                        else:
                            menores = [p for p in patchs_disponiveis if p < val]
                            novo_val = menores[-1] if menores else patchs_disponiveis[0]
                else:
                    novo_val = max(0, min(127, val + dir))

            if novo_val != val:
                self.canais[ch][prop] = novo_val
                if prop not in ["Nome", "Input", "Mute", "Solo", "Arm"]:
                    if ch not in self.overrides:
                        self.overrides[ch] = {}
                    self.overrides[ch][prop] = novo_val
                    self.enviar_midi_param(prop, novo_val, ch)
                
                # --- A ACESSIBILIDADE DIRETA QUE TAVA FALTANDO! ---
                from mhs_utils import falar_status
                if prop == "Bank":
                    nome_b = self.bank_names.get(novo_val) or self.bank_names.get(str(novo_val)) or f"Banco {novo_val}"
                    falar_status(f"Banco {novo_val}, {nome_b}", imediato=True)
                elif prop == "Patch":
                    b_atual = self.canais[ch].get("Bank", 0)
                    dict_patch = self.instrument_names.get(b_atual) or self.instrument_names.get(str(b_atual)) or {}
                    nome_p = dict_patch.get(novo_val) or dict_patch.get(str(novo_val)) or f"Patch {novo_val}"
                    falar_status(f"Patch {novo_val}, {nome_p}", imediato=True)
                elif prop in ["Mute", "Solo", "Arm"]:
                    estado = "Ligado" if novo_val else "Desligado"
                    falar_status(f"{prop} {estado}", imediato=True)
                else:
                    falar_status(f"{prop} {novo_val}", imediato=True)
                    
                mudou = True

        if mudou:
            self.dirty = True
            import wx
            wx.CallAfter(self.atualizar_status)
    def get_current_tempo(self):
        current_tempo = 500000
        if not hasattr(self, 'play_events'): return current_tempo
        for ev_time, msg in self.play_events:
            if ev_time > self.current_playback_time:
                break
            if msg.type == 'set_tempo':
                current_tempo = msg.tempo
        return current_tempo

    def abrir_envelope_tempo(self, event):
        actual_tempo = self.get_current_tempo()
        current_bpm = int(round(60000000.0 / actual_tempo))
        
        has_selection = False
        if self.time_selection_start is not None and self.time_selection_end is not None:
            if abs(self.time_selection_end - self.time_selection_start) > 0.05:
                has_selection = True
                
        from mhs_dialogs import TempoEnvelopeDialog
        dlg = TempoEnvelopeDialog(self, current_bpm, has_selection)
        if dlg.ShowModal() == wx.ID_OK:
            is_gradual, val_start, val_end = dlg.get_valores()
            self.aplicar_envelope_tempo(is_gradual, val_start, val_end)
        
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
        dlg.Destroy()
        
    def aplicar_envelope_tempo(self, is_gradual, start_bpm, end_bpm):
        from mhs_utils import falar_status
        if not self.midi_file: return

        if is_gradual and (self.time_selection_start is None or self.time_selection_end is None or abs(self.time_selection_end - self.time_selection_start) < 0.05):
            falar_status("Erro: Não foi possível criar a rampa. Você precisa marcar um trecho com as teclas I e O primeiro.", imediato=True)
            return

        self.save_state("Envelope de Tempo")

        start_bpm = max(10, min(400, start_bpm))
        end_bpm = max(10, min(400, end_bpm))

        if not is_gradual:
            # "Brusco" é uma troca de andamento GLOBAL (a música inteira),
            # exatamente como Ctrl+/Ctrl-, Tap Tempo e Tempo Preciso - por
            # isso usa a MESMA `_definir_bpm_global`, que sempre achata
            # TODO set_tempo de TODAS as trilhas antes de gravar o novo. A
            # versão antiga só apagava um set_tempo bem no tick atual (se
            # existisse um ali) e inseria o novo naquele mesmo ponto -
            # qualquer troca de andamento feita em outra posição (ou tick
            # 0) ficava intocada, e usar o Shift+C várias vezes em pontos
            # diferentes da música ia empilhando um "envelope" de tempo
            # não intencional (achado pelo Michel: gravações indo cada vez
            # mais adiantadas quanto mais ele mexia no andamento ao longo
            # da edição - o "envelope" acumulado desalinhava a conversão
            # segundo->tick usada na gravação).
            self._definir_bpm_global(start_bpm)
            self.dirty = True
            self.atualizar_titulo()
            falar_status(f"Tempo alterado bruscamente para {start_bpm} BPM", imediato=True)
            self.ler_midi_memoria(reset_canais=False)
            self.seek_flag = True
            return

        tpb = max(1, getattr(self.midi_file, 'ticks_per_beat', 480))

        start_sec = min(self.time_selection_start, self.time_selection_end)
        end_sec = max(self.time_selection_start, self.time_selection_end)

        start_tick = self.get_tick_at_sec(start_sec)
        end_tick = self.get_tick_at_sec(end_sec)

        if end_tick <= start_tick:
            falar_status("Erro: o trecho marcado é grande demais ou inválido para a rampa.", imediato=True)
            return

        track_idx = 0

        import mido
        if not self.midi_file.tracks:
            self.midi_file.tracks.append(mido.MidiTrack())

        track = self.midi_file.tracks[track_idx]

        abs_events = []
        current_abs = 0
        for msg in track:
            current_abs += msg.time
            abs_events.append([current_abs, msg])

        abs_events = [item for item in abs_events if not (item[1].type == 'set_tempo' and start_tick <= item[0] <= end_tick)]

        bpm_diff = end_bpm - start_bpm
        step_ticks = max(1, tpb // 4)

        current_tick = start_tick
        while current_tick < end_tick:
            progress = (current_tick - start_tick) / (end_tick - start_tick)
            current_bpm_step = start_bpm + (bpm_diff * progress)
            new_tempo = int(60000000.0 / current_bpm_step)
            abs_events.append([int(round(current_tick)), mido.MetaMessage('set_tempo', tempo=new_tempo)])
            current_tick += step_ticks

        final_tempo = int(60000000.0 / end_bpm)
        abs_events.append([end_tick, mido.MetaMessage('set_tempo', tempo=final_tempo)])
        falar_status(f"Rampa de tempo criada com sucesso de {start_bpm} para {end_bpm} BPM", imediato=True)

        abs_events.sort(key=lambda x: x[0])
        
        new_track = mido.MidiTrack()
        last_tick = 0
        for tick, msg in abs_events:
            delta = max(0, tick - last_tick)
            new_track.append(copiar_com_tempo(msg, delta))
            last_tick = tick
            
        self.midi_file.tracks[track_idx] = new_track
        
        self.dirty = True
        self.atualizar_titulo()
        
        was_playing = self.tocando
        if self.tocando:
            self.tocando = False
            self.all_notes_off()
            time.sleep(0.05)
            
        self.ler_midi_memoria(reset_canais=False)
        self.seek_flag = True
        
        if was_playing:
            self.tocando = True
            threading.Thread(target=self.play_thread, daemon=True).start()

    def obter_notas_selecao_global(self):
        t_start, t_end = self.get_selection_bounds()
        start_tick = self.get_tick_at_sec(t_start)
        end_tick = self.get_tick_at_sec(t_end)
        canais_alvo = getattr(self, 'canais_selecionados', {self.canal_atual})
        
        notas_selecionadas = []
        for track in self.midi_file.tracks:
            abs_t = 0
            active = {}
            for msg in track:
                abs_t += msg.time
                ch = getattr(msg, 'channel', None)
                if ch in canais_alvo:
                    if msg.type == 'note_on' and msg.velocity > 0:
                        if start_tick <= abs_t < end_tick:
                            ev = {'start': abs_t, 'msg_on': msg, 'channel': ch, 'end': abs_t + 100}
                            active[(ch, msg.note)] = ev
                            notas_selecionadas.append(ev)
                    elif msg.type in ['note_off', 'note_on']:
                        key = (ch, getattr(msg, 'note', None))
                        if key in active:
                            active[key]['end'] = abs_t
                            active[key]['msg_off'] = msg
                            del active[key]
        return notas_selecionadas

    def abrir_quantizacao_offline(self, event):
        from mhs_utils import falar_status
        if not self.midi_file:
            falar_status("Nenhum arquivo aberto.")
            return

        self.preview_is_playing = False
        from mhs_dialogs import QuantizeProDialog
        dlg = QuantizeProDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            grid_ticks, forca = dlg.get_values()
            self.save_state("Quantização de Precisão")
            
            t_start, t_end = self.get_selection_bounds()
            st_tick = self.get_tick_at_sec(t_start)
            ed_tick = self.get_tick_at_sec(t_end)
            canais_alvo = getattr(self, 'canais_selecionados', {self.canal_atual})
            
            import mido
            notas_mudadas = 0
            for i, track in enumerate(self.midi_file.tracks):
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
                    new_track.append(copiar_com_tempo(m, t - curr))
                    curr = t
                self.midi_file.tracks[i] = new_track

            self.dirty = True
            self.ler_midi_memoria(reset_canais=False)
            falar_status(f"{notas_mudadas} notas quantizadas.", imediato=True)
        
        dlg.Destroy()
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())

    def play_quantize_preview(self, grid_ticks, forca):
        self.preview_is_playing = False
        time.sleep(0.02)
        
        self.preview_is_playing = True
        t = threading.Thread(target=self._tocar_preview_quantize_global, args=(grid_ticks, forca))
        t.daemon = True
        t.start()
        try:
            from mhs_utils import falar_status
            falar_status("Tocando preview quantizado global...", imediato=True)
        except: pass

    def _tocar_preview_quantize_global(self, grid_ticks, forca):
        tpb = max(1, getattr(self.midi_file, 'ticks_per_beat', 480))
        t_start_sec = getattr(self, 'time_selection_start', None)
        t_end_sec = getattr(self, 'time_selection_end', None)
        has_selection = False
        t_min_sec, t_max_sec = 0.0, 0.0
        
        if t_start_sec is not None and t_end_sec is not None:
            if abs(t_end_sec - t_start_sec) > 0.01:
                has_selection = True
                t_min_sec = min(t_start_sec, t_end_sec)
                t_max_sec = max(t_start_sec, t_end_sec)
                
        canais_alvo = getattr(self, 'canais_selecionados', {self.canal_atual})
        if not canais_alvo: canais_alvo = {self.canal_atual}
        
        tempo_map = []
        for track in self.midi_file.tracks:
            abs_t_track = 0
            for msg in track:
                abs_t_track += msg.time
                if msg.type == 'set_tempo':
                    tempo_map.append((abs_t_track, msg.tempo))
        tempo_map.sort(key=lambda x: x[0])
        if not tempo_map:
            tempo_map.append((0, 500000))
            
        def tick_to_sec(target_tick):
            last_t = 0
            last_s = 0.0
            cur_tempo = 500000
            for tm_tick, tm_val in tempo_map:
                if tm_tick >= target_tick:
                    break
                diff_ticks = tm_tick - last_t
                last_s += mido.tick2second(diff_ticks, tpb, cur_tempo)
                last_t = tm_tick
                cur_tempo = tm_val
            diff_ticks = max(0, target_tick - last_t)
            if diff_ticks > 0:
                last_s += mido.tick2second(diff_ticks, tpb, cur_tempo)
            return last_s
        
        preview_events = []
        for track in self.midi_file.tracks:
            abs_t = 0
            active = {}
            for msg in track:
                abs_t += msg.time
                ch = getattr(msg, 'channel', None)
                if ch in canais_alvo:
                    if msg.type == 'note_on' and msg.velocity > 0:
                        sec = tick_to_sec(abs_t)
                        if has_selection and not (t_min_sec - 0.001 <= sec <= t_max_sec + 0.001):
                            continue
                        
                        closest = round(abs_t / grid_ticks) * grid_ticks
                        diff = closest - abs_t
                        move = int(round(diff * (forca / 100.0)))
                        new_start = max(0, abs_t + move)
                        active[(ch, msg.note)] = new_start
                        
                        sec_on = tick_to_sec(new_start)
                        preview_events.append({'sec': sec_on, 'type': 'on', 'msg': msg})
                        
                    elif msg.type in ['note_off', 'note_on']:
                        key = (ch, getattr(msg, 'note', None))
                        if key in active:
                            new_start = active.pop(key)
                            dur = max(10, abs_t - new_start) 
                            
                            sec_off = tick_to_sec(new_start + dur)
                            msg_off = mido.Message('note_off', channel=ch, note=msg.note, velocity=0)
                            preview_events.append({'sec': sec_off, 'type': 'off', 'msg': msg_off})
                            
        if not preview_events:
            self.preview_is_playing = False
            return
            
        preview_events.sort(key=lambda x: x['sec'])
        
        cursor_sec = getattr(self, 'current_playback_time', 0.0)
        valid_events = []
        for ev in preview_events:
            if ev['sec'] >= cursor_sec:
                valid_events.append(ev)
                
        if not valid_events:
            self.preview_is_playing = False
            return
            
        start_real_time = time.time()
        first_event_sec = valid_events[0]['sec']
        
        for p_ev in valid_events:
            if not getattr(self, 'preview_is_playing', False):
                break 
                
            target_real_time = start_real_time + (p_ev['sec'] - first_event_sec)
            
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
                
            if getattr(self, 'output', None):
                try:
                    self.output.send(p_ev['msg'])
                except: pass
                
        self.preview_is_playing = False
        if hasattr(self, 'all_notes_off'):
            self.all_notes_off()

    def abrir_quantizacao_realtime(self, event):
        from mhs_utils import falar_status
        from mhs_dialogs import QuantizacaoRealTimeDialog
        dlg = QuantizacaoRealTimeDialog(self, self.rt_quantize, self.rt_quantize_res)
        if dlg.ShowModal() == wx.ID_OK:
            self.rt_quantize, self.rt_quantize_res = dlg.get_valores()
            status_str = "Ligada" if self.rt_quantize else "Desligada"
            falar_status(f"Quantização em gravação {status_str}.")
            
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
        dlg.Destroy()

    def abrir_voice_creator(self, event):
        from mhs_utils import falar_status
        if not self.midi_file: return
        self.consolidar_projeto()
        falar_status(f"Abrindo Voice Creator para Canal {self.canal_atual + 1}")
        dlg = VoiceCreatorDialog(self, self.canal_atual, self.canais[self.canal_atual].get("VoiceCreator", {}))
        self.active_voice_creator = dlg
        try:
            if dlg.ShowModal() == wx.ID_OK:
                self.save_state("Edição Voice Creator")
                self.canais[self.canal_atual]["VoiceCreator"] = dlg.get_valores()
                self.dirty = True
                self.atualizar_titulo()
                self.consolidar_projeto()
                self.ler_midi_memoria(reset_canais=False)
                falar_status("Voice Creator salvo no canal.", imediato=True)
        finally:
            self.active_voice_creator = None
            dlg.Destroy()
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())

    def abrir_editor_sysex(self, event):
        from mhs_utils import falar_status
        from mhs_dialogs import SysExEditorDialog
        if not self.midi_file: return
        self.consolidar_projeto()
        falar_status(f"Abrindo Editor de SysEx para Canal {self.canal_atual + 1}")
        dlg = SysExEditorDialog(self, self.canal_atual)
        if dlg.ShowModal() == wx.ID_OK:
            bytes_sysex = dlg.get_sysex_bytes()
            if bytes_sysex:
                try:
                    sysex_msg = mido.Message.from_bytes(bytes_sysex)
                    self.aplicar_sysex_cabeca(sysex_msg)
                except Exception as e:
                    falar_status("Erro ao criar SysEx. Verifique os valores em Hexadecimal.", imediato=True)
            else:
                falar_status("Valores inválidos. SysEx cancelado.", imediato=True)
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
        dlg.Destroy()

    def aplicar_sysex_cabeca(self, sysex_msg):
        self.save_state("Inserir SysEx (Raiz)")
        
        if not self.midi_file.tracks:
            self.midi_file.tracks.append(mido.MidiTrack())
            
        track = self.midi_file.tracks[0]
        
        abs_events = []
        current_abs = 0
        for msg in track:
            current_abs += msg.time
            abs_events.append([current_abs, msg])
            
        abs_events.insert(0, [0, copiar_com_tempo(sysex_msg, 0)])
        abs_events.sort(key=lambda x: x[0])
        
        new_track = mido.MidiTrack()
        last_tick = 0
        for tick, msg in abs_events:
            delta = max(0, int(round(tick - last_tick)))
            new_track.append(copiar_com_tempo(msg, delta))
            last_tick = tick
            
        self.midi_file.tracks[0] = new_track
        self.dirty = True
        self.atualizar_titulo()
        
        if self.output:
            try:
                self.output.send(sysex_msg)
            except: pass
            
        self.ler_midi_memoria(reset_canais=True)
        from mhs_utils import falar_status
        falar_status("SysEx aplicado na cabeça da música e sincronizado com a tela.", imediato=True)

    def abrir_envelope_cc(self, event):
        from mhs_utils import falar_status
        from mhs_dialogs import EnvelopeCCDialog
        if not self.midi_file: return
        if self.time_selection_start is None or self.time_selection_end is None or abs(self.time_selection_end - self.time_selection_start) < 0.05:
            falar_status("Aviso: Marque um trecho com as teclas I e O antes de aplicar a rampa de Control Change.", imediato=True)
            return
            
        dlg = EnvelopeCCDialog(self, self.canal_atual)
        if dlg.ShowModal() == wx.ID_OK:
            cc_num, val_start, val_end = dlg.get_valores()
            self.aplicar_envelope_cc(cc_num, val_start, val_end)
        
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
        dlg.Destroy()

    def aplicar_envelope_cc(self, cc_num, val_start, val_end):
        from mhs_utils import falar_status, get_cc_name
        self.save_state("Envelope de CC")
        tpb = max(1, getattr(self.midi_file, 'ticks_per_beat', 480))
        
        start_sec = min(self.time_selection_start, self.time_selection_end)
        end_sec = max(self.time_selection_start, self.time_selection_end)
            
        start_tick = self.get_tick_at_sec(start_sec)
        end_tick = self.get_tick_at_sec(end_sec)
        
        if end_tick <= start_tick: return
        
        alvos = self.canais_selecionados if self.canais_selecionados else {self.canal_atual}
        
        for ch in alvos:
            track_idx = 0
            for i, tr in enumerate(self.midi_file.tracks):
                if any(getattr(m, 'channel', None) == ch for m in tr):
                    track_idx = i
                    break
            
            track = self.midi_file.tracks[track_idx]
            
            abs_events = []
            current_abs = 0
            for msg in track:
                current_abs += msg.time
                abs_events.append([current_abs, msg])
                
            abs_events = [item for item in abs_events if not (getattr(item[1], 'type', '') == 'control_change' and getattr(item[1], 'channel', None) == ch and item[1].control == cc_num and start_tick <= item[0] <= end_tick)]
            
            diff_val = val_end - val_start
            step_ticks = max(1, tpb // 8)
            
            current_tick = start_tick
            while current_tick < end_tick:
                progress = (current_tick - start_tick) / (end_tick - start_tick)
                current_val = int(round(val_start + (diff_val * progress)))
                abs_events.append([int(round(current_tick)), mido.Message('control_change', channel=ch, control=cc_num, value=current_val)])
                current_tick += step_ticks
                
            abs_events.append([end_tick, mido.Message('control_change', channel=ch, control=cc_num, value=val_end)])
                
            abs_events.sort(key=lambda x: x[0])
            
            new_track = mido.MidiTrack()
            last_tick = 0
            for tick, msg in abs_events:
                delta = max(0, tick - last_tick)
                new_track.append(copiar_com_tempo(msg, delta))
                last_tick = tick
                
            self.midi_file.tracks[track_idx] = new_track
            
        falar_status(f"Rampa de {get_cc_name(cc_num)} criada de {val_start} para {val_end} em {len(alvos)} canais", imediato=True)
        
        self.dirty = True
        self.atualizar_titulo()
        
        was_playing = self.tocando
        if self.tocando:
            self.tocando = False
            self.all_notes_off()
            time.sleep(0.05)
            
        self.ler_midi_memoria(reset_canais=False)
        self.seek_flag = True
        
        if was_playing:
            self.tocando = True
            threading.Thread(target=self.play_thread, daemon=True).start()


    def abrir_fade(self, event):
        from mhs_utils import falar_status
        if not self.midi_file:
            falar_status("Nenhum projeto aberto.", imediato=True)
            return
            
        t_start = getattr(self, 'time_selection_start', None)
        t_end = getattr(self, 'time_selection_end', None)
        
        if t_start is None or t_end is None or abs(t_end - t_start) < 0.05:
            falar_status("Aviso: Marque um trecho com as teclas I e O para definir o tamanho do Fade.", imediato=True)
            return
            
        try:
            from mhs_dialogs import FadeDialog
            dlg = FadeDialog(self)
            if dlg.ShowModal() == wx.ID_OK:
                tipo_fade, todos_canais = dlg.get_valores()
                # 0 = Fade In (0 a 127), 1 = Fade Out (127 a 0)
                val_start = 0 if tipo_fade == 0 else 127
                val_end = 127 if tipo_fade == 0 else 0
                
                # Guarda a sua seleção atual de canais para não bagunçar sua tela
                selecao_backup = set(self.canais_selecionados)
                
                # Se marcou Master Fade, o sistema força a seleção de todos os 16 canais na memória
                if todos_canais:
                    self.canais_selecionados = set(range(16))
                    
                self.aplicar_envelope_cc(11, val_start, val_end)
                
                # Devolve a seleção ao estado original
                self.canais_selecionados = selecao_backup
                
            dlg.Destroy()
            wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
        except Exception as e:
            falar_status(f"Erro ao abrir: {e}", imediato=True)
    def _sanear_time_signatures(self):
        # Remove Figuras de Compasso (time_signature) EMPILHADAS - mais de uma
        # no mesmo tick - mantendo a primeira de cada tick. NUNCA cria nem
        # altera nenhuma; figuras em ticks diferentes (mudança de compasso real
        # no meio da música) são preservadas.
        if not getattr(self, 'midi_file', None) or not self.midi_file.tracks:
            return
        for ti, track in enumerate(self.midi_file.tracks):
            vistos = set()
            carry = 0
            abs_t = 0
            novo = []
            for msg in track:
                abs_t += msg.time
                if msg.type == 'time_signature':
                    if abs_t in vistos:
                        carry += msg.time
                        continue
                    vistos.add(abs_t)
                if carry:
                    msg = copiar_com_tempo(msg, msg.time + carry)
                    carry = 0
                novo.append(msg)
            if carry and novo:
                novo[-1] = copiar_com_tempo(novo[-1], novo[-1].time + carry)
            track[:] = novo

    def _definir_bpm_global(self, bpm):
        # Define o ANDAMENTO GERAL da música: um único set_tempo no comecinho da
        # trilha mestre, sem tocar em NENHUM time_signature e sem deixar
        # "envelopes" de tempo espalhados. Usado por todos os caminhos de
        # mudança de BPM (Ctrl+/Ctrl-, Tempo Preciso, tap, teclado externo).
        import mido
        # Só o MICROSSEGUNDO por batida (o que vai de verdade pro MIDI)
        # precisa ser inteiro - o BPM em si é mantido com casas decimais.
        # Arredondar o BPM pra inteiro aqui (como era antes) fazia o
        # "Tempo Preciso" digitar 101.900 e aplicar 102 na cara dura, e o
        # Tap Tempo perder precisão silenciosamente contra o andamento
        # real de um áudio de referência.
        bpm = max(10.0, min(500.0, float(bpm)))
        self.current_tempo = int(round(60000000.0 / bpm))
        if not getattr(self, 'midi_file', None) or not self.midi_file.tracks:
            return bpm
        # Tira TODO set_tempo de TODAS as trilhas (achata envelope e remove
        # sobras), sem engolir o tempo do evento seguinte.
        for ti, track in enumerate(self.midi_file.tracks):
            carry = 0
            novo = []
            for msg in track:
                if msg.type == 'set_tempo':
                    carry += msg.time
                    continue
                if carry:
                    msg = copiar_com_tempo(msg, msg.time + carry)
                    carry = 0
                novo.append(msg)
            if carry and novo:
                novo[-1] = copiar_com_tempo(novo[-1], novo[-1].time + carry)
            track[:] = novo
        # Um único set_tempo no início da trilha mestre.
        self.midi_file.tracks[0].insert(0, mido.MetaMessage('set_tempo', tempo=self.current_tempo, time=0))
        # De quebra, cura qualquer Figura de Compasso empilhada de um arquivo
        # que já tenha sido corrompido antes.
        self._sanear_time_signatures()
        return bpm

    def change_tempo(self, amount=None, exact=None):
        from mhs_utils import falar_status
        import mido
        if not self.midi_file: return
        self.save_state("Mudança de Tempo")

        actual_tempo = self.get_current_tempo()
        current_bpm = int(round(60000000.0 / actual_tempo))

        if exact is not None:
            new_bpm = exact
        else:
            new_bpm = current_bpm + amount

        # Troca de andamento AO VIVO, igual ao Tap Tempo (ver do_tap_tempo)
        # - nunca para a thread de Play nem o Áudio Guia, nunca manda
        # all_notes_off nem tem sleep de segurança: só avisa a thread de
        # Play (_pausar_leitura_eventos) pra esperar 1ms enquanto
        # play_events/beat_events são reconstruídos, sem interromper nada.
        self._pausar_leitura_eventos = True
        try:
            new_bpm = self._definir_bpm_global(new_bpm)
            self.ler_midi_memoria(reset_canais=False)
            self.seek_flag = False

            self.msg_index = len(self.play_events)
            for i, ev in enumerate(self.play_events):
                if ev[0] >= self.current_playback_time:
                    self.msg_index = i
                    break
            self.beat_index = len(self.beat_events)
            for i, (b_time, is_d) in enumerate(self.beat_events):
                if b_time >= self.current_playback_time:
                    self.beat_index = i
                    break
        finally:
            self._pausar_leitura_eventos = False

        self.dirty = True
        self.atualizar_titulo()

        # --- A REVANCHE DO SEQUENCIADOR: Mandando o BPM pro Teclado! ---
        if getattr(self, 'output', None):
            try:
                micros = self.current_tempo
                # Engenharia Reversa: Quebra o numerão em 3 bytes de 7 bits (0 a 127)
                d4 = (micros // 16384) & 0x7F
                d5 = ((micros % 16384) // 128) & 0x7F
                d6 = micros % 128
                
                # Montando o pacote: F0 + Yamaha + Arranger + Tempo Control + 00 + Bytes de Tempo + F7
                syx_msg = mido.Message.from_bytes([0xF0, 67, 126, 1, 0, d4, d5, d6, 0xF7])
                self.output.send(syx_msg)
            except: pass

        falar_status(f"Tempo {new_bpm:g} BPM", imediato=True)
    def abrir_audio_guia(self, event):
        from mhs_dialogs import AudioGuiaDialog
        from mhs_utils import falar_status
        import os
        import re
        import wx
        
        dlg = AudioGuiaDialog(self, self.audio_path, self.audio_volume, self.audio_offset)
        if dlg.ShowModal() == wx.ID_OK:
            self.audio_path, self.audio_volume, self.audio_offset = dlg.get_valores()
            
            # --- A MÁGICA DA ÂNCORA MUSICAL ---
            if hasattr(self, 'get_tick_at_sec') and self.audio_offset >= 0:
                self.audio_offset_tick = self.get_tick_at_sec(self.audio_offset)
                
            self._audio_stop()
            try:
                if self.audio_path and os.path.exists(self.audio_path):
                    self._audio_reset_mixer_format()

                    # --- O DETETIVE DE BPM EMBUTIDO ---
                    nome_arquivo = os.path.basename(self.audio_path)
                    bpm_detectado = None

                    match = re.search(r'(\d+)[\s_-]*bpm', nome_arquivo, re.IGNORECASE)
                    if match:
                        bpm_detectado = int(match.group(1))

                    if bpm_detectado:
                        self.change_tempo(exact=bpm_detectado)
                        falar_status(f"Áudio configurado. BPM {bpm_detectado} detectado no arquivo e ajustado no projeto!", imediato=True)
                    else:
                        falar_status(f"Áudio Guia configurado. Volume {self.audio_volume} porcento.", imediato=True)

                else:
                    falar_status("Áudio Guia removido.", imediato=True)
            except Exception as e:
                pass
            
            self.dirty = True
            self.atualizar_titulo()
            self.salvar_config_audio()
            
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
        dlg.Destroy()
    def set_local_control(self, ligado):
        # Manda o Local Control (CC 122) pro estado pedido, sem depender do
        # que estava antes - usado tanto pelo F8 (que alterna) quanto pelo
        # liga/desliga automático ao abrir/fechar o programa.
        self.local_control_on = ligado
        val = 127 if ligado else 0

        if self.output:
            for ch in range(16):
                try:
                    self.output.send(mido.Message('control_change', channel=ch, control=122, value=val))
                except: pass

        return self.local_control_on

    def toggle_local_control(self, event):
        from mhs_utils import falar_status
        if not hasattr(self, 'local_control_on'):
            self.local_control_on = True

        self.set_local_control(not self.local_control_on)

        estado = "Ligado" if self.local_control_on else "Desligado"
        falar_status(f"Som do Teclado (Local Control) {estado}", imediato=True)

    def do_tap_tempo(self, event=None):
        agora = time.time()
        if not hasattr(self, 'tap_times'):
            self.tap_times = []
            
        if self.tap_times and (agora - self.tap_times[-1]) > 1.5:
            self.tap_times = []
            
        self.tap_times.append(agora)
        
        if len(self.tap_times) > 4:
            self.tap_times.pop(0)
            
        if len(self.tap_times) >= 2:
            intervalos = [self.tap_times[i] - self.tap_times[i-1] for i in range(1, len(self.tap_times))]
            media = sum(intervalos) / len(intervalos)
            if media > 0:
                novo_bpm = 60.0 / media
                novo_bpm = max(20.0, min(500.0, novo_bpm))

                # Troca de andamento AO VIVO, igual ao Reaper: a thread de
                # Play NUNCA é parada, o Áudio Guia NUNCA é tocado, e
                # nenhum all_notes_off é mandado - nada disso é preciso só
                # porque o andamento mudou. O único risco real era a
                # thread de Play ler play_events/beat_events NA HORA em
                # que ler_midi_memoria está reconstruindo essas listas por
                # baixo do pano (causava o "disparo"/"pinote"). A flag
                # _pausar_leitura_eventos avisa a thread de Play pra só
                # esperar 1 milissegundo sem tocar em nada enquanto isso
                # acontece - ela continua tocando normalmente assim que a
                # reconstrução termina, sem nenhuma pausa perceptível.
                self._pausar_leitura_eventos = True
                try:
                    self._definir_bpm_global(novo_bpm)
                    self.ler_midi_memoria(reset_canais=False)

                    # ler_midi_memoria(reset_canais=False) liga o
                    # seek_flag sozinha - aqui a gente NÃO quer o "seek"
                    # pesado (chase completo de estado + reinício do
                    # áudio), só o reposicionamento leve dos índices,
                    # feito abaixo, então desliga de novo.
                    self.seek_flag = False

                    self.msg_index = len(self.play_events)
                    for i, ev in enumerate(self.play_events):
                        if ev[0] >= self.current_playback_time:
                            self.msg_index = i
                            break
                    self.beat_index = len(self.beat_events)
                    for i, (b_time, is_d) in enumerate(self.beat_events):
                        if b_time >= self.current_playback_time:
                            self.beat_index = i
                            break
                finally:
                    self._pausar_leitura_eventos = False

                self.dirty = True
                self.atualizar_titulo()

                from mhs_utils import falar_status
                wx.CallAfter(falar_status, f"{novo_bpm:.1f} BPM", imediato=True)
        else:
            from mhs_utils import falar_status
            wx.CallAfter(falar_status, "Tap", imediato=True)
            
        try:
            foco = wx.Window.FindFocus()
            if foco and isinstance(foco, wx.Button):
                if hasattr(self, 'lista_canais'):
                    wx.CallAfter(self.lista_canais.SetFocus)
                else:
                    wx.CallAfter(self.SetFocus)
        except: pass

    def contar_estado(self, prop, nome_estado):
        from mhs_utils import falar_status
        if not self.canais: return
        
        canais_ativos = []
        for i, c in enumerate(self.canais):
            if c.get(prop, False):
                canais_ativos.append(i + 1)
                
        count = len(canais_ativos)
        if count == 0:
            falar_status(f"0 canais {nome_estado}.", imediato=True)
            return
            
        ranges = []
        start = canais_ativos[0]
        prev = canais_ativos[0]
        
        for n in canais_ativos[1:]:
            if n == prev + 1:
                prev = n
            else:
                if prev == start:
                    ranges.append(str(start))
                elif prev == start + 1:
                    ranges.append(f"{start}, {prev}")
                else:
                    ranges.append(f"{start} ao {prev}")
                start = n
                prev = n
                
        if prev == start:
            ranges.append(str(start))
        elif prev == start + 1:
            ranges.append(f"{start}, {prev}")
        else:
            ranges.append(f"{start} ao {prev}")
            
        texto_canais = ", ".join(ranges)
        
        if count == 1:
            nome_sing = nome_estado[:-1] if nome_estado.endswith('s') else nome_estado
            falar_status(f"1 canal {nome_sing}: {texto_canais}", imediato=True)
        else:
            falar_status(f"{count} canais {nome_estado}: {texto_canais}", imediato=True)

    def limpar_estado(self, prop, nome_acao):
        from mhs_utils import falar_status
        if not self.canais: return
        mudou = False
        for c in self.canais:
            if c.get(prop, False):
                c[prop] = False
                mudou = True
        if mudou:
            self.dirty = True
            self.atualizar_titulo()
            wx.CallAfter(self.atualizar_status, True, False)
            falar_status(f"Todos os {nome_acao}.", imediato=True)
        else:
            falar_status(f"Nenhum canal estava com {prop} ativado.", imediato=True)

    def renomear_canal(self, event):
        self.save_state("Renomear Canal")
        alvos = self.canais_selecionados if self.canal_atual in self.canais_selecionados else {self.canal_atual}
        
        nome_atual = self.canais[self.canal_atual].get("Nome", "")
        
        dlg = wx.TextEntryDialog(self, f"Digite o novo nome para {len(alvos)} canais:", "Renomear Canal", nome_atual)
        if dlg.ShowModal() == wx.ID_OK:
            novo_nome = dlg.GetValue().strip()
            for ch in alvos:
                self.canais[ch]["Nome"] = novo_nome
                
            self.dirty = True
            self.atualizar_titulo()
            
            from mhs_utils import falar_status
            falar_status(f"Canal renomeado para: {novo_nome}", imediato=True)
            self.atualizar_status(silenciar=True)
            
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
        dlg.Destroy()

    def abrir_tempo_preciso(self, event):
        self.save_state("Tempo Preciso")
        try:
            from mhs_dialogs import PreciseTempoDialog
        except ImportError:
            from mhs_utils import falar_status
            falar_status("Erro: Tela de BPM não encontrada no arquivo de diálogos.", imediato=True)
            return
            
        bpm_atual = 60000000.0 / self.current_tempo if getattr(self, 'current_tempo', 500000) > 0 else 120.0
        
        dlg = PreciseTempoDialog(self, bpm_atual)
        if dlg.ShowModal() == wx.ID_OK:
            novo_bpm = dlg.get_bpm()
            import mido

            # Mesma troca de andamento AO VIVO do Tap Tempo/Ctrl+/Ctrl-
            # (ver do_tap_tempo/change_tempo) - nunca para a thread de
            # Play nem o Áudio Guia, sem preservar por tick (causava
            # "pinote"). Também captura o BPM realmente aplicado (com
            # casas decimais preservadas - ver _definir_bpm_global) pra
            # falar o valor certo no final, não o que foi só digitado.
            self._pausar_leitura_eventos = True
            try:
                novo_bpm = self._definir_bpm_global(novo_bpm)
                self.ler_midi_memoria(reset_canais=False)
                self.seek_flag = False

                self.msg_index = len(self.play_events)
                for i, ev in enumerate(self.play_events):
                    if ev[0] >= self.current_playback_time:
                        self.msg_index = i
                        break
                self.beat_index = len(self.beat_events)
                for i, (b_time, is_d) in enumerate(self.beat_events):
                    if b_time >= self.current_playback_time:
                        self.beat_index = i
                        break
            finally:
                self._pausar_leitura_eventos = False

            self.dirty = True
            self.atualizar_titulo()

            # --- A REVANCHE DO SEQUENCIADOR NO CTRL+SHIFT+T ---
            if getattr(self, 'output', None):
                try:
                    micros = self.current_tempo
                    # Engenharia Reversa: Quebra o numerão em 3 bytes de 7 bits (0 a 127)
                    d4 = (micros // 16384) & 0x7F
                    d5 = ((micros % 16384) // 128) & 0x7F
                    d6 = micros % 128
                    
                    # Montando e atirando o pacote SysEx
                    syx_msg = mido.Message.from_bytes([0xF0, 67, 126, 1, 0, d4, d5, d6, 0xF7])
                    self.output.send(syx_msg)
                except: pass

            # Salva o status do áudio caso ele já estivesse rolando e foi afetado
            self.salvar_config_audio()
            
            from mhs_utils import falar_status
            falar_status(f"BPM cravado em: {novo_bpm:.3f}", imediato=True)
            
            if getattr(self, 'tocando', False):
                self.seek_flag = True
                
        dlg.Destroy()
    def toggle_gravacao_espera(self, event):
        if not self.gravando and not getattr(self, 'esperando_nota', False):
            if not any(can["Arm"] for can in self.canais):
                from mhs_utils import falar_status
                falar_status("Arme pelo menos um canal para gravar")
                return
            self.esperando_nota = True
            self.atualizar_titulo()
            from mhs_utils import falar_status
            falar_status("Aguardando MIDI...", imediato=True)
        else:
            self.esperando_nota = False
            self.gravando = False
            self.atualizar_titulo()
            from mhs_utils import falar_status
            falar_status("Gravação cancelada.", imediato=True)

    def aumentar_vol_audio(self, event):
        self.audio_volume = min(100, getattr(self, 'audio_volume', 100) + 5)
        self._apply_audio_vol()
        from mhs_utils import falar_status
        falar_status(f"Áudio Guia: {self.audio_volume}%", imediato=True)
        # Salva instantaneamente no config.json
        self.salvar_config_audio()

    def ajustar_offset_audio(self, amount):
        self.audio_offset += amount
        self.audio_offset = max(-3600.0, min(3600.0, self.audio_offset))
        
        # --- SINCRONIZA A ÂNCORA MUSICAL ---
        if self.audio_offset >= 0:
            self.audio_offset_tick = self.get_tick_at_sec(self.audio_offset)
            
        ms_val = int(round(self.audio_offset * 1000))
        from mhs_utils import falar_status
        
        if ms_val > 0:
            texto = f"Áudio acionado aos {ms_val} milissegundos"
        elif ms_val < 0:
            texto = f"Áudio adiantado em {abs(ms_val)} milissegundos"
        else:
            texto = "Deslocamento do áudio zerado"
            
        falar_status(texto, imediato=True)
        self.dirty = True
        self.atualizar_titulo()
        self.salvar_config_audio()
        
        if getattr(self, 'tocando', False):
            self.seek_flag = True
    def diminuir_vol_audio(self, event):
        self.audio_volume = max(0, getattr(self, 'audio_volume', 100) - 5)
        self._apply_audio_vol()
        from mhs_utils import falar_status
        falar_status(f"Áudio Guia: {self.audio_volume}%", imediato=True)

    def mutar_audio(self, event):
        self.audio_muted = not getattr(self, 'audio_muted', False)
        self._apply_audio_vol()
        from mhs_utils import falar_status
        estado = "Mutado" if self.audio_muted else "Ativado"
        falar_status(f"Áudio Guia {estado}", imediato=True)

    def _apply_audio_vol(self):
        try:
            vol = 0.0 if getattr(self, 'audio_muted', False) else (getattr(self, 'audio_volume', 100) / 100.0)
            canal = getattr(self, '_audio_channel', None)
            if canal is not None:
                canal.set_volume(vol)
        except: pass

    def limpar_selecoes(self, event):
        self.time_selection_start = None
        self.time_selection_end = None
        self.non_continuous_sel = False
        self.canais_selecionados = {self.canal_atual}
        from mhs_utils import falar_status
        self.atualizar_status(True, silenciar=True)
        falar_status("Todas as seleções de tempo e canais foram removidas.", imediato=True)

    def processar_novo_midi(self):
        if self.tocando:
            self.tocando = False
            self.gravando = False
            self.all_notes_off()
            import time
            time.sleep(0.1)
            
        # --- GATILHO AUTOMÁTICO: Limpa o teclado ao iniciar um projeto em branco ---
        self.enviar_reset_fisico_teclado()
            
        self.midi_file = mido.MidiFile(type=1)
        self.midi_file.tracks.append(mido.MidiTrack())
        self.current_midi_path = None
        # Projeto em branco não herda o Áudio Guia do projeto anterior
        # que porventura estivesse nesta mesma guia.
        self.audio_path = None
        self.audio_volume = 100
        self.audio_offset = 0.0
        self._audio_stop()
        self.canais = [self.gerar_canal_vazio(i+1) for i in range(16)]
        self.overrides = {i: {} for i in range(16)}
        self.canais_selecionados = {0}
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.recorded_events = []
        self.current_tempo = 500000 
        self.dirty = False
        self.ripple_mode = 0
        self.in_vel_ctrl_on = False
        self.in_vel_min = 1
        self.in_vel_max = 127
        
        self.dsp_cache = {
            'active': False, 'rev_msb_idx': 1, 'rev_lsb_idx': 0,
            'rev_p': [-1] * 16, 'rev_ret': 64,
            'cho_msb_idx': 1, 'cho_lsb_idx': 0,
            'cho_p': [-1] * 16, 'cho_ret': 64,
        }

        # CORREÇÃO: Cache vazio para projetos em branco
        self.variation_dsp_cache = {}
        self._dsp_teclado = {'slots': {}, 'vc': {}}
        self._captura_timbre = None

        self.ler_midi_memoria(reset_canais=True)
        self.atualizar_titulo()
        self.atualizar_status(True, silenciar=True)
        import wx
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
    def aplicar_sysex_ao_carregar(self):
        self.dsp_cache = {
            'active': False, 'rev_msb_idx': 1, 'rev_lsb_idx': 0,
            'rev_p': [-1] * 16, 'rev_ret': 64,
            'cho_msb_idx': 1, 'cho_lsb_idx': 0,
            'cho_p': [-1] * 16, 'cho_ret': 64,
        }
        self.variation_dsp_cache = {}
        self._dsp_teclado = {'slots': {}, 'vc': {}}
        self._captura_timbre = None
        self.tem_xg_on = False

        if not getattr(self, 'midi_file', None): return

        rev_msb_list = [v for _, v in REV_MSB_LIST]
        cho_msb_list = [v for _, v in CHO_MSB_LIST]
        dsp_msb_vals = [v for _, v in VARIATION_EFEITOS_LIST]

        offsets_var_2bytes = [0x42, 0x44, 0x46, 0x48, 0x4A, 0x4C, 0x4E, 0x50, 0x52, 0x54]
        offsets_var_1byte  = [0x70, 0x71, 0x72, 0x73, 0x74, 0x75]
        # Params 1-10 do efeito de Inserção XG ficam em 0x02-0x0B; os params
        # 11-16 ficam em 0x20-0x25 (NÃO em 0x0D-0x12, que são as sensibilidades
        # de controlador M.W./Bend/CAT/AC1/AC2/CBC1). Vários efeitos usam 11-16
        # (ex.: 95 = Amp Simulator com Speaker/LFO/Phaser/Delay) - o teclado
        # despeja esses endereços na troca de timbre.
        offsets_ins_1b     = [0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25]

        sysex_encontrados = []

        for track in self.midi_file.tracks:
            for msg in track:
                if msg.type == 'sysex':
                    data = msg.data

                    if len(data) >= 4 and tuple(data[0:4]) == (0x43, 0x10, 0x4C, 0x00):
                        continue

                    elif len(data) == 4 and tuple(data[0:4]) == (0x7E, 0x7F, 0x09, 0x01):
                        continue

                    elif len(data) >= 7:
                        header = tuple(data[0:6])
                        if header == (0x43, 0x10, 0x4C, 0x02, 0x01, 0x00) and len(data) >= 8:
                            sysex_encontrados.append(msg)
                            self.dsp_cache['active'] = True
                            msb, lsb = data[6], data[7]
                            if msb in rev_msb_list: self.dsp_cache['rev_msb_idx'] = rev_msb_list.index(msb)
                            self.dsp_cache['rev_lsb_idx'] = lsb
                            continue
                        elif header == (0x43, 0x10, 0x4C, 0x02, 0x01, 0x0C):
                            sysex_encontrados.append(msg)
                            self.dsp_cache['active'] = True
                            self.dsp_cache['rev_ret'] = data[6]
                            continue
                        elif header[0:5] == (0x43, 0x10, 0x4C, 0x02, 0x01) and data[5] in REV_PARAM_INDEX:
                            sysex_encontrados.append(msg)
                            self.dsp_cache['active'] = True
                            self.dsp_cache['rev_p'][REV_PARAM_INDEX[data[5]]] = data[6]
                            continue
                        elif header == (0x43, 0x10, 0x4C, 0x02, 0x01, 0x20) and len(data) >= 8:
                            sysex_encontrados.append(msg)
                            self.dsp_cache['active'] = True
                            msb, lsb = data[6], data[7]
                            if msb in cho_msb_list: self.dsp_cache['cho_msb_idx'] = cho_msb_list.index(msb)
                            self.dsp_cache['cho_lsb_idx'] = lsb
                            continue
                        elif header == (0x43, 0x10, 0x4C, 0x02, 0x01, 0x2C):
                            sysex_encontrados.append(msg)
                            self.dsp_cache['active'] = True
                            self.dsp_cache['cho_ret'] = data[6]
                            continue
                        elif header[0:5] == (0x43, 0x10, 0x4C, 0x02, 0x01) and data[5] in CHO_PARAM_INDEX:
                            sysex_encontrados.append(msg)
                            self.dsp_cache['active'] = True
                            self.dsp_cache['cho_p'][CHO_PARAM_INDEX[data[5]]] = data[6]
                            continue
                            
                        slot_idx = None
                        param = None
                        
                        if tuple(data[0:4]) == (0x43, 0x10, 0x4C, 0x02) and data[4] == 0x01:
                            slot_idx = 0
                            param = data[5]
                        elif tuple(data[0:4]) == (0x43, 0x10, 0x4C, 0x03):
                            slot_idx = data[4] + 1
                            param = data[5]

                        if slot_idx is not None:
                            sysex_encontrados.append(msg)
                            if slot_idx not in self.variation_dsp_cache:
                                self.variation_dsp_cache[slot_idx] = {'active': True, 'ch': 127, 'msb_idx': 0, 'lsb_idx': 0, 'ret': -1, 'p': [-1]*16, 'chs': {}}

                            v = self.variation_dsp_cache[slot_idx]
                            v['active'] = True

                            if param == 0x5B or param == 0x0C:
                                v['ch'] = data[6]
                                # Cada bloco carrega 1 canal: Gaveta 1 (Variation)
                                # pelo Part Number (5B), Inserção pela Conexão de
                                # parte (0C). Vira 1 entrada em 'chs'.
                                if data[6] != 0x7F:
                                    v.setdefault('chs', {})[data[6]] = v.get('chs', {}).get(data[6], 127)
                            elif param == 0x40 and slot_idx == 0 and len(data) >= 8:
                                msb, lsb = data[6], data[7]
                                if msb in dsp_msb_vals: v['msb_idx'] = dsp_msb_vals.index(msb)
                                v['lsb_idx'] = lsb
                            elif param == 0x00 and slot_idx > 0 and len(data) >= 8:
                                msb, lsb = data[6], data[7]
                                if msb in dsp_msb_vals: v['msb_idx'] = dsp_msb_vals.index(msb)
                                v['lsb_idx'] = lsb

                            elif param == 0x0B and slot_idx > 0 and len(data) >= 7:
                                v['ret'] = data[6]
                                # Inserção multi-canal: 0x0B é a mistura
                                # seco/molhado da cópia deste canal.
                                _cc = v.get('ch')
                                if isinstance(_cc, int) and 0 <= _cc < 16:
                                    v.setdefault('chs', {})[_cc] = data[6]

                            elif param == 0x54 and slot_idx == 0 and len(data) >= 8:
                                v['p'][9] = (data[6] * 128) + data[7]
                            elif param == 0x56 and slot_idx == 0 and len(data) >= 7:
                                v['ret'] = data[6]
                                
                            elif param in offsets_var_2bytes and slot_idx == 0 and len(data) >= 8:
                                idx_p = offsets_var_2bytes.index(param)
                                v['p'][idx_p] = (data[6] * 128) + data[7]
                            elif param in offsets_var_1byte and slot_idx == 0 and len(data) >= 7:
                                idx_p = offsets_var_1byte.index(param) + 10
                                v['p'][idx_p] = data[6]
                                
                            # O leitor de 1 e 2 bytes das Inserções (Lê no formato que tiver sido gravado!)
                            elif slot_idx > 0 and len(data) >= 8 and 0x30 <= param <= 0x4E:
                                idx_p = (param - 0x30) // 2
                                if idx_p < 16: v['p'][idx_p] = (data[6] * 128) + data[7]
                            elif slot_idx > 0 and param in offsets_ins_1b and len(data) >= 7:
                                idx_p = offsets_ins_1b.index(param)
                                v['p'][idx_p] = data[6]

        if getattr(self, 'output', None):
            import time
            for msg in sysex_encontrados:
                try: 
                    self.output.send(msg)
                    d = msg.data
                    precisa_esperar = False
                    
                    if len(d) >= 6 and d[0] == 0x43 and d[1] == 0x10 and d[2] == 0x4C:
                        if d[3] == 0x02 and d[4] == 0x01 and d[5] in [0x00, 0x20, 0x40]:
                            precisa_esperar = True
                        elif d[3] == 0x03 and d[5] == 0x00:
                            precisa_esperar = True
                            
                    if precisa_esperar:
                        time.sleep(0.25)
                    else:
                        time.sleep(0.01)
                except: pass
    def ler_midi_memoria(self, reset_canais=True):
        if not getattr(self, 'midi_file', None): return
        
        old_play_time = getattr(self, 'current_playback_time', 0.0)
        old_last_start = getattr(self, 'last_start_time', 0.0)
        
        if reset_canais:
            # Só preserva daqui pro "novos" o que é estado PURO de sessão -
            # sem nenhuma representação no arquivo .mid (Arm/Mute/Solo/
            # Transpose/Input não existem como SysEx nem CC, então uma
            # releitura nunca teria de onde os recuperar). Mono/Poly, Porta
            # Time e VoiceCreator SÃO derivados de SysEx (Mixagem/Multi
            # Part) - preservá-los aqui era o bug que fazia o Michel
            # esvaziar a Lista de SysEx (Ctrl+Shift+X), sair, e ver tudo
            # voltar: mesmo com o SysEx de verdade apagado do arquivo, o
            # valor antigo sobrevivia escondido aqui e o consolidar_projeto
            # reemitia a SysEx de novo a partir dele. Agora esses 3 só
            # voltam a existir se o scan mais abaixo achar o SysEx de
            # verdade ainda no arquivo.
            if hasattr(self, 'canais') and self.canais:
                estados_antigos = {i: {
                    "Arm": self.canais[i].get("Arm", False),
                    "Mute": self.canais[i].get("Mute", False),
                    "Solo": self.canais[i].get("Solo", False),
                    "Transpose": self.canais[i].get("Transpose", 0),
                    "Input": self.canais[i].get("Input", 1),
                } for i in range(16)}
            else:
                estados_antigos = {i: {"Arm": False, "Mute": False, "Solo": False, "Transpose": 0, "Input": 1} for i in range(16)}

            novos = [self.gerar_canal_vazio(i+1) for i in range(16)]
            for i in range(16):
                novos[i]["Arm"] = estados_antigos[i]["Arm"]
                novos[i]["Mute"] = estados_antigos[i]["Mute"]
                novos[i]["Solo"] = estados_antigos[i]["Solo"]
                novos[i]["Transpose"] = estados_antigos[i]["Transpose"]
                novos[i]["Input"] = estados_antigos[i]["Input"]

            msb = [0]*16
            lsb = [0]*16
            msb[9] = 127 
            
            cc_lidos = {i: set() for i in range(16)}
            patch_lido = {i: False for i in range(16)}
            rpn_estado = {i: [None, None] for i in range(16)}
            nrpn_estado = {i: [None, None] for i in range(16)}  # [MSB (parâmetro), LSB (peça)]
            detune_nibbles = {i: [0x08, 0x00] for i in range(16)}  # ver detune_combinar/detune_separar

            # --- LEITURA DO ARQUIVO: Procura SysEx de Bateria e de Mixagem (0x08) ---
            for i, track in enumerate(self.midi_file.tracks):
                for msg in track:
                    if msg.type == 'sysex':
                        data = msg.data
                        if len(data) >= 7 and tuple(data[0:3]) == (0x43, 0x10, 0x4C):
                            if data[3] in [0x30, 0x31]:
                                ch = 9 if data[3] == 0x30 else (data[3] - 0x31)
                                if 0 <= ch < 16:
                                    if data[5] == 0x70 and len(data) >= 10:
                                        if "CustomDrumMap" not in novos[ch]: novos[ch]["CustomDrumMap"] = {}
                                        orig_note, b, p, dest_note = data[4], (data[6] * 128) + data[7], data[8], data[9]
                                        novos[ch]["CustomDrumMap"][orig_note] = {'bank': b, 'patch': p, 'dest_note': dest_note}
                                    elif data[5] < 0x70 and len(data) >= 7:
                                        if "DrumParams" not in novos[ch]: novos[ch]["DrumParams"] = {}
                                        orig_note, param, val = data[4], data[5], data[6]
                                        novos[ch]["DrumParams"][(orig_note, param)] = val
                            
                            # A MAGIA: Lendo SysEx de Mixagem e a Equalização!
                            elif data[3] == 0x08 and len(data) >= 7:
                                ch = data[4]
                                if 0 <= ch < 16:
                                    param, val = data[5], data[6]
                                    if param == 0x01: 
                                        msb[ch] = val
                                        novos[ch]["Bank"] = (msb[ch] * 128) + lsb[ch]
                                    elif param == 0x02: 
                                        lsb[ch] = val
                                        novos[ch]["Bank"] = (msb[ch] * 128) + lsb[ch]
                                    elif param == 0x03:
                                        novos[ch]["Patch"] = val
                                        patch_lido[ch] = True
                                    elif param == 0x0B:
                                        novos[ch]["Volume"] = val
                                        cc_lidos[ch].add(7)
                                    elif param == 0x0E:
                                        novos[ch]["Pan"] = val
                                        cc_lidos[ch].add(10)
                                    elif param == 0x13:
                                        novos[ch]["Reverb"] = val
                                        cc_lidos[ch].add(91)
                                    elif param == 0x12:
                                        novos[ch]["Chorus"] = val
                                        cc_lidos[ch].add(93)
                                    elif param == 0x72:
                                        novos[ch]["Grave"] = val
                                    elif param == 0x73:
                                        novos[ch]["Agudo"] = val
                                    elif param in (0x09, 0x0A):
                                        par = detune_nibbles[ch]
                                        if param == 0x09: par[0] = val & 0x0F
                                        else: par[1] = val & 0x0F
                                        if "VoiceCreator" not in novos[ch]: novos[ch]["VoiceCreator"] = {}
                                        novos[ch]["VoiceCreator"][0x09] = detune_combinar(par[0], par[1])
                                    elif param not in MULTIPART_ADDR_RESERVADOS:
                                        # Qualquer outro endereço Multi Part (o
                                        # teclado manda uma penca de forma de
                                        # onda/filtro/EG/EQ na troca de timbre) -
                                        # guarda cru pra devolver igual ao salvar.
                                        if "VoiceCreator" not in novos[ch]: novos[ch]["VoiceCreator"] = {}
                                        novos[ch]["VoiceCreator"][param] = val

                            # Portamento (Mono Priority/Modo/Modo do Tempo) -
                            # bloco SEPARADO 0x0A, não o 0x08 de sempre (ver
                            # comentário perto de self.parametros_0a em
                            # VoiceCreatorDialog).
                            elif data[3] == 0x0A and len(data) >= 7:
                                ch = data[4]
                                param, val = data[5], data[6]
                                if 0 <= ch < 16 and param in (0x01, 0x02, 0x03):
                                    if "VoiceCreator" not in novos[ch]: novos[ch]["VoiceCreator"] = {}
                                    novos[ch]["VoiceCreator"][param] = val

            for i, track in enumerate(self.midi_file.tracks):
                t_name, t_chan = None, None
                for msg in track:
                    if msg.type == 'track_name' and not t_name: t_name = msg.name
                    ch = getattr(msg, 'channel', None)
                    if ch is not None and t_chan is None: t_chan = ch
                ch_idx = t_chan if t_chan is not None else (i - 1 if i > 0 else None)
                if ch_idx is not None and 0 <= ch_idx < 16 and t_name:
                    if not t_name.lower().startswith("track"): novos[ch_idx]["Nome"] = t_name

            for track in self.midi_file.tracks:
                for msg in track:
                    ch = getattr(msg, 'channel', None)
                    if ch is not None and ch < 16:
                        if msg.type == 'control_change':
                            if msg.control == 101: rpn_estado[ch][0] = msg.value
                            elif msg.control == 100: rpn_estado[ch][1] = msg.value
                            elif msg.control == 99: nrpn_estado[ch][0] = msg.value
                            elif msg.control == 98: nrpn_estado[ch][1] = msg.value
                            elif msg.control == 6:
                                if rpn_estado[ch] == [0, 0] and "PB" not in cc_lidos[ch]:
                                    novos[ch]["Pitch Bend"] = msg.value
                                    cc_lidos[ch].add("PB")
                                n_msb, n_lsb = nrpn_estado[ch]
                                # Guia 3 (Drum Setup via NRPN): só os endereços
                                # de bateria conhecidos (14H-35H do Data List) -
                                # outro uso de NRPN no mesmo canal (vibrato,
                                # filtro do Multi Part etc) não entra aqui.
                                if n_msb in DRUM_NRPN_MSBS and n_lsb is not None:
                                    novos[ch].setdefault("DrumParamsNRPN", {})[(n_lsb, n_msb)] = msg.value
                            if msg.control not in cc_lidos[ch]:
                                if msg.control == 0: 
                                    msb[ch] = msg.value
                                    novos[ch]["Bank"] = (msb[ch] * 128) + lsb[ch]
                                    cc_lidos[ch].add(0)
                                elif msg.control == 32: 
                                    lsb[ch] = msg.value
                                    novos[ch]["Bank"] = (msb[ch] * 128) + lsb[ch]
                                    cc_lidos[ch].add(32)
                                elif msg.control == 7: novos[ch]["Volume"] = msg.value; cc_lidos[ch].add(7)
                                elif msg.control == 10: novos[ch]["Pan"] = msg.value; cc_lidos[ch].add(10)
                                elif msg.control == 11: novos[ch]["Expression"] = msg.value; cc_lidos[ch].add(11)
                                elif msg.control == 91: novos[ch]["Reverb"] = msg.value; cc_lidos[ch].add(91)
                                elif msg.control == 93: novos[ch]["Chorus"] = msg.value; cc_lidos[ch].add(93)
                                elif msg.control == 5: novos[ch]["Porta Time"] = msg.value; cc_lidos[ch].add(5)
                                elif msg.control == 126: novos[ch]["Mono/Poly"] = False; cc_lidos[ch].add(126)
                                elif msg.control == 127: novos[ch]["Mono/Poly"] = True; cc_lidos[ch].add(127)
                                elif msg.control == 94 and msg.value > 0:
                                    # "Variation Send Level" - é assim que 2+
                                    # canais mandam pro MESMO efeito da Gaveta 1.
                                    if not hasattr(self, 'variation_dsp_cache'):
                                        self.variation_dsp_cache = {}
                                    v0 = self.variation_dsp_cache.setdefault(
                                        0, {'active': False, 'ch': 0x7F, 'msb_idx': 0, 'lsb_idx': 0, 'ret': -1, 'p': [-1] * 16, 'chs': {}})
                                    v0['active'] = True
                                    v0.setdefault('chs', {})[ch] = msg.value
                                    cc_lidos[ch].add(94)
                        elif msg.type == 'program_change': 
                            if not patch_lido[ch]:
                                novos[ch]["Patch"] = msg.program
                                patch_lido[ch] = True
            self.canais = novos

        self.play_events = []
        self.beat_events = []
        import mido
        from operator import itemgetter
        ticks_per_beat = max(1, getattr(self.midi_file, 'ticks_per_beat', 480))
        all_events = []
        for track in getattr(self, 'midi_file', mido.MidiFile()).tracks:
            curr = 0
            for msg in track:
                curr += msg.time
                all_events.append((curr, msg))
        # OTIMIZAÇÃO: itemgetter é bem mais rápido que lambda num sort deste tamanho
        all_events.sort(key=itemgetter(0))
        
        abs_t, abs_s, current_num, next_b, beat_m = 0, 0.0, 4, 0, 0
        t_div = 1000000.0 * ticks_per_beat

        # Andamento padrão do MIDI (120 BPM) até o PRIMEIRO set_tempo do
        # arquivo. Antes, o laço abaixo herdava o valor que sobrou em
        # self.current_tempo (o último tempo da leitura anterior ou do
        # arquivo aberto antes), então um MIDI cujo primeiro set_tempo não
        # está no tick 0 (ex.: TA9506SeAcontecer.mid, tempo no tick 360) tocava
        # os primeiros tempos no andamento errado - e a gravação, que
        # converte segundos em ticks pelo mapa de tempo correto
        # (build_time_map, que começa em 120 BPM), caía quase meio tempo
        # depois de onde o Michel tocou.
        self.current_tempo = 500000

        for t_tick, msg in all_events:
            # --- A CORREÇÃO DE OURO: A matemática da fita métrica! ---
            # 1. Calcula o tempo decorrido usando o BPM vigente ANTES da mudança
            d_tick = t_tick - abs_t
            d_sec = (d_tick * float(self.current_tempo) / t_div) if d_tick > 0 else 0.0
            
            # 2. SÓ DEPOIS de calcular o espaço, atualiza o BPM se houver mudança!
            if msg.type == 'set_tempo': 
                self.current_tempo = msg.tempo
            # ---------------------------------------------------------
            
            while next_b <= t_tick:
                if next_b == t_tick and getattr(msg, 'type', '') == 'time_signature': break 
                frac = (next_b - abs_t) / d_tick if d_tick > 0 else 0
                b_sec = abs_s + frac * d_sec
                is_d = (beat_m == 0)
                if not self.beat_events or b_sec > self.beat_events[-1][0] + 0.005:
                    self.beat_events.append((b_sec, is_d))
                beat_m = (beat_m + 1) % current_num
                next_b += ticks_per_beat
            abs_t, abs_s = t_tick, abs_s + d_sec
            if msg.type == 'time_signature':
                current_num, beat_m, next_b = max(1, msg.numerator), 0, abs_t 
            self.play_events.append((abs_s, msg))
            
        self.total_time = abs_s
        
        if not self.beat_events:
            self.beat_events.append((0.0, True))
            beat_m = 1
            
        # OTIMIZAÇÃO: A extensão "virtual" cobre 1 HORA de batidas fictícias além
        # do fim da música (pra permitir navegar/gravar depois do fim). Isso é
        # recalculado do zero em TODO arrasto/edição, mesmo quando o final real
        # da música e o tempo não mudaram. Como esse trecho depende só de
        # (last_beat_sec, tempo, fórmula de compasso, fase do compasso), dá pra
        # reaproveitar a lista pronta quando esses valores baterem com a última
        # vez — sem risco, porque só reusa quando a "receita" é idêntica.
        last_beat_sec = self.beat_events[-1][0]
        beat_duration = max(0.01, self.current_tempo / 1000000.0)
        limite_virtual = max(self.total_time, 0.0) + 3600.0

        chave_cache = (round(last_beat_sec, 6), self.current_tempo, current_num, beat_m, round(limite_virtual, 6))
        cache_virtual = getattr(self, '_beat_virtual_cache', None)

        if cache_virtual is not None and cache_virtual[0] == chave_cache:
            self.beat_events.extend(cache_virtual[1])
        else:
            cauda_virtual = []
            while last_beat_sec < limite_virtual:
                last_beat_sec += beat_duration
                is_downbeat = (beat_m == 0)
                par = (last_beat_sec, is_downbeat)
                cauda_virtual.append(par)
                beat_m = (beat_m + 1) % current_num
            self.beat_events.extend(cauda_virtual)
            self._beat_virtual_cache = (chave_cache, cauda_virtual)

        self.virtual_total_time = max(self.total_time, 3600.0)

        if reset_canais:
            estado_anterior = getattr(self, 'metronomo_ligado', False)
            if not getattr(self, 'current_midi_path', None) and self.total_time < 0.1:
                self.metronomo_ligado = True
                if not estado_anterior:
                    try:
                        import wx
                        from mhs_utils import falar_status
                        wx.CallAfter(falar_status, "Projeto em branco. Metrônomo Ligado.", imediato=False)
                    except: pass
            else:
                self.metronomo_ligado = False
                if estado_anterior:
                    try:
                        import wx
                        from mhs_utils import falar_status
                        wx.CallAfter(falar_status, "Arquivo carregado. Metrônomo Desligado.", imediato=False)
                    except: pass

        if not reset_canais:
            self.current_playback_time = old_play_time
            self.last_start_time = old_last_start
            self.seek_flag = True
        else:
            self.current_playback_time = 0.0
            self.last_start_time = 0.0
            self.msg_index = 0
            self.beat_index = 0
            self.seek_flag = False

        # O Áudio Guia é um arquivo de áudio de verdade - não "estica"
        # quando o andamento muda (Tap Tempo, Ctrl+/Ctrl-, etc). O
        # audio_offset (em segundos) é o relógio: fica parado exatamente
        # onde o Michel o deixou, independente de qualquer troca de BPM.
        # (Antes daqui recalculava audio_offset a partir de uma âncora em
        # TICK - isso fazia o áudio "andar" sozinho em segundos toda vez
        # que o andamento mudava, atrapalhando justamente o uso do Tap
        # Tempo pra achar o BPM certo contra um áudio já posicionado.)

        if hasattr(self, 'propriedade_atual'): 
            try:
                import wx
                wx.CallAfter(self.atualizar_status, True, True)
            except: pass
    def abrir_efeitos_globais(self, event):
        try:
            from mhs_dialogs import GlobalEffectsDialog
        except ImportError:
            from mhs_utils import falar_status
            falar_status("Erro: Tela de DSP não encontrada no arquivo de diálogos.", imediato=True)
            return
            
        from mhs_utils import falar_status
        if not getattr(self, 'midi_file', None):
            return
            
        falar_status("Abrindo Configurações de Efeitos Globais.")
        dlg = GlobalEffectsDialog(self)
        
        if dlg.ShowModal() == wx.ID_OK:
            if getattr(self, 'recorded_events', None): self.aplicar_gravacao()

            # O próprio diálogo já escreveu tudo em self.dsp_cache a cada
            # mudança (ver GlobalEffectsDialog.on_change) - só falta marcar
            # ativo e gravar de vez no projeto.
            self.dsp_cache['active'] = True
            self.save_state("Efeitos Globais XG")
            
            # Grava imediatamente na Trilha Mestra do projeto
            self.consolidar_projeto()
                
            self.dirty = True
            self.atualizar_titulo()
            self.ler_midi_memoria(reset_canais=False)
            falar_status("Efeitos Globais aplicados e gravados na música!", imediato=True)

        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
        dlg.Destroy()

    def abrir_efeitos_midi(self, event):
        from mhs_utils import falar_status
        if not self.midi_file:
            falar_status("Nenhum projeto aberto.", imediato=True)
            return
            
        t_start, t_end = self.get_selection_bounds()
        if t_start == 0.0 and t_end == float('inf'):
            falar_status("Por segurança, selecione um trecho marcando Início e Fim antes de aplicar efeitos.", imediato=True)
            return
            
        try:
            from mhs_dialogs import MidiEffectsDialog
            dlg = MidiEffectsDialog(self)
            if dlg.ShowModal() == wx.ID_OK:
                tipo, params = dlg.get_valores()
                self.aplicar_efeito_midi(tipo, params)
            dlg.Destroy()
            wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
        except Exception as e:
            falar_status(f"Erro ao abrir: {e}", imediato=True)

    def aplicar_efeito_midi(self, tipo_efeito, params, is_preview=False, backup_midi=None):
        from mhs_utils import falar_status
        # Import no TOPO da função: há vários "import mido" locais mais
        # abaixo (em ramos diferentes), o que torna `mido` uma variável
        # local da função inteira - sem este, o ramo bateria_preset usava
        # mido.Message antes de qualquer um deles rodar (UnboundLocalError:
        # o preset soava no preview isolado mas nunca entrava no MIDI).
        import mido
        if not self.midi_file: return

        if not is_preview:
            self.save_state(f"Efeito MIDI: {tipo_efeito}")
            
        # Se for um Preview, resgatamos o backup antes de aplicar para evitar que o efeito se some a cada mudança
        if is_preview and backup_midi:
            self.midi_file = self.clone_midi_rapido(backup_midi)
            
        t_start, t_end = self.get_selection_bounds()
        st_tick = self.get_tick_at_sec(t_start) if t_start != float('inf') else 0
        ed_tick = self.get_tick_at_sec(t_end) if t_end != float('inf') else float('inf')
        canais_alvo = getattr(self, 'canais_selecionados', {self.canal_atual})
        if tipo_efeito == 'bateria_preset':
            # Preset de bateria é sempre um INSERT no canal em foco, nunca
            # nos outros canais que porventura estejam multi-selecionados -
            # diferente do Arpejo/Delay/Harpa, que respeitam a seleção.
            canais_alvo = {self.canal_atual}

        tpb = max(1, getattr(self.midi_file, 'ticks_per_beat', 480))
        eventos_processados = 0
        
        for i, track in enumerate(self.midi_file.tracks):
            if not any(getattr(msg, 'channel', None) in canais_alvo for msg in track):
                continue
                
            abs_t = 0
            flat = []
            active_notes = {}
            notas_originais = []
            
            for msg in track:
                abs_t += msg.time
                ch = getattr(msg, 'channel', None)
                
                is_off = 0 if msg.type == 'note_off' or (msg.type == 'note_on' and getattr(msg, 'velocity', 0) == 0) else 1
                
                if ch in canais_alvo and (st_tick <= abs_t < ed_tick):
                    if msg.type == 'note_on' and msg.velocity > 0:
                        ev = {'start': abs_t, 'msg_on': msg, 'ch': ch, 'end': -1, 'msg_off': None}
                        active_notes[(ch, msg.note)] = ev
                        notas_originais.append(ev)
                        # O Delay mantém as notas originais, o Arpejador remove
                        if tipo_efeito in ('delay', 'bateria_preset'):
                            flat.append((abs_t, is_off, msg))
                    elif msg.type in ['note_off', 'note_on'] and (ch, getattr(msg, 'note', None)) in active_notes:
                        ev = active_notes.pop((ch, msg.note))
                        ev['end'] = abs_t
                        ev['msg_off'] = msg
                        if tipo_efeito in ('delay', 'bateria_preset'):
                            flat.append((abs_t, is_off, msg))
                    else:
                        flat.append((abs_t, is_off, msg))
                else:
                    flat.append((abs_t, is_off, msg))
                    
            for ev in active_notes.values():
                if ev['end'] == -1:
                    ev['end'] = abs_t + tpb
                    import mido
                    ev['msg_off'] = mido.Message('note_off', channel=ev['ch'], note=ev['msg_on'].note, velocity=0)
            
            if not notas_originais and tipo_efeito != 'bateria_preset':
                # Preset de bateria pode INSERIR num trecho que não tinha
                # nenhuma nota do canal ainda - não dá pra sair cedo aqui
                # só porque não havia nada pra transformar (diferente do
                # Arpejo/Delay/Harpa, que realmente não têm o que fazer
                # sem nota nenhuma no trecho).
                import mido
                new_track = mido.MidiTrack()
                last_t = 0
                for t_ev, _, m_ev in flat:
                    m_ev.time = max(0, int(round(t_ev - last_t)))
                    new_track.append(m_ev)
                    last_t = t_ev
                self.midi_file.tracks[i] = new_track
                continue

            novos_eventos = []
            
            # === MOTOR DO DELAY ===
            if tipo_efeito == 'delay':
                grid = int(round(params['grid'] * (tpb / 480.0)))
                repeats = params['repeats']
                decay = params['decay'] / 100.0
                
                for ev in notas_originais:
                    dur = ev['end'] - ev['start']
                    for rep in range(1, repeats + 1):
                        new_vel = int(round(ev['msg_on'].velocity * (decay ** rep)))
                        if new_vel < 1: break
                        
                        new_start = ev['start'] + (rep * grid)
                        new_end = new_start + dur
                        
                        # Delay é livre para ultrapassar o ed_tick (Ressoar)
                        m_on = ev['msg_on'].copy(velocity=new_vel)
                        m_off = ev['msg_off'].copy()
                        
                        novos_eventos.append((new_start, 1, m_on))
                        novos_eventos.append((new_end, 0, m_off))
                        eventos_processados += 1
                        
            # === MOTOR DO ARPEJADOR ===
            elif tipo_efeito == 'arpejo':
                grid = int(round(params['grid'] * (tpb / 480.0)))
                octaves = params['octaves']
                direction = params['direction'] 
                gate = params['gate'] / 100.0
                
                notas_originais.sort(key=lambda x: x['start'])
                chords = []
                current_chord = []
                chord_start = -1
                
                # Agrupa notas tocadas juntas (dentro de uma tolerância de 60 ticks)
                for ev in notas_originais:
                    if not current_chord:
                        current_chord.append(ev)
                        chord_start = ev['start']
                    else:
                        if abs(ev['start'] - chord_start) <= 60:
                            current_chord.append(ev)
                        else:
                            chords.append(current_chord)
                            current_chord = [ev]
                            chord_start = ev['start']
                if current_chord:
                    chords.append(current_chord)
                    
                import random
                
                for chord in chords:
                    c_start = min(x['start'] for x in chord)
                    c_end = max(x['end'] for x in chord)
                    
                    # --- AQUI ESTÁ A CORREÇÃO: Clipagem Estrita ---
                    # Limita o fim do arpejo estritamente à Marca Final (O / ed_tick)
                    if ed_tick != float('inf') and c_end > ed_tick:
                        c_end = ed_tick
                        
                    # Se, após o corte, a nota for menor ou igual a 0 em duração, pula fora!
                    if c_start >= c_end:
                        continue
                    
                    base_as_played = []
                    for x in sorted(chord, key=lambda ev: ev['start']):
                        if x['msg_on'].note not in base_as_played:
                            base_as_played.append(x['msg_on'].note)
                    
                    if not base_as_played: continue
                    
                    raw_pattern = []
                    for oct in range(octaves):
                        for p in base_as_played:
                            np = p + (oct * 12)
                            if np <= 127 and np not in raw_pattern:
                                raw_pattern.append(np)
                                
                    if direction == 0: # Up
                        pattern = sorted(raw_pattern)
                    elif direction == 1: # Down
                        pattern = sorted(raw_pattern, reverse=True)
                    elif direction == 2: # Up/Down
                        up = sorted(raw_pattern)
                        if len(up) > 1:
                            pattern = up + up[-2:0:-1]
                        else:
                            pattern = up
                    elif direction == 3: # As Played
                        pattern = raw_pattern
                    elif direction == 4: # Random
                        pattern = raw_pattern 
                        
                    if not pattern: continue
                    
                    cur_tick = c_start
                    p_idx = 0
                    ref_vel = chord[0]['msg_on'].velocity
                    
                    # Cria a sequência até a duração permitida acabar
                    while cur_tick < c_end:
                        if direction == 4:
                            note_val = random.choice(pattern)
                        else:
                            note_val = pattern[p_idx % len(pattern)]
                            
                        dur_real = int(round(grid * gate))
                        note_end = cur_tick + dur_real
                        
                        # Clipa o final da nota gerada se passar do limite estrito
                        if note_end > c_end: note_end = c_end 
                        
                        # Evita escrever notas com tamanho zero caso o corte caia exatamente na linha
                        if note_end > cur_tick:
                            import mido
                            m_on = mido.Message('note_on', channel=chord[0]['ch'], note=note_val, velocity=ref_vel)
                            m_off = mido.Message('note_off', channel=chord[0]['ch'], note=note_val, velocity=0)
                            
                            novos_eventos.append((cur_tick, 1, m_on))
                            novos_eventos.append((note_end, 0, m_off))
                            eventos_processados += 1
                            
                        cur_tick += grid
                        p_idx += 1

            # === MOTOR DA HARPA / STRUM (NOVO) ===
            elif tipo_efeito == 'harpa':
                delay_ticks = params['delay_ticks']
                direction = params['direction'] # 0: Subindo, 1: Descendo, 2: Vai e Volta
                octaves = params['octaves']
                
                # Tolerância para considerar que notas são "do mesmo acorde" (tocadas quase juntas)
                chord_tolerance = 40 
                
                i_nota = 0
                while i_nota < len(notas_originais):
                    ev = notas_originais[i_nota]
                    start_tick = ev['start']
                    
                    # Coleta todas as notas que formam este acorde específico
                    chord_notes = [ev]
                    j = i_nota + 1
                    while j < len(notas_originais):
                        next_ev = notas_originais[j]
                        if next_ev['start'] - start_tick <= chord_tolerance:
                            chord_notes.append(next_ev)
                            j += 1
                        else:
                            break
                    
                    # Só aplicamos harpa se o usuário tocou um acorde (2 ou mais notas juntas)
                    # Ou se ele pediu para espalhar uma nota só por várias oitavas!
                    if len(chord_notes) >= 2 or octaves > 1:
                        
                        # Remove os eventos originais do acorde (já que eles estão sem efeito na trilha principal)
                        # Como eles já não estão na lista 'novos_eventos', a gente só ignora eles e cria os novos
                        
                        expanded_chord = []
                        for oct_idx in range(octaves):
                            for ce in chord_notes:
                                nota_real = ce['msg_on'].note + (oct_idx * 12)
                                # Trava a nota no limite MIDI para não bugar o Yamaha
                                if 0 <= nota_real <= 127:
                                    # Cria uma cópia inteira do dicionário e das mensagens Mido
                                    m_on_copy = ce['msg_on'].copy(note=nota_real)
                                    m_off_copy = ce['msg_off'].copy(note=nota_real)
                                    
                                    novo_ce = {
                                        'start': ce['start'],
                                        'end': ce['end'],
                                        'msg_on': m_on_copy,
                                        'msg_off': m_off_copy
                                    }
                                    expanded_chord.append(novo_ce)
                        
                        # Ordena o acorde pelo tom (do grave pro agudo)
                        expanded_chord.sort(key=lambda x: x['msg_on'].note)
                        
                        # Se for "Descendo", invertemos a lista inteira
                        if direction == 1:
                            expanded_chord.reverse()
                        # Se for "Vai e Volta", simulamos uma palhetada dupla contínua
                        elif direction == 2:
                            meio = len(expanded_chord) // 2
                            subida = expanded_chord[:meio]
                            descida = expanded_chord[meio:]
                            descida.reverse()
                            expanded_chord = subida + descida
                            
                        # Espalha as notas no tempo simulando a palheta nas cordas!
                        for idx, ce in enumerate(expanded_chord):
                            offset = idx * delay_ticks
                            
                            # Desloca a nota pra frente (mantendo a mesma duração original de cada uma)
                            novo_start = ce['start'] + offset
                            novo_end = ce['end'] + offset
                            
                            novos_eventos.append((novo_start, 1, ce['msg_on']))
                            novos_eventos.append((novo_end, 0, ce['msg_off']))
                            eventos_processados += 1
                    else:
                        # Se for só uma nota sozinha e sem oitava extra, deixa ela quieta e joga pros novos_eventos
                        novos_eventos.append((chord_notes[0]['start'], 1, chord_notes[0]['msg_on']))
                        novos_eventos.append((chord_notes[0]['end'], 0, chord_notes[0]['msg_off']))
                    
                    i_nota = j # Avança o loop para depois do acorde que acabamos de processar

            # === MOTOR DO PRESET DE BATERIA (NOVO, trazido do MHS Style
            # Creator) === INSERE um desenho pronto no canal em foco, a
            # partir do Início (I) - diferente do Arpejo/Delay/Harpa, não
            # precisa de nota nenhuma já existente no trecho. SOBREPÕE (não
            # apaga) o que já está tocando no canal - o preamble acima
            # mantém as notas originais em `flat` pra este tipo (mesmo
            # tratamento do Delay), então o desenho só ACRESCENTA batidas
            # de bateria em cima do que já estava ali (pedido do Michel:
            # "não queria que os dados inseridos apagassem o que está por
            # baixo, quero que se sobreponha").
            elif tipo_efeito == 'bateria_preset':
                from mhs_dialogs import BATERIA_PRESETS
                preset_idx = params.get('preset_idx')
                if preset_idx is not None and 0 <= preset_idx < len(BATERIA_PRESETS):
                    _, _, duracao_beats, eventos_preset = BATERIA_PRESETS[preset_idx]
                    escala = tpb / 480.0
                    dur_ticks = int(round(480 * duracao_beats * escala))
                    fim_preset = min(st_tick + dur_ticks, ed_tick) if ed_tick != float('inf') else st_tick + dur_ticks
                    gate = max(1, int(round(30 * escala)))
                    for offset480, nota, vel in eventos_preset:
                        t_evento = st_tick + int(round(offset480 * escala))
                        if t_evento >= fim_preset:
                            continue
                        # note_off estritamente dentro de [st_tick, fim_preset)
                        # - grudar exatamente em fim_preset deixa o tick fora
                        # da faixa que a seção usa pra tocar isolada no loop,
                        # e o "desligar" do último toque de um rufo (comum
                        # perto da borda) nunca chega dentro do próprio loop.
                        fim_nota = min(t_evento + gate, max(t_evento + 1, fim_preset - 1))
                        novos_eventos.append((t_evento, 1, mido.Message('note_on', channel=self.canal_atual, note=nota, velocity=vel)))
                        novos_eventos.append((fim_nota, 0, mido.Message('note_off', channel=self.canal_atual, note=nota, velocity=0)))
                        eventos_processados += 1

            flat.extend(novos_eventos)
            flat.sort(key=lambda x: (x[0], x[1]))
            
            import mido
            new_track = mido.MidiTrack()
            last_t = 0
            for t_ev, _, m_ev in flat:
                m_ev.time = max(0, int(round(t_ev - last_t)))
                new_track.append(m_ev)
                last_t = t_ev
                
            self.midi_file.tracks[i] = new_track
            
        if not is_preview:
            self.dirty = True
            self.atualizar_titulo()
            
        was_playing = self.tocando
        if self.tocando:
            self.tocando = False
            self.all_notes_off()
            import time
            time.sleep(0.05)
            
        self.ler_midi_memoria(reset_canais=False)
        self.seek_flag = True
        
        if was_playing:
            self.tocando = True
            import threading
            threading.Thread(target=self.play_thread, daemon=True).start()
            
        if not is_preview:
            falar_status(f"Efeito {tipo_efeito.capitalize()} aplicado! {eventos_processados} notas geradas.", imediato=True)
    def abrir_lista_sysex(self, event):
        from mhs_utils import falar_status
        if not self.midi_file: return
        
        # 1. Rolo Compressor ANTES da janela: Salva tudo o que está na tela pro arquivo físico
        self.consolidar_projeto()
        
        falar_status("Abrindo Gerenciador Avançado de SysEx da Música")
        from mhs_dialogs import SysExListDialog
        dlg = SysExListDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            # 2. O usuário colou/editou no arquivo físico lá dentro da janela.
            # O MILAGRE: Agora o programa "Suga" os SysEx de volta para abastecer o cache da GUI!
            self.aplicar_sysex_ao_carregar()
            self.ler_midi_memoria(reset_canais=True)
            
            self.dirty = True
            self.atualizar_titulo()
            falar_status("Projeto atualizado e sincronizado com os SysEx colados.", imediato=True)
        else:
            # Se cancelou a janela, apenas relê o arquivo intacto
            self.ler_midi_memoria(reset_canais=False)
            
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
        dlg.Destroy()
    def _slot0_canais(self, v):
        # Canais que passam por este efeito de DSP. `chs` = {canal: nível}.
        # Gaveta 1 (Variation): Conexão SYSTEM + CC94 por canal. Gavetas 2-7
        # (Inserção): uma cópia física do efeito por canal (o consolidar
        # espalha nos mids livres). Cai no 'ch' antigo quando não tem 'chs'.
        if not isinstance(v, dict):
            return {}
        chs = v.get('chs')
        if isinstance(chs, dict) and chs:
            return {c: n for c, n in chs.items() if isinstance(c, int) and 0 <= c < 16}
        ch = v.get('ch')
        dsp_msb_vals = [x for _, x in VARIATION_EFEITOS_LIST]
        msb_v = dsp_msb_vals[v.get('msb_idx', 0)] if v.get('msb_idx', 0) < len(dsp_msb_vals) else 0
        if isinstance(ch, int) and 0 <= ch < 16 and msb_v != 0:
            return {ch: 127}
        return {}

    def abrir_variation_dsp(self, event):
        from mhs_utils import falar_status
        import wx
        if not getattr(self, 'midi_file', None): return

        if not hasattr(self, 'variation_dsp_cache'):
            self.variation_dsp_cache = {}

        # 1. Abre a tela de escolha de Gaveta e Família
        try:
            from mhs_dialogs import SelectDSPFamilyDialog, DelayDSPEditor, StandardDSPEditor
        except ImportError:
            falar_status("Erro: Classes de DSP não encontradas nos diálogos.", imediato=True)
            return

        dlg_seletor = SelectDSPFamilyDialog(self, self.canal_atual, self.variation_dsp_cache)
        res_sel = dlg_seletor.ShowModal()
        if res_sel == wx.ID_DELETE:
            dlg_seletor.Destroy()
            self.remover_dsp_do_canal(self.canal_atual)
            wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
            return
        if res_sel != wx.ID_OK:
            dlg_seletor.Destroy()
            return

        slot_idx, msb_idx, msb_val, lsb_idx, canais_marcados = dlg_seletor.get_valores()
        dlg_seletor.Destroy()

        # Cria a base do cache para não dar erro
        if slot_idx not in self.variation_dsp_cache:
            self.variation_dsp_cache[slot_idx] = {'active': False, 'ch': self.canal_atual, 'msb_idx': msb_idx, 'lsb_idx': lsb_idx, 'ret': -1, 'p': [-1]*16, 'chs': {}}

        v_slot = self.variation_dsp_cache[slot_idx]
        # Gaveta 1 (Variation) OU Gaveta de Inserção: vários canais marcados =
        # todos passam pelo mesmo efeito.
        chs_antigo = v_slot.get('chs', {}) if isinstance(v_slot.get('chs'), dict) else {}
        v_slot['chs'] = {c: chs_antigo.get(c, 127) for c in canais_marcados if 0 <= c < 16}
        v_slot['ch'] = next(iter(v_slot['chs']), self.canal_atual if slot_idx else 0x7F)

        # Inserção: "reivindica" os canais marcados - tira eles de qualquer
        # OUTRA gaveta de Inserção (senão o mesmo canal sairia por 2 efeitos).
        # Puxa a mistura seco/molhado que o canal já tinha na gaveta antiga.
        if slot_idx != 0:
            marcados = set(v_slot['chs'])
            for k, ov in list(self.variation_dsp_cache.items()):
                if k == slot_idx or not (isinstance(k, int) and 1 <= k <= 6) or not isinstance(ov, dict):
                    continue
                antes = set(self._slot0_canais(ov))
                if not (antes & marcados):
                    continue
                och = ov.setdefault('chs', {})
                for c in list(marcados):
                    if c in och:
                        v_slot['chs'][c] = och.pop(c)
                restantes = antes - marcados
                if restantes:
                    ov['chs'] = {c: och.get(c, 127) for c in restantes}
                    ov['ch'] = next(iter(ov['chs']))
                else:
                    ov['active'] = False
                    ov['chs'] = {}
                    ov['ch'] = 0x7F

        # Nomes de parâmetro vêm da tabela compartilhada (mhs_utils.DSP_PARAM_NAMES),
        # a mesma já conferida contra o Data List oficial e usada no Style Creator -
        # nada de manter uma cópia própria desatualizada aqui.
        nomes_param = DSP_PARAM_NAMES.get(msb_val, ["Param " + str(i+1) for i in range(16)])

        # 2. A FÁBRICA: Abre a tela específica dependendo da Família escolhida!
        if msb_val in [5, 6, 7, 8]:
            dlg_editor = DelayDSPEditor(self, self.canal_atual, slot_idx, msb_val, msb_idx, lsb_idx, nomes_param)
        else:
            dlg_editor = StandardDSPEditor(self, self.canal_atual, slot_idx, msb_val, msb_idx, lsb_idx, nomes_param)
            
        self.active_dsp_editor = dlg_editor
        try:
            if dlg_editor.ShowModal() == wx.ID_OK:
                if getattr(self, 'recorded_events', None): self.aplicar_gravacao()
                self.save_state(f"Efeito DSP (Gaveta {slot_idx + 1})")

                if hasattr(self, 'consolidar_projeto'): self.consolidar_projeto()

                self.dirty = True
                self.atualizar_titulo()
                self.ler_midi_memoria(reset_canais=False)
                falar_status(f"Efeito salvo na Gaveta {slot_idx + 1}.", imediato=True)
        finally:
            self.active_dsp_editor = None
            dlg_editor.Destroy()

        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())

    def remover_dsp_do_canal(self, ch):
        # Botão "Remover TODOS os DSP deste Canal" na 1ª tela do DSP Variation:
        # desliga toda gaveta (Variation/Insertion) que aponta pra esse canal,
        # manda o comando físico de desligar pro teclado e tira do arquivo.
        from mhs_utils import falar_status
        import mido
        if not hasattr(self, 'variation_dsp_cache'):
            self.variation_dsp_cache = {}
        def usa_canal(k, v):
            if not (isinstance(v, dict) and v.get('active')):
                return False
            return ch in self._slot0_canais(v)

        alvos = [k for k, v in self.variation_dsp_cache.items() if usa_canal(k, v)]
        if not alvos:
            falar_status(f"O canal {ch + 1} não tem nenhum DSP.", imediato=True)
            return

        self.save_state(f"Remover DSP do Canal {ch + 1}")
        so_tirou_do_slot0 = []
        for k in list(alvos):
            v = self.variation_dsp_cache[k]
            if len(self._slot0_canais(v)) >= 2:
                # Efeito compartilhado (Variation SYSTEM ou grupo de Inserção) -
                # tira SÓ este canal, o efeito continua pros outros.
                v.get('chs', {}).pop(ch, None)
                v['ch'] = next(iter(v.get('chs', {})), 0x7F)
                so_tirou_do_slot0.append(k)
                alvos.remove(k)
                continue
            v['active'] = False
            v['p'] = [-1] * 16
            v['ret'] = -1
            if getattr(self, 'output', None):
                try:
                    if k == 0:
                        off = mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x5B, 0x7F, 0xF7])
                    else:
                        off = mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x03, k - 1, 0x0C, 0x7F, 0xF7])
                    self.output.send(off)
                except Exception:
                    pass

        if hasattr(self, '_dsp_teclado'):
            self._dsp_teclado.get('slots', {}).pop(ch, None)

        # consolidar_projeto tira do arquivo o SysEx das gavetas desligadas
        # (a autoridade é o cache) e reescreve só o que sobrou ativo.
        if hasattr(self, 'consolidar_projeto'):
            self.consolidar_projeto()
        for k in alvos:
            self.variation_dsp_cache.pop(k, None)

        self.dirty = True
        self.atualizar_titulo()
        self.ler_midi_memoria(reset_canais=False)
        n = len(alvos) + len(so_tirou_do_slot0)
        falar_status(f"{n} efeito(s) DSP removido(s) do canal {ch + 1}.", imediato=True)

    def is_sysex_dsp_antigo(self, msg, is_start=True):
        if msg.type != 'sysex': return False
        if not is_start: return False # Se for no meio da música, passa batido!
        
        data = msg.data
        if len(data) >= 4 and tuple(data[0:4]) == (0x43, 0x10, 0x4C, 0x00): return True
        if len(data) == 4 and tuple(data[0:4]) == (0x7E, 0x7F, 0x09, 0x01): return True
        if len(data) >= 5 and tuple(data[0:4]) == (0x7F, 0x7F, 0x04, 0x01): return True
        if len(data) >= 6 and tuple(data[0:6]) in [(0x43, 0x10, 0x4C, 0x02, 0x01, 0x00), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x02), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x0C), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x20), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x22), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x2C), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x5A), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x5B), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x40), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x54), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x56), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x42), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x44), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x46), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x48), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x4A), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x4E), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x50), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x52), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x58), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x70), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x71), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x72), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x73), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x74), (0x43, 0x10, 0x4C, 0x02, 0x01, 0x75)]: return True
        if len(data) >= 4 and tuple(data[0:4]) == (0x43, 0x10, 0x4C, 0x03): return True
        return False
    def enviar_variation_dsp_completo(self):
        if not getattr(self, 'output', None) or not hasattr(self, 'variation_dsp_cache'): return
            
        import mido
        import time
        dsp_msb_vals = [v for _, v in VARIATION_EFEITOS_LIST]
        offsets_var_2bytes = [0x42, 0x44, 0x46, 0x48, 0x4A, 0x4C, 0x4E, 0x50, 0x52, 0x54]
        offsets_var_1byte  = [0x70, 0x71, 0x72, 0x73, 0x74, 0x75]
        # Params 1-10 do efeito de Inserção XG ficam em 0x02-0x0B; os params
        # 11-16 ficam em 0x20-0x25 (NÃO em 0x0D-0x12, que são as sensibilidades
        # de controlador M.W./Bend/CAT/AC1/AC2/CBC1). Vários efeitos usam 11-16
        # (ex.: 95 = Amp Simulator com Speaker/LFO/Phaser/Delay) - o teclado
        # despeja esses endereços na troca de timbre.
        offsets_ins_1b     = [0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25]

        for slot_idx, v in self.variation_dsp_cache.items():
            if not isinstance(v, dict) or not v.get('active', False): continue

            idx = v.get('msb_idx', 0)
            msb = dsp_msb_vals[idx] if idx < len(dsp_msb_vals) else 0
            lsb = v.get('lsb_idx', 0)
            ch = v.get('ch', 0)
            ret = v.get('ret', -1)
            p_list = v.get('p', [-1]*16)
            
            part_val = 0x7F if msb == 0 else ch
            msgs = []
            
            if slot_idx == 0:
                slot0_chs = self._slot0_canais(v)
                if len(slot0_chs) >= 2:
                    conn_val, part_val = 0x01, 0x7F
                else:
                    conn_val = 0x01 if part_val == 0x7F else 0x00
                msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x5A, conn_val, 0xF7])
                msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x5B, part_val, 0xF7])
                msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x40, msb, lsb, 0xF7])
                if len(slot0_chs) >= 2:
                    for c_env, niv_env in slot0_chs.items():
                        msgs.append([0xB0 + c_env, 94, max(0, min(127, int(niv_env)))])

                if ret != -1:
                    # O Return genérico original (0x56) e, de quebra, o Parameter
                    # 10 (0x54) de 2 bytes - mesma dupla-escrita que já valeu a
                    # pena em consolidar_projeto ("a mágica que travou o volume
                    # no teclado"). Sem padrão único confirmado em hardware
                    # (testes deram os dois funcionando em momentos diferentes),
                    # então manda os dois igual.
                    msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x56, ret, 0xF7])
                    msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x54, 0x00, ret, 0xF7])

                for i in range(16):
                    if p_list[i] != -1:
                        # Não manda o 0x54 duplicado se o Return já assumiu esse endereço.
                        if i == 9 and ret != -1:
                            continue
                        if i < 10: msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, offsets_var_2bytes[i], p_list[i] // 128, p_list[i] % 128, 0xF7])
                        else: msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, offsets_var_1byte[i-10], p_list[i] & 0x7F, 0xF7])
            else:
                nn = slot_idx - 1
                msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x03, nn, 0x0C, part_val, 0xF7])
                msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x03, nn, 0x00, msb, lsb, 0xF7])
                
                if ret != -1: msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x03, nn, 0x0B, ret, 0xF7])
                
                # --- CORREÇÃO GAVETA 2 EM DIANTE: Delay livre para usar 2 bytes em todos os params ---
                # O Data List oficial (MIDI Parameter Change, MULTI PART, pág.
                # 65) é claro: "Type MSB of the effect types that require
                # Parameter MSB are: 5, 6, 7, 8, 95, 96, 97, 98, 104" - faltavam
                # os 5 últimos aqui (95=Multi FX, 96=Small Stereo Dist, 97=British
                # Combo, 98=V Distortion, 104=V Flanger). Sem eles, os parâmetros
                # desses efeitos eram mandados no endereço de 1 byte errado - o
                # teclado real ignora silenciosamente (a mesma página diz que,
                # pros efeitos que precisam de MSB, os endereços 02-0B "will not
                # be received").
                is_delay = msb in [5, 6, 7, 8, 95, 96, 97, 98, 104]
                for i in range(16):
                    if p_list[i] != -1:
                        if is_delay: 
                            msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x03, nn, 0x30 + (i * 2), p_list[i] // 128, p_list[i] % 128, 0xF7])
                        else: 
                            msgs.append([0xF0, 0x43, 0x10, 0x4C, 0x03, nn, offsets_ins_1b[i], p_list[i] & 0x7F, 0xF7])

            for data in msgs:
                try: 
                    self.output.send(mido.Message.from_bytes(data))
                    if len(data) >= 7 and data[6] in [0x40, 0x00]: time.sleep(0.25)
                except: pass
    def consolidar_projeto(self):
        if not getattr(self, 'midi_file', None): return
        import mido

        # A SysEx "Mixagem" (43 10 4C 08) é redundante pra Bank/Patch/Volume/
        # Pan/Reverb/Chorus - esses 6 já saem sempre como CC/Program Change
        # normal, incondicionalmente (ver o laço "for ch in range(16)" mais
        # abaixo) - nenhum teclado XG precisa da SysEx pra recuperar isso.
        # Só Grave/Agudo (0x72/0x73, sem CC padrão) e o VoiceCreator (formas
        # de onda/filtro/EQ arbitrários do teclado, e o Detune/Portamento
        # dentro dele) realmente EXIGEM SysEx pra sobreviver. Mono/Poly (CC
        # 126/127) e Porta Time (CC 5) também já têm CC próprio (ver mais
        # abaixo) - nunca precisaram de SysEx nenhuma, e entravam aqui só por
        # engano.
        #
        # Bug real (Michel, "Gerenciador Avançado de SysEx" apagando tudo e
        # o arquivo voltando com SysEx depois de salvar/reabrir): esta
        # decisão era um ÚNICO flag global (`usa_sysex_mixagem`) - bastava
        # UM canal ter qualquer coisa fora do padrão (inclusive Porta Time,
        # que nem é SysEx) pra TODOS os canais com Volume/Pan/etc não-padrão
        # (a imensa maioria de um MIDI de verdade) ganharem de volta os 6
        # campos redundantes em SysEx, mesmo sem ter Grave/Agudo/VoiceCreator
        # nenhum - o consolidar_projeto "ressuscitava" exatamente o que tinha
        # acabado de ser apagado. Corrigido: a decisão agora é por CANAL,
        # baseada só no que aquele canal específico tem de verdade em
        # self.canais (a mesma fonte de verdade que Drum Setup/DSP já usam
        # aqui - nunca mais lida direto do arquivo físico).
        canais_com_mixagem_sysex = set()
        for ch, c in enumerate(self.canais):
            if c.get("Grave", 64) != 64 or c.get("Agudo", 64) != 64 or len(c.get("VoiceCreator", {})) > 0:
                canais_com_mixagem_sysex.add(ch)

        tpb = getattr(self.midi_file, 'ticks_per_beat', 480)

        variation_active = False
        if hasattr(self, 'variation_dsp_cache'):
            for slot, v in self.variation_dsp_cache.items():
                if isinstance(v, dict) and v.get('active', False):
                    variation_active = True
                    break

        meta_events, channel_events = [], {i: [] for i in range(16)}
        nrpn_estado_antigo = {i: [None, None] for i in range(16)}

        for track in self.midi_file.tracks:
            abs_tick = 0
            for msg in track:
                abs_tick += msg.time
                if abs_tick == 0 and msg.type == 'track_name': continue
                
                if msg.type == 'sysex':
                    data = msg.data
                    is_old_dsp = False
                    
                    t4 = tuple(data[0:4]) if len(data) >= 4 else ()
                    t3 = tuple(data[0:3]) if len(data) >= 3 else ()
                    
                    if t4 == (0x43, 0x10, 0x4C, 0x00): is_old_dsp = True
                    elif t4 == (0x7E, 0x7F, 0x09, 0x01): is_old_dsp = True
                    elif t4 == (0x7F, 0x7F, 0x04, 0x01): is_old_dsp = True
                    
                    elif len(data) >= 5 and t3 == (0x43, 0x10, 0x4C) and data[3] in [0x30, 0x31, 0x08]:
                        if data[3] == 0x08:
                            # Qualquer Multi Part (menos Rcv Channel/Mode 0x04-0x07)
                            # é reconstruído a partir do modelo, então tira o
                            # antigo pra não duplicar.
                            if len(data) >= 6 and data[5] not in (0x04, 0x05, 0x06, 0x07):
                                is_old_dsp = True
                        else:
                            is_old_dsp = True
                            
                    elif len(data) >= 6:
                        t5 = tuple(data[0:5])
                        addr = data[5]
                        if t5 == (0x43, 0x10, 0x4C, 0x02, 0x01) and (
                            addr in [0x00, 0x0C, 0x20, 0x2C, 0x5A, 0x5B, 0x40, 0x54, 0x56,
                                     0x42, 0x44, 0x46, 0x48, 0x4A, 0x4E, 0x50, 0x52, 0x58,
                                     0x70, 0x71, 0x72, 0x73, 0x74, 0x75]
                            or addr in OFFSETS_REV_PARAMS or addr in OFFSETS_CHO_PARAMS
                        ):
                            is_old_dsp = True
                            
                    # Se a gaveta de Inserção está no cache, o consolidar_projeto
                    # é a autoridade sobre ela: reemite se ativa, e descarta o
                    # SysEx antigo se foi desligada (troca de efeito pelo teclado
                    # ou "Remover DSP do Canal"). Vale mesmo sem nenhuma gaveta
                    # ativa - senão um "remover tudo" não removia de verdade.
                    if not is_old_dsp and t4 == (0x43, 0x10, 0x4C, 0x03):
                        if (data[4] + 1) in self.variation_dsp_cache:
                            is_old_dsp = True

                    if is_old_dsp: continue

                # Guia 3 (Drum Setup via NRPN): o consolidar_projeto é a
                # autoridade sobre ela (igual já acontece com o SysEx da
                # Guia 1 e a Inserção de DSP acima) - a trinca 99/98/6
                # antiga é descartada de vez, e reemitida do zero a partir
                # de self.canais[ch]["DrumParamsNRPN"] mais abaixo. Isso
                # tem que valer INDEPENDENTE de já ter passado a 1ª nota
                # do canal - o filtro antigo ("só descarta antes da 1ª
                # nota", usado pros outros CCs mais abaixo) falhava bem
                # aqui: num canal de bateria a 1ª nota costuma vir logo no
                # início da música, ANTES de onde essas trincas ficam - o
                # "Remover" do Drum Setup limpava o dicionário, mas a
                # trinca física sobrevivia intacta e "ressuscitava" de
                # volta no dicionário na próxima leitura do arquivo.
                is_old_drum_nrpn = False
                if msg.type == 'control_change':
                    ch_nrpn = getattr(msg, 'channel', None)
                    if ch_nrpn is not None and 0 <= ch_nrpn < 16:
                        if msg.control == 99:
                            nrpn_estado_antigo[ch_nrpn][0] = msg.value
                        elif msg.control == 98:
                            nrpn_estado_antigo[ch_nrpn][1] = msg.value
                        elif msg.control == 6:
                            n_msb, n_lsb = nrpn_estado_antigo[ch_nrpn]
                            if n_msb in DRUM_NRPN_MSBS and n_lsb is not None:
                                is_old_drum_nrpn = True
                                fila = channel_events[ch_nrpn]
                                if fila and fila[-1][1].type == 'control_change' and fila[-1][1].control == 98:
                                    fila.pop()
                                if fila and fila[-1][1].type == 'control_change' and fila[-1][1].control == 99:
                                    fila.pop()
                            nrpn_estado_antigo[ch_nrpn] = [None, None]

                if is_old_drum_nrpn: continue

                ch = getattr(msg, 'channel', None)
                if ch is not None and 0 <= ch < 16:
                    channel_events[ch].append([int(abs_tick), msg])
                else:
                    meta_events.append([int(abs_tick), msg])

        # Gaveta 1 (Variation) ativa -> o consolidar reemite o CC94 ("Variation
        # Send Level") de cada canal a partir do cache; joga fora os antigos
        # pra não duplicar ao reabrir.
        _vc0 = getattr(self, 'variation_dsp_cache', {}).get(0)
        _slot0_ativa = isinstance(_vc0, dict) and _vc0.get('active', False)
        for ch in range(16):
            channel_events[ch].sort(key=lambda x: x[0])
            seen_note = False
            filtered_events = []
            for tick, msg in channel_events[ch]:
                if msg.type == 'note_on' and msg.velocity > 0:
                    seen_note = True
                if _slot0_ativa and msg.type == 'control_change' and msg.control == 94:
                    continue
                if not seen_note:
                    if msg.type == 'program_change': continue
                    if msg.type == 'control_change' and msg.control in [0, 5, 6, 7, 10, 11, 32, 38, 65, 91, 93, 98, 99, 100, 101, 126, 127]: continue
                filtered_events.append([tick, msg])
            channel_events[ch] = filtered_events

        novo_mid = mido.MidiFile(type=1)
        novo_mid.ticks_per_beat = tpb
        tr0 = mido.MidiTrack()
        
        sys_tick = 10 
        param_tick = 140 

        if hasattr(self, 'dsp_cache') and self.dsp_cache.get('active', False):
            c = self.dsp_cache
            rev_msb_list = [v for _, v in REV_MSB_LIST]
            cho_msb_list = [v for _, v in CHO_MSB_LIST]
            r_msb = rev_msb_list[c.get('rev_msb_idx', 1)] if c.get('rev_msb_idx', 1) < len(rev_msb_list) else 1
            c_msb = cho_msb_list[c.get('cho_msb_idx', 1)] if c.get('cho_msb_idx', 1) < len(cho_msb_list) else 65

            meta_events.append([sys_tick, mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x00, r_msb, c.get('rev_lsb_idx', 0), 0xF7])])
            meta_events.append([param_tick, mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x0C, c.get('rev_ret', 64), 0xF7])])
            meta_events.append([sys_tick, mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x20, c_msb, c.get('cho_lsb_idx', 0), 0xF7])])
            meta_events.append([param_tick, mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, 0x2C, c.get('cho_ret', 64), 0xF7])])
            rev_p = c.get('rev_p', [-1] * 16)
            for i in range(16):
                if rev_p[i] != -1:
                    meta_events.append([param_tick, mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, OFFSETS_REV_PARAMS[i], rev_p[i] & 0x7F, 0xF7])])
            cho_p = c.get('cho_p', [-1] * 16)
            for i in range(16):
                if cho_p[i] != -1:
                    meta_events.append([param_tick, mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x02, 0x01, OFFSETS_CHO_PARAMS[i], cho_p[i] & 0x7F, 0xF7])])

        if variation_active:
            v_cache = self.variation_dsp_cache
            dsp_msb_vals = [v for _, v in VARIATION_EFEITOS_LIST]

            offsets_var_2bytes = [0x42, 0x44, 0x46, 0x48, 0x4A, 0x4C, 0x4E, 0x50, 0x52, 0x54]
            offsets_var_1byte  = [0x70, 0x71, 0x72, 0x73, 0x74, 0x75]
            # Params 11-16 do efeito de Inserção XG ficam em 0x20-0x25.
            offsets_ins_1b     = [0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25]

            # "mid" (0-5) das gavetas de Inserção. Cada slot de Inserção ativo
            # fica com o SEU "home" (slot_idx - 1); as cópias extras de um slot
            # multi-canal puxam de mids que nenhum slot ativo reivindica como
            # home. Assim uma gaveta de 1 canal continua no mesmo mid de antes.
            _homes_ins = {sk - 1 for sk in v_cache
                          if isinstance(sk, int) and 1 <= sk <= 6
                          and isinstance(v_cache.get(sk), dict) and v_cache[sk].get('active')}
            nn_livres = [m for m in range(6) if m not in _homes_ins]

            for slot_idx in sorted(v_cache.keys()):
                if not isinstance(slot_idx, int): continue
                dsp_slot = v_cache[slot_idx]
                if not isinstance(dsp_slot, dict) or not dsp_slot.get('active', False): continue
                
                idx_v = dsp_slot.get('msb_idx', 0)
                msb_v = dsp_msb_vals[idx_v] if idx_v < len(dsp_msb_vals) else 0
                ch_v = dsp_slot.get('ch', 0)
                ret_v = dsp_slot.get('ret', -1)
                p_list = dsp_slot.get('p', [-1]*16)
                
                part_val = 0x7F if msb_v == 0 else ch_v
                high = 0x02 if slot_idx == 0 else 0x03
                mid = 0x01 if slot_idx == 0 else (slot_idx - 1)
                type_offset = 0x40 if slot_idx == 0 else 0x00

                # Gaveta 1 (Variation) com 2+ canais: Conexão SYSTEM + um CC94
                # ("Variation Send Level") por canal - mesma técnica do estilo.
                slot0_chs = self._slot0_canais(dsp_slot) if slot_idx == 0 else {}
                slot0_system = len(slot0_chs) >= 2

                if slot_idx == 0:
                    if slot0_system:
                        conn_val, part_val = 0x01, 0x7F
                    else:
                        part_val = 0x7F if (msb_v == 0 or not slot0_chs) else next(iter(slot0_chs))
                        conn_val = 0x01 if part_val == 0x7F else 0x00
                    meta_events.append([sys_tick, mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, high, mid, 0x5A, conn_val, 0xF7])])
                    meta_events.append([sys_tick, mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, high, mid, 0x5B, part_val, 0xF7])])
                    meta_events.append([sys_tick, mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, high, mid, type_offset, msb_v, dsp_slot.get('lsb_idx', 0), 0xF7])])
                    if slot0_system:
                        # O CC94 ("Variation Send Level") de cada canal TEM que
                        # vir DEPOIS do tipo/conexão da Variation, senão o
                        # PSR-SX ignora o envio (o efeito só "pega" no arquivo
                        # depois de um rec/stop no teclado). Por isso vai na
                        # track 0, logo após os parâmetros, e não na track do
                        # canal (que fica no tick 0 e chega antes).
                        for c_env, niv_env in slot0_chs.items():
                            meta_events.append([param_tick + 2, mido.Message('control_change', channel=c_env, control=94, value=max(0, min(127, int(niv_env))))])

                    if ret_v != -1:
                        # O Return genérico original (0x56) para manter compatibilidade
                        meta_events.append([param_tick, mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, high, mid, 0x56, ret_v, 0xF7])])
                        
                        # A MÁGICA AQUI: Espelhando o comportamento da Gaveta (StandardDSPEditor).
                        # Gravamos fisicamente o Parameter 10 (0x54 - Dry/Wet) de 2 bytes para travar o volume no teclado!
                        meta_events.append([param_tick, mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, high, mid, 0x54, 0x00, ret_v, 0xF7])])

                    for i in range(16):
                        if p_list[i] != -1:
                            # Proteção para não mandar o endereço 0x54 duplicado se o ret_v já assumiu o controle!
                            if i == 9 and ret_v != -1:
                                continue
                                
                            if i < 10: 
                                meta_events.append([param_tick, mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, high, mid, offsets_var_2bytes[i], p_list[i] // 128, p_list[i] % 128, 0xF7])])
                            else: 
                                meta_events.append([param_tick, mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, high, mid, offsets_var_1byte[i-10], p_list[i] & 0x7F, 0xF7])])
                else:
                    # Inserção: uma cópia física do efeito por canal, cada uma
                    # numa "mid" livre (0-5). 1 canal = 1 gaveta, igual antes.
                    chs_ins = self._slot0_canais(dsp_slot)
                    if not chs_ins:
                        chs_ins = {ch_v: 127} if isinstance(ch_v, int) and 0 <= ch_v < 16 else {}
                    # Mesma correção da função anterior (Data List oficial,
                    # MULTI PART pág. 65) - os 5 efeitos que exigem 2 bytes
                    # e não estavam na lista: 95, 96, 97, 98, 104.
                    is_delay = msb_v in [5, 6, 7, 8, 95, 96, 97, 98, 104]
                    home = slot_idx - 1
                    mids_deste = []
                    for _ in chs_ins:
                        if not mids_deste and 0 <= home <= 5:
                            mids_deste.append(home)
                        elif nn_livres:
                            mids_deste.append(nn_livres.pop(0))
                    multi_ins = len(chs_ins) >= 2
                    for canal_ins, nn in zip(chs_ins, mids_deste):
                        # Multi-canal: a mistura seco/molhado (0x0B) de cada
                        # cópia vem do nível do canal em `chs`; senão o Dry/Wet
                        # global da gaveta (`ret`).
                        dw = chs_ins.get(canal_ins) if multi_ins else ret_v
                        if not (isinstance(dw, int) and 0 <= dw <= 127):
                            dw = ret_v
                        meta_events.append([sys_tick, mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x03, nn, 0x0C, canal_ins, 0xF7])])
                        meta_events.append([sys_tick, mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x03, nn, 0x00, msb_v, dsp_slot.get('lsb_idx', 0), 0xF7])])
                        if dw != -1:
                            meta_events.append([param_tick, mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x03, nn, 0x0B, dw & 0x7F, 0xF7])])
                        for i in range(16):
                            if p_list[i] != -1:
                                if multi_ins and i == 9:
                                    continue  # índice 9 = Dry/Wet, mandado por canal acima
                                if is_delay:
                                    meta_events.append([param_tick, mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x03, nn, 0x30 + (i * 2), p_list[i] // 128, p_list[i] % 128, 0xF7])])
                                else:
                                    meta_events.append([param_tick, mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x03, nn, offsets_ins_1b[i], p_list[i] & 0x7F, 0xF7])])

        for ch in range(16):
            part_byte = 0x30 if ch == 9 else 0x31 
            if "CustomDrumMap" in self.canais[ch]:
                for orig_note, m in self.canais[ch]["CustomDrumMap"].items():
                    b = m['bank']
                    b_msb = min(127, b // 128)
                    syx_data = [0xF0, 0x43, 0x10, 0x4C, part_byte, orig_note, 0x70, b_msb, b % 128, m['patch'], m['dest_note'], 0xF7]
                    meta_events.append([120, mido.Message.from_bytes(syx_data)])

            if "DrumParams" in self.canais[ch]:
                for (note, param_id), val in self.canais[ch]["DrumParams"].items():
                    syx_data = [0xF0, 0x43, 0x10, 0x4C, part_byte, note, param_id, val, 0xF7]
                    meta_events.append([121, mido.Message.from_bytes(syx_data)])

            # Guia 3 (NRPN puro, não é SysEx - carrega o canal no próprio CC,
            # então não precisa do part_byte por canal). 99=parâmetro,
            # 98=peça, 6=valor, em sequência (a leitura em ler_midi_memoria
            # espera essa ordem). Uma trinca por peça/parâmetro editado,
            # ticks crescentes pra garantir a ordem mesmo com sort estável.
            if "DrumParamsNRPN" in self.canais[ch]:
                tick_nrpn = 122
                for (note, param_id), val in self.canais[ch]["DrumParamsNRPN"].items():
                    channel_events[ch].append([tick_nrpn, mido.Message('control_change', channel=ch, control=99, value=param_id)])
                    channel_events[ch].append([tick_nrpn + 1, mido.Message('control_change', channel=ch, control=98, value=note)])
                    channel_events[ch].append([tick_nrpn + 2, mido.Message('control_change', channel=ch, control=6, value=val)])
                    tick_nrpn += 3

        meta_events.sort(key=lambda x: x[0])
        last_t = 0
        for tick, msg in meta_events:
            tr0.append(copiar_com_tempo(msg, max(0, tick - last_t)))
            last_t = tick
        novo_mid.tracks.append(tr0)

        for ch in range(16):
            c = self.canais[ch]
            nome_canal = str(c.get("Nome", ""))
            foi_mexido = (c.get("Volume") != 100 or c.get("Pan") != 64 or
                          c.get("Bank") != (16256 if ch == 9 else 0) or
                          c.get("Patch") != 0 or c.get("Reverb") != 0 or
                          c.get("Chorus") != 0 or c.get("Grave", 64) != 64 or c.get("Agudo", 64) != 64 or c.get("Pitch Bend", 2) != 2 or c.get("Mono/Poly", True) is False or c.get("Porta Time", 0) != 0 or
                          len(c.get("VoiceCreator", {})) > 0 or
                          (nome_canal and nome_canal != f"Track {ch+1}"))
            
            if not channel_events[ch] and not foi_mexido: continue

            tr = mido.MidiTrack()
            tr.append(mido.MetaMessage('track_name', name=(nome_canal if nome_canal else f"Track {ch+1}"), time=0))
            
            b = int(c.get("Bank", 0))
            v_vol = int(c.get("Volume", 100))
            v_pan = int(c.get("Pan", 64))
            v_grave = int(c.get("Grave", 64))
            v_agudo = int(c.get("Agudo", 64))
            v_exp = int(c.get("Expression", 127))
            v_rev = int(c.get("Reverb", 0))
            v_cho = int(c.get("Chorus", 0))
            v_mono = c.get("Mono/Poly", True)
            v_porta = int(c.get("Porta Time", 0))
            
            tr.append(mido.Message('control_change', channel=ch, control=0, value=b // 128, time=0))
            tr.append(mido.Message('control_change', channel=ch, control=32, value=b % 128, time=0))
            tr.append(mido.Message('program_change', channel=ch, program=int(c.get("Patch", 0)), time=0))
            tr.append(mido.Message('control_change', channel=ch, control=7, value=v_vol, time=0))
            tr.append(mido.Message('control_change', channel=ch, control=10, value=v_pan, time=0))
            tr.append(mido.Message('control_change', channel=ch, control=11, value=v_exp, time=0))
            tr.append(mido.Message('control_change', channel=ch, control=91, value=v_rev, time=0))
            tr.append(mido.Message('control_change', channel=ch, control=93, value=v_cho, time=0))

            pb_range = int(c.get("Pitch Bend", 2))
            tr.append(mido.Message('control_change', channel=ch, control=101, value=0, time=0))
            tr.append(mido.Message('control_change', channel=ch, control=100, value=0, time=0))
            tr.append(mido.Message('control_change', channel=ch, control=6, value=pb_range, time=0))
            tr.append(mido.Message('control_change', channel=ch, control=101, value=127, time=0))
            tr.append(mido.Message('control_change', channel=ch, control=100, value=127, time=0))

            tr.append(mido.Message('control_change', channel=ch, control=5, value=v_porta, time=0))
            tr.append(mido.Message('control_change', channel=ch, control=65, value=127 if v_porta > 0 else 0, time=0))
            tr.append(mido.Message('control_change', channel=ch, control=127 if v_mono else 126, value=0 if v_mono else 1, time=0))

            if ch in canais_com_mixagem_sysex:
                tr.append(mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x08, ch, 0x01, b // 128, 0xF7], time=0))
                tr.append(mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x08, ch, 0x02, b % 128, 0xF7], time=0))
                tr.append(mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x08, ch, 0x03, int(c.get("Patch", 0)), 0xF7], time=0))
                tr.append(mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x08, ch, 0x0B, v_vol, 0xF7], time=0))
                tr.append(mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x08, ch, 0x0E, v_pan, 0xF7], time=0))
                tr.append(mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x08, ch, 0x13, v_rev, 0xF7], time=0))
                tr.append(mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x08, ch, 0x12, v_cho, 0xF7], time=0))
                tr.append(mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x08, ch, 0x72, v_grave, 0xF7], time=0))
                tr.append(mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x08, ch, 0x73, v_agudo, 0xF7], time=0))
                vc_params = c.get("VoiceCreator", {})
                for addr_vc, val_vc in vc_params.items():
                    if addr_vc == 0x09:
                        # Detune: o modelo guarda 1 valor combinado (0-255) -
                        # a SysEx de verdade continua sendo 2 mensagens, 1
                        # nibble por endereço (ver detune_separar).
                        alto, baixo = detune_separar(val_vc)
                        tr.append(mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x08, ch, 0x09, alto, 0xF7], time=0))
                        tr.append(mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x08, ch, 0x0A, baixo, 0xF7], time=0))
                    elif addr_vc in (0x01, 0x02, 0x03):
                        # Portamento (Mono Priority/Modo/Modo do Tempo) -
                        # bloco 0x0A de verdade, não o 0x08 de sempre.
                        tr.append(mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x0A, ch, addr_vc, val_vc, 0xF7], time=0))
                    else:
                        tr.append(mido.Message.from_bytes([0xF0, 0x43, 0x10, 0x4C, 0x08, ch, addr_vc, val_vc, 0xF7], time=0))

            channel_events[ch].sort(key=lambda x: x[0])
            last_tc = 0
            for tick, msg in channel_events[ch]:
                tr.append(copiar_com_tempo(msg, max(0, tick - last_tc)))
                last_tc = tick
            novo_mid.tracks.append(tr)
            
        self.midi_file = novo_mid

    def garantir_cabecalho_xg(self):
        import mido
        if not getattr(self, 'midi_file', None) or not self.midi_file.tracks:
            return
            
        track_0 = self.midi_file.tracks[0]
        # SysEx do XG System On: F0 43 10 4C 00 00 7E 00 F7
        xg_on_data = (67, 16, 76, 0, 0, 126, 0) 
        
        # Verifica se já tem o XG ON para não duplicar
        tem_xg = False
        for msg in track_0:
            if getattr(msg, 'type', '') == 'sysex' and tuple(msg.data) == xg_on_data:
                tem_xg = True
                break
                
        if not tem_xg:
            # Cria a mensagem de ativação do XG
            xg_msg = mido.Message('sysex', data=xg_on_data, time=0)
            
            # Insere no comecinho da música (posição 0 da Track 0)
            track_0.insert(0, xg_msg)
            
            # Dá um tempo de 120 ticks (~50ms) no próximo evento para o Yamaha conseguir "respirar"
            if len(track_0) > 1:
                track_0[1] = copiar_com_tempo(track_0[1], track_0[1].time + 120)
    def on_paste_repeat(self, event):
        from mhs_utils import falar_status
        if not getattr(self, 'event_clipboard', []):
            falar_status("Área de transferência vazia.", imediato=True)
            return
            
        from mhs_dialogs import PasteRepeatDialog
        dlg = PasteRepeatDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            repeats, mode, int_sec, int_ticks = dlg.get_valores()
            
            self.save_state(f"Colar Repetido ({repeats}x)")
            
            paste_tick_original = self.get_tick_at_sec(self.current_playback_time)
            base_target_ch = self.canal_atual
            new_events_by_track = {i: [] for i in range(len(self.midi_file.tracks))}
            
            dest_tpb = max(1, getattr(self.midi_file, 'ticks_per_beat', 480))
            clipboard_ticks = getattr(self, 'clipboard_length_ticks', dest_tpb) 
            
            if mode == 0: jump_step = clipboard_ticks 
            elif mode == 1: jump_step = self.get_tick_at_sec(self.current_playback_time + int_sec) - paste_tick_original
            elif mode == 2: jump_step = int_ticks
            else: jump_step = clipboard_ticks
            
            jump_step = max(1, jump_step)
            canais_afetados = set()
            count = 0
            
            for rep in range(repeats):
                current_paste_tick = paste_tick_original + (rep * jump_step)
                
                for ev in self.event_clipboard:
                    target_ch = base_target_ch + ev['ch_offset']
                    if 0 <= target_ch <= 15:
                        canais_afetados.add(target_ch)
                        new_msg = ev['msg'].copy(channel=target_ch)
                        
                        source_tpb = ev.get('source_tpb', dest_tpb)
                        scale = dest_tpb / float(source_tpb)
                        scaled_offset = int(round(ev['tick_offset'] * scale))
                        
                        target_tick = current_paste_tick + scaled_offset
                        
                        best_track = 0
                        for i, tr in enumerate(self.midi_file.tracks):
                            if any(getattr(m, 'channel', None) == target_ch for m in tr):
                                best_track = i
                                break
                        new_events_by_track[best_track].append((target_tick, new_msg))
                        count += 1
                        
            for i, tr in enumerate(self.midi_file.tracks):
                if not new_events_by_track[i]: continue
                flat = []
                t = 0
                for m in tr:
                    t += m.time
                    # OTIMIZAÇÃO: Pré-cálculo rápido
                    is_off = 0 if m.type == 'note_off' or (m.type == 'note_on' and getattr(m, 'velocity', 0) == 0) else 1
                    flat.append((t, is_off, m))
                    
                for t_new, m_new in new_events_by_track[i]:
                    is_off_new = 0 if m_new.type == 'note_off' or (m_new.type == 'note_on' and getattr(m_new, 'velocity', 0) == 0) else 1
                    flat.append((t_new, is_off_new, m_new))
                    
                flat.sort(key=lambda x: (x[0], x[1]))
                
                import mido
                new_track = mido.MidiTrack()
                last_t = 0
                for t_ev, _, m_ev in flat:
                    delta = max(0, int(round(t_ev - last_t)))
                    m_ev.time = delta
                    new_track.append(m_ev)
                    last_t = t_ev
                self.midi_file.tracks[i] = new_track
                
            self.dirty = True
            self.atualizar_titulo()
            
            was_playing = self.tocando
            if self.tocando:
                self.tocando = False
                self.all_notes_off()
                import time
                time.sleep(0.05)
                
            self.ler_midi_memoria(reset_canais=False)
            
            final_tick = paste_tick_original + (repeats * jump_step)
            self.current_playback_time = self.get_sec_at_tick(final_tick)
            self.last_start_time = self.current_playback_time
            self.seek_flag = True
            
            if was_playing:
                self.tocando = True
                import threading
                threading.Thread(target=self.play_thread, daemon=True).start()
                
            txt_pos = self._obter_str_compasso(self.current_playback_time)
            falar_status(f"Colado {repeats} vezes. Cursor movido para {txt_pos}.", imediato=True)
            
        dlg.Destroy()
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
    def on_ir_para_compasso(self, event):
        from mhs_utils import falar_status
        import wx
        dlg = wx.TextEntryDialog(self, "Digite o número do compasso para onde quer ir:", "Ir para compasso")
        if dlg.ShowModal() == wx.ID_OK:
            try:
                comp = int(dlg.GetValue())
                if comp < 1: comp = 1
                
                # Calcula o tempo baseado na assinatura de compasso atual
                num = 4
                for track in self.midi_file.tracks:
                    for msg in track:
                        if msg.type == 'time_signature':
                            num = msg.numerator
                            break
                
                # (Compasso - 1) * Compassos * Ticks por beat * 4 (assumindo 4 tempos por compasso como base)
                # O motor usa ticks por batida (480)
                tpb = getattr(self.midi_file, 'ticks_per_beat', 480)
                target_tick = (comp - 1) * num * tpb
                
                # Converte tick para segundos usando o tempo atual
                sec = (target_tick * float(self.current_tempo)) / (1000000.0 * tpb)
                
                self.current_playback_time = sec
                self.last_start_time = sec
                self.seek_flag = True
                falar_status(f"Indo para o compasso {comp} (tempo {sec:.2f}s)", imediato=True)
            except ValueError:
                falar_status("Número inválido!", imediato=True)
        dlg.Destroy()


    def abrir_inserir_compassos(self, event):
        if not self.midi_file: return
        from mhs_utils import falar_status
        import mido
        import threading
        import time
        
        dlg = InserirCompassosDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            self.save_state("Inserir Compassos")
            qtd, num, den = dlg.get_valores()
            
            tpb = max(1, getattr(self.midi_file, 'ticks_per_beat', 480))
            target_tick = self.get_tick_at_sec(self.current_playback_time)
            
            # Descobre a fórmula de compasso ativa no ponto atual antes de empurrar
            orig_num, orig_den = 4, 4
            for track in self.midi_file.tracks:
                t = 0
                for msg in track:
                    t += msg.time
                    if t > target_tick: break
                    if msg.type == 'time_signature':
                        orig_num = msg.numerator
                        orig_den = msg.denominator
            
            # Calcula o tamanho do bloco em ticks
            ticks_por_compasso = int((tpb * 4.0 / den) * num)
            shift_ticks = qtd * ticks_por_compasso
            
            # Varre todas as pistas empurrando os eventos
            for i, track in enumerate(self.midi_file.tracks):
                flat = []
                abs_t = 0
                for msg in track:
                    abs_t += msg.time
                    if abs_t >= target_tick:
                        flat.append([abs_t + shift_ticks, msg])
                    else:
                        flat.append([abs_t, msg])
                
                # Injeta a nova marcação de compasso na Track Mestra (Track 0)
                if i == 0:
                    ts_msg = mido.MetaMessage('time_signature', numerator=num, denominator=den, clocks_per_click=24, notated_32nd_notes_per_beat=8, time=0)
                    flat.append([target_tick, ts_msg])
                    # Restaura a fórmula anterior imediatamente no final do bloco em branco inserido
                    ts_restore = mido.MetaMessage('time_signature', numerator=orig_num, denominator=orig_den, clocks_per_click=24, notated_32nd_notes_per_beat=8, time=0)
                    flat.append([target_tick + shift_ticks, ts_restore])
                
                flat.sort(key=lambda x: x[0])
                
                new_track = mido.MidiTrack()
                last_t = 0
                for t, msg in flat:
                    delta = max(0, t - last_t)
                    new_track.append(copiar_com_tempo(msg, delta))
                    last_t = t
                self.midi_file.tracks[i] = new_track
                
            self.dirty = True
            self.atualizar_titulo()
            
            was_playing = self.tocando
            if self.tocando:
                self.tocando = False
                self.all_notes_off()
                time.sleep(0.05)
                
            self.ler_midi_memoria(reset_canais=False)
            self.seek_flag = True
            
            if was_playing:
                self.tocando = True
                threading.Thread(target=self.play_thread, daemon=True).start()
                
            falar_status(f"Inseridos {qtd} compassos de {num} por {den}.", imediato=True)
            
        dlg.Destroy()
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
    def transpor_midi_in(self, event):
        eid = event.GetId()
        from mhs_utils import falar_status
        
        if not hasattr(self, 'midi_in_octave'): self.midi_in_octave = 0
        if not hasattr(self, 'midi_in_semitone'): self.midi_in_semitone = 0
        
        if eid == 280: # Ctrl + Up
            if self.midi_in_octave < 3:
                self.midi_in_octave += 1
                falar_status(f"Oitava {self.midi_in_octave}", imediato=True)
            else:
                falar_status("Limite máximo de três oitavas atingido", imediato=True)
        elif eid == 281: # Ctrl + Down
            if self.midi_in_octave > -3:
                self.midi_in_octave -= 1
                falar_status(f"Oitava {self.midi_in_octave}", imediato=True)
            else:
                falar_status("Limite mínimo de menos três oitavas atingido", imediato=True)
        elif eid == 282: # Ctrl + Left
            if self.midi_in_semitone > -12:
                self.midi_in_semitone -= 1
                falar_status(f"Semitom {self.midi_in_semitone}", imediato=True)
            else:
                falar_status("Limite mínimo de menos doze semitons atingido", imediato=True)
        elif eid == 283: # Ctrl + Right
            if self.midi_in_semitone < 12:
                self.midi_in_semitone += 1
                falar_status(f"Semitom {self.midi_in_semitone}", imediato=True)
            else:
                falar_status("Limite máximo de doze semitons atingido", imediato=True)

    def mover_midi_tempo(self, direction, ctrl, shift, alt):
        self.foco_inteligente = None
        if not getattr(self, 'midi_file', None):
            return
            
        tpb = max(1, getattr(self.midi_file, 'ticks_per_beat', 480))
        
        # 1. Determina o tamanho do pulo por toque
        if ctrl and alt:
            ticks_pulo = 4 * tpb
        elif alt:
            ticks_pulo = tpb
        elif ctrl and shift:
            ticks_pulo = 10
        elif shift:
            ticks_pulo = 5
        else:
            ticks_pulo = 1
            
        shift_ticks = ticks_pulo * direction
        
        # ACUMULADOR VIRTUAL: Guarda na memória para não travar a digitação rápida
        if not hasattr(self, 'nudge_acumulado') or self.nudge_acumulado == 0:
            self.nudge_acumulado = 0
            if hasattr(self, 'save_state'):
                self.save_state("Arrastar Eventos")
                
        self.nudge_acumulado += shift_ticks
        
        import wx
        if hasattr(self, 'nudge_timer'):
            self.nudge_timer.Stop()
        else:
            self.nudge_timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self.finalizar_arraste_midi, self.nudge_timer)
            
        # O programa aguarda 400ms após o ÚLTIMO toque para processar tudo com precisão
        self.nudge_timer.Start(400, wx.TIMER_ONE_SHOT)

    def buscar_posicao(self, event):
        self.foco_inteligente = None
        eid = event.GetId()
        self.all_notes_off() 
        
        msg_type = ""
        novo_tempo = self.current_playback_time
        
        current_b_idx = 0
        if self.beat_events:
            for i, (b_time, is_down) in enumerate(self.beat_events):
                if b_time > self.current_playback_time + 0.005:
                    current_b_idx = max(0, i - 1)
                    break
            else:
                current_b_idx = len(self.beat_events) - 1
                
        if eid == 110: 
            idx = current_b_idx
            while idx > 0 and not self.beat_events[idx][1]:
                idx -= 1
            if idx > 0:
                idx -= 1
                while idx > 0 and not self.beat_events[idx][1]:
                    idx -= 1
            idx = max(0, idx)
            novo_tempo = self.beat_events[idx][0]
            msg_type = "compasso"
            
        elif eid == 111: 
            idx = current_b_idx + 1
            while idx < len(self.beat_events) and not self.beat_events[idx][1]:
                idx += 1
            if idx < len(self.beat_events): novo_tempo = self.beat_events[idx][0]
            msg_type = "compasso"
            
        elif eid == 112: 
            idx = current_b_idx - 1
            idx = max(0, idx)
            novo_tempo = self.beat_events[idx][0]
            msg_type = "tempo"
            
        elif eid == 113: 
            idx = min(len(self.beat_events) - 1, current_b_idx + 1)
            novo_tempo = self.beat_events[idx][0]
            msg_type = "tempo"
            
        elif eid == 114: 
            novo_tempo = 0.0
            msg_type = "inicio"
            
        elif eid == 115: 
            novo_tempo = self.total_time
            msg_type = "fim"
            
        virtual_max = getattr(self, 'virtual_total_time', self.total_time + 3600.0)
        self.current_playback_time = max(0.0, min(virtual_max, novo_tempo))
        self.last_start_time = self.current_playback_time
        self.seek_flag = True
        
        if self.gravando or self.recorded_events:
            self.gravando = False
            self.aplicar_gravacao()
        
        compasso_count = 1
        tempo_count = 1
        for i in range(len(self.beat_events)):
            b_time, is_down = self.beat_events[i]
            if is_down and i > 0:
                compasso_count += 1
                tempo_count = 1
            else:
                if i > 0: tempo_count += 1
            if b_time >= self.current_playback_time - 0.01:
                break
                
        texto = ""
        if msg_type == "compasso":
            texto = f"Compasso {compasso_count}"
        elif msg_type == "tempo":
            if tempo_count == 1: texto = f"Compasso {compasso_count}, Tempo 1"
            else: texto = f"Tempo {tempo_count}"
        elif msg_type == "inicio":
            texto = "Início, Compasso 1"
        elif msg_type == "fim":
            texto = "Fim da música"
            
        from mhs_utils import falar_status
        if texto: falar_status(texto)

        if getattr(self, 'active_event_list', None):
            wx.CallAfter(self.active_event_list.sync_to_playback_time)

    def toggle_reproducao(self, event):
        self.foco_inteligente = None
        self.esperando_nota = False
        
        if getattr(self, 'active_event_list', None):
            if self.active_event_list.needs_audio_rebuild:
                play_time = self.current_playback_time
                self.active_event_list.rebuild_final_midi()
                self.ler_midi_memoria(reset_canais=False)
                self.current_playback_time = play_time
                self.last_start_time = play_time
                self.seek_flag = True
                self.active_event_list.needs_audio_rebuild = False

        if self.tocando:
            self.tocando = False
            self.all_notes_off()
            # Parar (diferente de Pausar) é definitivo - solta o canal do
            # Áudio Guia de vez, não só congela (o all_notes_off acima já
            # pausou; aqui garantimos o stop de verdade).
            self._audio_stop()

            # --- A BLINDAGEM DO BPM ---
            if getattr(self, 'live_multiplier', 1.0) != 1.0:
                base_bpm = int(round(60000000.0 / self.current_tempo)) if self.current_tempo > 0 else 120
                novo_bpm = int(round(base_bpm * self.live_multiplier))
                import wx
                wx.CallAfter(self.change_tempo, exact=novo_bpm)
                self.live_multiplier = 1.0 # <-- Fundamental: Desliga o fator para não bugar o Play
                self.target_live_bpm = None
            
            self.current_playback_time = self.last_start_time
            self.seek_flag = True
            # Mesma ideia do toggle_pausa: parar e tocar de novo do mesmo
            # ponto (sem editar nada no meio) não precisa reconstruir o
            # estado do zero - o teclado já está certo.
            self._chase_dispensavel = (self.current_playback_time, getattr(self, '_revisao_estado', 0))

            if self.gravando or self.recorded_events:
                self.gravando = False
                self.aplicar_gravacao()
            
            if getattr(self, 'active_event_list', None):
                import wx
                wx.CallAfter(self.active_event_list.sync_to_playback_time)
        else:
            if not getattr(self, 'midi_file', None) or not getattr(self, 'output', None): 
                if not getattr(self, 'gravando', False): return
                
            if getattr(self, 'total_time', 0.0) > 0 and self.current_playback_time >= self.total_time and not getattr(self, 'gravando', False):
                self.current_playback_time = self.last_start_time
                
            self.current_playback_time = self.last_start_time
            self.tocando = True
            self.seek_flag = True
            import threading
            threading.Thread(target=self.play_thread, daemon=True).start()

    def toggle_pausa(self, event):
        self.foco_inteligente = None
        self.esperando_nota = False
        if getattr(self, 'active_event_list', None):
            if self.active_event_list.needs_audio_rebuild:
                play_time = self.current_playback_time
                self.active_event_list.rebuild_final_midi()
                self.ler_midi_memoria(reset_canais=False)
                self.current_playback_time = play_time
                self.last_start_time = play_time
                self.seek_flag = True
                self.active_event_list.needs_audio_rebuild = False

        if self.tocando:
            self.tocando = False
            # all_notes_off() (acima "tocando" já está False) pausa o
            # Áudio Guia de verdade agora (Channel.pause() - ver
            # _audio_pause) - o canal fica CONGELADO exatamente na
            # amostra em que estava, em vez de continuar tocando
            # escondido ou de perder a posição como um "stop" faria.
            self.all_notes_off()
            self.last_start_time = self.current_playback_time
            # all_notes_off só desliga nota - Bank/Patch/CC/NRPN de cada
            # canal continuam exatamente como estavam no teclado. Se
            # ninguém editar nada até o Play voltar (mesma posição, mesma
            # _revisao_estado), o play_thread pode pular o "chase" (ver lá)
            # e voltar a tocar na hora, sem os ~90ms de Drum Setup à toa.
            self._chase_dispensavel = (self.current_playback_time, getattr(self, '_revisao_estado', 0))
            if self.gravando or self.recorded_events:
                self.gravando = False
                self.aplicar_gravacao()
            if getattr(self, 'active_event_list', None):
                import wx
                wx.CallAfter(self.active_event_list.sync_to_playback_time)
        else:
            if not self.midi_file or not self.output: return
            if self.current_playback_time >= self.total_time:
                self.current_playback_time = self.last_start_time
            self.last_start_time = self.current_playback_time
            self.tocando = True
            self.seek_flag = True
            import threading
            threading.Thread(target=self.play_thread, daemon=True).start()
    def finalizar_arraste_midi(self, event):
        shift_ticks = getattr(self, 'nudge_acumulado', 0)
        if shift_ticks == 0:
            return
        self.nudge_acumulado = 0 
        
        t_start = getattr(self, 'time_selection_start', None)
        t_end = getattr(self, 'time_selection_end', None)
        has_time_sel = (t_start is not None or t_end is not None)
        
        canais_selecionados = getattr(self, 'canais_selecionados', set())
        has_chan_sel = len(canais_selecionados) > 0
        canais_alvo = canais_selecionados if has_chan_sel else {getattr(self, 'canal_atual', 0)}
        
        if t_start is not None and t_end is not None:
            tick_min = min(self.get_tick_at_sec(t_start), self.get_tick_at_sec(t_end))
            tick_max = max(self.get_tick_at_sec(t_start), self.get_tick_at_sec(t_end))
        elif t_start is not None:
            tick_min = self.get_tick_at_sec(t_start)
            tick_max = float('inf')
        elif t_end is not None:
            tick_min = 0
            tick_max = self.get_tick_at_sec(t_end)
        else:
            tick_min = 0
            tick_max = float('inf')
            
        if not has_time_sel and not has_chan_sel:
            for track in self.midi_file.tracks:
                if len(track) > 0:
                    track[0].time = max(0, track[0].time + shift_ticks)
        else:
            for i, track in enumerate(self.midi_file.tracks):
                if not any(getattr(msg, 'channel', None) in canais_alvo for msg in track):
                    continue
                    
                flat = []
                t = 0
                for msg in track:
                    t += msg.time
                    msg_ch = getattr(msg, 'channel', None)
                    if msg_ch is not None and msg_ch in canais_alvo:
                        if not has_time_sel or (tick_min <= t <= tick_max):
                            new_t = max(0, t + shift_ticks)
                        else:
                            new_t = t
                    else:
                        new_t = t
                    
                    # OTIMIZAÇÃO: Calculamos antes a prioridade
                    is_off = 0 if msg.type == 'note_off' or (msg.type == 'note_on' and getattr(msg, 'velocity', 0) == 0) else 1
                    flat.append((new_t, is_off, msg))

                # OTIMIZAÇÃO: itemgetter é mais rápido que lambda aqui
                from operator import itemgetter
                flat.sort(key=itemgetter(0, 1))

                track.clear()
                last_t = 0
                for t_ev, _, m_ev in flat:
                    m_ev.time = max(0, int(round(t_ev - last_t)))
                    track.append(m_ev)
                    last_t = t_ev
                    
        self.dirty = True
        
        was_playing = self.tocando
        if self.tocando:
            self.tocando = False
            self.all_notes_off()
            
        self.ler_midi_memoria(reset_canais=False)
        self.seek_flag = True
        self.atualizar_titulo()
        
        if was_playing:
            self.tocando = True
            import threading
            threading.Thread(target=self.play_thread, daemon=True).start()
            
        from mhs_utils import falar_status
        dir_str = "para trás" if shift_ticks < 0 else "para frente"
        ticks_totais = abs(shift_ticks)
        
        if not has_time_sel and not has_chan_sel:
            escopo_str = "no MIDI inteiro"
        elif t_start is not None and t_end is None:
            escopo_str = f"em {len(canais_alvo)} canais a partir do ponto marcado"
        elif has_time_sel and has_chan_sel:
            escopo_str = f"em {len(canais_alvo)} canais no trecho"
        elif has_time_sel:
            escopo_str = "no canal atual no trecho"
        else:
            escopo_str = f"em {len(canais_alvo)} canais"
            
        falar_status(f"Arrastado {ticks_totais} Ticks {dir_str} {escopo_str}.", imediato=True)

    # ---- Vozes (.vce): importar/exportar a voz de um canal ----
    def _campos_voz_do_canal(self, ch):
        c = self.canais[ch]
        extras = dict(c.get("VceExtras", {}))
        # Mono/Poly mora no bloco Multi Part (43 10 4C 08 nn 05): 1=Poly, 0=Mono
        extras["43104c080005"] = "01" if c.get("Mono/Poly", True) else "00"
        return {
            "Bank": c.get("Bank", 0), "Patch": c.get("Patch", 0),
            "Expression": c.get("Expression", 127), "Reverb": c.get("Reverb", 0),
            "Chorus": c.get("Chorus", 0), "Grave": c.get("Grave", 64), "Agudo": c.get("Agudo", 64),
            "PortaTime": c.get("Porta Time", 0),
            "VoiceCreator": {k: v for k, v in c.get("VoiceCreator", {}).items() if isinstance(k, int)},
            "Extras": extras,
        }

    def exportar_voz_canal(self, event=None):
        from mhs_utils import falar_status
        from mhs_vce import vce_exportar
        if not getattr(self, 'midi_file', None):
            falar_status("Nenhum projeto aberto.", imediato=True)
            return
        ch = self.canal_atual
        c = self.canais[ch]
        nome = self.instrument_names.get(c.get("Bank", 0), {}).get(c.get("Patch", 0), "") or "Voz"
        nome = re.sub(r'[\\/:*?"<>|]', "", nome.replace('PSR-SX600 ', '')).strip().replace(" ", "_")[:30] or "Voz"
        from mhs_vce import WILDCARD_SALVAR, TIPOS_VOZ, extensao_sugerida
        ext_sug = extensao_sugerida(c.get("Bank", 0))
        exts = [e for e, _ in TIPOS_VOZ]
        dlg = wx.FileDialog(self, f"Exportar voz do canal {ch + 1}", wildcard=WILDCARD_SALVAR,
                            defaultFile=nome + ext_sug, style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        dlg.SetFilterIndex(exts.index(ext_sug))
        if dlg.ShowModal() == wx.ID_OK:
            caminho = dlg.GetPath()
            if os.path.splitext(caminho)[1].lower() not in exts:
                caminho += exts[max(0, dlg.GetFilterIndex())]
            try:
                vce_exportar(self._campos_voz_do_canal(ch), caminho)
                falar_status(f"Voz do canal {ch + 1} exportada para {os.path.basename(caminho)}.", imediato=True)
            except Exception as e:
                falar_status(f"Erro ao exportar a voz: {e}", imediato=True)
        dlg.Destroy()
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())

    def importar_voz_canal(self, event=None):
        from mhs_utils import falar_status
        if not getattr(self, 'midi_file', None):
            falar_status("Nenhum projeto aberto.", imediato=True)
            return
        dlg = wx.FileDialog(self, f"Importar voz para o canal {self.canal_atual + 1}",
                            wildcard=__import__("mhs_vce").WILDCARD_ABRIR, style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            caminho = dlg.GetPath()
            dlg.Destroy()
            self.importar_voz_de_arquivo(self.canal_atual, caminho)
        else:
            dlg.Destroy()
        wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())

    def importar_voz_de_arquivo(self, ch, caminho):
        from mhs_utils import falar_status
        from mhs_vce import vce_ler
        try:
            d = vce_ler(caminho)
        except Exception as e:
            falar_status(f"Não consegui ler esse arquivo de voz: {e}", imediato=True)
            return False
        self.save_state(f"Importar Voz no Canal {ch + 1}")
        c = self.canais[ch]
        for p in ("Bank", "Patch", "Expression", "Reverb", "Chorus", "Grave", "Agudo"):
            if p in d:
                c[p] = d[p]
        c["Porta Time"] = d.get("PortaTime", 0)
        c["VoiceCreator"] = {k: v for k, v in d.get("VoiceCreator", {}).items() if isinstance(k, int)}
        extras = dict(d.get("Extras", {}))
        mono = extras.pop("43104c080005", None)
        if mono is not None:
            c["Mono/Poly"] = (mono == "01")
        c["VceExtras"] = extras
        # Ao vivo: timbre, mixagem e Voice Creator no teclado
        for p in ("Bank", "Patch", "Volume", "Pan", "Expression", "Reverb", "Chorus", "Grave", "Agudo", "Mono/Poly", "Porta Time"):
            if p in c:
                self.overrides.setdefault(ch, {})[p] = c[p]
                self.enviar_midi_param(p, c[p], canal=ch)
        self._enviar_voice_creator_ao_vivo(ch, c["VoiceCreator"])
        # Grava no projeto (SysEx do Voice Creator) e recarrega
        self.consolidar_projeto()
        self.dirty = True
        self.atualizar_titulo()
        was_playing = self.tocando
        if self.tocando:
            self.tocando = False
            self.all_notes_off()
            time.sleep(0.05)
        self.ler_midi_memoria(reset_canais=False)
        self.seek_flag = True
        if was_playing:
            self.tocando = True
            threading.Thread(target=self.play_thread, daemon=True).start()
        nome = self.instrument_names.get(c["Bank"], {}).get(c["Patch"], f"Patch {c['Patch']}").replace('PSR-SX600 ', '')
        falar_status(f"Voz {os.path.basename(caminho)} importada no canal {ch + 1}: {nome}.", imediato=True)
        return True

    def _enviar_voice_creator_ao_vivo(self, ch, vc):
        porta = getattr(self, 'output', None)
        if not porta:
            return
        from mhs_utils import detune_separar
        try:
            for a, v in vc.items():
                if not isinstance(a, int):
                    continue
                if a == 0x09:
                    alto, baixo = detune_separar(v)
                    porta.send(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x08, ch, 0x09, alto)))
                    porta.send(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x08, ch, 0x0A, baixo)))
                elif a in (0x01, 0x02, 0x03):
                    porta.send(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x0A, ch, a, v)))
                else:
                    porta.send(mido.Message('sysex', data=(0x43, 0x10, 0x4C, 0x08, ch, a, v)))
        except Exception:
            pass

    def abrir_clonar_config(self, event):
        import wx
        from mhs_utils import falar_status
        if not getattr(self, 'midi_file', None):
            falar_status("Nenhum projeto aberto.", imediato=True)
            return
            
        try:
            from mhs_dialogs import ClonarConfigCanalDialog
            dlg = ClonarConfigCanalDialog(self, self.canal_atual)
            if dlg.ShowModal() == wx.ID_OK:
                ch_alvo = dlg.get_canal_alvo()
                if ch_alvo == self.canal_atual:
                    falar_status("O canal de destino é o mesmo de origem.", imediato=True)
                    dlg.Destroy()
                    return
                
                self.save_state(f"Clonar config. do C{self.canal_atual+1} para C{ch_alvo+1}")
                
                source = self.canais[self.canal_atual]
                target = self.canais[ch_alvo]
                
                import copy
                props_to_copy = [
                    "Volume", "Pan", "Expression", "Reverb", "Chorus",
                    "Grave", "Agudo", "Bank", "Patch", "Pitch Bend",
                    "Mono/Poly", "Porta Time", "DrumParams",
                    "CustomDrumMap", "DrumParamsNRPN", "VoiceCreator"
                ]
                
                # Copia profundamente todos os dicionários e valores do canal
                for p in props_to_copy:
                    if p in source:
                        if isinstance(source[p], (dict, list)):
                            target[p] = copy.deepcopy(source[p])
                        else:
                            target[p] = source[p]
                
                # Sincroniza a tela e envia pro Sintetizador em tempo real
                for p in ["Bank", "Patch", "Volume", "Pan", "Expression", "Reverb", "Chorus", "Grave", "Agudo", "Pitch Bend", "Mono/Poly", "Porta Time"]:
                    if p in target:
                        if ch_alvo not in self.overrides:
                            self.overrides[ch_alvo] = {}
                        self.overrides[ch_alvo][p] = target[p]
                        self.enviar_midi_param(p, target[p], canal=ch_alvo)
                
                # A mágica: Grava os SysEx clonados (DrumMap e VoiceCreator) direto na trilha física
                self.consolidar_projeto()
                self.dirty = True
                self.atualizar_titulo()
                
                was_playing = self.tocando
                if self.tocando:
                    self.tocando = False
                    self.all_notes_off()
                    import time
                    time.sleep(0.05)
                
                self.ler_midi_memoria(reset_canais=False)
                self.seek_flag = True
                
                if was_playing:
                    self.tocando = True
                    import threading
                    threading.Thread(target=self.play_thread, daemon=True).start()

                falar_status(f"Configurações clonadas para o canal {ch_alvo + 1}", imediato=True)
            dlg.Destroy()
            wx.CallLater(100, lambda: getattr(self, 'panel', None) and self.panel.SetFocus())
        except Exception as e:
            falar_status(f"Erro ao abrir clonagem: {e}", imediato=True)
if __name__ == '__main__':
    app = wx.App()
    # sys.argv[1] = caminho do arquivo, quando o Windows chama o programa
    # por associação de extensão (duplo clique / "Abrir com").
    arquivo_inicial = sys.argv[1] if len(sys.argv) > 1 else None
    frame = MidiSequencer(None, f"MHS MIDI Sequencer {VERSAO_APP}", arquivo_inicial)
    frame.Show()
    # Tela de Changelog, só na primeira vez que uma versão nova é aberta.
    wx.CallAfter(frame.mostrar_changelog_se_necessario)
    # Checagem de atualização (opcional, ver aba "Atualizações" em
    # Preferências) - roda em thread e não atrasa a abertura da janela.
    wx.CallAfter(frame.verificar_atualizacoes_ao_iniciar)
    app.MainLoop()