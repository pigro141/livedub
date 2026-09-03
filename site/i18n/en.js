/* ===========================================================================
   livedub — la pagina, in inglese.

   Questo file e' **l'originale**: insieme la struttura della vetrina e il suo
   testo. `index.html` non contiene una parola, e gli altri cataloghi in questa
   cartella sono dizionari `{ stringa inglese -> stringa tradotta }` che gli
   stanno sopra. La chiave e' l'inglese, come in `ui/lingua.py` la chiave e' la
   stringa italiana del sorgente: nessun identificatore da inventare, e una
   stringa nuova compare fra le mancanti invece di sparire.

   ## I segnaposto

   `{{COSI_MAIUSCOLO}}` (fra doppie graffe) e' un dato che **non e' ancora stato misurato**, e a schermo si
   vede: riquadro tratteggiato color ambra. Non c'e' nessun numero di esempio in
   questo file, e non ce ne devono entrare. In questo repo un errno scritto a
   mano e' gia' finito in una schermata ed e' stato riletto come una misura —
   un numero finto in una vetrina e' peggio: lo legge chi decide se installare.

   Adesso non ne resta **nessuno**: `{{DOWNLOADS}}` e' stato riempito il giorno
   in cui la costruzione in CI ha aperto l'eseguibile e lo ha provato da
   dentro. Un segnaposto nuovo entra qui solo con la stessa regola.

   ## Il markup ammesso dentro una stringa

   `<b>`, `<i>`, `<code>`, `<a href>`. Niente altro: chi traduce copia i tag
   dov'erano e traduce cio' che ci sta in mezzo.
   =========================================================================== */

(function () {
  var L = (window.LIVEDUB = window.LIVEDUB || {});

  L.pagina = {
    nome: "livedub",
    titoloPagina: "livedub — live dubbing for game subtitles",
    descrizione: "livedub reads a game's on-screen subtitles while you play, works out who is speaking from the audio, synthesises the line with that character's voice and mixes it over the game. All on your own machine, on Windows.",

    /* ------------------------------------------------------------------ */
    testata: {
      logo: "assets/logo/livedub-256.png",
      logoAlt: "the livedub logo",
      titolo: "livedub",
      occhiello: "It reads the subtitles on screen while you play, works out <b>who is speaking</b> from the game's audio, synthesises the line in that character's voice and mixes it over the game.",
      sotto: "Everything runs on your own machine, on Windows. No account, no server, nothing to extract from the game: it watches the screen and plays into your headphones, the way a player does.",
      marche: [
        "GPL-3.0-or-later",
        "Windows <b>10 · 11</b>",
        "Python <b>3.11</b>",
        "the network is <b>not needed</b>",
        "the interface speaks <b>42 languages</b>",
        "it speaks out loud in <b>53 languages</b>",
        "NVIDIA GPU <b>optional</b>"
      ],
      bottoni: [
        { x: "See it and hear it", href: "#watch", pieno: true },
        { x: "Code on GitHub", href: "https://github.com/pigro141/livedub" },
        { x: "Install it", href: "#install" }
      ],
      immagine: {
        chiaro: "assets/menta-anteprima-chiaro.png",
        scuro: "assets/menta-anteprima.png",
        alt: "the livedub window during a game"
      }
    },

    /* ------------------------------------------------------------------ */
    sezioni: [
      {
        id: "watch",
        nav: "See it",
        etichetta: "See it",
        titolo: "The full clips, with the sound",
        lede: "Turn the volume up. GitHub cannot play these in a README, and that is the reason this page exists: a program that <b>speaks</b> cannot be shown by a silent GIF.",
        blocchi: [
          {
            t: "video",
            src: "assets/vetrina/doppiaggio-gtav.mp4",
            poster: "assets/vetrina/doppiaggio-gtav-poster.jpg",
            x: "<b>The dubbing, on GTA V.</b> The black band on top is the text <b>as the OCR read it</b>, with the voice that was assigned to it. It is there to tell <i>misread</i> apart from <i>mispronounced</i>, and it is how every listening test in this project is delivered. You can hear the voice change between two characters — <code>[nicola]</code> and <code>[nicola-2_5]</code> are the same voice at two pitches."
          },
          {
            t: "video",
            src: "assets/vetrina/trailer-multilingua.mp4",
            poster: "assets/vetrina/trailer-multilingua-poster.jpg",
            x: "<b>Four languages, one scene.</b> The same thirteen seconds of the GTA VI trailer, dubbed four times. The official subtitles were <b>burned into the picture</b> the way GTA V writes them — font size and position measured off a real frame of the game, not guessed — and the chain read them back out of the pixels. Nothing is translated here: each pass reads the subtitle already written in that language and speaks it with a Kokoro voice <b>of that language</b>. A name in the black band — <code>[nicola-2_5]</code>, <code>[es_santa]</code> — means the fingerprint has confirmed <b>who</b> is talking. The stretch is a phone call on purpose: the fingerprint needs somebody who speaks for a while, and where the lines last a second the honest answer stays <code>[neutra]</code>, <i>I do not know yet who is talking</i>."
          },
          {
            t: "video",
            src: "assets/vetrina/traduzione-overlay.mp4",
            poster: "assets/vetrina/traduzione-overlay-poster.jpg",
            x: "<b>Translation, drawn over the game</b> — Italian into English here. The original subtitle is <b>erased by rebuilding the background</b> behind it, not covered with a rectangle, and the translated line takes its place with the size and colour <b>copied from the game</b>. Translation is a separate feature, <b>off by default</b>."
          },
          {
            t: "video",
            src: "assets/vetrina/finestra-menta.mp4",
            poster: "assets/vetrina/finestra-menta-poster.jpg",
            muto: true,
            x: "<b>The window while it works.</b> One colour per character in the log, and the measurement bar along the bottom: reads per second, lines, latency, compression, underruns and the reading area. The question you ask yourself watching it is not <i>what did it say</i> but <b>is it still the same person talking?</b> — and a colour answers that long before a label does. <span class=\"muto\">This one has no sound: it is only the window.</span>"
          },
          {
            t: "nota",
            righe: [
              "<b>One thing worth saying about these clips.</b> They are made by running <b>the very same chain</b> over a recording: same code, real OCR, real audio, real voice fingerprint, real synthesis, real mixer, and causality is respected — the chain never sees the future. It is not a simulation.",
              "<b>But the bench gives time away.</b> On a virtual clock synthesis costs nothing and no frame is ever dropped, so a clip like this can show everything <b>except how fast it is</b>. Every latency figure on this page comes from a live session with the game running, and says which one."
            ]
          }
        ]
      },

      {
        id: "how",
        nav: "How it works",
        etichetta: "How you use it",
        titolo: "In the order you meet it",
        lede: "There is nothing to configure first: you open it and follow along.",
        blocchi: [
          {
            t: "passi",
            voci: [
              {
                b: "You open it.",
                p: "The window is already in the language you use Windows in — 42 languages in total, and every one of the 41 catalogs is complete: 258 strings out of 258, none of them half-done. Arabic, Hebrew, Persian and Urdu also flip the window the other way round."
              },
              {
                b: "A guide takes you through it, in 7 steps.",
                p: "It opens by itself the first time and comes back with <code>?</code>. Wherever it can it <b>checks instead of telling</b>: it counts the audio devices you actually have, it asks ONNX Runtime whether CUDA is really there instead of assuming, and it measures the height of your reading area with the real rule."
              },
              {
                b: "A bench measures this PC and picks the engines.",
                p: "It is not a convenience: <b>a model that is missing does not raise an error</b>. Programs are installed once, models are not — they are fetched on first use, and if they do not arrive the chain falls back to something lighter and carries on. Without this step you would be listening to the fallback without knowing. The bench measures, picks, downloads what is missing, and <b>installs no programs</b>: if one is missing it hands you the exact line to paste."
              },
              {
                b: "You pick the game's window.",
                p: "It captures <b>one window</b>, not the screen: nothing else can end up in the frame that goes to the OCR — not even our own windows. The game has to run windowed or borderless, not in exclusive fullscreen."
              },
              {
                b: "You drag a box around the subtitle line.",
                p: "Two seconds with the mouse. The area is <b>relative to the window</b>, so if you move the game, the area follows it."
              },
              {
                b: "Start.",
                p: "From there it reads, works out who is speaking, synthesises and mixes. The voice always arrives a little after the subtitle, and that is deliberate: <b>500 ms</b> of game audio is what it takes to know who is talking before choosing a voice."
              }
            ]
          },
          {
            t: "griglia",
            voci: [
              { img: "assets/guida-1.png", alt: "the first step of the guide: the interface language" },
              { img: "assets/guida-4.png", alt: "the guide step about the reading area" },
              { img: "assets/guida-banco.png", alt: "the bench measuring the PC and picking the engines" },
              { img: "assets/guida-banco-rotto.png", alt: "the bench declaring what did not arrive" }
            ]
          },
          {
            t: "p",
            x: "The panel turns amber when something did <b>not</b> arrive. <i>No graphics card</i> is a fact; <i>asked for the GPU and got the CPU</i> is not, and giving them the same green tick would be a silent fallback put on display."
          }
        ]
      },

      {
        id: "window",
        nav: "The window",
        etichetta: "The window",
        titolo: "Six tabs, and none of them has to be touched to hear the first line",
        lede: "They open when you need them.",
        blocchi: [
          {
            t: "tabella",
            testa: ["tab", "what it is for"],
            righe: [
              ["<b>Setup</b>", "the steps in order — the only tab you need before Start"],
              ["<b>Session</b>", "who is speaking, right now, one colour per character"],
              ["<b>Voice</b>", "which engine, how many voices in the pool, how long to wait before deciding who is speaking"],
              ["<b>Levels</b>", "how far the game ducks and how far our voice comes up, <b>while you listen</b>"],
              ["<b>Translation</b>", "only for playing a game whose subtitles are not in your language"],
              ["<b>All settings</b>", "the 170 parameters, with a search box"]
            ]
          },
          {
            t: "griglia",
            voci: [
              { img: "assets/menta-preparazione.png", alt: "the Setup tab" },
              { img: "assets/menta-volumi.png", alt: "the Levels tab" },
              { img: "assets/menta-traduzione.png", alt: "the Translation tab" },
              { img: "assets/menta-anteprima.png", alt: "the window during a game" }
            ]
          },
          {
            t: "p",
            x: "<b>The parameters.</b> 170 of them; <b>131 apply straight away</b>, and the 39 that are only read at startup <b>say so</b> instead of pretending. 127 of them carry a <code>?</code> that explains what they do, what was measured, and what you risk by changing them — and it is the same text that sits beside the parameter inside <code>core/config.py</code>, not a second copy nobody updates."
          },
          {
            t: "p",
            x: "<b>The bar along the bottom</b> reports reads per second, lines, median latency, compression, underruns and the reading area, <b>twice a second</b> — not thirty times, because a number that flickers is a number nobody reads. The only red one is <code>underrun</code>, and it is not a number out of range: it is a line you did not hear."
          },
          {
            t: "nota",
            ambra: true,
            x: "<b>The two languages are two different things, and they sit two tabs apart on purpose.</b> <code>ui.lingua</code>, in Setup, decides what is <b>written on the buttons</b>; <code>translate.source</code> and <code>translate.target</code>, in Translation, decide what is <b>said out loud</b>. Mixing them up costs you a session: you put <code>en</code> in the wrong place believing you have turned translation on, and the chain keeps dubbing in the original language."
          }
        ]
      },

      {
        id: "numbers",
        nav: "The numbers",
        etichetta: "The numbers",
        titolo: "And which session they come from",
        lede: "Live sessions only, with the game running. None of these come from the bench, for the reason written further up.",
        blocchi: [
          {
            t: "tabella",
            testa: ["", "piper, on CPU", "kokoro, on CUDA", "kokoro on CUDA, translation on"],
            righe: [
              ["lines dubbed", "44", "146", "<b>589</b>, in one 44-minute session"],
              ["<b>subtitle → voice</b>, median", "<b>665 ms</b>", "<b>1290 ms</b>", "<b>1421 ms</b>"],
              ["synthesis, median", "57 ms", "580 ms", "248 ms"],
              ["speech compression, median", "<b>1.00</b> — none at all", "<b>1.00</b> — none at all", "<b>1.00</b> — none at all"],
              ["<code>underrun</code> — lines you did not hear", "<b>0</b>", "<b>0</b>", "<b>0</b>"],
              ["subtitle reads per second", "not recorded", "15.3", "18.8"],
              ["the session it comes from", "<code>runs/2026-08-11_18-31-55</code>", "<code>runs/2026-08-20_00-01-56</code>", "<code>runs/2026-08-07_01-40-16</code>"]
            ]
          },
          {
            t: "p",
            x: "<b>The figure that is worth more than any latency: not one <code>underrun</code>, in any of the 53 live sessions</b> in <code>runs/</code> that used one of the three current engines. And the Piper column is not a lucky pass — four sibling sessions the same evening gave 664, 669, 687 and 687 ms."
          },
          {
            t: "p",
            x: "Two engines is two choices, not a quality ladder: one is faster, the other articulates better — and it is the bench in the setup guide that says which of them holds up on a given machine."
          },
          {
            t: "nota",
            x: "<b>Where the time actually goes, once the engine is fast.</b> Of Kokoro's latency, about <b>500 ms is the wait to find out who is speaking</b> — more than the synthesis itself. That is the number to attack if you want it quicker, and the price of lowering it is getting the speaker wrong more often, which only your ear can judge."
          },
          { t: "h3", x: "How many cores an engine needs" },
          {
            t: "p",
            x: "This one comes from the bench and <b>is not a latency</b>: it is the cost of synthesising one line with everything else held equal, timed on the wall clock while the process is restricted to fewer cores. It is a <b>lower bound</b> on how much an older PC would slow down — it simulates fewer cores, not slower ones."
          },
          {
            t: "tabella",
            testa: ["physical cores", "one Piper line, median", "p95", "against 8 cores"],
            righe: [
              ["8", "<b>78 ms</b>", "144 ms", "1.00×"],
              ["6", "<b>88 ms</b>", "236 ms", "1.12×"],
              ["4", "<b>302 ms</b>", "544 ms", "<b>3.85×</b>"],
              ["2", "363 ms", "1050 ms", "4.63×"]
            ]
          },
          {
            t: "p",
            x: "<b>The cliff is between 6 and 4 cores</b>, and that is why the recommended machine below says 6 rather than 8: the step from 8 to 6 costs 12%, the step from 6 to 4 costs nearly four times. Only Piper was measured this way, so this page puts no number on the heavier engines — the bench in the guide measures them on <i>your</i> machine, which is the answer that matters anyway."
          }
        ]
      },

      {
        id: "privacy",
        nav: "Privacy",
        etichetta: "Privacy",
        titolo: "It all runs on your machine",
        lede: "That is not a slogan, it is the list of what leaves the computer.",
        blocchi: [
          {
            t: "tabella",
            testa: ["", "does anything leave?"],
            righe: [
              ["reading the subtitles (OCR)", "<b>no</b> — on your machine"],
              ["who is speaking (voice fingerprint)", "<b>no</b> — on your machine"],
              ["synthesising the voice", "<b>no</b> — on your machine"],
              ["translating with the offline backends", "<b>no</b>"],
              ["translating with the online backend", "<b>yes</b>, and the program says so every time"],
              ["downloading the models", "<b>once</b>, on first use"]
            ]
          },
          {
            t: "p",
            x: "The only way to send text out is to pick the online translator on purpose. No telemetry, no account, no connection to a server of ours — there is no server of ours."
          }
        ]
      },

      {
        id: "install",
        nav: "Install",
        etichetta: "Requirements and install",
        titolo: "What it takes, and how to get it running",
        blocchi: [
          {
            t: "p",
            x: "<b>The recommended way is to install from source</b>, with the PowerShell script below: it is the one that works on every machine, and it has not changed."
          },
          {
            t: "p",
            x: "<b>There is also an executable, and it has been launched.</b> Every push builds it on GitHub Actions and then <i>runs</i> it: inside the package it reads a drawn subtitle, synthesises a line and builds the window, and the artifact is uploaded only if all of that passes. It is the <code>livedub-windows</code> artifact at the foot of the <a href=\"https://github.com/pigro141/livedub/actions/workflows/eseguibile.yml\">latest green run</a>. Downloading an artifact needs a GitHub account, and each one is kept for 14 days."
          },
          {
            t: "p",
            x: "<b>Two limits, stated rather than hidden.</b> With <b>Smart App Control</b> on — and it is on by default on a clean Windows 11 install — the executable <b>does not start</b>: every build is a new file, and a new file has no reputation by construction. A signature lifts that; another test does not. And the build machine has no sound card, no graphics card and no game running, so screen capture, the audio loopback, mixing and synthesis on the GPU stay <b>unproven</b> — Smart App Control is off there too, so <i>it starts on the runner</i> does not mean <i>it starts on a freshly installed Windows 11</i>."
          },
          {
            t: "tabella",
            testa: ["", "runs on", "runs better on"],
            righe: [
              ["CPU", "6 physical cores", "8 physical cores"],
              ["GPU", "<b>none</b> — nothing breaks without one", "any NVIDIA with about 2 GB of free VRAM: the measured need is <b>1128 MB</b>"],
              ["RAM", "8 GB", "16 GB"],
              ["disk", "<b>1.6 GB</b> — the environment without the CUDA libraries, plus 225 MB of models", "<b>3.5 GB</b> — with the CUDA libraries and 543 MB of models. Offline translation adds <b>3.2 GB</b> on top of either"],
              ["Windows", "<b>10</b> — capture goes through <code>PrintWindow</code>, which lives in <code>user32.dll</code> and needs nothing installed", "<b>11</b> — OneOCR only exists there, and it reads the outlined text of a game far better"],
              ["Python", "3.11", "3.11"],
              ["<b>what you get</b>", "<b>Piper on CPU.</b> 665 ms from subtitle to voice, no underruns, no speeding the speech up. The recogniser is PP-OCR, and 50 of the 53 spoken languages are already here.", "<b>Kokoro on CUDA</b>: better articulation, and its 54 voices across 8 languages. 1290 ms."],
              ["<b>what the step buys</b>", "below 6 cores Piper's synthesis goes from 88 ms to <b>302 ms</b> — see the table above", "the graphics card buys <b>3.5× on synthesis</b> (741 ms down to 213 ms), and it is the only thing that lets a language move the engine onto kokoro: on the CPU that engine costs 741 ms a line, which is not liveable"]
            ]
          },
          {
            t: "p",
            x: "<b>A requirement cannot be read without the machine it was measured on</b>, so here it is: an Intel Core i9-11900K (8 physical cores), an <b>RTX 4060 with 8 GB</b> — <i>with GTA V running on it at the same time</i> — 31.8 GB of RAM, Windows 11 Pro build 26200, Python 3.11.9. Every number on this page comes from that machine unless it says otherwise, and the recommended column is not a wish list: it is that machine."
          },
          {
            t: "p",
            x: "<b>You also need</b> a way to hear the game's audio without your own dubbing looping back into it: the WASAPI loopback that ships with Windows is enough. <a href=\"https://vb-audio.com/Voicemeeter/\">Voicemeeter</a> is <b>optional</b> — it only helps if you want everything in a single pair of headphones."
          },
          { t: "h3", x: "Install" },
          {
            t: "codice",
            x: "git clone https://github.com/pigro141/livedub.git\ncd livedub\npowershell -ExecutionPolicy Bypass -File installa.ps1"
          },
          {
            t: "p",
            x: "The script <b>checks that it got what it asked for</b> instead of reporting success: Python, the virtual environment, the dependencies, the OCR, the real CUDA provider, the models — and it finishes by running the test suite. Whatever is missing is listed with the reason and what it costs you. Without an NVIDIA GPU, add <code>-SenzaGpu</code>."
          },
          {
            t: "p",
            x: "<b>The install is deliberately light, and one thing is deliberately left out of it.</b> Offline translation is <b>not installed</b>: it costs <b>3100 MB</b>, almost all of it <code>torch</code> — which the translation never uses, but without which its sentence splitter will not even import. Charging that to everyone who installs the program, for a feature that is <b>off by default</b>, is the opposite of a choice. It arrives <b>when you need it</b>: the bench in the guide looks at what is missing, <b>says how much it weighs before you decide</b>, and hands you the line to paste. It hands it over rather than running it, because those are <i>packages</i>, and a naïve <code>pip install</code> there pulls in the CPU build of ONNX Runtime and switches CUDA off in silence. If it does not arrive, that is a <b>declared refusal</b>, not a mute fallback. The language pair itself is a model, 98 MB, and that one the bench downloads on its own."
          },
          { t: "h3", x: "Run it" },
          { t: "codice", x: ".\\.venv\\Scripts\\python.exe -m tools.ui_qt --profile live" },
          {
            t: "p",
            x: "In the window: <b>Pick window</b> → <b>Select area</b> → <b>Start</b>. On Windows you can also just double-click <code>livedub.bat</code>."
          },
          {
            t: "nota",
            ambra: true,
            righe: [
              "<b>If your Windows has Smart App Control switched on.</b> It ships in <i>evaluation</i> mode and Windows switches it off by itself as soon as it sees developer tools being run — and once off it cannot be switched back on without reinstalling Windows. So this is a minority of machines, not the normal case.",
              "On a machine where it is still on, and installing the pinned versions in this repo, exactly <b>two packages are blocked and they are one capability</b>: Windows Graphics Capture. Capture then falls back to <code>PrintWindow</code>, which needs nothing installed. <b>Everything else keeps working</b> — reading the subtitles, working out who is speaking, all three synthesis engines, the mixer, the overlay, offline translation and the window itself. Any PyInstaller executable is blocked too, this project's included: every build is a new file, and a new file has no reputation by construction.",
              "<b>And where it does bite, the program says what fell and what to use instead.</b> A blocked library is not handed to you as a stack trace: there is one place that answers <i>can this piece load on this machine?</i>, it tells <i>you never installed it</i> apart from <i>it is here and Windows will not load it</i> — because the first is fixed with one <code>pip install</code> and the second is not — and the menus mark the choices that would fail, on the closed box and not only in the list, since the value that does not work is usually the one already in your configuration. The choice is <b>marked, not removed</b>: removing it would hide that the program can do it and that the defect belongs to this machine."
            ]
          },
          {
            t: "p",
            x: "<b>Why you can trust the numbers.</b> There is a test suite of <b>2195 checks</b> in 81 groups that runs without a game, without a GPU and without any model, and a bench that runs <b>the same chain</b> over a recording. The measurements that changed a decision are written <b>next to the parameter they decided</b>, inside <code>core/config.py</code> — which is the same text the window shows when you press <code>?</code>."
          }
        ]
      },

      {
        id: "games",
        nav: "Your game",
        etichetta: "Compatibility",
        titolo: "Will it work with my game?",
        lede: "Tested on two: <b>GTA V</b> and <b>Mafia: The Old Country</b>, both in Italian. Honestly, that is what is known.",
        blocchi: [
          {
            t: "p",
            x: "<b>Always needed</b>, for any game: dragging the area around the subtitles, and clearing the <i>ignore coloured subtitles</i> box if the game colours the speaker's name."
          },
          {
            t: "p",
            x: "<b>Good odds of working straight away</b> if the game writes <b>light text on a dark background</b>, on a line near the bottom."
          },
          {
            t: "p",
            x: "<b>Worth a try</b> if it writes dark text on a light background: on purpose-built frames it reads, but it smudges. No one has ever tried it on a real game like that."
          },
          {
            t: "p",
            x: "<b>Not planned</b>: subtitles inside speech bubbles that follow the character, or positions that move from one line to the next."
          },
          {
            t: "nota",
            x: "<b>And it does not translate the whole screen: it reads one subtitle line at a time</b>, inside the box you drag around it. That is a choice, not a gap — the entire chain is built on that shape. <i>An earlier version promised several reading areas at once: it was removed, because the overlay draws one line at a time and the promise could not be kept live.</i>"
          }
        ]
      },

      {
        id: "languages",
        nav: "Languages",
        etichetta: "Languages",
        titolo: "Three different things called language",
        lede: "What it can <b>read</b>, what it can <b>say</b>, and what the <b>buttons</b> are written in. They are set in different places, and they are worth keeping apart.",
        blocchi: [
          { t: "h3", x: "The short answer, before the detail" },
          {
            t: "tabella",
            testa: ["", "how many", "where you set it"],
            righe: [
              ["what the <b>buttons</b> are written in", "<b>42</b>", "<code>ui.lingua</code>, in the Setup tab"],
              ["what it can <b>translate a subtitle into</b>", "<b>133</b> with the online backend — the offline ones have no closed list", "<code>translate.target</code>, in the Translation tab"],
              ["what it can <b>say out loud</b>", "<b>53</b> — but not with every engine: 50 with piper, 31 with supertonic, 8 with kokoro", "you pick the language, and the engine follows it"]
            ]
          },
          {
            t: "nota",
            ambra: true,
            x: "<b>Three lists, three questions, and merging them is how a program ends up promising what it does not have.</b> The interface speaks 42 languages, the translator reaches 133, and the mouth speaks 53. That last number is not one number: <b>the three engines have different catalogues</b>, and picking a language is really picking an engine. Before the change that made it 53, the mouth spoke <b>two</b> — and that was never a limit of the engines, it was the only thing the code declared: translating into Spanish and then reading it out with an Italian voice produced <b>no error at all</b>."
          },
          { t: "h3", x: "What it can say" },
          {
            t: "tabella",
            testa: ["engine", "languages", "voices", "runs on", "how the voices work"],
            righe: [
              ["<b>piper</b> <i>— default</i>", "<b>50</b>", "175 models in the official index", "CPU", "one model per voice, one download each (28–114 MB)"],
              ["<b>supertonic</b>", "<b>31</b>", "10 speaker styles, valid in <i>every</i> language", "CPU", "one multilingual model; the language selects the phonemiser"],
              ["<b>kokoro</b>", "<b>8</b>", "54, language and gender encoded in the name", "CUDA", "one model, one 510 KB style file per voice"],
              ["<code>tone</code>, <code>silent</code>", "—", "a beep has no language", "—", "—"],
              ["<b>union</b>", "<b>53</b>", "", "", ""]
            ]
          },
          {
            t: "p",
            x: "<b>Which engine speaks which is the list below</b>, and it is not written by hand: it is regenerated from the engines' own catalogues by <code>tools/tabella_lingue.py</code>, and the test suite fails if it ever stops matching them. A character beyond the number of native voices is told apart by shifting the pitch, which is what you hear in the first clip: <code>[nicola]</code> and <code>[nicola-2_5]</code> are one voice at two pitches."
          },
          {
            t: "lingue",
            riassunto: "Open the full list, language by language",
            testa: ["code", "language", "piper", "supertonic", "kokoro"],
            /* Le righe qui sotto sono **generate**, e per questo non passano dal
               traduttore: si veda il blocco `lingue` in `site/livedub.js` e la
               testata di `tools/tabella_lingue.py`. */
            righe: [
/* lingue: inizio */
              /* generato da `tools/tabella_lingue.py`, non si scrive a mano */
              ["sq", "Albanian", "✓", "", ""],
              ["ar", "Arabic", "✓", "✓", ""],
              ["hy", "Armenian", "✓", "", ""],
              ["eu", "Basque", "✓", "", ""],
              ["bn", "Bengali", "✓", "", ""],
              ["bg", "Bulgarian", "✓", "✓", ""],
              ["ca", "Catalan", "✓", "", ""],
              ["zh", "Chinese (Simplified)", "✓", "", "✓"],
              ["hr", "Croatian", "", "✓", ""],
              ["cs", "Czech", "✓", "✓", ""],
              ["da", "Danish", "✓", "✓", ""],
              ["nl", "Dutch", "✓", "✓", ""],
              ["en", "English", "✓", "✓", "✓"],
              ["et", "Estonian", "✓", "✓", ""],
              ["fi", "Finnish", "✓", "✓", ""],
              ["fr", "French", "✓", "✓", "✓"],
              ["ka", "Georgian", "✓", "", ""],
              ["de", "German", "✓", "✓", ""],
              ["el", "Greek", "✓", "✓", ""],
              ["he", "Hebrew", "✓", "", ""],
              ["hi", "Hindi", "✓", "✓", "✓"],
              ["hu", "Hungarian", "✓", "✓", ""],
              ["is", "Icelandic", "✓", "", ""],
              ["id", "Indonesian", "✓", "✓", ""],
              ["it", "Italian", "✓", "✓", "✓"],
              ["ja", "Japanese", "", "✓", "✓"],
              ["kk", "Kazakh", "✓", "", ""],
              ["ko", "Korean", "✓", "✓", ""],
              ["ku", "Kurdish (Kurmanji)", "✓", "", ""],
              ["lv", "Latvian", "✓", "✓", ""],
              ["lt", "Lithuanian", "", "✓", ""],
              ["lb", "Luxembourgish", "✓", "", ""],
              ["ml", "Malayalam", "✓", "", ""],
              ["mr", "Marathi", "✓", "", ""],
              ["ne", "Nepali", "✓", "", ""],
              ["no", "Norwegian", "✓", "", ""],
              ["fa", "Persian", "✓", "", ""],
              ["pl", "Polish", "✓", "✓", ""],
              ["pt", "Portuguese", "✓", "✓", "✓"],
              ["ro", "Romanian", "✓", "✓", ""],
              ["ru", "Russian", "✓", "✓", ""],
              ["sr", "Serbian", "✓", "", ""],
              ["sk", "Slovak", "✓", "✓", ""],
              ["sl", "Slovenian", "✓", "✓", ""],
              ["es", "Spanish", "✓", "✓", "✓"],
              ["sw", "Swahili", "✓", "", ""],
              ["sv", "Swedish", "✓", "✓", ""],
              ["te", "Telugu", "✓", "", ""],
              ["tr", "Turkish", "✓", "✓", ""],
              ["uk", "Ukrainian", "✓", "✓", ""],
              ["ur", "Urdu", "✓", "", ""],
              ["vi", "Vietnamese", "✓", "✓", ""],
              ["cy", "Welsh", "✓", "", ""]
/* lingue: fine */
            ]
          },
          {
            t: "p",
            x: "The names in that list stay in English in every language of this page: they are data read from the code, like a device name or a model key. A language name run through a machine translator is how <code>uk — Ucraino</code> once became «Regno Unito — ucraino» inside the window."
          },
          { t: "h3", x: "What is claimed, and what was actually tested" },
          {
            t: "p",
            x: "This matters more than the numbers. <b>Claimed, and verifiable from the catalogue</b>: that a voice <i>exists</i> and that it <i>belongs to that language</i>. Each engine publishes it — piper in <code>rhasspy/piper-voices/voices.json</code>, kokoro in the first letter of every voice name, supertonic in its list of supported languages. Nothing there is guessed."
          },
          {
            t: "nota",
            ambra: true,
            x: "<b>Not claimed: that the pronunciation is good.</b> Nobody has listened to 53 languages, and saying otherwise would be a promise no measurement backs."
          },
          {
            t: "p",
            x: "<b>Checked mechanically instead</b>: for a sample of languages one sentence is synthesised <i>in that language's own script</i> and the result is checked for a plausible <b>speaking rate</b> — characters of speech per second. A wrong phonemisation does not raise: the model answers, audio comes out, every counter stays green, and an out-of-scale rate is the only trace it leaves."
          },
          {
            t: "tabella",
            testa: ["engine", "languages measured", "outcome"],
            righe: [
              ["<b>supertonic</b>", "<b>31 of 31</b>", "all plausible: 6.6–17.8 characters per second, the low end being Japanese, Korean, Chinese and Hindi, as their scripts lead you to expect"],
              ["<b>piper</b>", "<b>1 of 50</b>", "Hebrew, 9.14 char/s. The rest could not be measured <i>on this machine</i>: Smart App Control blocks <code>espeakbridge.pyd</code>, and every other piper language phonemises through espeak"],
              ["<b>kokoro</b>", "<b>0 of 8</b>", "<code>kokoro-onnx</code> does not import here at all — Smart App Control blocks the native module of one of its dependencies"]
            ]
          },
          {
            t: "p",
            x: "The two engines that could not be measured are blocked by a <b>property of this machine</b>, not of the code. Their language lists are declared from the catalogue and <b>marked as unmeasured</b>, rather than presented as tested."
          },
          {
            t: "nota",
            x: "<b>One claim the check took away.</b> The piper index lists <b>51</b> languages and this program offers <b>50</b>. Japanese is the difference: that voice needs a phonemiser the installed <code>piper-tts</code> does not have, so the model downloads happily and the <i>first synthesis</i> raises. Declaring 51 would have been true of the index and false of this program. Japanese is still spoken — by kokoro, or by supertonic."
          },
          { t: "h3", x: "Pick a language, and the engine follows it" },
          {
            t: "p",
            x: "There are exactly three outcomes, and the difference between them is the whole design."
          },
          {
            t: "tabella",
            testa: ["", "what happens", "what it says"],
            righe: [
              ["<b>the engine you picked already speaks it</b>", "nothing changes", "<b>nothing</b> — and it has to stay silent: a notice that fires on every language change is one that stops being read"],
              ["<b>it does not, but another engine does</b>", "the engine is switched", "it says so, because your own choice has just been overridden — <i>«piper» has no voices in this language: switching to «supertonic», which speaks 31</i>"],
              ["<b>no usable engine speaks it</b>", "nothing is switched, because switching would not help", "the fact is stated instead of being resolved silently — <i>no engine has voices in this language (and «kokoro» will not run here): the line would come out in a voice that pronounces a different one</i>"]
            ]
          },
          {
            t: "p",
            x: "The parenthesis in the last one is the point: <b>the answer depends on the machine</b>, and the message says which engines were ruled out. The replacement has to be one this machine can actually run — kokoro costs 741 ms a line on the CPU against 213 on CUDA, so a machine without CUDA is never switched onto it: following a language must not cost double the latency. Japanese shows the whole mechanism in one line: piper has the voice and cannot pronounce it, kokoro has five and wants CUDA, supertonic does it on the CPU — so a CUDA machine goes to kokoro and a CPU machine to supertonic, and neither is a guess."
          },
          {
            t: "p",
            x: "<b>Two structural facts worth knowing.</b> Supertonic's ten voices are <i>speakers, not languages</i>: the same ten styles speak all 31, and the language only selects the phonemiser — which is why it is the cheapest way to add one. Piper is the opposite, one model and one download per voice — and its index has <b>no field for gender</b>, so outside Italian the pool marks piper voices <code>?</code> and falls back to plain ordering instead of alternating male and female. A declared regression, not a hidden one."
          },
          { t: "h3", x: "What it can translate (off by default)" },
          {
            t: "tabella",
            testa: ["backend", "network", "how many languages", "worth knowing"],
            righe: [
              ["<b><code>locale</code></b>, Argos <i>— default</i>", "<b>no</b>", "no closed list: whichever pairs Argos publishes, downloaded when you press Start", "does not understand <code>auto</code> — it quietly becomes <i>from English</i>"],
              ["<code>llm</code>, Gemma 3 1B in this same process", "<b>no</b>", "depends on the model you point it at", "same <code>auto</code> caveat"],
              ["<code>ollama</code>, TranslateGemma outside the environment", "<b>no</b>, but a local server has to be running", "depends on the model", "the slowest in practice: the live sessions using it sit at 1592–1805 ms end to end"],
              ["<code>google</code>", "<b>yes</b>, and the program says so every time", "<b>133</b> — the only closed list of the four", "the only one that understands <code>auto</code>"]
            ]
          },
          {
            t: "p",
            x: "The menu <b>shows all four and declares</b> rather than filtering: three of them have no closed list, so a filter would hide choices that work and let through choices that do not, with the air of knowing."
          },
          {
            t: "nota",
            ambra: true,
            x: "<b>Something no counter shows.</b> On coarse language, local models <b>rewrite it in silence</b>. The translation succeeds beautifully: it says something else. Before asking whether a translator is good, ask whether it says what is written."
          },
          { t: "h3", x: "What the buttons are written in" },
          {
            t: "p",
            x: "<b>42 languages</b>: 41 catalogs plus Italian, which is the language the source is written in. All 41 are <b>complete — 258 strings out of 258</b>, with none half-translated. Four of them run right to left and turn the whole window round: Arabic, Hebrew, Persian and Urdu."
          },
          {
            t: "p",
            x: "They are generated once and committed into the repo — not asked from the network while the window opens, because a window that asks the network for its own text is a blank window when the network is not there, <i>and blank without an error</i>. It follows your Windows language and changes without a restart."
          },
          {
            t: "p",
            x: "What is <b>not</b> translated, and on purpose: the explanations behind the <code>?</code> on each parameter. They come from the comments in <code>core/config.py</code> with the measurements inside them, and running a measurement through a machine translator is how a measurement quietly stops being one. The log and the measurement bar stay in Italian for the same reason — they are numbers and device names."
          }
        ]
      },

      {
        id: "limits",
        nav: "Limits",
        etichetta: "Limits",
        titolo: "What it does not do",
        lede: "The quickest way to be disappointed by a program is to find this list out by using it. So here it is before you install.",
        blocchi: [
          {
            t: "tabella",
            testa: ["", ""],
            righe: [
              ["<b>Nobody has listened to the 53 languages</b>", "what is verified is that a voice exists, that it belongs to that language and — where it could be measured — that its speaking rate is plausible. The pronunciation is not verified, and Italian is the language this program was built in and listened to in."],
              ["<b>A language your engine does not speak is a switch, not an error</b>", "the engine moves to one that speaks it and says so. If none of the engines this machine can run speaks it, that is stated too — instead of handing you a voice that pronounces a different language."],
              ["<b>The first session in a new piper language downloads its voices</b>", "one model per voice, 28–114 MB each, up to six of them, and the guide's bench does not yet declare that weight in advance the way it declares the others. Start can sit there for a few minutes without saying why."],
              ["<b>One subtitle line at a time</b>", "inside the box you drag: not the whole screen, not several areas at once. An earlier version promised several reading areas and it was removed, because the overlay draws one line at a time and the promise could not be kept live."],
              ["<b>The game must be windowed or borderless</b>", "exclusive fullscreen is not captured."],
              ["<b>Windows only</b>", "and the recogniser that reads a game's outlined text best, OneOCR, exists only on Windows 11. On Windows 10 you get PP-OCR."],
              ["<b>The voice arrives after the subtitle</b>", "about half a second of it is the wait for enough game audio to say who is speaking — and that wait, not the synthesis, is the largest single piece of the delay."],
              ["<b>More characters than voices share one</b>", "past the number of native voices they are told apart by shifting the pitch, and you can hear it."],
              ["<b>One player, one window</b>", "it is not a streaming tool, not a localisation pipeline and not multiplayer."]
            ]
          },
          { t: "h3", x: "Where the capture can fail" },
          {
            t: "p",
            x: "It grabs the game's window through Windows Graphics Capture where that is available, and falls back to <code>PrintWindow</code> — <b>saying so in the log</b> — where it is not. The fallback needs nothing installed, but it is synchronous and costs more: <b>17.5 ms</b> for a 1191×958 window, measured. And on a game drawing through a Direct3D flip-model swap chain, <code>PrintWindow</code> can <b>succeed and hand back a black frame</b>; the program inspects the first eight frames and declares it instead of quietly reading black. <b>Nobody has yet tried that fallback on GTA V itself.</b>"
          },
          {
            t: "nota",
            x: "<b>And the honest frame around every number on this page.</b> They were measured on one machine, on two games, by one person. A game that writes dark text on a light background reads on purpose-built frames and smudges; nobody has run it on a real one. Where a figure has not been measured, this page leaves the gap visible instead of filling it."
          }
        ]
      },

      {
        id: "support",
        nav: "Support it",
        nudo: true,
        blocchi: [
          {
            t: "sostegno",
            titolo: "Support the project",
            x: "livedub is free, runs entirely on your own machine and has neither accounts nor servers: there is nothing to sell and no data to collect. If you find it useful:",
            bottone: { x: "☕ Buy me a token!", href: "https://ko-fi.com/filippodebenedittis", pieno: true },
            postilla: "It unlocks no features and lifts no limits — there are none."
          }
        ]
      }
    ],

    /* ------------------------------------------------------------------ */
    piede: {
      righe: [
        "<b>livedub</b> — GPL-3.0-or-later, and not out of taste: the default speech synthesiser and the grapheme-to-phoneme engine behind one of the others are GPL-3, so anything distributed here is too."
      ],
      link: [
        { x: "Code", href: "https://github.com/pigro141/livedub" },
        { x: "The licence accounting", href: "https://github.com/pigro141/livedub/blob/main/docs/LICENZE.md" },
        { x: "Ko-fi", href: "https://ko-fi.com/filippodebenedittis" }
      ],
      nota: "Built and maintained by one person, in the open."
    }
  };
})();
