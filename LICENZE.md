# Licenza, e perché è questa

**livedub è GPL-3.0-or-later**, e non per gusto: è quello che impongono le
librerie da cui dipende. Chi legge questa pagina deve poter rifare il conto, non
fidarsi.

## La riga che decide

Il sintetizzatore **di default** è Piper, e `piper-tts` 1.6.0
(`OHF-voice/piper1-gpl`) dichiara **GPL-3.0-or-later**. Lo importa
`speak/backends/piper.py`, e Piper è il motore che parte se nessuno sceglie
altro. Un programma che a ogni avvio carica in processo una libreria GPL-3 e la
distribuisce insieme a sé è un'opera derivata: la licenza non è una scelta, è
una conseguenza.

La stessa cosa arriva da una seconda strada, il che toglie ogni dubbio: la voce
Kokoro ha bisogno del g2p italiano, che viene da `espeakng-loader`, e dentro quel
pacchetto c'è **`espeak-ng.dll`** — eSpeak NG è GPL-3.0-or-later. Nella stessa
catena c'è `phonemizer-fork`, anch'esso GPL-3.

Quindi due dei tre motori di voce sono legati a GPL-3, compreso quello di
default. **Anche scrivendo "MIT" sul nostro codice**, l'eseguibile distribuito
resterebbe soggetto a GPL-3: MIT è compatibile con GPL-3, ma la compatibilità
funziona in una direzione sola — il risultato combinato è GPL. Dichiarare MIT sul
repository sarebbe formalmente difendibile per i file che ho scritto io e
**fuorviante** per la cosa che la gente scarica.

## Le librerie, una per una

Lette dai metadati dei pacchetti **installati** in `.venv`, non da memoria.

| libreria | licenza | dove pesa |
|---|---|---|
| **piper-tts** 1.6.0 | **GPL-3.0-or-later** | motore di voce **di default** |
| **espeakng-loader** (`espeak-ng.dll`) | **GPL-3.0-or-later** | g2p per Kokoro |
| **phonemizer-fork** | **GPL-3.0** | idem |
| onnxruntime-gpu | MIT | tutti i modelli |
| supertonic | MIT | voce su CPU |
| kokoro-onnx | MIT | voce su GPU |
| windows-capture | MIT | cattura della finestra |
| mss | MIT | cattura schermo (ripiego) |
| pillow | MIT-CMU | disegno dell'overlay |
| opencv-python | Apache-2.0 | visione |
| rapidocr-onnxruntime | Apache-2.0 | OCR di ripiego |
| PyAudioWPatch | Apache-2.0 | loopback WASAPI |
| huggingface_hub | Apache-2.0 | scarica i modelli |
| numpy | BSD-3-Clause e altre | ovunque |
| soundfile | BSD-3-Clause | WAV |
| imageio-ffmpeg | BSD-2-Clause | montaggio degli MP4 di prova |

Nessuna di queste è **incompatibile** con GPL-3: MIT, BSD e Apache-2.0 si possono
combinare in un'opera GPL-3 (Apache-2.0 solo verso GPL-**3**, non GPL-2 — un
motivo in più per non scrivere "GPL-2 or later").

## Le due cose che non si possono ridistribuire, e non si ridistribuiscono

**OneOCR** — `oneocr.dll`, `oneocr.onemodel` e la sua `onnxruntime.dll` sono di
Microsoft e arrivano dallo Strumento di cattura di Windows 11. **Non sono
ridistribuibili**, quindi non stanno nel repository e non devono finire in
nessun pacchetto: `tools/fetch_oneocr.py` li copia dalla macchina su cui il
programma gira, dove l'utente li ha già in virtù della sua licenza Windows. È
anche il motivo per cui l'OCR di default in config resta `ppocr`.

**I pesi dei modelli** (Piper, Kokoro, ECAPA, il lessico, il modello di
traduzione) si scaricano al primo uso in `models/`, che è gitignorato. Ognuno ha
la sua licenza, e distribuirli insieme al programma vorrebbe dire assumersele
tutte senza averle lette.

Da qui una regola per l'eseguibile: **si impacchetta il programma, non i
modelli.**

## Cosa comporta, in pratica

- Chiunque può usare livedub, anche per farci soldi.
- Chi lo **distribuisce** modificato deve pubblicare il proprio codice sotto
  GPL-3, e deve consegnare anche il sorgente.
- Chi lo usa per sé, o lo fa girare per un video, non deve niente a nessuno.
- Un'azienda che volesse chiuderlo dentro un prodotto proprietario non può —
  ed è la ragione per cui, potendo scegliere, sceglierei comunque questa.

## Se un giorno si volesse una licenza permissiva

Si può, ma il conto è chiaro e va fatto prima: si dovrebbe **togliere Piper come
default e come dipendenza**, e togliere il g2p di Kokoro basato su eSpeak NG.
Resterebbe SuperTonic (MIT), che gira solo su CPU e che questo progetto ha
misurato al tetto di compressione in quattordici sessioni su sedici. Sarebbe una
scelta di prodotto, non di licenza.
