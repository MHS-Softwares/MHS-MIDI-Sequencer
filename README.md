# MHS MIDI Sequencer

Editor acessível de arquivos MIDI (`.mid`) para teclados arranjadores
Yamaha, feito para funcionar **100% por teclado**, com retorno falado em
praticamente toda ação. Pensado desde o início para músicos cegos e com
baixa visão: nenhuma função depende de enxergar a tela, de mouse, ou de
cores.

Diferente do MHS Style Creator (que edita estilos/ritmos em loop), o MIDI
Sequencer edita uma música MIDI completa do início ao fim - gravação,
edição de notas, controle dos 16 canais, efeitos e mais - tudo sobre um
arquivo `.mid` padrão, compatível com qualquer teclado XG ou GM/GS,
incluindo o Yamaha PSR-SX600.

## O que dá pra fazer

- Gravar e editar notas, com transporte completo (tocar, pausar, gravar,
  navegar por compasso/beat/seção).
- Controlar Volume/Pan/Expression/Reverb/Chorus/Bank/Patch de cada um dos
  16 canais MIDI.
- Afinar peças de bateria nota a nota (Drum Setup, inclusive via SysEx e
  via NRPN puro - funciona em qualquer sintetizador XG/GS).
- Montar e editar efeitos de DSP (Reverb, Chorus, Variation, Inserção),
  inclusive vários canais compartilhando o mesmo efeito.
- Criar timbres próprios (Voice Creator) e importar/exportar vozes (.vce,
  .drm, .mgv, .sar, .liv).
- Quantizar, humanizar, aplicar arpejador/delay/harpa/presets de bateria.
- Editor de Envelope de Tempo (BPM variável ao longo da música) e Tap
  Tempo.
- Sincronizar um Áudio Guia (WAV/MP3/OGG) com o projeto, com ajuste fino
  de sincronismo.
- Editar SysEx manualmente com um gerenciador dedicado, categorizado por
  tipo (Mixagem, Voice Creator, DSP, Drum Setup, etc).

O manual completo (`Manual do MHS MIDI Sequencer.txt`) documenta cada tela
e atalho de teclado em detalhe.

## Instalação

Requer Python 3 e as dependências em `requirements.txt`:

```bash
pip install -r requirements.txt
python MHS.py
```

Um `.mid` pode ser passado como argumento (ou associado à extensão no
Windows) para abrir direto.

## Sobre este projeto

Este programa é feito e mantido por um músico cego, para músicos com
deficiência visual que trabalham com teclados arranjadores Yamaha. Se ele
ajudar no seu trabalho e você quiser reconhecer/incentivar o
desenvolvimento, uma contribuição via Pix é sempre bem-vinda:

- **Chave Pix (e-mail):** michel.teclado@gmail.com
- **Destinatário:** Michel Henrique da Silva

## Licença

Nenhuma licença de código aberto foi concedida sobre este repositório -
todos os direitos são reservados ao autor. O código é público para
consulta e uso pessoal, mas redistribuir, revender ou publicar versões
modificadas não é permitido sem autorização.

## Aviso importante

O autor só dá suporte e se responsabiliza pelo instalador **oficial**,
disponibilizado na aba [Releases](https://github.com/MHS-Softwares/MHS-MIDI-Sequencer/releases)
deste repositório. Cópias obtidas por qualquer outro meio - sites de
terceiros, redes sociais, pendrive, e-mail, ou qualquer versão
recompilada/modificada por outra pessoa - não têm garantia nenhuma de
segurança ou de funcionamento correto, e o autor não tem como saber o
que foi alterado nelas.
