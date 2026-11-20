# -*- coding: utf-8 -*-
"""
Letra de karaokê dentro do MIDI (MHS MIDI Sequencer).

A letra fica no arquivo como eventos meta "Lyrics" (FF 05), um por sílaba, no tick exato da nota da melodia; é o mesmo
formato dos arquivos de karaokê "Lyrics" que o teclado do Michel mostra na tela. Convenção igual à desses arquivos:
    - uma sílaba que termina a palavra leva um espaço no fim ("ção ");
    - uma sílaba que continua a palavra não leva ("co", "ra");
    - uma quebra de linha é um evento próprio "\\r" antes da primeira sílaba da linha nova.
Também LÊ o padrão Soft Karaoke (.kar): eventos de texto (FF 01) numa faixa com cabeçalhos "@KMIDI KARAOKE FILE", "@L", "@T"...
com "\\" e "/" marcando linha nova e um espaço no começo da primeira sílaba de cada palavra. Ao gravar, tudo vira "Lyrics".

Este módulo tem a parte sem janela (ler, gravar, dividir em sílabas, encaixar nas notas) e as janelas (EditorLetraDialog,
JanelaCantor). A letra é editada por NOTA: a lista mostra só a sílaba de cada nota da melodia.
"""
import bisect
import re

import mido

try:
    from mhs_utils import falar_status
except Exception:                           # os testes sem o resto do programa
    def falar_status(texto, imediato=False):
        pass

QUEBRA = "\r"


# ----------------------------------------------------------------------------------------------------------- ler a letra
def _abs(track):
    t = 0
    saida = []
    for msg in track:
        t += msg.time
        saida.append((t, msg))
    return saida


def _faixa_kar(midi):
    """índice da faixa do Soft Karaoke (a que tem os cabeçalhos @ ou se chama Words), ou None"""
    melhor, quantos = None, 0
    for i, tr in enumerate(midi.tracks):
        cabecalho = any(m.type == "text" and m.text.startswith(("@K", "@L", "@T", "@V", "@I", "@W")) for m in tr)
        words = any(m.type == "track_name" and m.name.strip().lower() == "words" for m in tr)
        if not (cabecalho or words):
            continue
        n = sum(1 for m in tr if m.type == "text" and not m.text.startswith(("@", "%")))
        if words:
            n += 1000000                                   # a faixa "Words" é a da letra
        if n > quantos:
            melhor, quantos = i, n
    return melhor


def _eventos_de_letra(midi):
    """(fonte, [(tick, texto)]) em ordem de tick. fonte = 'lyrics' (FF05), 'kar' (Soft Karaoke) ou None"""
    lyr = []
    for tr in midi.tracks:
        lyr.extend((t, m.text) for t, m in _abs(tr) if m.type == "lyrics")
    if lyr:
        lyr.sort(key=lambda x: x[0])
        return "lyrics", lyr
    k = _faixa_kar(midi)
    if k is not None:
        textos = [(t, m.text) for t, m in _abs(midi.tracks[k]) if m.type == "text" and not m.text.startswith(("@", "%"))]
        if textos:
            return "kar", textos
    return None, []


def ler_letra(midi):
    """lê a letra de um MidiFile -> (fonte, [sílaba]); sílaba = {'tick','texto','cont','linha'}
    cont = a palavra continua na próxima sílaba; linha = esta sílaba abre uma linha nova."""
    fonte, eventos = _eventos_de_letra(midi)
    if not eventos:
        return None, []
    tem_espaco = any(txt[:1] == " " or txt[-1:] == " " for _, txt in eventos)
    silabas = []
    quebra = False
    prev_terminou_espaco = False
    for tick, txt in eventos:
        if txt.strip(" ") == "" and ("\r" in txt or "\n" in txt):
            quebra = True
            continue
        bruto = txt
        if bruto[:1] in ("\\", "/"):
            quebra = True
            bruto = bruto[1:]
        elif bruto[:1] in ("\r", "\n"):
            quebra = True
        terminou_quebra = bruto[-1:] in ("\r", "\n")
        limpo = bruto.strip(" \r\n")
        if not limpo:
            if terminou_quebra:
                quebra = True
            continue
        novo = bruto[:1] == " " or quebra or prev_terminou_espaco or not tem_espaco
        if silabas and novo:
            silabas[-1]["cont"] = False
        silabas.append({"tick": tick, "texto": limpo, "cont": True, "linha": quebra and len(silabas) > 0})
        quebra = terminou_quebra
        prev_terminou_espaco = bruto[-1:] == " "
    if silabas:
        silabas[-1]["cont"] = False
    return fonte, silabas


# ------------------------------------------------------------------------------------------------------ gravar a letra
def _para_delta(lista):
    """[(tick, msg)] em ordem estável -> MidiTrack com os tempos relativos"""
    lista = sorted(enumerate(lista), key=lambda x: (x[1][0], x[0]))
    tr = mido.MidiTrack()
    ultimo = 0
    fim = None
    for _, (t, m) in lista:
        if m.type == "end_of_track":
            fim = max(fim or 0, t)
            continue
        tr.append(m.copy(time=max(0, t - ultimo)))
        ultimo = t
    if fim is not None:
        tr.append(mido.MetaMessage("end_of_track", time=max(0, fim - ultimo)))
    return tr


def remover_letra(midi):
    """tira do arquivo todos os eventos de letra (Lyrics e, se for Soft Karaoke, os textos da faixa de letra e os cabeçalhos @)"""
    k = _faixa_kar(midi)
    for i, tr in enumerate(midi.tracks):
        mantidos = []
        mudou = False
        for t, m in _abs(tr):
            if m.type == "lyrics":
                mudou = True
                continue
            if k is not None and m.type == "text" and (
                    m.text.startswith(("@K", "@L", "@T", "@V", "@I", "@W")) or (i == k and not m.text.startswith("%"))):
                mudou = True
                continue
            mantidos.append((t, m))
        if mudou:
            midi.tracks[i] = _para_delta(mantidos)


def escrever_letra(midi, silabas):
    """regrava a letra no MIDI como eventos Lyrics na primeira faixa (a mestre)"""
    remover_letra(midi)
    if not silabas:
        return
    if not midi.tracks:
        midi.tracks.append(mido.MidiTrack())
    lista = _abs(midi.tracks[0])
    novas = []
    for i, s in enumerate(sorted(silabas, key=lambda x: x["tick"])):
        if s.get("linha") and i > 0:
            novas.append((s["tick"], mido.MetaMessage("lyrics", text=QUEBRA)))
        novas.append((s["tick"], mido.MetaMessage("lyrics", text=texto_latin1(s["texto"]) + ("" if s.get("cont") else " "))))
    midi.tracks[0] = _para_delta(lista + novas)


_TROCAS_LATIN1 = {"’": "'", "‘": "'", "“": '"', "”": '"', "…": "...", "–": "-", "—": "-", " ": " "}


def texto_latin1(texto):
    """o MIDI guarda texto em latin-1: troca aspas curvas, reticências e travessões; o que mesmo assim não couber vira '?'"""
    for k, v in _TROCAS_LATIN1.items():
        texto = texto.replace(k, v)
    return texto.encode("latin-1", errors="replace").decode("latin-1")


# -------------------------------------------------------------------------------------------------- notas da melodia
def notas_do_canal(midi, canal):
    """começos de nota do canal (acordes viram uma entrada, com a nota mais aguda): [{'tick','nota','dur'}]"""
    inicios = []
    for tr in midi.tracks:
        abertas = {}
        for t, m in _abs(tr):
            if getattr(m, "channel", None) != canal:
                continue
            if m.type == "note_on" and m.velocity > 0:
                ev = {"tick": t, "nota": m.note, "dur": 0}
                inicios.append(ev)
                abertas.setdefault(m.note, []).append(ev)
            elif m.type == "note_off" or (m.type == "note_on" and m.velocity == 0):
                fila = abertas.get(m.note)
                if fila:
                    ev = fila.pop(0)
                    ev["dur"] = t - ev["tick"]
    notas = {}
    for ev in sorted(inicios, key=lambda e: (e["tick"], -e["nota"])):
        atual = notas.get(ev["tick"])
        if atual is None:
            notas[ev["tick"]] = dict(ev)
        else:
            atual["dur"] = max(atual["dur"], ev["dur"])
    return [notas[t] for t in sorted(notas)]


def contar_notas_por_canal(midi):
    cont = {}
    for tr in midi.tracks:
        for m in tr:
            if m.type == "note_on" and m.velocity > 0 and hasattr(m, "channel"):
                cont[m.channel] = cont.get(m.channel, 0) + 1
    return cont


def palpite_canal_melodia(midi, canal_atual=None, nomes=None):
    """canal provável da melodia: o selecionado se tem notas; senão um com nome Melody/Melodia/Vocal/Voz; senão o 4; senão o mais 'cantável'"""
    cont = contar_notas_por_canal(midi)
    cont.pop(9, None)
    if canal_atual is not None and cont.get(canal_atual, 0) >= 4:
        return canal_atual
    for ch, nome in (nomes or {}).items():
        if ch in cont and re.search(r"melod|melody|vocal|voz|voice|lead|canto", str(nome).lower()):
            return ch
    if cont.get(3, 0) >= 8:
        return 3
    melhor, pontos = None, -1
    for ch, n in cont.items():
        notas = notas_do_canal(midi, ch)
        if len(notas) < 8:
            continue
        mono = len(notas) / max(1, n)                       # 1.0 = uma nota de cada vez
        p = mono * 1000 + len(notas)
        if p > pontos:
            melhor, pontos = ch, p
    if melhor is not None:
        return melhor
    return min(cont) if cont else (canal_atual or 0)


# ------------------------------------------------------------------------------------------------- sílabas em português
_VOG = set("aeiouáéíóúâêôãõàüAEIOUÁÉÍÓÚÂÊÔÃÕÀÜ")
_FORTES = set("aeoáéóâêôãõàAEOÁÉÓÂÊÔÃÕÀ")
_INSEP = {"bl", "br", "cl", "cr", "dr", "fl", "fr", "gl", "gr", "pl", "pr", "tr", "vr", "ch", "lh", "nh"}


def _silabas_palavra(w):
    """sílabas de uma palavra só de letras (regras comuns do português; o usuário corrige o que errar com hífen)"""
    n = len(w)
    low = w.lower()
    tipo = ["V" if c in _VOG else "C" for c in low]
    for i in range(1, n - 1):                              # o "u" mudo de que/qui/gue/gui
        if low[i] == "u" and low[i - 1] in "qg" and low[i + 1] in "eiéíêè":
            tipo[i] = "C"
    nucleos = []
    i = 0
    while i < n:
        if tipo[i] != "V":
            i += 1
            continue
        j = i + 1
        while j < n and tipo[j] == "V":
            a, b = low[j - 1], low[j]
            if a in "ãõ" and b in "eo":                    # ão, ãe, õe: ditongo nasal
                j += 1
                continue
            if (a in _FORTES and b in _FORTES) or b in "íú":
                break
            j += 1
        nucleos.append((i, j))
        i = j
    if len(nucleos) <= 1:
        return [w]
    cortes = []
    for (a0, a1), (b0, _) in zip(nucleos, nucleos[1:]):
        cl = low[a1:b0]
        if not cl:
            cortes.append(a1)
            continue
        if len(cl) >= 2 and (cl[-2:] in _INSEP or cl[-2:] in ("qu", "gu")):
            vai = 2
        else:
            vai = 1
        cortes.append(b0 - vai)
    partes, ini = [], 0
    for c in cortes:
        partes.append(w[ini:c])
        ini = c
    partes.append(w[ini:])
    return [p for p in partes if p]


def silabas_pt(palavra):
    """divide uma palavra em sílabas; pontuação e números ficam grudados na sílaba vizinha. Palavra com hífen digitado: usa as partes."""
    if "-" in palavra.strip("-"):
        partes = [p for p in palavra.split("-") if p != ""]
        return partes or [palavra]
    pedacos = re.findall(r"[^\W\d_]+|[^\w]+|[\d_]+", palavra, flags=re.UNICODE)
    saida = []
    prefixo = ""
    for p in pedacos:
        if re.match(r"[^\W\d_]", p):
            partes = _silabas_palavra(p)
            if prefixo:
                partes[0] = prefixo + partes[0]
                prefixo = ""
            saida.extend(partes)
        elif saida and p in ("'", "’"):                    # d'água: o apóstrofo junta as duas partes
            prefixo = saida.pop() + p
        elif saida:
            saida[-1] += p
        else:
            prefixo += p
    if prefixo:
        saida.append(prefixo)
    return saida or [palavra]


def texto_para_silabas(texto):
    """texto colado -> lista de itens: {'texto','cont','linha'} ou {'vazio': True} (a "_" = nota sem sílaba).
    Uma frase por linha; palavra com hífen vira as sílabas digitadas; sem hífen, divide sozinho."""
    itens = []
    for linha in texto.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        palavras = linha.split()
        if not palavras:
            continue
        primeira = True
        for w in palavras:
            if w in ("_", "~"):
                itens.append({"vazio": True})
                continue
            continua = len(w) > 1 and w.endswith("-") and w.strip("-") != ""
            partes = silabas_pt(w.rstrip("-") if continua else w)
            for k, p in enumerate(partes):
                itens.append({"texto": p, "cont": k < len(partes) - 1 or continua, "linha": primeira and bool(itens)})
                primeira = False
    return itens


# --------------------------------------------------------------------------------------------- modelo: uma sílaba por nota
class LetraModelo:
    """slots[i] = sílaba da i-ésima nota da melodia (ou None). Edição só por nota, como o Event List."""

    def __init__(self, notas, silabas=(), tolerancia=None):
        self.notas = list(notas)
        self.slots = [None] * len(self.notas)
        self.deslocadas = 0
        self.lidas = len(silabas)          # sílabas que já existiam no arquivo
        self.coincidem = 0                 # quantas delas caem em cima (até 'tolerancia' ticks) de uma nota deste canal
        self.tolerancia = tolerancia
        self.alinhar(silabas)

    @classmethod
    def do_midi(cls, midi, canal):
        fonte, silabas = ler_letra(midi)
        m = cls(notas_do_canal(midi, canal), silabas, tolerancia=max(1, getattr(midi, "ticks_per_beat", 480) // 8))
        m.fonte = fonte
        return m

    def letra_presa_as_notas(self):
        """False quando o arquivo já tem letra mas ela NÃO está presa às notas deste canal (letra sincronizada só por tempo, como nos
        karaokês feitos à parte). Editar por nota um arquivo assim jogaria a letra para as notas erradas."""
        return self.lidas < 8 or self.coincidem >= 0.6 * self.lidas

    fonte = None
    modo_tempo = False          # True: cada "nota" é o tempo de uma sílaba que já existia (letra sincronizada só por tempo)

    @classmethod
    def por_tempo(cls, silabas, fonte=None):
        """modo por tempo, para MIDIs sem melodia gravada ou com a letra sincronizada à parte: cada item é uma sílaba com o SEU tick"""
        m = cls([], (), tolerancia=None)
        m.modo_tempo = True
        m.fonte = fonte
        m.notas = [{"tick": s["tick"], "nota": None, "dur": 0} for s in silabas]
        m.slots = [{"texto": s["texto"], "cont": bool(s.get("cont")), "linha": bool(s.get("linha"))} for s in silabas]
        m.lidas = len(silabas)
        m.coincidem = len(silabas)
        return m

    # --- só no modo por tempo
    def inserir_item_tempo(self, tick, item):
        """põe uma sílaba no tick dado (se já houver uma exatamente ali, vai para o tick seguinte livre). -> índice do item novo"""
        tick = max(0, int(tick))
        usados = {n["tick"] for n in self.notas}
        while tick in usados:
            tick += 1
        i = bisect.bisect_left([n["tick"] for n in self.notas], tick)
        self.notas.insert(i, {"tick": tick, "nota": None, "dur": 0})
        self.slots.insert(i, {"texto": item["texto"], "cont": bool(item.get("cont")), "linha": bool(item.get("linha"))})
        return i

    def remover_item(self, i):
        del self.notas[i]
        del self.slots[i]

    def mover_para(self, i, tick):
        """muda o tempo do item i; a lista continua em ordem de tempo. -> novo índice do item"""
        tick = max(0, int(tick))
        nota, slot = self.notas.pop(i), self.slots.pop(i)
        usados = {n["tick"] for n in self.notas}
        while tick in usados:
            tick += 1
        nota["tick"] = tick
        j = bisect.bisect_left([n["tick"] for n in self.notas], tick)
        self.notas.insert(j, nota)
        self.slots.insert(j, slot)
        return j

    def mover(self, i, delta):
        return self.mover_para(i, self.notas[i]["tick"] + delta)

    def estado(self):
        """foto para o desfazer: as sílabas e (no modo por tempo) os tempos"""
        return {"slots": self.copia(), "notas": [dict(n) for n in self.notas]}

    def restaurar_estado(self, est):
        self.slots = [dict(s) if s else None for s in est["slots"]]
        self.notas = [dict(n) for n in est["notas"]]

    def validar_texto(self, texto, inicio=0):
        """o texto do bloco de notas cabe? -> (True, "") ou (False, explicação)"""
        nec, disp = self.contar_texto(texto, inicio)
        if self.modo_tempo:
            if nec != disp and not (nec == 0 and not any(self.slots)):
                return False, ("O número de palavras mudou (eram %d, ficaram %d). No modo por tempo cada palavra tem o seu tempo: "
                               "mude o texto sem mudar a quantidade; para incluir ou tirar palavras use Insert e Delete no editor."
                               % (disp, nec))
            return True, ""
        if nec > disp:
            return False, "A letra passou do fim da melodia: faltam %d notas. Tire sílabas e aplique de novo." % (nec - disp)
        return True, ""

    def alinhar(self, silabas):
        ticks = [n["tick"] for n in self.notas]
        if not ticks:
            return
        for s in silabas:
            i = bisect.bisect_left(ticks, s["tick"])
            if i > 0 and (i == len(ticks) or s["tick"] - ticks[i - 1] <= ticks[i] - s["tick"]):
                i -= 1
            if self.tolerancia is not None and abs(ticks[i] - s["tick"]) <= self.tolerancia:
                self.coincidem += 1
            if self.slots[i] is not None:                  # nota já ocupada: vai para a próxima livre
                k = i
                while k < len(ticks) and self.slots[k] is not None:
                    k += 1
                if k >= len(ticks):
                    k = i
                    while k >= 0 and self.slots[k] is not None:
                        k -= 1
                if k < 0:
                    continue
                i = k
                self.deslocadas += 1
            self.slots[i] = {"texto": s["texto"], "cont": bool(s.get("cont")), "linha": bool(s.get("linha"))}

    def total_silabas(self):
        return sum(1 for s in self.slots if s)

    def silabas(self):
        """lista final para gravar no arquivo, com o tick de cada nota; a 1ª sílaba nunca abre 'linha nova'"""
        saida = []
        for n, s in zip(self.notas, self.slots):
            if s:
                saida.append({"tick": n["tick"], "texto": s["texto"], "cont": s["cont"], "linha": s["linha"]})
        if saida:
            saida[0]["linha"] = False
            saida[-1]["cont"] = False
        return saida

    # --- fala (o NVDA lê só isto)
    def fala(self, i):
        s = self.slots[i]
        if not s:
            return "sem letra"
        return ("nova linha, " if s["linha"] else "") + s["texto"]

    # --- texto de edição: "co-" continua a palavra; "/pe" abre linha
    def texto_de_edicao(self, i):
        s = self.slots[i]
        if not s:
            return ""
        return ("/" if s["linha"] else "") + s["texto"] + ("-" if s["cont"] else "")

    @staticmethod
    def ler_edicao(texto):
        t = texto.strip()
        linha = t.startswith("/")
        t = t.lstrip("/").strip()
        cont = t.endswith("-") and len(t) > 1
        t = t.rstrip("-").strip() if cont else t
        if not t:
            return None
        return {"texto": t, "cont": cont, "linha": linha}

    def definir(self, i, texto):
        """grava (ou apaga, se vazio) a sílaba da nota i a partir do texto digitado"""
        self.slots[i] = self.ler_edicao(texto)

    def apagar(self, i):
        self.slots[i] = None

    def alternar_linha(self, i):
        if self.slots[i]:
            self.slots[i]["linha"] = not self.slots[i]["linha"]
            return self.slots[i]["linha"]
        return None

    def inserir_empurrando(self, i, texto):
        """põe a sílaba na nota i e empurra as seguintes uma nota para a frente; False se não há nota livre no fim"""
        nova = self.ler_edicao(texto)
        if nova is None:
            return False
        fim = i
        while fim < len(self.slots) and self.slots[fim] is not None:
            fim += 1
        if fim >= len(self.slots):
            return False
        for k in range(fim, i, -1):
            self.slots[k] = self.slots[k - 1]
        self.slots[i] = nova
        return True

    def apagar_puxando(self, i):
        """tira a sílaba da nota i e puxa as seguintes uma nota para trás (até a próxima nota vazia)"""
        k = i
        while k + 1 < len(self.slots) and self.slots[k + 1] is not None:
            self.slots[k] = self.slots[k + 1]
            k += 1
        self.slots[k] = None

    def distribuir(self, texto, inicio=0):
        """espalha o texto nas notas a partir da nota 'inicio' (sobrescreve). -> (colocadas, sobraram)"""
        itens = texto_para_silabas(texto)
        i = inicio
        colocadas = 0
        for k, it in enumerate(itens):
            if i >= len(self.slots):
                return colocadas, sum(1 for x in itens[k:] if not x.get("vazio"))
            if it.get("vazio"):
                self.slots[i] = None
            else:
                self.slots[i] = {"texto": it["texto"], "cont": it["cont"], "linha": it["linha"]}
                colocadas += 1
            i += 1
        return colocadas, 0

    # --- o "bloco de notas": a letra inteira como texto (hífen separa sílabas, _ é nota sem sílaba, linha nova = quebra de linha)
    def para_texto(self):
        """-> (texto, {nota: posição do texto onde a sílaba dela começa}, nota da primeira sílaba)"""
        idxs = [i for i, s in enumerate(self.slots) if s]
        if not idxs:
            return "", {}, 0
        ini, fim = idxs[0], idxs[-1]
        saida, posicoes, pos = [], {}, 0
        for i in range(ini, fim + 1):
            s = self.slots[i]
            ant = self.slots[i - 1] if i > ini else None
            if i == ini:
                sep = ""
            elif s and s["linha"]:
                sep = "\n"
            elif ant is not None and ant["cont"] and s is not None:
                sep = ""
            else:
                sep = " "
            tok = "_" if s is None else s["texto"] + ("-" if s["cont"] else "")
            pos += len(sep)
            posicoes[i] = pos
            saida.append(sep + tok)
            pos += len(tok)
        return "".join(saida), posicoes, ini

    def para_texto_leitura(self):
        """a letra como se lê (palavras inteiras, sem hífens, uma frase por linha, sem as notas puladas), como no exibidor de letras
        do Winamp. -> (texto, {nota: posição da sílaba no texto})"""
        saida, posicoes, pos = [], {}, 0
        ultimo = None
        for i, s in enumerate(self.slots):
            if not s:
                continue
            if ultimo is None:
                sep = ""
            elif s["linha"]:
                sep = "\n"
            elif ultimo["cont"]:
                sep = ""
            else:
                sep = " "
            pos += len(sep)
            posicoes[i] = pos
            saida.append(sep + s["texto"])
            pos += len(s["texto"])
            ultimo = s
        return "".join(saida), posicoes

    def contar_texto(self, texto, inicio=0):
        """(posições de nota que o texto ocupa, notas disponíveis a partir de 'inicio')"""
        return len(texto_para_silabas(texto)), max(0, len(self.slots) - inicio)

    def aplicar_texto(self, texto, inicio=0):
        """troca a letra inteira pelo texto, a partir da nota 'inicio'. -> (sílabas colocadas, 0) ou (None, quantas faltam) sem mudar nada"""
        itens = texto_para_silabas(texto)
        if inicio + len(itens) > len(self.slots) or (self.modo_tempo and inicio + len(itens) != len(self.slots)):
            return None, abs(inicio + len(itens) - len(self.slots))
        self.slots = [None] * len(self.slots)
        colocadas = 0
        for k, it in enumerate(itens):
            if not it.get("vazio"):
                self.slots[inicio + k] = {"texto": it["texto"], "cont": it["cont"], "linha": it["linha"]}
                colocadas += 1
        return colocadas, 0

    def copia(self):
        return [dict(s) if s else None for s in self.slots]

    def restaurar(self, copia):
        self.slots = [dict(s) if s else None for s in copia]
