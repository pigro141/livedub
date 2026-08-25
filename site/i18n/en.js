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

   L'elenco dei segnaposto, con cosa ci va e da dove si prende, sta nel
   passaggio di consegne dell'impalcatura.

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
        "Windows <b>{{OS_SUPPORTED}}</b>",
        "Python <b>{{PYTHON_VERSION}}</b>",
        "the network is <b>not needed</b>",
        "the interface speaks <b>{{UI_LANGUAGES_COUNT}}</b>",
        "NVIDIA GPU <b>{{GPU_REQUIREMENT}}</b>"
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
                p: "The window is already in the language you use Windows in — {{UI_LANGUAGES_COUNT}} in total. Arabic, Hebrew, Persian and Urdu also flip the window the other way round."
              },
              {
                b: "A guide takes you through it, in {{TUTORIAL_STEPS}} steps.",
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
                p: "From there it reads, works out who is speaking, synthesises and mixes. The voice always arrives a little after the subtitle, and that is deliberate: {{SPEAKER_DECIDE_MS}} of game audio is what it takes to know who is talking before choosing a voice."
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
        titolo: "{{TABS_COUNT}} tabs, and none of them has to be touched to hear the first line",
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
              ["<b>All settings</b>", "the {{PARAMS_TOTAL}} parameters, with a search box"]
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
            x: "<b>The parameters.</b> {{PARAMS_TOTAL}} of them; <b>{{PARAMS_HOT}} apply straight away</b>, and the {{PARAMS_COLD}} that are only read at startup <b>say so</b> instead of pretending. {{PARAMS_WITH_HELP}} of them carry a <code>?</code> that explains what they do, what was measured, and what you risk by changing them — and it is the same text that sits beside the parameter inside <code>core/config.py</code>, not a second copy nobody updates."
          },
          {
            t: "p",
            x: "<b>The bar along the bottom</b> reports reads per second, lines, median latency, compression, underruns and the reading area, {{MEASURE_BAR_HZ}}. The only red one is <code>underrun</code>, and it is not a number out of range: it is a line you did not hear."
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
          { t: "posto", nome: "LIVE_NUMBERS_TABLE", forma: "a table: one column per engine, one row per figure (lines dubbed, median latency from subtitle to voice, synthesis cost, speech compression, underruns), plus the session folder each column comes from" },
          {
            t: "p",
            x: "Two engines is two choices, not a quality ladder: one is faster, the other articulates better — and it is the bench in the setup guide that says which of them holds up on a given machine."
          },
          { t: "h3", x: "How many cores an engine needs" },
          {
            t: "p",
            x: "This one comes from the bench and <b>is not a latency</b>: it is the cost of synthesising one line with everything else held equal, timed on the wall clock while the process is restricted to fewer cores. It is a <b>lower bound</b> on how much an older PC would slow down — it simulates fewer cores, not slower ones."
          },
          { t: "posto", nome: "CPU_CORES_TABLE", forma: "a table: physical cores against the per-line synthesis cost of each engine, and the line where an engine stops being usable" }
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
          { t: "posto", nome: "DOWNLOADS", forma: "the packaged build: what to download and for which Windows. It goes in only once the build on CI is green — until then this page promises no executable, because a download that is announced and not there is worse than one that is not announced" },
          { t: "posto", nome: "HARDWARE_TABLE", forma: "a table: what it runs well on and what it runs better on — OS, Python, cores, RAM, GPU and VRAM, and which engines each row makes available" },
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
              "On a machine where it is still on, {{SAC_BLOCKED_LIST}}"
            ]
          },
          {
            t: "p",
            x: "<b>Why you can trust the numbers.</b> There is a test suite of <b>{{SELFTEST_CHECKS}} checks</b> in {{SELFTEST_GROUPS}} groups that runs without a game, without a GPU and without any model, and a bench that runs <b>the same chain</b> over a recording. The measurements that changed a decision are written <b>next to the parameter they decided</b>, inside <code>core/config.py</code> — which is the same text the window shows when you press <code>?</code>."
          }
        ]
      },

      {
        id: "games",
        nav: "Your game",
        etichetta: "Compatibility",
        titolo: "Will it work with my game?",
        lede: "Tested on {{GAMES_TESTED}}. Honestly, that is what is known.",
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
          { t: "h3", x: "What it can say" },
          {
            t: "p",
            x: "This is the honest limit, and it is worth stating plainly: a character beyond the number of native voices is told apart by shifting the pitch, which is what you hear in the first clip. <b>And the menu says so when a voice is missing</b>: translating into a language you have no voice for would not raise an error — you would get a voice from another language pronouncing it, which is a model phonemised by the wrong rules, with audio coming out and the logs all green."
          },
          { t: "posto", nome: "VOICE_LANGUAGES_TABLE", forma: "a table: engine, how many voices and in which languages, and whether it runs on CPU or GPU" },
          { t: "h3", x: "What it can translate (off by default)" },
          { t: "posto", nome: "TRANSLATION_BACKENDS_TABLE", forma: "a table: backend, whether it needs the network, how many language pairs, and the one line of caveat each deserves" },
          {
            t: "nota",
            ambra: true,
            x: "<b>Something no counter shows.</b> On coarse language, local models <b>rewrite it in silence</b>. The translation succeeds beautifully: it says something else. Before asking whether a translator is good, ask whether it says what is written."
          },
          { t: "h3", x: "What the buttons are written in" },
          {
            t: "p",
            x: "{{UI_LANGUAGES_COUNT}}, generated once and committed into the repo — not asked from the network while the window opens, because a window that asks the network for its own text is a blank window when the network is not there, <i>and blank without an error</i>. It follows your Windows language and changes without a restart."
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
