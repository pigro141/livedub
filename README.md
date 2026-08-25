<div align="center">

<img src="assets/logo/livedub-256.png" alt="livedub" width="128">

# livedub

**Live dubbing for a video game's subtitles.**
It reads the text on screen while you play, works out who is speaking from the
game's audio, synthesises the line in that character's voice and mixes it over
the game. All on your own machine.

![licence](https://img.shields.io/badge/licence-GPL--3.0--or--later-2b8a6b)
![windows](https://img.shields.io/badge/Windows-10%20%7C%2011-2b8a6b)
![python](https://img.shields.io/badge/Python-3.11-2b8a6b)
![network](https://img.shields.io/badge/network-not%20needed-2b8a6b)
![checks](https://img.shields.io/badge/checks-1932-2b8a6b)
![interface languages](https://img.shields.io/badge/interface%20languages-42-2b8a6b)
![spoken languages](https://img.shields.io/badge/spoken%20languages-2-b8860b)
![gpu](https://img.shields.io/badge/NVIDIA%20GPU-optional-6b7280)
![version](https://img.shields.io/badge/version-0.9.0-b8860b)

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
| **Speaks 42 languages** *(the interface)* | follows your Windows language, and changes without a restart |

---

## How you use it, in the order you meet it

There is nothing to configure first: you open it and follow along.

**1. You open it.** The window is already in the language you use Windows in —
42 languages. Arabic, Hebrew, Persian and Urdu also flip the window
the other way round.

**2. A guide takes you through it**, 7 steps, and it comes back
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
500 ms of game audio is what it takes to know who is talking
before choosing a voice.

---

## What happens inside

```mermaid
flowchart TD
    subgraph W["the wait · 500 ms · speaker.decide_after_ms"]
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

| | piper, on CPU | kokoro, on CUDA | kokoro on CUDA, translation on |
|---|---|---|---|
| lines dubbed | 44 | 146 | **589**, in one 44-minute session |
| **subtitle → voice**, median | **665 ms** | **1290 ms** | **1421 ms** |
| synthesis, median | 57 ms | 580 ms | 248 ms |
| speech compression, median | **1.00** — none at all | **1.00** — none at all | **1.00** — none at all |
| `underrun` — lines you did not hear | **0** | **0** | **0** |
| subtitle reads per second | not recorded | 15.3 | 18.8 |
| the session it comes from | `runs/2026-08-11_18-31-55` | `runs/2026-08-20_00-01-56` | `runs/2026-08-07_01-40-16` |

**The figure that is worth more than any latency: not one `underrun`, in any of
the 53 live sessions** in `runs/` that used one of the three current engines.
And the Piper column is not a lucky pass — four sibling sessions the same
evening gave 664, 669, 687 and 687 ms.

**Where the time actually goes, once the engine is fast.** Of Kokoro's latency,
about **500 ms is the wait to find out who is speaking** — more than the
synthesis itself. That is the number to attack if you want it quicker, and the
price of lowering it is getting the speaker wrong more often, which only your
ear can judge.

**How many cores an engine needs.** This one comes from the bench and is not a
latency: it is the **cost of synthesising one line** with everything else held
equal, timed on the wall clock while the process is restricted to fewer cores.
It is a **lower bound** on how much an older PC would slow down — it simulates
fewer cores, not slower ones.

| physical cores | one Piper line, median | p95 | against 8 cores |
|---|---|---|---|
| 8 | **78 ms** | 144 ms | 1.00× |
| 6 | **88 ms** | 236 ms | 1.12× |
| 4 | **302 ms** | 544 ms | **3.85×** |
| 2 | 363 ms | 1050 ms | 4.63× |

**The cliff is between 6 and 4 cores**, and that is why the table below asks for
6 rather than 8: the step from 8 to 6 costs 12%, the step from 6 to 4 costs
nearly four times. Only Piper was measured this way, so this README puts no
number on the heavier engines — the bench in the setup guide measures them on
*your* machine, which is the answer that matters anyway.

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

| | runs on | runs better on |
|---|---|---|
| CPU | 6 physical cores | 8 physical cores |
| GPU | **none** — nothing breaks without one | any NVIDIA with about 2 GB of free VRAM: the measured need is **1128 MB** |
| RAM | 8 GB | 16 GB |
| disk | **1.6 GB** — the environment without the CUDA libraries, plus 225 MB of models | **3.5 GB** — with the CUDA libraries and 543 MB of models. Offline translation adds **3.2 GB** on top of either |
| Windows | **10** — capture goes through `PrintWindow`, which lives in `user32.dll` and needs nothing installed | **11** — OneOCR only exists there, and it reads the outlined text of a game far better |
| Python | 3.11 | 3.11 |
| **what you get** | **Piper on CPU.** 665 ms from subtitle to voice, no underruns, no speeding the speech up. The recogniser is PP-OCR. | **Kokoro on CUDA**: better articulation, and the only non-Italian voices in the product. 1290 ms. |
| **what the step buys** | below 6 cores Piper's synthesis goes from 88 ms to **302 ms** — see the table above | the graphics card buys **3.5× on synthesis** (741 ms down to 213 ms) and the six English voices |

**A requirement cannot be read without the machine it was measured on**, so here
it is: an Intel Core i9-11900K (8 physical cores), an **RTX 4060 with 8 GB** —
*with GTA V running on it at the same time* — 31.8 GB of RAM, Windows 11 Pro
build 26200, Python 3.11.9. Every number in this README comes from that machine
unless it says otherwise, and the *runs better on* column is not a wish list: it
is that machine.

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
> On one where it is still on, it blocks exactly **two packages, and they
> are one capability**: Windows Graphics Capture. Capture then falls back to
> `PrintWindow`, which needs nothing installed. **Everything else keeps
> working** — reading the subtitles, working out who is speaking, all three
> synthesis engines, the mixer, the overlay, offline translation and the window
> itself. Any PyInstaller executable is blocked too, this project's included:
> every build is a new file, and a new file has no reputation by construction.

---

## The window

Six tabs. **None of them has to be touched to hear the first line**:
they open when you need them.

| tab | what it is for |
|---|---|
| **Setup** | the steps in order — the only tab you need before Start |
| **Session** | who is speaking, right now, one colour per character |
| **Voice** | which engine, how many voices in the pool, how long to wait before deciding who is speaking |
| **Levels** | how far the game ducks and how far our voice comes up, **while you listen** |
| **Translation** | only for playing a game whose subtitles are not in your language |
| **All settings** | the 170 parameters, with a search box |

<img src="assets/menta-preparazione.png" alt="the Setup tab" width="440"> <img src="assets/menta-volumi.png" alt="the Levels tab" width="440">

**The Session tab is not a log.** At the top, the line being spoken right now
with its voice and its hurry; then who has spoken, one card per character; the
log underneath. The question you ask yourself watching it is not *what did it
say* but **is it still the same person talking?** — and a colour answers that
long before a label does.

**The parameters.** 170 in total; **131 apply straight
away**, and the 39 that are only read at startup **say so** instead
of pretending. 127 carry a `?` that explains what they do, what
was measured and what you risk by changing them — and it is the same text that
sits beside the parameter inside [`core/config.py`](core/config.py), not a
second copy nobody updates.

**The two languages are two different things, and they sit two tabs apart on
purpose.** `ui.lingua`, in Setup, decides what is **written on the buttons**;
`translate.source` and `translate.target`, in Translation, decide what is
**said**. Mixing them up costs you a session.

---

## Will it work with my game?

Tested on two: **GTA V** and **Mafia: The Old Country**, both in Italian. Honestly, that is what is known.

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

Three different things get called *language* here, they are set in three
different places, and merging them is how a program ends up promising what it
does not have.

| | how many | where you set it |
|---|---|---|
| what the **buttons** are written in | **42** | `ui.lingua`, in the Setup tab |
| what it can **translate a subtitle into** | **133** with the online backend — the offline ones have no closed list | `translate.target`, in the Translation tab |
| what it can **say out loud** | **2** — Italian, and English on one engine | it follows the engine you pick |

> **The interface speaks 42 languages, the translator reaches 133, and the mouth
> speaks 2.** That last number is the one to read twice, because it is the one
> that decides whether this program is useful to you: **Italian with any engine,
> English only with Kokoro** — which needs an NVIDIA card. There is no third
> language, and nothing on the way.

**Reading**: whatever the recogniser can read.

**Speaking**, with the voices that are wired up today:

| engine | languages with a real voice | how many voices | runs on |
|---|---|---|---|
| **piper** *(default)* | **Italian only** | 2 native (`paola`, `riccardo`), taken to 8 in the pool by shifting the pitch | CPU |
| **supertonic** | **Italian only** | 10 native (M1–M5, F1–F5) — no shifting needed | CPU |
| **kokoro** | **Italian and English** | Italian 2, shifted to 8; English **6 native** | CUDA |
| `tone`, `silent` | none — a beep has no language | — | — |

> **Asking for a language with no voice does not raise an error**, and this is
> the trap worth stating plainly. Measured: ask Kokoro for Japanese and you get
> eight voices back — the six English ones and the two Italian ones — reading
> Japanese text. What comes out is a model phonemised by the wrong rules: the
> audio plays, the counters stay green, the test suite stays green. What exists
> is a **declaration, not a block**: the menu marks the choice as having no
> voice, and then lets you make it.

Beyond the number of native voices, characters are told apart by shifting the
pitch — that is what you hear in the first GIF: `[nicola]` and `[nicola-2_5]`
are one voice at two pitches.

**Translation** *(off by default)*:

| backend | network | how many languages | worth knowing |
|---|---|---|---|
| **`locale`**, Argos *(default)* | **no** | no closed list: whichever pairs Argos publishes, downloaded when you press Start | does not understand `auto` — it quietly becomes *from English* |
| `llm`, Gemma 3 1B in this same process | **no** | depends on the model you point it at | same `auto` caveat |
| `ollama`, TranslateGemma outside the environment | **no**, but a local server has to be running | depends on the model | the slowest in practice: the live sessions using it sit at 1592–1805 ms end to end |
| `google` | **yes**, and the program says so every time | **133** — the only closed list of the four | the only one that understands `auto` |

The menu **shows all four and declares** rather than filtering: three of them
have no closed list, so a filter would hide choices that work and let through
choices that do not, with the air of knowing.

> **Something no counter shows.** On coarse language, local models **rewrite it
> in silence**. The translation succeeds beautifully: it says something else.
> Before asking whether a translator is good, ask whether it says what is
> written.

**The interface language** is a third thing again: **42** — 41 catalogs plus
Italian, which is the language the source is written in. All 41 are **complete,
254 strings out of 254**, with none half-translated; four of them run right to
left and turn the whole window round (Arabic, Hebrew, Persian, Urdu). They are
generated once and committed into the repo — not asked from the network while
the window opens, because a window that asks the network for its own text is a
blank window when the network is not there, *and blank without an error*.

What is **not** translated, on purpose: the explanations behind the `?` on each
parameter. They come from the comments in
[`core/config.py`](core/config.py) with the measurements inside them, and
running a measurement through a machine translator is how a measurement quietly
stops being one. The log and the measurement bar stay in Italian for the same
reason — they are numbers and device names.

---

## What it does not do

The quickest way to be disappointed by a program is to find this list out by
using it. So here it is before you install.

| | |
|---|---|
| **It speaks two languages** | Italian with any engine, English only with Kokoro on an NVIDIA card. A third language does not raise an error — you get an Italian or English voice pronouncing it with the wrong rules. |
| **One subtitle line at a time** | inside the box you drag: not the whole screen, not several areas at once. An earlier version promised several reading areas and it was removed, because the overlay draws one line at a time and the promise could not be kept live. |
| **The game must be windowed or borderless** | exclusive fullscreen is not captured. |
| **Windows only** | and the recogniser that reads a game's outlined text best, OneOCR, exists only on Windows 11. On Windows 10 you get PP-OCR. |
| **The voice arrives after the subtitle** | about half a second of it is the wait for enough game audio to say who is speaking — and that wait, not the synthesis, is the largest single piece of the delay. |
| **More characters than voices share one** | past the number of native voices they are told apart by shifting the pitch, and you can hear it. |
| **One player, one window** | it is not a streaming tool, not a localisation pipeline and not multiplayer. |

**Where the capture can fail.** It grabs the game's window through Windows
Graphics Capture where that is available, and falls back to `PrintWindow` —
**saying so in the log** — where it is not. The fallback needs nothing
installed, but it is synchronous and costs more: **17.5 ms** for a 1191×958
window, measured. And on a game drawing through a Direct3D flip-model swap
chain, `PrintWindow` can **succeed and hand back a black frame**; the program
inspects the first eight frames and declares it instead of quietly reading
black. **Nobody has yet tried that fallback on GTA V itself.**

> **And the honest frame around every number here.** They were measured on one
> machine, on two games, by one person. Where a figure has not been measured,
> this README leaves the gap visible instead of filling it.

---

## How it is built, and why the numbers can be trusted

There is no pytest: the suite is a runnable module, **1932
checks** in 75 groups.

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
