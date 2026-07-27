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
.\.venv\Scripts\python.exe -m tools.selftest              # suite completa (398 verifiche)
.\.venv\Scripts\python.exe -m tools.selftest ring config  # un gruppo solo
.\.venv\Scripts\python.exe -m tools.demo                  # scena finta completa -> runs\demo_mix.wav
.\.venv\Scripts\python.exe -m tools.demo --no-duck        # la stessa, per sentire cosa fa il duck
.\.venv\Scripts\python.exe -m tools.say --pool            # ascoltare le voci
.\.venv\Scripts\python.exe main.py --dump-config
```

## Cosa e' stato misurato

Ogni numero qui sotto viene dal banco, non da una stima. Le sorprese sono
segnate perche' sono quelle che hanno cambiato il disegno.

| | |
|---|---|
| OCR, sola recognition | 8–60 ms per riga **su CPU**, contro 985 ms del det+rec completo |
| OCR, det+rec vs ritaglio stretto | CER 5,6% → **0%**: era l'ingresso a essere sbagliato, non il modello |
| OCR, costo | scala con la **larghezza**; ingrandire in altezza raddoppia il costo a parita' di accuratezza |
| OCR, ritaglio | grigio mascherato invece che binario: CER 4,4% → 2,9% |
| Piper, primo campione | 36–70 ms, RTF 0,024–0,037, zero VRAM |
| Piper, `length_scale` | **non proporzionale**: chiedendo 0,8 si sbaglia del 14% |
| Latenza end-to-end | **135 ms** p95 (sottotitolo → prima voce italiana), budget 350 |
| Soglia di luminanza assoluta | si rompe su fondo chiaro da 120 in su; col contrasto locale regge fino a 180 |

Conseguenza grossa: **la GPU non serve a niente di tutto questo** e resta
interamente al gioco.

## Stato

**F0 — scheletro misurabile** e **F1 — la catena parla**. Cattura dei
sottotitoli, OCR, pool di sei voci italiane, mixer con duck del centro,
tutto montato in `core/pipeline.py` e verificabile con `tools.demo`.

Non c'e' ancora: il riconoscimento di *quale* personaggio parla (F3, per ora
bianco e grigio ricevono due voci fisse), l'aggancio della durata al sottotitolo
(F2), l'emozione (F4) e la cattura dal vivo da schermo e scheda audio.

Piano completo: `C:\Users\filde\.claude\plans\progetto-so-che-ci-fancy-rossum.md`
