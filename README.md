# livedub

Doppiaggio italiano **live** dei sottotitoli di un videogioco: voci diverse per
personaggi diversi, tono e volume guidati dall'emozione, durata agganciata al
parlato originale. Nessuna battuta viene scartata.

## Come funziona

Due domini scorrono in parallelo e si incontrano in un punto solo.

```
VIDEO   ROI → righe → classe colore → OCR → SubtitleEvent(testo, bianco|grigio)
                                                        │
AUDIO   loopback → center → VAD → embedding → tracker → SpeakerEvent(chi, come)
                                                        │
                                                    FUSIONE
                                                        ▼
                                    voce assegnata → TTS → prosodia → filtri
                                                        ▼
                        audio gioco → duck del centro → MIX → uscita
```

**L'audio non dice mai *cosa* si dice** — quello viene dall'OCR. Dice solo *chi*
e *come*. Questo toglie dalla catena il riconoscimento vocale, e con lui la sua
latenza.

### La grammatica dei sottotitoli

Il colore del testo porta informazione, e si legge **per riga**:

| | |
|---|---|
| riga con glifi **saturi** | non e' dialogo: suggerimento o obiettivo → **si scarta la riga intera** |
| riga **bianca** | battuta dello speaker principale |
| riga **grigia** | battuta di un *secondo* speaker che parla quasi in contemporanea |

Due righe della stessa luminanza sono una frase andata a capo. Due righe di
luminanza diversa sono **due battute distinte**, con due voci diverse — ed e'
anche l'unico indizio su chi parla disponibile *nell'istante* in cui il
sottotitolo compare, quando l'embedding audio e' ancora incerto.

## Comandi

```powershell
.\.venv\Scripts\python.exe -m tools.selftest              # suite completa
.\.venv\Scripts\python.exe -m tools.selftest ring config  # un gruppo solo
.\.venv\Scripts\python.exe -m tools.replay --demo         # banco di prova
.\.venv\Scripts\python.exe -m tools.replay --demo --determinism
.\.venv\Scripts\python.exe main.py --dump-config
```

## Stato

**F0 — scheletro misurabile.** `core/` (orologio, metriche, stadi, config,
tipi, ring buffer), la suite di autoverifica e il banco di prova sono in piedi.
La grammatica dei sottotitoli e' implementata e verificata. Non doppia ancora
nulla: la catena live si accende in F1.

Piano completo: `C:\Users\filde\.claude\plans\progetto-so-che-ci-fancy-rossum.md`
