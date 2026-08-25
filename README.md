<div align="center">

<img src="assets/logo/livedub-256.png" alt="livedub" width="128">

# livedub

**Live dubbing for a video game's subtitles.**
It reads the text on screen while you play, works out who is speaking from the
game's audio, synthesises the line in that character's voice and mixes it over
the game. All on your own machine.

{{BADGES}}

<img src="assets/menta-anteprima.png" alt="the livedub window during a game" width="760">

**English** ·
[Italiano](docs/readme/README.it.md) ·
[Deutsch](docs/readme/README.de.md) ·
[Español](docs/readme/README.es.md) ·
[Français](docs/readme/README.fr.md) ·
[日本語](docs/readme/README.ja.md) ·
[中文](docs/readme/README.zh.md)

**[See it and hear it — the videos, with sound](https://pigro141.github.io/livedub/)**

</div>

> **There is no mandatory translation in this chain.** If the game's subtitles
> are already in your language, the program reads them and *says* them.
> Translating is a separate feature, **off by default**, for a game written in a
> language that is not yours.

---

## See it

Three silent clips below, because a README cannot play sound: GitHub animates a
GIF but gives it no audio, and this program **speaks** — hearing it is half of
what there is to see. Each clip links to the full video, with the voice:
**[the showcase](https://pigro141.github.io/livedub/#watch)**.

### The dubbing, on GTA V

The black band on top is the text **as the OCR read it**, with the voice that
was assigned to it. It is there to tell *misread* apart from *mispronounced*,
and it is why every listening test in this project is delivered that way. You
can hear the voice change between two characters: `[nicola]` and `[nicola-2_5]`
are the same voice at two pitches.

[![dubbing on GTA V](assets/vetrina/doppiaggio-gtav.gif)](https://pigro141.github.io/livedub/#watch)

*Play it with sound: silent, you can see that it reads, not that it says.*

### Translation, drawn over the game

The original subtitle is **erased by rebuilding the background** behind it — not
covered with a rectangle — and the translated line takes its place, with the
size and colour copied from the game.

[![translated overlay](assets/vetrina/traduzione-overlay.gif)](https://pigro141.github.io/livedub/#watch)

### The window, while it works

One colour per character in the log, and the measurement bar along the bottom:
reads per second, lines, latency, compression, underruns, reading area.

[![the livedub window](assets/vetrina/finestra-menta.gif)](https://pigro141.github.io/livedub/#watch)

---

## What it does, in short

| | |
|---|---|
| **Reads** the subtitles | OCR on the game's window alone, not on the screen |
| **Works out who is speaking** | a voice fingerprint on the game's own audio, with no labels |
| **Gives each character a voice** | and remembers it from one session to the next |
| **Keeps up with the scene** | it speeds a line up just enough to fit the time it has |
| **Mixes** | it ducks **only the centre channel** of the game, where the dialogue sits: music and effects stay where they are |
| **Translates** *(off by default)* | several backends, most of them with no network at all |
| **Rewrites the subtitle on screen** *(off by default)* | erases the original and draws the translated line |
| **Speaks {{UI_LANGUAGES_COUNT}}** *(the interface)* | follows your Windows language, and changes without a restart |

---

## How you use it, in the order you meet it

There is nothing to configure first: you open it and follow along.

**1. You open it.** The window is already in the language you use Windows in —
{{UI_LANGUAGES_COUNT}}. Arabic, Hebrew, Persian and Urdu also flip the window
the other way round.

**2. A guide takes you through it**, {{TUTORIAL_STEPS}} steps, and it comes back
with `?`. Wherever it can it **checks instead of telling**: it counts the audio
devices you actually have, it asks ONNX Runtime whether CUDA is really there
instead of assuming, and it measures the height of your reading area with the
real rule.

<img src="assets/guida-1.png" alt="the first step of the guide" width="440"> <img src="assets/guida-4.png" alt="the reading-area step" width="440">

**3. A bench measures this PC and picks the engines.** It is not a convenience:
**a model that is missing does not raise an error**. Programs are installed
once, models are not — they are fetched on first use, and if they do not arrive
the chain *falls back to something lighter and carries on*. Without this step
you would be listening to the fallback without knowing. The bench measures,
picks, downloads what is missing, and **installs no programs**: if one is
missing it hands you the exact line to paste.

<img src="assets/guida-banco.png" alt="the bench measuring the PC" width="560">

**4. You pick the game's window.** It captures **one window**, not the screen,
so nothing else can end up in the frame that goes to the OCR — not even our own
windows. The game has to run windowed or *borderless*, not in exclusive
fullscreen.

**5. You drag a box around the subtitle line.** Two seconds with the mouse. The
area is **relative to the window**: move the game and the area follows it.

**6. Start.** From there it reads, works out who is speaking, synthesises and
mixes.

The voice always arrives a little after the subtitle, and that is deliberate:
{{SPEAKER_DECIDE_MS}} of game audio is what it takes to know who is talking
before choosing a voice.

---

## What happens inside

```mermaid
flowchart TD
    subgraph W["the wait · {{SPEAKER_DECIDE_MS}} · speaker.decide_after_ms"]
      direction LR
      W1["game audio piles up<br/>for the fingerprint"]
      W2["the line is <b>translated</b><br/><i>(optional)</i>"]
      W1 ~~~ W2
    end

    A["capture of the<br/><b>game window</b>"] --> B["the band that gets read:<br/>lines found<br/>and sorted by colour"]
    B --> C["OCR<br/>one line at a time"]
    C --> D["stabiliser:<br/>two reads that agree<br/>= one line"]
    D --> W
    W --> E["<b>who is speaking</b>:<br/>the voice fingerprint<br/>against the centroids"]
    E --> F["<b>which voice</b>:<br/>one from the pool,<br/>the same as yesterday"]
    F --> G["<b>synthesis</b>"]
    G --> H["<b>hurry</b>: the engine first,<br/>the remainder to WSOLA"]
    H --> I["<b>mixer</b>: ducks the game's<br/>centre channel,<br/>pours the line in"]
    I --> J(["headphones"])
    D -.->|"the boxes and the ink<br/>of the lines that were read"| K["overlay: erases the original,<br/>draws the translation"]
    K -.-> L(["screen"])

    style W fill:#123a33,stroke:#43f1c1,color:#e6fff8
    style J fill:#123a33,stroke:#43f1c1,color:#e6fff8
    style L fill:#123a33,stroke:#43f1c1,color:#e6fff8
```

**Two domains, two threads, one meeting point.** The video domain decides
**what** will be said and **when**; the audio domain pours in what was
scheduled. **The mixer never calls the synthesiser**: if it did, the sample
stream would stop at every line — and a hole in the stream is not a slowdown, it
is a line you do not hear.

**Translation happens *inside* the wait, not after it.** They are two
independent waits: one needs the *text*, which is there as soon as the subtitle
is confirmed; the other needs *audio*, which has to pile up. In a row they cost
`wait + translation`; overlapped they cost `max(wait, translation)`.

The rest is in [`docs/architettura.md`](docs/architettura.md) *(in Italian, like
the code)*.

---

## The numbers, and which session they come from

**Live sessions only, with the game running.** There is also a bench that runs
the very same chain over a recording — real code, not a simulation — but **the
bench gives time away**: on a virtual clock synthesis costs nothing and no frame
is ever dropped. No latency comes from there, and none in this table does.

{{LIVE_NUMBERS_TABLE}}

**How many cores an engine needs.** This one comes from the bench and is not a
latency: it is the **cost of synthesising one line** with everything else held
equal, timed on the wall clock while the process is restricted to fewer cores.
It is a **lower bound** on how much an older PC would slow down — it simulates
fewer cores, not slower ones.

{{CPU_CORES_TABLE}}

---

## Privacy: it all runs on your machine

That is not a slogan, it is the list of what leaves the computer.

| | does anything leave? |
|---|---|
| reading the subtitles (OCR) | **no** — on your machine |
| who is speaking (voice fingerprint) | **no** — on your machine |
| synthesising the voice | **no** — on your machine |
| translating with the offline backends | **no** |
| translating with the online backend | **yes**, and the program says so every time |
| downloading the models | **once**, on first use |

The only way to send text out is to pick the online translator on purpose. No
telemetry, no account, no connection to a server of ours — there is no server of
ours.

---

## Requirements

{{HARDWARE_TABLE}}

**You also need** a way to hear the game's audio without your own dubbing
looping back into it: the WASAPI loopback that ships with Windows is enough.
[Voicemeeter](https://vb-audio.com/Voicemeeter/) is **optional** — it only helps
if you want everything in a single pair of headphones.

## Download

{{DOWNLOADS}}

## Install from source

```powershell
git clone https://github.com/pigro141/livedub.git
cd livedub
powershell -ExecutionPolicy Bypass -File installa.ps1
```

The script **checks that it got what it asked for** instead of reporting
success: Python, the virtual environment, the dependencies, the OCR, the real
CUDA provider, the models — and it finishes by running the test suite. Whatever
is missing is listed with the reason and what it costs you.

Without an NVIDIA GPU:

```powershell
powershell -ExecutionPolicy Bypass -File installa.ps1 -SenzaGpu
```

### Run it

```powershell
.\.venv\Scripts\python.exe -m tools.ui_qt --profile live
```

In the window: **Pick window** → **Select area** → **Start**. On Windows you can
also just double-click `livedub.bat`.

> **If your Windows has Smart App Control switched on.** It ships in
> *evaluation* mode and Windows switches it off by itself as soon as it sees
> developer tools being run — and once off it cannot be switched back on without
> reinstalling Windows. So this is a minority of machines, not the normal case.
> On one where it is still on, {{SAC_BLOCKED_LIST}}

---

## The window

{{TABS_COUNT}} tabs. **None of them has to be touched to hear the first line**:
they open when you need them.

| tab | what it is for |
|---|---|
| **Setup** | the steps in order — the only tab you need before Start |
| **Session** | who is speaking, right now, one colour per character |
| **Voice** | which engine, how many voices in the pool, how long to wait before deciding who is speaking |
| **Levels** | how far the game ducks and how far our voice comes up, **while you listen** |
| **Translation** | only for playing a game whose subtitles are not in your language |
| **All settings** | the {{PARAMS_TOTAL}} parameters, with a search box |

<img src="assets/menta-preparazione.png" alt="the Setup tab" width="440"> <img src="assets/menta-volumi.png" alt="the Levels tab" width="440">

**The Session tab is not a log.** At the top, the line being spoken right now
with its voice and its hurry; then who has spoken, one card per character; the
log underneath. The question you ask yourself watching it is not *what did it
say* but **is it still the same person talking?** — and a colour answers that
long before a label does.

**The parameters.** {{PARAMS_TOTAL}} in total; **{{PARAMS_HOT}} apply straight
away**, and the {{PARAMS_COLD}} that are only read at startup **say so** instead
of pretending. {{PARAMS_WITH_HELP}} carry a `?` that explains what they do, what
was measured and what you risk by changing them — and it is the same text that
sits beside the parameter inside [`core/config.py`](core/config.py), not a
second copy nobody updates.

**The two languages are two different things, and they sit two tabs apart on
purpose.** `ui.lingua`, in Setup, decides what is **written on the buttons**;
`translate.source` and `translate.target`, in Translation, decide what is
**said**. Mixing them up costs you a session.

---

## Will it work with my game?

Tested on {{GAMES_TESTED}}. Honestly, that is what is known.

**Always needed**, for any game: dragging the area around the subtitles, and
clearing the *ignore coloured subtitles* box if the game colours the speaker's
name.

**Good odds of working straight away** if the game writes **light text on a dark
background**, on a line near the bottom.

**Worth a try** if it writes dark text on a light background: on purpose-built
frames it reads, but it smudges. No one has ever tried it on a real game like
that.

**Not planned**: subtitles inside speech bubbles that follow the character, or
positions that move from one line to the next.

**And it does not translate the whole screen: it reads one subtitle line at a
time**, inside the box you drag around it. That is a choice, not a gap — the
whole chain is built on that shape.

**About the area, the thing people get backwards.** Drag it wide and the program
**still reads**: a large area is less precise, not mute. What actually gets
worse is the drawing — the translated line is drawn by rebuilding the background
around it, and the taller the area, the more unrelated scenery that rebuild
picks up. Past a certain height the program tells you so, while you are dragging
the rectangle and again when you start.

---

## Languages

**Reading**: whatever the recogniser can read.

**Speaking**, with the voices that are wired up today:

{{VOICE_LANGUAGES_TABLE}}

Beyond the number of native voices, characters are told apart by shifting the
pitch — that is what you hear in the first GIF. **And the menu says so when a
voice is missing**: translating into a language you have no voice for would not
raise an error — you would get a voice from another language pronouncing it,
which is a model phonemised by the wrong rules, with audio coming out and the
logs all green.

**Translation** *(off by default)*:

{{TRANSLATION_BACKENDS_TABLE}}

> **Something no counter shows.** On coarse language, local models **rewrite it
> in silence**. The translation succeeds beautifully: it says something else.
> Before asking whether a translator is good, ask whether it says what is
> written.

**The interface language** is a third thing again: {{UI_LANGUAGES_COUNT}},
generated once and committed into the repo — not asked from the network while
the window opens, because a window that asks the network for its own text is a
blank window when the network is not there, *and blank without an error*.

---

## How it is built, and why the numbers can be trusted

There is no pytest: the suite is a runnable module, **{{SELFTEST_CHECKS}}
checks** in {{SELFTEST_GROUPS}} groups.

```powershell
.\.venv\Scripts\python.exe -m tools.selftest
```

And there is the bench, which runs **the very same chain** over a recording,
without the game: same code, real OCR, real audio, real fingerprint, real
synthesis, and causality respected — the chain never sees the future.

```powershell
.\.venv\Scripts\python.exe -m tools.dub recording.mp4 --profile gtav --mp4
```

**But the bench is not enough, by construction**, and here that is a rule
written in blood: on a virtual clock synthesis costs nothing and no frame is
ever dropped, so from there you can show *everything* except how fast it is.
Every serious defect in this project came out by running the chain for real.

The measurements that changed a decision are written **next to the parameter
they decided**, inside [`core/config.py`](core/config.py) — the same text the
window shows when you press `?`.

*The code, its comments and the documents under `docs/` are in Italian. This
README and the [showcase](https://pigro141.github.io/livedub/) are in English.*

---

## Support the project

livedub is free, runs entirely on your own machine and has neither accounts nor
servers: there is nothing to sell and no data to collect. If you find it useful:

**[☕ Buy me a token!](https://ko-fi.com/filippodebenedittis)**

It unlocks no features and lifts no limits — there are none.

---

## Licence

**GPL-3.0-or-later**, and not out of taste: the default speech synthesiser and
the grapheme-to-phoneme engine behind one of the others are GPL-3, so anything
distributed here is too. The full accounting, library by library, is in
[`docs/LICENZE.md`](docs/LICENZE.md) — including why the OCR and the model
weights are **not** redistributed.
