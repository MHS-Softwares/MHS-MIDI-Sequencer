import wx
import mido
import threading
import queue
import sys
import os
import re

# --- ONDE O PROGRAMA REALMENTE ESTÁ (não onde o Windows "achou" que
# devia rodar) ---
# Sem isso, um caminho relativo tipo "config.json" é procurado a partir
# do DIRETÓRIO DE TRABALHO ATUAL - que o Windows define como a pasta do
# ARQUIVO clicado (não a pasta do programa!) quando o .exe é aberto por
# associação de extensão/"Abrir com" a partir de outra pasta. Resultado:
# abrir um .mid de fora da pasta de instalação "achava" que não tinha
# config.json nenhum e tocava com tudo zerado. Ancorando em sys.executable
# (build compilado) ou no próprio arquivo .py (rodando do código-fonte),
# o caminho fica sempre o mesmo, não importa de onde o Windows lançou o
# programa.
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def achar_porta_certa(nome_salvo, portas_disponiveis):
    # O Windows troca a numeração final de uma porta MIDI a cada logon/
    # reconexão (ex: "Digital Keyboard-1 4" vira "Digital Keyboard-1 5"
    # ou "Digital Keyboard-1 1") - sem isso, o nome salvo deixa de bater
    # com nenhuma porta disponível.
    #
    # IMPORTANTE: o "-1"/"-2" faz parte da IDENTIDADE da porta (o Michel
    # tem duas portas reais do mesmo teclado - "Digital Keyboard-1" pra
    # entrada/saída principal e "Digital Keyboard-2" pro metrônomo, numa
    # porta física separada) - só o número final (depois de um espaço) é
    # que o Windows reatribui a cada boot. Uma versão anterior desta
    # função removia TUDO que fosse traço/espaço/dígito do final
    # (`r'[-\s\d]+$'`), o que colapsava "Digital Keyboard-1 5" E "Digital
    # Keyboard-2 6" pro MESMO nome-base "Digital Keyboard" - aí então a
    # correspondência virava sorte (pegava a PRIMEIRA porta da lista com
    # esse nome-base, não necessariamente a certa) - era exatamente por
    # isso que o metrônomo (porta -2) às vezes "roubava" a porta -1
    # (principal) depois de uma reconexão. Agora só o número final
    # (espaço + dígitos) é removido - o "-1"/"-2" nunca é tocado.
    if not nome_salvo: return None
    # 1. Tenta o nome exato primeiro
    if nome_salvo in portas_disponiveis: return nome_salvo

    # 2. A inteligência: remove só o número final que o Windows reatribui
    # a cada boot (ex: "Digital Keyboard-1 2" vira "Digital Keyboard-1")
    base_salva = re.sub(r'\s+\d+$', '', str(nome_salvo)).strip()
    if not base_salva: base_salva = str(nome_salvo)  # Fallback

    for p in portas_disponiveis:
        base_p = re.sub(r'\s+\d+$', '', p).strip()
        if base_salva == base_p:
            return p

    # 3. Último recurso: vê se a base salva faz parte de algum nome na lista
    for p in portas_disponiveis:
        if base_salva in p or p in base_salva:
            return p
    return None

# --- MOTOR DE VOZ ASSINCRONO ---
try:
    from accessible_output2.outputs.auto import Auto
    speaker_obj = Auto()
    speaker_active = True
except Exception as e:
    print(f"Erro ao carregar accessible_output2: {e}")
    speaker_active = False

fila_de_voz = queue.Queue()

def _trabalhador_de_voz():
    while True:
        item = fila_de_voz.get()
        if item is None:
            break
        texto, interrupt = item
        try:
            speaker_obj.output(texto, interrupt)
        except:
            pass
        fila_de_voz.task_done()

if speaker_active:
    thread_voz = threading.Thread(target=_trabalhador_de_voz, daemon=True)
    thread_voz.start()

def falar(texto, imediato=False, interromper=False):
    interrupt_flag = imediato or interromper
    if speaker_active:
        if interrupt_flag:
            with fila_de_voz.mutex:
                fila_de_voz.queue.clear()
        fila_de_voz.put((texto, interrupt_flag))

falar_status = falar
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# --- UTILITÁRIOS: CONVERSORES DE NOMES MIDI ---
def get_nome_nota(nota_num):
    notas = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    oitava = (nota_num // 12) - 1
    nome = notas[nota_num % 12]
    return f"{nome}{oitava}"

CC_NAMES = {
    0: "Bank Select MSB", 1: "Modulation", 2: "Breath Controller", 4: "Foot Controller",
    5: "Portamento Time", 6: "Data Entry MSB", 7: "Volume", 8: "Balance", 10: "Pan",
    11: "Expression", 32: "Bank Select LSB", 64: "Sustain", 65: "Portamento Switch",
    66: "Sostenuto", 67: "Soft Pedal", 68: "Legato Switch", 71: "Resonance",
    72: "Release Time", 73: "Attack Time", 74: "Cutoff", 84: "Portamento Control",
    91: "Reverb", 92: "Tremolo", 93: "Chorus", 94: "Celeste / Detune", 95: "Phaser",
    120: "All Sound Off", 121: "Reset All Controllers", 123: "All Notes Off"
}

def get_cc_name(cc_num):
    return CC_NAMES.get(cc_num, f"CC {cc_num}")

# NRPN por peça de bateria (canal com voz de bateria) - conferido contra o
# Data List oficial do PSR-SX600 (MIDI Data Format, tabela NRPN, endereços
# 14H-35H) e batido byte a byte com anotações reais do Michel de 2011 (feitas
# no Event List do Sonar): os 9 parâmetros que ele anotou (2560=Abafar,
# 2688=Efeito, 2816=Ataque, 2944=Sustentação, 3072=Afinação, 3200=Afinação
# leve, 3328=Volume, 3584=Pan, 3712=Reverb - cada um é MSB*128, LSB=0) batem
# exatamente com 20,21,22,23,24,25,26,28,29 abaixo - inclusive o "buraco" no
# 27 (não existe: depois do Level em 26 pula direto pro Pan em 28), que
# intrigava as contas dele. A versão anterior deste dicionário (nunca usada
# em lugar nenhum do código - import morto) tinha esses valores errados a
# partir do 26 e inventava "Key Assign"/"Rx Note Off"/"Rx Note On" que não
# existem nesta tabela.
NRPN_MSB_NAMES = {
    0x14: "Drum Low Pass Filter Cutoff Frequency", 0x15: "Drum Low Pass Filter Resonance",
    0x16: "Drum EG Attack Rate", 0x17: "Drum EG Decay Rate",
    0x18: "Drum Pitch Coarse", 0x19: "Drum Pitch Fine", 0x1A: "Drum Level",
    0x1C: "Drum Pan", 0x1D: "Drum Reverb Send Level", 0x1E: "Drum Chorus Send Level",
    0x1F: "Drum Variation Send Level", 0x30: "Drum EQ Bass Gain", 0x31: "Drum EQ Treble Gain",
    0x34: "Drum EQ Bass Frequency", 0x35: "Drum EQ Treble Frequency",
}

# --- VOICE CREATOR: Detune (Multi Part, endereços 0x09/0x0A) ---
# Conferido no Data List oficial do PSR-SX600 (MIDI Parameter Change table,
# MULTI PART, pág. 65): ao contrário de quase todo outro parâmetro do Multi
# Part (1 byte, 0x00-0x7F), o DETUNE é um valor ÚNICO de 2 bytes - cada byte
# só usa o NIBBLE baixo (0x00-0x0F), formando um valor combinado de 8 bits
# (0-255) que mapeia -12.8...0...+12.7 Hz (128 = 0.0 Hz, o centro/padrão de
# fábrica - bate com o default oficial "08 00": (0x08<<4)|0x00 = 128). Os
# dois programas guardam esse valor JÁ COMBINADO no dicionário VoiceCreator,
# sempre na chave 0x09 (0x0A nunca vira uma entrada própria) - estas duas
# funções convertem pra frente e pra trás na hora de mandar/receber a SysEx
# de verdade (que continua sendo 2 mensagens físicas, uma por endereço).
def detune_combinar(nibble_alto, nibble_baixo):
    return ((int(nibble_alto) & 0x0F) << 4) | (int(nibble_baixo) & 0x0F)


def detune_separar(valor_combinado):
    v = max(0, min(255, int(valor_combinado)))
    return (v >> 4) & 0x0F, v & 0x0F


# Mesma tabela acima, mas pronta pra Guia 3 do Drum Setup: rótulo em
# português com o atalho Alt+letra embutido (padrão dos outros parâmetros de
# DSP deste programa) e a faixa real de cada um. Ao contrário da Guia 1 (SysEx
# `43 1n 4C <nota> <endereço> <valor>`, exclusiva Yamaha), isto é NRPN puro -
# `control_change 99=MSB(parâmetro) / 98=LSB(nota) / 6=valor` - protocolo
# comum a qualquer sintetizador XG/GS, e o CANAL já vem no próprio CC (não
# precisa de "part_byte" por canal como a SysEx precisa). Ordem igual à da
# Guia 1 (`sysex_params` abaixo) - só pulando os 3 que não têm equivalente em
# NRPN (Decay 2, Agrupamento/Alt Group, Key Assign). Atalhos (Alt+letra)
# escolhidos pra bater EXATAMENTE com o mesmo parâmetro da Guia 1 - o Michel
# achou os atalhos "bem diferentões" entre as duas guias e pediu pra
# igualar; a letra é sempre a mesma nas duas, só a posição do & no texto
# muda pra caber na palavra certa de cada rótulo.
DRUM_NRPN_PARAMS = [
    (0x1A, "&Volume (Level)", 0, 127),
    (0x1C, "&Pan (0 = Aleatório/RND)", 0, 127),
    (0x1D, "R&everb Send", 0, 127),
    (0x1E, "C&horus Send", 0, 127),
    (0x1F, "Var&iation Send", 0, 127),
    (0x14, "Abafar (C&utoff do Filtro - quanto menor, mais abafado)", 0, 127),
    (0x15, "Efeito (Re&ssonância do Filtro)", 0, 127),
    (0x16, "&Ataque (EG Attack Rate)", 0, 127),
    (0x17, "Sustentação (&Decay - EG Decay Rate)", 0, 127),
    (0x18, "Afinação Grossa (Pitch C&oarse)", 0, 127),
    (0x19, "Afinação Leve (Pitch &Fine)", 0, 127),
    (0x30, "E&Q Grave (Bass Gain)", 0, 127),
    (0x31, "EQ Agudo (&Treble Gain)", 0, 127),
    (0x34, "Frequência do Grave (EQ &Bass Freq)", 4, 40),
    (0x35, "Frequência do Agudo (EQ Treb&le Freq)", 28, 58),
]
# Padrão de fábrica por parâmetro - os "-64...0...+63" (centrados) começam em
# 64; Volume começa cheio (127); Reverb/Chorus/Variation começam em 0 (sem
# envio, igual ao resto do programa); as 2 frequências de EQ têm faixa
# própria (conferido no Data List: 0x34=0x0C, 0x35=0x36).
DRUM_NRPN_DEFAULTS = {
    0x14: 64, 0x15: 64, 0x16: 64, 0x17: 64, 0x18: 64, 0x19: 64,
    0x1A: 127, 0x1C: 64, 0x1D: 0, 0x1E: 0, 0x1F: 0,
    0x30: 64, 0x31: 64, 0x34: 12, 0x35: 54,
}
DRUM_NRPN_MSBS = frozenset(p[0] for p in DRUM_NRPN_PARAMS)

GM_DRUM_MAP = {
    35: "Acoustic Bass Drum (Bumbo acústico)", 36: "Bass Drum 1 (Bumbo 1)", 37: "Side Stick (Aro da Caixa)", 
    38: "Acoustic Snare (Caixa acústica)", 39: "Hand Clap (Palmas)", 40: "Electric Snare (Caixa Eletrônica)", 
    41: "Low Floor Tom (Surdo grave)", 42: "Closed Hi Hat (Chimbal fechado)", 43: "High Floor Tom (Surdo agudo)", 
    44: "Pedal Hi-Hat (Chimbal com pedal)", 45: "Low Tom (Tom grave)", 46: "Open Hi-Hat (Chimbal aberto)",
    47: "Low-Mid Tom (Tom médio grave)", 48: "Hi-Mid Tom (Tom médio agudo)", 49: "Crash Cymbal 1 (Prato de ataque 1)", 
    50: "High Tom (Tom agudo)", 51: "Ride Cymbal 1 (Prato de condução 1)", 52: "Chinese Cymbal (Prato chinês)", 
    53: "Ride Bell (Cúpula do prato)", 54: "Tambourine (Pandeirola)", 55: "Splash Cymbal (Prato splash)", 
    56: "Cowbell (Caneca)", 57: "Crash Cymbal 2 (Prato de ataque 2)", 58: "Vibraslap",
    59: "Ride Cymbal 2 (Prato de condução 2)", 60: "Hi Bongo (Bongô agudo)", 61: "Low Bongo (Bongô grave)", 
    62: "Mute Hi Conga (Conga aguda muda)", 63: "Open Hi Conga (Conga aguda aberta)", 64: "Low Conga (Conga grave)", 
    65: "High Timbale (Timbales agudo)", 66: "Low Timbale (Timbales grave)", 67: "High Agogo (Agogô agudo)", 
    68: "Low Agogo (Agogô grave)", 69: "Cabasa (Cabaça)", 70: "Maracas",
    71: "Short Whistle (Apito curto)", 72: "Long Whistle (Apito longo)", 73: "Short Guiro (Reco-reco curto)", 
    74: "Long Guiro (Reco-reco longo)", 75: "Claves", 76: "Hi Wood Block (Bloco sonoro agudo)", 
    77: "Low Wood Block (Bloco sonoro grave)", 78: "Mute Cuica (Cuíca muda)", 79: "Open Cuica (Cuíca aberta)", 
    80: "Mute Triangle (Triângulo mudo)", 81: "Open Triangle (Triângulo aberto)"
}

def get_drum_name(note):
    return GM_DRUM_MAP.get(note, f"Peça não mapeada ({note})")

# --- LÓGICA DE ACORDES E CASM ---
CHORD_MAP = {
    (0, 4, 7): ("", 0), (0, 3, 7): ("m", 1), (0, 4, 7, 10): ("7", 2),
    (0, 3, 7, 10): ("m7", 3), (0, 4, 7, 11): ("maj7", 4), (0, 3, 6): ("dim", 5),
    (0, 3, 6, 9): ("dim7", 5), (0, 4, 8): ("aug", 6), (0, 7): ("5", 0),
    (0, 5, 7): ("sus4", 7), (0, 2, 7): ("sus2", 8), (0, 3, 7, 11): ("mM7", 9),
    (0, 3, 6, 10): ("m7b5", 10), (0, 4): ("", 0), (0, 3): ("m", 1),
}

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

YAMAHA_SECTION_ORDER = [
    "Intro A", "Intro B", "Intro C", "Main A", "Main B", "Main C", "Main D",
    "Fill In AA", "Fill In BB", "Fill In CC", "Fill In DD", "Fill In BA",
    "Ending A", "Ending B", "Ending C"
]

def identify_chord(notes):
    if not notes: return None, 0, 0
    unique_notes = sorted(list(set([n % 12 for n in notes])))
    for i in range(len(unique_notes)):
        root_candidate = unique_notes[i]
        intervals = tuple(sorted([(n - root_candidate) % 12 for n in unique_notes]))
        if intervals in CHORD_MAP:
            name_suffix, chord_type = CHORD_MAP[intervals]
            return f"{NOTE_NAMES[root_candidate]}{name_suffix}", root_candidate, chord_type
    first_root = unique_notes[0]
    return f"{NOTE_NAMES[first_root]}?", first_root, 0

def apply_ntt(note, chord_type, root_note, casm_rule):
    play_type = casm_rule.get('play_type', 'trans').lower()
    ntt_type = casm_rule.get('ntt_type', 'chord').lower()
    if ntt_type == 'bypass': return note
    pitch = note % 12
    octave = (note // 12) * 12
    mpc = pitch 
    if pitch == 4:
        if chord_type in [1, 3, 5, 9, 10]: mpc = 3      
        elif chord_type == 7: mpc = 5                   
        elif chord_type == 8: mpc = 2                   
    elif pitch == 7: 
        if chord_type in [5, 10]: mpc = 6               
        elif chord_type == 6: mpc = 8                   
    elif pitch == 11: 
        if chord_type in [0, 1, 6, 7, 8]: mpc = 0       
        elif chord_type in [2, 3, 10]: mpc = 10         
        elif chord_type == 5: mpc = 9                   
        elif chord_type in [4, 9]: mpc = 11             
    elif pitch == 9:
        if chord_type in [5, 1, 3, 10]: mpc = 8         

    if play_type == 'fixed' or ntt_type == 'chord':
        target_abs_pc = (mpc + root_note) % 12
        target_notes = [target_abs_pc + oct * 12 for oct in range(11)]
        valid_notes = [n for n in target_notes if 0 <= n <= 127]
        final_note = min(valid_notes, key=lambda x: abs(x - note))
    else:
        shift = root_note
        if shift > casm_rule.get('high_key', 6): shift -= 12
        final_note = octave + mpc + shift

    low_limit = casm_rule.get('note_limit_low', 0)
    high_limit = casm_rule.get('note_limit_high', 127)
    while final_note > high_limit: final_note -= 12
    while final_note < low_limit: final_note += 12
    return max(0, min(127, final_note))

# --- DSP GLOBAL (Reverb/Chorus) e DSP VARIATION/INSERTION ---
# Dados conferidos contra o Data List oficial do PSR-SX600 (o mesmo bloco de
# Effect XG vale pra toda a família Yamaha) e sincronizados com o MHS Style
# Creator - a lista de efeitos antiga tinha 10 famílias fabricadas (MSB
# 20/24/25/36/43/44/48/49/50/51) que não existem de verdade no protocolo;
# os nomes que elas usavam ("Chorus 1", "Celeste 1" etc.) são, na real,
# apenas PRESETS (LSB) dentro das famílias abaixo.
REV_MSB_LIST = [
    ("00 - Nenhum", 0), ("01 - Hall", 1), ("02 - Room", 2),
    ("03 - Stage", 3), ("04 - Plate", 4), ("16 - White Room", 16),
    ("17 - Tunnel", 17), ("18 - Canyon", 18), ("19 - Basement", 19)
]
CHO_MSB_LIST = [
    ("00 - Nenhum", 0), ("65 - Chorus", 65), ("66 - Celeste", 66),
    ("67 - Flanger", 67), ("68 - Symphonic", 68), ("69 - Rotary", 69)
]
VARIATION_EFEITOS_LIST = [
    ("00 - Bypass (Sem Efeito)", 0), ("01 - Reverb Hall", 1), ("02 - Reverb Room", 2),
    ("03 - Reverb Stage", 3), ("04 - Reverb Plate", 4), ("05 - Delay L,C,R", 5),
    ("06 - Delay L,R", 6), ("07 - Echo", 7), ("08 - Cross Delay", 8),
    ("09 - Early Reflection", 9), ("10 - Gate Reverb", 10),
    ("65 - Chorus", 65), ("66 - Celeste", 66), ("67 - Flanger", 67), ("68 - Symphonic", 68),
    ("69 - Rotary Speaker", 69), ("70 - Tremolo", 70), ("71 - Auto Pan", 71),
    ("72 - Phaser", 72), ("73 - Distortion", 73), ("74 - Overdrive", 74),
    ("75 - Amp Simulator", 75), ("76 - 3-Band EQ", 76), ("77 - 2-Band EQ", 77),
    ("78 - Auto Wah 2", 78), ("79 - Tempo Auto Wah", 79), ("80 - Pitch Change", 80),
    ("81 - Harmonic Enhancer", 81), ("82 - Touch Wah", 82), ("83 - Compressor", 83),
    ("84 - Noise Gate", 84), ("85 - Voice Cancel", 85), ("86 - 2-Way Rotary Speaker", 86),
    ("87 - Ensemble Detune", 87), ("88 - Ambience", 88), ("93 - Talking Modulation", 93),
    ("94 - Lo-Fi", 94), ("95 - Multi FX", 95),
    ("96 - Small Stereo Dist", 96), ("97 - British Combo", 97),
    ("98 - V Distortion", 98), ("99 - Dual Rotary Speaker", 99),
    ("100 - Distortion + Tempo Delay", 100), ("101 - Comp/Dist + Tempo Delay", 101),
    ("102 - Wah/Dist + Tempo Delay", 102), ("103 - V Distortion + Tempo Delay", 103),
    ("104 - V Flanger", 104), ("105 - Multi Band Comp", 105),
    ("107 - Tempo Flanger", 107), ("108 - Tempo Phaser", 108),
    ("109 - Dynamic Filter", 109), ("110 - Dynamic Flanger", 110),
    ("111 - Dynamic Phaser", 111), ("112 - Dynamic Ring Mod", 112),
    ("113 - Ring Modulator", 113), ("115 - Isolator", 115),
    ("119 - Vibe Rotor", 119), ("120 - Tempo Tremolo", 120),
    ("121 - Tempo Auto Pan", 121), ("122 - Pedal Wah", 122)
]
# Nome de cada parâmetro (No.1..No.16 do Data List) por MSB do efeito. Gerado
# do Effect Parameter List oficial do PSR-SX600 (Data List, páginas 35-45),
# via o mapa MSB->tabela do Effect Type List (páginas 29-34). O índice 9 (a
# 10ª posição) é sempre o Dry/Wet e os editores já tratam ele à parte no campo
# "Return / Dry-Wet". A versão anterior tinha vários nomes deslocados 1 casa
# (o "No.5"/"No.6" vazio de várias famílias não estava contado), então um
# slider "EQ Mid Gain" mexia na verdade na frequência do médio, etc.
DSP_PARAM_NAMES = {
    1: ['Reverb Time', 'Diffusion', 'Initial Delay Time', 'HPF Cutoff', 'LPF Cutoff', '-', '-', '-', '-', 'Dry/Wet Balance', 'Reverb Delay Time', 'Density', 'ER/Reverb Balance', 'High Damp', 'Feedback Level'],
    2: ['Reverb Time', 'Diffusion', 'Initial Delay Time', 'HPF Cutoff', 'LPF Cutoff', '-', '-', '-', '-', 'Dry/Wet Balance', 'Reverb Delay Time', 'Density', 'ER/Reverb Balance', 'High Damp', 'Feedback Level'],
    3: ['Reverb Time', 'Diffusion', 'Initial Delay Time', 'HPF Cutoff', 'LPF Cutoff', '-', '-', '-', '-', 'Dry/Wet Balance', 'Reverb Delay Time', 'Density', 'ER/Reverb Balance', 'High Damp', 'Feedback Level'],
    4: ['Reverb Time', 'Diffusion', 'Initial Delay Time', 'HPF Cutoff', 'LPF Cutoff', '-', '-', '-', '-', 'Dry/Wet Balance', 'Reverb Delay Time', 'Density', 'ER/Reverb Balance', 'High Damp', 'Feedback Level'],
    5: ['Lch Delay Time', 'Rch Delay Time', 'Cch Delay Time', 'Feedback Delay Time', 'Feedback Level', 'Cch Level', 'Feedback High Damp', '-', '-', 'Dry/Wet Balance', '-', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain'],
    6: ['Lch Delay Time', 'Rch Delay Time', 'Feedback Delay 1 Time', 'Feedback Delay 2 Time', 'Feedback Level', 'Feedback High Damp', '-', '-', '-', 'Dry/Wet Balance', '-', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain'],
    7: ['Lch Delay 1 Time', 'Lch Feedback Level', 'Rch Delay 1 Time', 'Rch Feedback Level', 'Feedback High Damp', 'Lch Delay 2 Time', 'Rch Delay 2 Time', 'Delay 2 Level', '-', 'Dry/Wet Balance', '-', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain'],
    8: ['L->R Delay Time', 'R->L Delay Time', 'Feedback Level', 'Input Select', 'Feedback High Damp', '-', '-', '-', '-', 'Dry/Wet Balance', '-', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain'],
    9: ['Type', 'Room Size', 'Diffusion', 'Initial Delay Time', 'Feedback Level', 'HPF Cutoff', 'LPF Cutoff', '-', '-', 'Dry/Wet Balance', 'Liveness', 'Density', 'High Damp'],
    10: ['Type', 'Room Size', 'Diffusion', 'Initial Delay Time', 'Feedback Level', 'HPF Cutoff', 'LPF Cutoff', '-', '-', 'Dry/Wet Balance', 'Liveness', 'Density', 'High Damp'],
    65: ['LFO Freq', 'LFO Depth', 'Feedback Level', 'Delay Offset', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain', 'Dry/Wet Balance', 'EQ Mid Freq', 'EQ Mid Gain', 'EQ Mid Width', '-', 'Input Mode'],
    66: ['LFO Freq', 'LFO Depth', 'Feedback Level', 'Delay Offset', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain', 'Dry/Wet Balance', 'EQ Mid Freq', 'EQ Mid Gain', 'EQ Mid Width', '-', 'Input Mode'],
    67: ['LFO Freq', 'LFO Depth', 'Feedback Level', 'Delay Offset', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain', 'Dry/Wet Balance', 'EQ Mid Freq', 'EQ Mid Gain', 'EQ Mid Width', 'LFO Phase Difference'],
    68: ['LFO Freq', 'LFO Depth', 'Delay Offset', '-', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain', 'Dry/Wet Balance', 'EQ Mid Freq', 'EQ Mid Gain', 'EQ Mid Width'],
    69: ['LFO Freq', 'LFO Depth', '-', '-', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain', 'Dry/Wet Balance', 'EQ Mid Freq', 'EQ Mid Gain', 'EQ Mid Width'],
    70: ['LFO Freq', 'AM Depth', 'PM Depth', '-', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain', '-', 'EQ Mid Freq', 'EQ Mid Gain', 'EQ Mid Width', 'LFO Phase Difference', 'Input Mode'],
    71: ['LFO Freq', 'L/R Depth', 'F/R Depth', 'Pan Direction', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain', '-', 'EQ Mid Freq', 'EQ Mid Gain', 'EQ Mid Width'],
    72: ['LFO Freq', 'LFO Depth', 'Phase Shift Offset', 'Feedback Level', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain', 'Dry/Wet Balance', 'Stage', 'Diffusion'],
    73: ['Drive', 'EQ Low Freq', 'EQ Low Gain', 'LPF Cutoff', 'Output Level', '-', 'EQ Mid Freq', 'EQ Mid Gain', 'EQ Mid Width', 'Dry/Wet Balance', 'Edge (Clip Curve)'],
    74: ['Drive', 'EQ Low Freq', 'EQ Low Gain', 'LPF Cutoff', 'Output Level', '-', 'EQ Mid Freq', 'EQ Mid Gain', 'EQ Mid Width', 'Dry/Wet Balance', 'Edge (Clip Curve)'],
    75: ['Drive', 'Amp Type', 'LPF Cutoff', 'Output Level', '-', '-', '-', '-', '-', 'Dry/Wet Balance', 'Edge (Clip Curve)'],
    76: ['EQ Low Gain', 'EQ Mid Freq', 'EQ Mid Gain', 'EQ Mid Width', 'EQ High Gain', 'EQ Low Freq', 'EQ High Freq', '-', '-', '-', '-', '-', '-', '-', 'Input Mode'],
    77: ['EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain'],
    78: ['LFO Freq', 'LFO Depth', 'Cutoff Freq Offset', 'Resonance', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain', 'Dry/Wet Balance', 'Drive'],
    79: ['LFO Freq', 'LFO Depth', 'Cutoff Freq Offset', 'Resonance', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain', 'Dry/Wet Balance', 'Drive'],
    80: ['Pitch', 'Initial Delay Time', 'Fine 1', 'Fine 2', 'Feedback Level', '-', '-', '-', '-', 'Dry/Wet Balance', 'Pan 1', 'Output Level 1', 'Pan 2', 'Output Level 2'],
    81: ['HPF Cutoff', 'Drive', 'Mix Level'],
    82: ['Sensitivity', 'Cutoff Freq Offset', 'Resonance', '-', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain', 'Dry/Wet Balance', 'Drive'],
    83: ['Attack', 'Release', 'Threshold', 'Ratio', 'Output Level'],
    84: ['Attack', 'Release', 'Threshold', 'Output Level'],
    85: ['-', '-', '-', '-', '-', '-', '-', '-', '-', '-', 'Low Adjust', 'High Adjust'],
    86: ['Rotor Speed', 'Drive Low', 'Drive High', 'Low/High Balance', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain', '-', 'Crossover Freq', 'Mic L-R Angle'],
    87: ['Detune', 'Lch Initial Delay', 'Rch Initial Delay', '-', '-', '-', '-', '-', '-', 'Dry/Wet Balance', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain'],
    88: ['Delay Time', 'Output Phase', '-', '-', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain', 'Dry/Wet Balance'],
    93: ['Vowel', 'Move Speed', 'Drive', 'Output Level'],
    94: ['Sampling Freq', 'Word Length', 'Output Gain', 'LPF Cutoff', 'Filter Type', 'LPF Resonance', 'Bit Assign', 'Emphasis', '-', 'Dry/Wet Balance', '-', '-', '-', '-', 'Input Mode'],
    95: ['Comp Sustain', 'Wah SW', 'Wah Pedal', 'Dist SW', 'Dist Drive', 'Dist EQ', 'Dist Tone', 'Dist Presence', 'Output', '-', 'Speaker Type', 'LFO Speed', 'Phaser SW', 'Delay SW', 'Delay Ctrl', 'Delay Time'],
    96: ['Comp SW', 'Comp Sustain', 'Comp Level', 'Dist Type', 'Dist Drive', 'Dist EQ', 'Dist Tone', 'Dist Presence', 'Output', '-', 'Speaker Type'],
    97: ['Mode', 'Normal', 'Brilliant', 'Bass', '-', 'Treble', 'Cut', '-', 'Output', '-', 'Speaker Type', 'Speaker Air', 'Mic Position'],
    98: ['Overdrive', 'Device', 'Speaker Type', 'Presence', 'Output Level', '-', '-', '-', '-', 'Dry/Wet Balance'],
    99: ['Woofer Speed Slow', 'Horn Speed Slow', 'Woofer Speed Fast', 'Horn Speed Fast', 'Slow-Fast Time Woofer', 'Slow-Fast Time Horn', 'Drive Low', 'Drive High', 'Low/High Balance', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain', 'Mic L-R Angle', 'Speed Control'],
    100: ['Delay Time', 'Delay Feedback Level', 'Delay Mix', 'Dist Drive', 'Dist Output Level', 'Dist EQ Low Gain', 'Dist EQ Mid Gain', 'L/R Diffusion', 'Lag', 'Dry/Wet Balance'],
    101: ['Delay Time', 'Delay Feedback Level', 'Delay Mix', 'Dist Drive', 'Dist Output Level', 'Dist EQ Low Gain', 'Dist EQ Mid Gain', '-', '-', 'Dry/Wet Balance', 'Comp Attack', 'Comp Release', 'Comp Threshold', 'Comp Ratio'],
    102: ['Delay Time', 'Delay Feedback Level', 'Delay Mix', 'Dist Drive', 'Dist Output Level', 'Dist EQ Low Gain', 'Dist EQ Mid Gain', 'L/R Diffusion', 'Lag', 'Dry/Wet Balance', 'Wah Sensitivity', 'Wah Cutoff Freq Offset', 'Wah Resonance', 'Wah Release'],
    103: ['Overdrive', 'Device', 'Speaker Type', 'Presence', 'Output Level', 'Delay Time', 'Delay Feedback Level', 'L/R Diffusion', 'Lag', 'Dry/Wet Balance', 'Delay Mix', 'Feedback High Damp'],
    104: ['LFO Freq', 'LFO Depth', 'LFO Wave', 'Delay Offset', 'Feedback Level', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain', 'Dry/Wet Balance', 'EQ Mid Freq', 'EQ Mid Gain', 'EQ Mid Width', 'Modulation Phase', 'Feedback High Damp', 'Analog Feel'],
    105: ['Type', 'Threshold Offset', 'Low Gain Offset', 'Mid Gain Offset', 'High Gain Offset'],
    107: ['LFO Freq', 'LFO Depth', 'Feedback Level', 'Delay Offset', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain', 'Dry/Wet Balance', 'EQ Mid Freq', 'EQ Mid Gain', 'EQ Mid Width', 'LFO Phase Difference'],
    108: ['LFO Freq', 'LFO Depth', 'Phase Shift Offset', 'Feedback Level', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain', 'Dry/Wet Balance', 'Stage', '-', 'LFO Phase Difference'],
    109: ['Filter Type', 'Sensitivity', 'Dyna Level Offset', 'Resonance', 'Attack Time', 'Release Time', 'Release Curve', 'Direction', 'Dyna Threshold Level', 'Dry/Wet Balance', '-', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain'],
    110: ['Sensitivity', 'Delay Time Offset', 'Feedback Level', 'Attack Time', 'Release Time', 'Release Curve', 'Direction', 'Dyna Threshold Level', 'Dyna Level Offset', 'Dry/Wet Balance', '-', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain'],
    111: ['Sensitivity', 'Dyna Level Offset', 'Feedback Level', 'Attack Time', 'Release Time', 'Release Curve', 'Direction', 'Dyna Threshold Level', '-', 'Dry/Wet Balance', 'Stage', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain'],
    112: ['Sensitivity', 'HPF Cutoff', 'LPF Cutoff', 'Attack Time', 'Release Time', 'Release Curve', 'Direction', 'Dyna Threshold Level', 'Dyna Level Offset', 'Dry/Wet Balance', '-', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain'],
    113: ['Osc Freq Coarse', 'Osc Freq Fine', 'LFO Wave', 'LFO Depth', 'LFO Freq', 'HPF Cutoff', 'LPF Cutoff', '-', '-', 'Dry/Wet Balance', '-', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain'],
    115: ['On/Off SW', 'Low Level', 'Mid Level', 'High Level', 'Low Mute', 'Mid Mute', 'High Mute'],
    119: ['Rotor Speed', 'AM Depth', 'PM Depth', '-', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain', 'Dry/Wet Balance', 'EQ Mid Freq', 'EQ Mid Gain', 'EQ Mid Width', 'LFO Phase Difference', 'Input Mode', 'Rotor SW'],
    120: ['LFO Freq', 'AM Depth', 'PM Depth', '-', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain', '-', 'EQ Mid Freq', 'EQ Mid Gain', 'EQ Mid Width', 'LFO Phase Difference', 'Input Mode'],
    121: ['LFO Freq', 'L/R Depth', 'F/R Depth', 'Pan Direction', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain', '-', 'EQ Mid Freq', 'EQ Mid Gain', 'EQ Mid Width'],
    122: ['Pedal Control', 'Depth', 'Cutoff Freq Offset', 'Resonance', '-', 'EQ Low Freq', 'EQ Low Gain', 'EQ High Freq', 'EQ High Gain', 'Dry/Wet Balance', 'Drive'],
}
# -*- coding: utf-8 -*-
# DSP_PARAM_MAX = {msb: {indice_0based: valor_maximo_real}}
# Só pros parametros que o Data List documenta como uma LISTA CURTA de opções
# com nome (Device, Speaker Type, Wah SW, Input Mode, Direction...) - o
# slider (min continua -1 = "não usar") para de rolar no último nome em vez
# de ir até 127. Extraído/conferido com pdfplumber (coordenadas das colunas
# Min/Max do PDF, não o texto corrido) contra o Effect Parameter List oficial
# do PSR-SX600 (páginas 35-45).
DSP_PARAM_MAX = {
    8:   {3: 2},                                        # CROSS DELAY: Input Select (L, R, L&R)
    9:   {0: 5},                                        # EARLY REFLECTION: Type (6 opções)
    10:  {0: 1},                                        # GATE REVERB: Type (TypeA, TypeB)
    65:  {14: 1},                                        # CHORUS: Input Mode (Mono, Stereo)
    66:  {14: 1},                                        # (mesma tabela CHORUS)
    70:  {14: 1},                                        # TREMOLO: Input Mode
    71:  {3: 5},                                         # AUTO PAN1: Pan Direction (6 opções)
    72:  {10: 22, 11: 1},                                 # PHASER1: Stage (4-22), Diffusion (Mono/Stereo)
    75:  {1: 3},                                          # AMP SIMULATOR1: Amp Type (Off/Stack/Combo/Tube)
    76:  {14: 1},                                         # 3BAND EQ: Input Mode
    86:  {15: 1},                                         # 2WAY ROTARY SPEAKER: Speed Control (Slow/Fast)
    93:  {0: 4},                                          # TALKING MODULATION: Vowel (a,i,u,e,o)
    94:  {4: 5, 14: 1},                                   # LO FI: Filter Type (6 opções), Input Mode
    95:  {1: 7, 3: 7, 5: 8, 10: 12, 12: 4, 13: 16},        # MULTI FX: Wah SW, Dist SW, Dist EQ, Speaker Type, Phaser SW, Delay SW
    96:  {0: 1, 3: 7, 10: 12},                             # SMALL STEREO DIST: Comp SW, Dist Type(*), Speaker Type
    97:  {0: 1, 10: 12, 12: 1},                            # BRITISH COMBO: Mode, Speaker Type, Mic Position
    98:  {1: 4, 2: 5},                                     # V DISTORTION: Device, Speaker Type
    99:  {15: 1},                                          # ROTARY SPEAKER1 (Dual): Speed Control
    103: {1: 4, 2: 5},                                     # V DIST TEMPO DELAY: Device, Speaker Type (mesmo front-end do 98)
    104: {2: 2},                                           # V FLANGER: LFO Wave (Triangle, Sine, Random)
    105: {0: 12},                                          # MULTI BAND COMP: Type (13 opções)
    108: {10: 11},                                         # TEMPO PHASER: Stage (3-11)
    109: {0: 5, 7: 1},                                     # DYNAMIC FILTER: Filter Type (6 opções), Direction
    110: {6: 1},                                           # DYNAMIC FLANGER: Direction
    111: {6: 1, 10: 6},                                    # DYNAMIC PHASER: Direction, Stage (4,5,6)
    112: {6: 1},                                           # DYNAMIC RING MOD: Direction
    113: {2: 1},                                           # RING MODULATOR: LFO Wave (Triangle, Sine)
    115: {0: 1, 4: 1, 5: 1, 6: 1},                          # ISOLATOR: On/Off SW, Low/Mid/High Mute
    119: {15: 1},                                          # VIBE VIBRATE: Rotor SW
    120: {14: 1},                                          # TEMPO TREMOLO: Input Mode
}
# (*) SMALL STEREO DIST "Dist Type" não tem "Off" na lista (o Comp SW já cobre
# o bypass) - por isso o Data List documenta ele de 1 a 7, não de 0 a 7. Como
# o min do SpinCtrl continua -1 (sentinela de "não usar"), isso só limita o
# topo; ainda dá pra escolher 0 mesmo não sendo um nome oficial da lista.

# -*- coding: utf-8 -*-
# DSP_PARAM_OPTIONS = {msb: {indice_0based: (valor_minimo, [nome_da_opcao, ...])}}
# Os mesmos parâmetros do DSP_PARAM_MAX, mas com o NOME de cada opção (na
# ordem certa - índice 0 da lista = valor `valor_minimo`, não sempre 0).
# Usado pra falar "Device: Vintage Tube" em vez de "Device: 1" pro NVDA.
DSP_PARAM_OPTIONS = {
    8:   {3: (0, ["L", "R", "L&R"])},
    9:   {0: (0, ["S-H", "L-H", "Rdm", "Rvs", "Plt", "Spr"])},
    10:  {0: (0, ["TypeA", "TypeB"])},
    65:  {14: (0, ["Mono", "Stereo"])},
    66:  {14: (0, ["Mono", "Stereo"])},
    70:  {14: (0, ["Mono", "Stereo"])},
    71:  {3: (0, ["L<->R", "L->R", "L<-R", "Lturn", "Rturn", "L/R"])},
    72:  {11: (0, ["Mono", "Stereo"])},
    75:  {1: (0, ["Off", "Stack", "Combo", "Tube"])},
    76:  {14: (0, ["Mono", "Stereo"])},
    86:  {15: (0, ["Slow", "Fast"])},
    93:  {0: (0, ["a", "i", "u", "e", "o"])},
    94:  {4: (0, ["Thru", "PowerBass", "Radio", "Tel", "Clean", "Low"]), 14: (0, ["Mono", "Stereo"])},
    95:  {
        1: (0, ["Off", "Wah Pedal", "Auto+ Full", "Auto+ Mid", "Auto+ Light", "Auto- Full", "Auto- Mid", "Auto- Light"]),
        3: (0, ["Off", "Overdrive", "Distortion1", "Distortion2", "Clean", "Crunch", "Hi-Gain", "Modern"]),
        5: (0, ["High Boost", "Mid Boost", "Mid Cut 1", "Mid Cut 2", "Mid Cut 3", "Low Cut 1", "Low Cut 2", "High Cut", "High/Low"]),
        10: (0, ["Off", "Stack", "Twin", "Tweed", "Oldies", "Modern", "Mean", "Soft", "Small", "Dip1", "Dip2", "Metal", "Light"]),
        12: (0, ["Off", "Standard", "Wide", "Vibe", "Tremolo"]),
        13: (0, ["Off", "Delay M", "Echo1 M", "Echo2 M", "Chorus M", "Dl Chorus M", "Flanger1 M", "Flanger2 M",
                 "Flanger3 M", "Delay St", "Echo1 St", "Echo2 St", "Chorus St", "Dl Chorus St", "Flanger1 St",
                 "Flanger2 St", "Flanger3 St"]),
    },
    96:  {
        0: (0, ["Off", "On"]),
        3: (1, ["Overdrive", "Distortion1", "Distortion2", "Clean", "Crunch", "Hi-Gain", "Modern"]),
        10: (0, ["Off", "Stack", "Twin", "Tweed", "Oldies", "Modern", "Mean", "Soft", "Small", "Dip1", "Dip2", "Metal", "Light"]),
    },
    97:  {
        0: (0, ["Bright", "Top Boost"]),
        10: (0, ["Off", "Stack", "Twin", "Tweed", "Oldies", "Modern", "Mean", "Soft", "Small", "Dip1", "Dip2", "Metal", "Light"]),
        12: (0, ["Center", "Edge"]),
    },
    98:  {1: (0, ["Transistor", "Vintage Tube", "Dist1", "Dist2", "Fuzz"]),
          2: (0, ["Flat", "Stack", "Combo", "Twin", "Radio", "Megaphone"])},
    99:  {15: (0, ["Slow", "Fast"])},
    103: {1: (0, ["Transistor", "Vintage Tube", "Dist1", "Dist2", "Fuzz"]),
          2: (0, ["Flat", "Stack", "Combo", "Twin", "Radio", "Megaphone"])},
    104: {2: (0, ["Triangle", "Sine", "Random"])},
    105: {0: (0, ["Normal", "Low", "Mid", "High", "Low/High", "Low/Mid", "Mid/High", "Full Bit", "Wild",
                  "Attacky", "Low End", "Hard", "Basic"])},
    109: {0: (0, ["LPF(12dB)", "LPF(18dB)", "LPF(24dB)", "HPF", "BPF", "BEF"]), 7: (0, ["Up", "Down"])},
    110: {6: (0, ["Up", "Down"])},
    111: {6: (0, ["Up", "Down"])},
    112: {6: (0, ["Up", "Down"])},
    113: {2: (0, ["Triangle", "Sine"])},
    115: {0: (0, ["Off", "On"]), 4: (0, ["Off", "On"]), 5: (0, ["Off", "On"]), 6: (0, ["Off", "On"])},
    119: {15: (0, ["Off", "On"])},
    120: {14: (0, ["Mono", "Stereo"])},
}

OFFSETS_VAR_2BYTES = [0x42, 0x44, 0x46, 0x48, 0x4A, 0x4C, 0x4E, 0x50, 0x52, 0x54]
OFFSETS_VAR_1BYTE = [0x70, 0x71, 0x72, 0x73, 0x74, 0x75]
OFFSETS_REV_PARAMS = [0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15]
OFFSETS_CHO_PARAMS = [0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2A, 0x2B, 0x30, 0x31, 0x32, 0x33, 0x34, 0x35]
REV_PARAM_INDEX = {addr: i for i, addr in enumerate(OFFSETS_REV_PARAMS)}
CHO_PARAM_INDEX = {addr: i for i, addr in enumerate(OFFSETS_CHO_PARAMS)}
DSP_LONG_PARAM_INDICES = {5: [0, 1, 2, 3], 6: [0, 1, 2, 3], 7: [0, 2, 5, 6], 8: [0, 1]}
DSP_PRESET_NAMES = {
    1: {32: "RealLrgHall", 33: "RealMedHall", 34: "RealBrtHall", 21: "BasicHall",
        22: "LightHall", 19: "BalladHall", 20: "PianoHall", 0: "Hall1", 16: "Hall2",
        17: "Hall3", 18: "Hall4", 1: "Hall5", 27: "VocalHall1", 28: "VocalHall2",
        6: "HallM", 7: "HallL", 23: "AtmoHall", 2: "LargeHall", 3: "MediumHall"},
    2: {32: "RealRoom", 33: "RealPwrRoom", 20: "AcousticRoom", 21: "DrumsRoom",
        22: "PercRoom", 16: "Room1", 17: "Room2", 18: "Room3", 19: "Room4",
        0: "Room5", 1: "Room6", 2: "Room7", 5: "RoomS", 6: "RoomM", 7: "RoomL",
        3: "WarmRoom", 4: "WoodyRoom"},
    3: {16: "Stage1", 17: "Stage2", 0: "Stage3", 1: "Stage4"},
    4: {32: "RealLrgPlate", 33: "RealMedPlate", 34: "RealRtlPlate", 16: "Plate1",
        17: "Plate2", 0: "Plate3", 7: "GM Plate", 1: "RichPlate"},
    16: {0: "WhiteRoom"}, 17: {0: "Tunnel"}, 18: {0: "Canyon"}, 19: {0: "Basement"},
    5: {16: "DelayLCR1", 0: "DelayLCR2"}, 6: {0: "DelayLR"}, 7: {0: "Echo"},
    8: {0: "CrossDelay1", 16: "CrossDelay2"}, 9: {0: "EarlyRef1", 1: "EarlyRef2"},
    10: {0: "GateReverb1", 16: "GateReverb2"},
    65: {2: "Chorus5", 0: "Chorus6", 1: "Chorus7", 8: "Chorus8", 16: "ChorusFast",
         17: "ChorusLite", 3: "GM Chorus1", 4: "GM Chorus2", 5: "GM Chorus3",
         6: "GM Chorus4", 7: "FeedBkChorus", 9: "AmbiChorus"},
    66: {17: "Chorus1", 8: "Chorus2", 16: "Chorus3", 1: "Chorus4", 0: "Celeste1",
         2: "Celeste2", 18: "RotarySp5", 9: "AmbiCeleste"},
    67: {8: "Flanger1", 16: "Flanger2", 17: "Flanger3", 1: "Flanger4", 0: "Flanger5",
         7: "GM Flanger", 9: "AmbiFlanger"},
    68: {16: "Symphonic1", 0: "Symphonic2", 9: "AmbiSympho"},
    69: {16: "RotarySp1", 0: "RotarySp6", 1: "Dist+RotSp", 2: "OD+RotarySp", 3: "Amp+RotSp"},
    70: {16: "Tremolo1", 18: "EP Tremolo", 17: "RotarySp4", 0: "Tremolo3", 19: "GtTremolo2"},
    71: {16: "AutoPan1", 17: "RotarySp2", 18: "RotarySp3", 19: "Tremolo2",
         20: "GtTremolo1", 21: "EP AutoPan", 22: "RotarySp7", 0: "AutoPan2", 1: "AutoPan3"},
    72: {0: "Phaser1", 17: "EP Phaser1", 8: "Phaser2", 19: "Phaser3",
         18: "EP Phaser2", 16: "EP Phaser3"},
    73: {0: "DistHeavy", 8: "StDistortion", 16: "Comp+Dist1", 1: "Comp+Dist2"},
    74: {0: "Overdrive", 8: "StOverdrive"},
    75: {29: "StAmpSolid", 30: "StAmpCrunch", 28: "StAmpBlues", 27: "StAmpClean",
         31: "StAmpHarp", 16: "DistHard1", 22: "DistHard2", 17: "DistSoft1",
         23: "DistSoft2", 18: "StDistHard", 19: "StDistSoft", 0: "AmpSim1",
         1: "AmpSim2", 20: "StAmpSim1", 21: "StAmpSim2", 8: "StAmpSim3",
         24: "StAmpSim4", 25: "StAmpSim5", 26: "StAmpSim6"},
    76: {17: "EQ Telephone", 0: "3BandEQ", 19: "Lo-FiDrum3", 20: "Lo-FiDrum4",
         16: "EQ Disco", 18: "St3BandEQ"},
    77: {0: "2BandEQ"},
    78: {16: "AutoWah1", 17: "AtWah+Dist1", 0: "AutoWah2", 1: "AtWah+Dist2",
         21: "AtWah+DistHd", 23: "AtWah+DistHv", 25: "AtWah+DistLt",
         18: "AtWah+OD1", 2: "AtWah+OD2", 22: "AtWah+OD Hd", 24: "AtWah+OD Hv",
         26: "AtWah+OD Lt"},
    83: {16: "CompMed", 17: "CompHeavy", 0: "Compressor"},
    95: {32: "MltDistSolo", 33: "MltDistBasic", 34: "MltOD Chorus", 35: "MltCrunchWah",
         36: "MltOldDelay", 37: "MltVintgEcho", 16: "Dist+Delay1", 0: "Dist+Delay2",
         17: "OD+Delay1", 1: "OD+Delay2"},
    96: {32: "SmallStDist", 33: "SmallStOD", 34: "SmallStVintg", 35: "SmallStHeavy",
         16: "Cmp+Dst+Dly1", 0: "Cmp+Dst+Dly2", 17: "Cmp+OD+Dly1", 1: "Cmp+OD+Dly2"},
    97: {32: "BCmbClassic", 33: "BCmbTopBst", 34: "BCmbCustom", 35: "BCmbHeavy",
         16: "Wah+Dst+Dly1", 0: "Wah+Dst+Dly2", 17: "Wah+OD+Dly1", 1: "Wah+OD+Dly2"},
    98: {32: "BLegndBlues", 33: "BLegndHvy1", 34: "BLegndHvy2", 35: "BLegndClean",
         36: "BLegndDtCln", 18: "VDistCrunch", 21: "VDistBlues", 22: "VDistWarm",
         23: "VDistClsHd", 20: "VDistClsSft", 24: "VDistMetal", 19: "VDistEdgy",
         25: "VDistSolid", 17: "VDistClean1", 26: "VDistClean2", 16: "VDistTwin",
         27: "VDistJzCln", 0: "VDistHard", 2: "VDistSoft", 1: "VDistHd+Dly", 3: "VDistS+Dly"},
    104: {0: "VFlanger"},
    79: {0: "TempoAutoWah", 1: "T.AtWh+Dst", 21: "T.AtWh+DstHd", 23: "T.AtWh+DstHv",
         25: "T.AtWh+DstLt", 2: "T.AtWah+OD", 22: "T.AtWah+ODHd", 24: "T.AtWah+ODHv",
         26: "T.AtWah+ODLt"},
    80: {16: "PitchChange1", 0: "PitchChange2", 1: "PitchChange3"},
    81: {16: "HmEnhance1", 0: "HmEnhance2"},
    82: {0: "TouchWah1", 16: "TcWah+Dist1", 8: "TouchWah2", 20: "TouchWah3",
         1: "TcWah+Dist2", 21: "TcWah+DistHd", 23: "TcWah+DistHv", 25: "TcWah+DistLt",
         17: "TcWah+OD1", 2: "TcWah+OD2", 22: "TcWah+OD Hd", 24: "TcWah+OD Hv",
         26: "TcWah+OD Lt", 18: "ClaviTcWah", 19: "EP TcWah"},
    84: {0: "NoiseGate"},
    85: {0: "VoiceCancel"},
    86: {0: "2WayRotarySp", 1: "Dist+2RotSp", 2: "OD+2RotarySp", 3: "Amp+2RotSp"},
    87: {0: "EnsDetune1", 16: "EnsDetune2"},
    88: {0: "Ambience"},
    93: {0: "TalkingMod"},
    94: {16: "LoopFX1", 17: "LoopFX2", 18: "Lo-FiDrum1", 19: "Lo-FiDrum2", 0: "Lo-Fi"},
    99: {16: "DualRotBrt", 17: "DualRotWarm", 0: "DualRotSp1", 1: "DualRotSp2"},
    100: {0: "Dst+TmpDelay", 1: "OD+TmpDelay"},
    101: {0: "Cmp+Dst+TDly", 1: "Cmp+OD+TDly1", 16: "Cmp+OD+TDly2", 17: "Cmp+OD+TDly3",
          18: "Cmp+OD+TDly4", 19: "Cmp+OD+TDly5", 20: "Cmp+OD+TDly6"},
    102: {0: "Wah+Dst+TDly", 1: "Wah+OD+TDly1", 16: "Wah+OD+TDly2"},
    103: {0: "VDistH+TDly1", 17: "VDistH+TDly2", 1: "VDistS+TDly1", 16: "VDistS+TDly2",
          18: "VDistRockbly", 19: "VDistFusion"},
    105: {16: "CompMelody", 17: "CompBass", 0: "MltBandComp"},
    107: {0: "TempoFlanger"}, 108: {0: "TempoPhaser1", 16: "TempoPhaser2"},
    109: {0: "DynFilter"}, 110: {0: "DynFlanger"}, 111: {0: "DynPhaser"},
    112: {0: "DynRingMod"}, 113: {0: "RingMod"}, 115: {0: "Isolator"},
    119: {0: "VibeRotor"}, 120: {0: "TempoTremolo"},
    121: {0: "TempoAtPan1", 1: "TempoAtPan2"},
    122: {0: "PedalWah", 1: "PWah+Dist", 21: "PWah+DistHd", 23: "PWah+DistHv",
          25: "PWah+DistLt", 2: "PWah+OD", 22: "PWah+OD Hd", 24: "PWah+OD Hv", 26: "PWah+OD Lt"},
}
def nomes_presets(msb, faixa=40):
    tabela = DSP_PRESET_NAMES.get(msb, {})
    return [f"{i:02d} - {tabela[i]}" if i in tabela else f"{i:02d}" for i in range(faixa)]