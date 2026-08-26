"""Configurazione della pipeline.

Un solo albero di dataclass, con tutti i valori che si toccano durante il
tuning, e un modo per cambiarne uno solo dalla riga di comando:

    main.py --set vision.sat_max=70 --set tts.backend=tone

La ragione di `--set` invece di una raffica di flag e' che il tuning non si fa
con i valori previsti: si fa con quello che nessuno aveva previsto di dover
cambiare. Ogni campo qui dentro e' raggiungibile senza toccare l'argparse.

I default sono **punti di partenza dichiarati, non misure**. Le soglie di colore,
la ROI e i coefficienti di durata vanno ricavati dal video con
`tools/calibrate.py` e scritti nel profilo del gioco.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any


@dataclass
class CaptureConfig:
    """Cattura dello schermo."""

    # `auto` | `wgc` | `finestra-gdi` | `dxcam` | `mss`. I primi due catturano
    # **una finestra sola** (e valgono solo se una finestra e' stata scelta), gli
    # altri lo schermo.
    #
    # **`wgc` e `finestra-gdi` fanno la stessa cosa in due modi diversi**, e la
    # differenza e' cosa serve installare. Windows Graphics Capture e' il modo
    # buono — asincrono, in GPU, regge il fullscreen esclusivo — e arriva da una
    # libreria che Smart App Control blocca in **tutte** le versioni pubblicate
    # (`windows-capture` 2.0.1/2.0.0/1.5.0/1.4.4, `winrt-Windows.Graphics.Capture`
    # 3.2.1/3.1.0/3.0.0/2.3.0/2.0.1 e con lei `winrt-runtime`). `finestra-gdi` usa
    # `PrintWindow` di `user32.dll`, cioe' Windows: niente da installare e niente
    # reputazione da maturare.
    #
    # Il prezzo e' misurato ed e' di due tipi. Il costo: 17,6 ms per una finestra
    # 1278x1391 intera contro 6,2 per la fascia che si legge (WGC non lo paga:
    # consegna da sola). E il difetto vero: su un gioco Direct3D senza superficie
    # di redirezione `PrintWindow` **riesce e restituisce nero**, che non e' un
    # errore — la sessione resta accesa e sembra rotto l'OCR. Per questo la
    # sorgente guarda i primi fotogrammi e lo **dichiara** (`PrintWindowSource.nero`).
    #
    # `wgc` non e' un vicolo cieco: se la libreria non c'e', si ripiega su
    # `finestra-gdi` **dicendolo** (`capture.screen.apri_finestra`).
    backend: str = "auto"  # auto | wgc | finestra-gdi | dxcam | mss
    monitor: int = 1
    fps: float = 30.0  # ritmo del diff sulla ROI, non dell'OCR
    # **Prendere dallo schermo solo la fascia che si legge.** Di un fotogramma
    # 2560x1440 si guarda una striscia alta il 5% — il sottotitolo — e si paga
    # tutto il resto. Misurato con `mss`, la stessa macchina e lo stesso momento:
    #
    #     schermo intero    2560x1440    32,4 ms
    #     fascia 0,06       1308x248      9,2 ms
    #     fascia 0,08       1366x306     11,7 ms   <- qui
    #     fascia 0,10       1424x364     11,6 ms
    #
    # A 30 Hz il giro dura 33 ms: prendere lo schermo intero se ne mangia il
    # 90%, e dal vivo si vede. Provato sulla stessa scena, 60 secondi per parte:
    #
    #                       letture   sottotitoli   battute
    #     schermo intero    884 (14,7 Hz)     30        28
    #     solo la fascia   1197 (20,0 Hz)     35        34
    #
    # Non e' solo un risparmio: sono cinque sottotitoli in piu' letti, perche' il
    # lettore ha bisogno di **frame consecutivi** per confermare una riga.
    #
    # **Il prezzo, che va detto**: fuori dalla fascia il fotogramma e' **nero**.
    # Chi legge la ROI non se ne accorge, ma una prova che guardasse altrove
    # troverebbe il buio senza nessun errore. Con la cattura della **finestra**
    # non si applica: li' il fotogramma e' gia' solo il gioco.
    solo_roi: bool = True
    # Quanto si prende **attorno** alla fascia, in frazione dell'altezza dello
    # schermo. Non e' prudenza: l'overlay sfoca i pixel intorno alla riga e
    # **cresce verso l'alto** quando il tradotto occupa piu' righe della riga che
    # copre. A 0,06 (86 px su 1440) tre righe di tradotto ci arriverebbero al
    # bordo; 0,08 sono 115 px e costano 2,5 ms in piu' di un margine che sta
    # stretto proprio quando serve.
    roi_margin: float = 0.08


@dataclass
class VisionConfig:
    """Lettura dei sottotitoli.

    `roi` e' normalizzata (x, y, w, h) sul frame, cosi' non dipende dalla
    risoluzione. Le tre soglie di colore implementano la grammatica: satura =>
    riga scartata, altrimenti bianco o grigio secondo la luminanza.
    """

    roi: tuple[float, float, float, float] = (0.15, 0.72, 0.70, 0.22)
    diff_threshold: float = 0.004  # frazione di pixel cambiati che sveglia l'OCR
    diff_stride: int = 4  # sottocampionamento del diff: costa 1/16 e basta
    # Quanto testo deve vedere il diff per dire "c'e' un sottotitolo", misurato
    # in **pixel di testo per colonna** della ROI sottocampionata. Per colonna e
    # non per area: una frazione dell'area dipende da quanto e' alta la ROI, e
    # lo stesso identico sottotitolo dentro una ROI quattro volte piu' alta
    # darebbe un quarto del valore. Per colonna il numero e' lo stesso.
    #
    # Misurato: una riga di sottotitolo sintetico 0,54; su 2000 frame di gioco
    # con sottotitolo il minimo e' 0,243; a schermo vuoto la mediana e' 0,18.
    # La soglia va **sotto** il minimo osservato, perche' un falso "non c'e'
    # testo" chiude una battuta ancora a schermo e la fa riaprire, mentre un
    # falso "c'e' testo" ritarda solo la chiusura di `hold_frames`.
    ink_min_columns: float = 0.20
    # **Quanti frame consecutivi senza inchiostro prima di credere a una
    # sparizione.** Uno non basta, e il difetto che questo numero cura era il
    # peggiore visto dal vivo: la stessa battuta letta due o tre volte di
    # seguito, con testo *identico*, e ogni copia una voce in piu' accodata.
    #
    # Il meccanismo: l'inchiostro si misura col contrasto locale dei glifi, cioe'
    # quanto le lettere staccano da cio' che hanno intorno. Quando dietro il
    # sottotitolo passa una scena chiara — un'esplosione, il cielo, dei fari —
    # le lettere staccano meno, l'inchiostro scende sotto soglia per un frame, e
    # il diff dichiara `VANISHED`. Il sottotitolo pero' e' ancora li': cambia il
    # contorno, non il testo. Quella dichiarazione arriva al tracker come
    # `certain=True`, che chiude **d'autorita'** saltando tenuta e somiglianza,
    # e la lettura successiva riapre lo stesso testo come battuta nuova.
    #
    # Sul banco non si vedeva perche' il file e' 1080p pulito e il contrasto non
    # crolla mai; dal vivo si cattura Chrome riscalato, il testo stacca meno in
    # partenza (`contrast_min` 68,8 nel profilo live contro 28,9 in quello del
    # file) e basta molto meno a farlo scendere.
    #
    # E' la stessa forma di `min_speech_ms` nel VAD e di `stable_reads`
    # nell'OCR: una transizione si dichiara quando persiste, non quando la si
    # intravede. Il prezzo e' un `t_off` in ritardo di `vanish_frames / fps`
    # (100 ms a 30 fps), che allunga di altrettanto la durata misurata.
    vanish_frames: int = 3
    sat_max: int = 60  # saturazione oltre la quale un pixel non e' un glifo di dialogo
    # Quanta parte dell'inchiostro di una riga puo' essere satura prima che la
    # riga smetta di essere dialogo.
    #
    # La prima versione bocciava la riga sul **picco** di saturazione, e
    # sbagliava per una ragione che si e' vista solo sulla registrazione: i
    # pixel saturi spesso non sono glifi, sono scenario entrato nella ROI. Una
    # battuta bianca a luminanza 253 veniva scartata perche' una macchia viola
    # passava nell'inquadratura — 863 righe scartate in venti minuti, e leggendo
    # cosa contenevano erano quasi tutte dialogo.
    #
    # Ordinando le righe scartate per quota di inchiostro saturo, le due
    # popolazioni si separano: sopra ~0,25 ci sono le righe-obiettivo (`Scegli
    # una delle auto`, `Raggiungi ...`, `Segui ...`, dove la parola colorata e'
    # una frazione grossa di una riga corta), sotto c'e' il dialogo con lo
    # scenario dentro la ROI. I pixel saturi vengono comunque tolti dalla
    # maschera prima del riconoscimento: non sono testo, e nel ritaglio danno
    # solo fastidio.
    sat_ink_max: float = 0.25
    # **Quanto dev'essere largo un tratto colorato continuo per essere una
    # parola**, in frazione della larghezza della riga. E' l'altra meta' del
    # filtro del colore, e risponde a una domanda che `sat_ink_max` non puo'
    # porre.
    #
    # `sat_ink_max` e' una **quota**: pixel saturi diviso pixel di testo. Il
    # denominatore e' la maschera dell'OCR, che dipende da `contrast_min` —
    # quindi tarare il riconoscimento sposta il filtro del colore. Misurato: col
    # profilo del banco (contrasto 28,9) l'obiettivo `Raggiungi Vespucci Beach.`
    # e' scartato, il ciano e' il 44% del suo inchiostro; con le soglie di una
    # sessione dal vivo (68,8, ROI disegnata a mano) la stessa riga passa per
    # dialogo e viene doppiata.
    #
    # La larghezza no: una parola colorata e' larga quanto e', qualunque sia la
    # soglia con cui si e' deciso quali pixel guardare.
    #
    # **E si misura in frazione, non in pixel.** Un numero assoluto sarebbe
    # legato alla risoluzione e a quanto largo e' stato disegnato il rettangolo
    # — che l'utente disegna come vuole, ed e' il percorso di produzione
    # previsto. Una parola invece occupa sempre la stessa quota della frase
    # che la contiene: `Vespucci Beach` dentro `Raggiungi Vespucci Beach.` e'
    # oltre meta' della riga, a qualunque ingrandimento.
    #
    # **Il valore viene dal vivo, e il banco non poteva trovarlo.**
    #
    # Sul banco questo criterio sembrava inutile: gli obiettivi di missione
    # interi sono gia' scartati da `sat_ink_max`, e l'unica riga che passava era
    # `'Raggiungi'` **da sola** — la scritta a meta' dissolvenza, dove il ciano
    # non e' ancora disegnato e quindi nessun criterio sul colore puo' prenderla.
    # Lo spazzamento non trovava altopiano: a 0,06 "funzionava" solo beccando
    # colore di scenario, e perdeva `'Ma domani'`, che e' dialogo vero.
    #
    # **Due sessioni dal vivo hanno detto un'altra cosa**, e il guadagno non e'
    # dove lo si cercava. Stessa scena, 155 s, criterio spento contro 0,15 —
    # accoppiando le battute per testo:
    #
    #     spento                                    ->  0,15
    #     'Rec.Lavoriamo insieme gia da...'         ->  'Lavoriamo insieme gia da...'
    #     'Senti, amico ...Rei'                     ->  'Senti, amico'
    #     '...sono onorato di annunciartiRer'       ->  '...sono onorato di annunciarti'
    #     "Si, era lui.Adam'a App"                  ->  'Si, era lui.'
    #     'ma devo dare una : olta alla mia vita.'  ->  'ma devo dare una svolta alla mia vita.'
    #
    # Non sono righe **saltate**: sono righe **sporcate**. Frammenti di HUD
    # colorata (nomi di app, radio, testo di missione) finivano dentro il
    # sottotitolo e venivano pronunciati. E l'ultima riga dice di piu': togliendo
    # i pixel colorati dal ritaglio **l'OCR legge meglio anche il resto**.
    #
    # 69 battute contro 66, voci neutre 14 contro 18. Col profilo del banco a
    # 0,15 e 0,25 non cambia nulla (43 battute, nessuna persa), quindi non fa
    # danno dove non serve.
    #
    # **Il limite della prova, dichiarato**: due passate dal vivo su scene non
    # identiche (73% dei testi in comune). Non e' un caso nullo — ma le
    # differenze non sono sparse, sono tutte della stessa forma, cioe' spazzatura
    # colorata tolta. `vision.lines.color_word` conta quante volte scatta, cosi'
    # la prossima sessione lo dice invece di lasciarlo dedurre.
    #
    # **Tutto quanto sopra e' stato misurato con la corsa rotta, e va riletto
    # sapendolo.** `_corsa_piu_lunga` girava sulle colonne colorate **grezze**,
    # e fra una lettera e l'altra c'e' del fondo: misurava la lettera piu' larga,
    # non la parola. Su «Raggiungi la destinazione» con `destinazione` colorata
    # la quota valeva 0,043 contro una soglia di 0,15 — il criterio non poteva
    # scattare per **nessuna** parola, di nessuna lunghezza. Cio' che scattava
    # 957 volte nella sessione dal vivo del 7 agosto erano macchie piene:
    # scenario e HUD, non parole. Ecco perche' lo spazzamento non trovava
    # altopiano — a 0,06 pescava scenario perche' era l'unica cosa che quella
    # misura sapesse vedere.
    #
    # Quello che passava, e che l'utente ha sentito pronunciare: `'Raggiungi i'`,
    # `'Sali sul'`, `'Aspetta'`. Righe di missione **troncate** proprio dove
    # comincia la parola colorata, perche' i pixel saturi vengono tolti dal
    # ritaglio e l'OCR legge il moncone bianco che resta.
    #
    # Adesso le lettere si saldano prima (`_chiudi_buchi`) e la quota misura la
    # parola. **La soglia va quindi ritarata**: 0,15 era una frazione di una
    # quantita' diversa, ed e' la sesta volta che questo progetto paga per una
    # soglia riusata su un'altra distribuzione.
    #
    # A zero il criterio e' spento e resta la sola quota `sat_ink_max`.
    min_color_word_frac: float = 0.15
    # **Se le righe con dell'inchiostro colorato vanno buttate. E' una scelta
    # del gioco, quindi la fa l'utente.**
    #
    # Acceso e' giusto su GTA V, dove il colore e' dell'HUD: obiettivi di
    # missione, nomi di app, la radio. Spegnerlo li' significa sentirli
    # pronunciare — misurato, con la difesa giu' tornano `'Andiamo a Vinewood
    # Boulevard.'` e `'Vinewood Boul'`.
    #
    # Ma il colore vuol dire un'altra cosa in un gioco che colora **il nome di
    # chi parla** davanti a ogni battuta. Mafia: The Old Country scrive `ENZO:`,
    # `ALFIO:` in giallo, e con la difesa accesa si butta tutto il dialogo.
    # Misurato sulle due scene, con la verita' presa fuori dalla catena:
    #
    # | | GTA V, righe scartate | GTA V, fuori lessico | Mafia, battute lette |
    # |---|---|---|---|
    # | acceso (default) | 1349 | 8,0% | **0 su 18** |
    # | spento | **0** | 9,4% | **12 su 18** |
    #
    # I due giochi vogliono il contrario, e **nessuna soglia li concilia**:
    # nessun valore separa un nome giallo da un obiettivo giallo. Quindi non e'
    # un numero da tarare meglio, e' un interruttore — e sta all'utente, che il
    # suo gioco lo conosce. La UI lo espone come «Ignora i sottotitoli
    # colorati», e si puo' cambiare **a caldo**: la riga si riclassifica a ogni
    # fotogramma, quindi non c'e' niente da ricostruire.
    #
    # Il giorno in cui si sapra' dire «il colore e' del **nome**, non di
    # scenario» — il nome sta a inizio riga, finisce con i due punti, e si
    # ripete identico fra le battute — questo interruttore potra' avere un terzo
    # valore invece di due.
    exclude_colored: bool = True
    # Quanto vuoto si chiude fra due colonne colorate perche' contino come la
    # stessa parola, in quote dell'altezza della banda. Misurato su Arial
    # grassetto a 20, 34 e 60 punti: **0,16-0,205** fra due lettere della stessa
    # parola, **0,375-0,438** fra due parole. In mezzo c'e' un altopiano largo, e
    # 0,28 ci sta dentro con un fattore due da tutte e due le parti — chiude le
    # lettere senza saldare le parole. A zero i buchi non si chiudono e si torna
    # a misurare la lettera.
    color_word_gap: float = 0.28
    # Quanto dev'essere largo un buco orizzontale perche' cio' che sta di la'
    # non sia piu' la stessa scritta, in quote dell'altezza della banda. Fra due
    # parole il buco vale 0,4 (p75 misurato su 39248 buchi di 1125 bande di
    # dialogo: p50 0,16, p75 0,39); sopra c'e' la coda dell'HUD sulla stessa
    # riga. Fra i blocchi si tiene quello piu' vicino al centro dell'area.
    # A zero non si spezza niente e il ritaglio torna a prendere tutta la riga.
    #
    # **2,5 e' scelto largo apposta**: uno spazio fra parole vale 0,4, quindi qui
    # serve un buco sei volte piu' largo perche' si tagli. Sul banco con l'area
    # calibrata il guadagno e' piccolo — spariscono `tMa ti dir�,` e
    # `AaMerda. Per se stesso, penso.`, e si perde una battuta su 115 — perche'
    # con quell'area l'HUD resta quasi tutto fuori. **Il caso che conta e' l'area
    # larga di una sessione vera**, dove il difetto vale 63 battute su 576.
    #
    # Il limite della prova, dichiarato: la verifica sull'area larga non e' stata
    # portata a termine (la passata di controllo e' andata in timeout), quindi il
    # numero dal vivo e' quello del difetto, non quello del rimedio.
    line_gap_split: float = 2.5
    # Quanto margine sopra e sotto la banda va nel ritaglio dell'OCR, in quote
    # dell'altezza della banda. La banda finisce dove finisce l'inchiostro
    # trovato dalla maschera, e li' dentro non ci stanno accenti, code di `g` e
    # `p` e bordi antialiasati. Misurato su un secondo gioco, banda alta 20 px:
    # senza margine l'OCR torna **vuoto**, con 4 px sopra e sotto legge tutto a
    # confidenza 1,00. A zero e' il comportamento di sempre.
    #
    # **E su GTA V non costa niente: e' l'unico dei due rimedi del secondo gioco
    # che vada bene a tutti e due.** Le due scene a confronto, con la verita'
    # misurata **fuori** dalla catena (OCR sull'area intera a 2 Hz):
    #
    # | `line_pad` | GTA V (105 battute vere) | Mafia (18 vere) | fuori lessico (GTA V) |
    # |---|---|---|---|
    # | 0,0 | 87 ritrovate (83%) | 2 (11%) | 8,2% |
    # | **0,2** | **88 (84%)** | **12 (67%)** | **8,0%** |
    #
    # Su GTA V il guadagno non e' nel conteggio, e' nella frammentazione: il
    # grappolo `Sali sul Mia / 3eo,ar / Joo,c / sigr;ta / ajepis / ...` — quattordici
    # righe di spazzatura — diventa `Sali sul furgone.` piu' quattro frammenti, e
    # `Torna sul fu re` diventa `Torna sul furgone.`. Tornano anche gli accenti
    # (`E l'ultima moda` -> `E' l'ultima moda`), che e' proprio cio' che il
    # margine recupera. Le due passate di controllo sono uscite **identiche
    # carattere per carattere**, quindi la differenza e' del trattamento e non
    # della fortuna.
    #
    # Resta a 0 perche' cambia il comportamento sul gioco principale (130 -> 123
    # battute aperte) e quel giudizio e' dell'orecchio, non del lessico.
    line_pad: float = 0.0
    white_min_luma: int = 200  # bianco pieno
    grey_min_luma: int = 110  # sotto questa soglia non e' testo
    # Il testo di gioco e' bordato di nero: non e' luminoso in assoluto, e'
    # luminoso *rispetto a cio' che ha intorno*. Con la sola soglia assoluta un
    # cielo chiaro fa sparire i sottotitoli (misurato: si rompe da luma 120 in
    # su); togliendo un fondo locale il limite si sposta a 180.
    use_local_contrast: bool = True
    contrast_kernel: int = 63  # lato del fondo locale, in pixel
    contrast_min: float = 30.0  # quanto il glifo deve staccare dal suo intorno
    # Il corpo del glifo si misura su un percentile alto, non sulla mediana: il
    # testo e' antialiasato e bordato, e i pixel di bordo falserebbero la media.
    luma_percentile: int = 90
    sat_percentile: int = 98
    min_line_height: int = 8  # px: sotto e' rumore, non una riga
    min_line_fill: float = 0.01  # frazione minima di larghezza occupata da testo
    # Quanto la banda di una riga puo' crescere oltre il proprio nucleo, in
    # frazione dell'altezza del nucleo. Serve a non tagliare code e punti: le
    # righe-pixel dove passano solo le code di g, q, p hanno pochi pixel e non
    # superano `min_line_fill`. Vedi `vision/lines.find_bands`.
    line_grow: float = 0.45
    # Ultimo filtro, e l'unico che non viene da una misura ma dalla lingua:
    # nessuna battuta italiana e' lunga una lettera. Sulla registrazione vera
    # la texture della scena produce righe che l'OCR legge come '1', '?', '—';
    # passavano ogni soglia di colore perche' un cordolo bianco *e'* bianco.
    # Si contano le **lettere**, non gli alfanumerici: una riga letta '·..··' ha
    # cinque caratteri e nessuna lettera, e '11' ne ha due di alfanumerici e
    # zero di lingua. Le cifre nella ROI vengono dalla scena — civici, cartelli,
    # cordoli — mentre una battuta di soli numeri non esiste.
    min_ocr_chars: int = 2
    # L'ultimo filtro, e l'unico che guarda la **lingua** invece della forma.
    # Una battuta italiana contiene almeno una parola italiana; una banda di
    # asfalto no. Basta UNA parola riconosciuta, perche' l'OCR ne rompe sempre
    # qualcuna e pretenderle tutte buone scarterebbe il dialogo vero.
    #
    # Il prezzo, misurato su 173 battute: restano fuori le forme che i dizionari
    # non elencano — `'accoglilo'`, imperativo piu' pronome — circa una su
    # trenta. E' l'unico filtro del progetto che puo' scartare una battuta vera,
    # quindi si spegne da qui.
    use_lexicon: bool = True
    lexicon_dir: str = "models/lexicon"
    stable_reads: int = 2  # letture concordi prima di dare per buona una battuta
    # Quanto una battuta puo' non farsi leggere restando a schermo: **entrambe**
    # le condizioni devono cadere prima di dichiararla chiusa.
    #
    # `hold_frames` conta le passate del tracker, e non e' un ripiego: una
    # passata avviene quando la scena cambia, e un sottotitolo che sparisce *e'*
    # un cambiamento — sostituire il conteggio col solo tempo e' stato provato e
    # peggiora (1105 aperture contro 1129 del migliore tempo puro).
    # `hold_seconds` mette il pavimento che al conteggio manca nelle scene
    # mosse, dove tre passate valgono un decimo di secondo. 0,6 s copre il
    # novantesimo percentile delle raffiche di letture fallite misurate sui 27
    # minuti (17 passate).
    #
    # Puo' essere generoso perche' la sparizione vera arriva dal diff
    # (`certain`), non dal silenzio dell'OCR: sbagliare per eccesso allunga una
    # durata, sbagliare per difetto spezza la battuta in due.
    #
    # **Da solo non serviva a niente**: finche' la sostituzione scavalcava la
    # scadenza (64% delle chiusure passava di li') allungare la tenuta non
    # cambiava una virgola. Ha cominciato a pagare solo insieme a
    # `continue_similarity`, ed e' il motivo per cui i due valori vanno tarati
    # insieme e non uno per volta.
    hold_frames: int = 3
    hold_seconds: float = 0.6
    # Quanto due letture possono differire restando "la stessa battuta". Si
    # confrontano le forme normalizzate (sole lettere e cifre), e il conto e' in
    # **caratteri**, non in percentuale: l'OCR sbaglia una lettera ogni tanto,
    # non una quota del testo. Vedi `vision/subtitles.wrong_chars`.
    # Misurato sulla fetta di 50 s: 2 caratteri danno 33 aperture, 3 ne danno
    # 30, 4 ne danno 29, 5 ne danno 28. Il salto e' fra 2 e 3 e poi la curva si
    # appiattisce, quindi 3 prende quasi tutto il guadagno restando vicino al
    # CER misurato dell'OCR (2,9%) — cioe' senza essere tarato sulla fetta.
    max_wrong_chars: int = 3  # sempre tollerati, a qualunque lunghezza
    max_wrong_frac: float = 0.06  # e in piu' questa quota della battuta piu' lunga
    # Soglia separata e piu' larga per un caso solo: una battuta appena
    # confermata che sta per cacciare l'**unica** orfana a schermo. Li' le
    # candidate sono due e la domanda e' piu' facile che nel caso generale,
    # quindi ci si puo' permettere di essere generosi senza rischiare di fondere
    # due frasi diverse in mezzo a molte. Vedi `SubtitleTracker.feed`.
    #
    # Il valore viene da una guardia della suite, non da una spazzata: a 0,60 il
    # banco dava il risultato migliore (692 aperture contro 742), ma `prima
    # battuta` e `seconda battuta` si somigliano per 0,62 e venivano fuse. Due
    # righe che finiscono con la stessa parola sono un caso reale, quindi la
    # soglia sta sopra quella fascia e si tiene l'83% del guadagno.
    continue_similarity: float = 0.75
    # **E la seconda domanda: la lettura nuova e' un pezzo di quella orfana?**
    # `continue_similarity` copre le riletture che si somigliano; non copre
    # quelle in cui l'OCR ha preso la battuta a meta' — un frammento contro il
    # testo intero fa un rapporto basso perche' meta' del lungo non ha
    # corrispondenza, e la battuta viene riaperta. Misurato sulle riletture di
    # una sessione dal vivo, 13 coppie marcate a mano contro 217 battute
    # distinte: il rapporto a 0,90 non ne prende **nessuna**, il contenimento a
    # 0,80 ne prende 8 senza sbagliarne una.
    #
    # Le due soglie non sono confrontabili e non vanno mosse insieme: sopra la
    # prima due letture si somigliano, sopra la seconda una **contiene** l'altra.
    continue_containment: float = 0.80
    # Sotto questa lunghezza il contenimento non si applica: su `'Segui.'` e
    # `'Se qui'` — sei caratteri, due battute vere e diverse — qualunque misura
    # di contenimento risponde quello che le si chiede.
    continue_min_chars: int = 8
    # `oneocr` e' il riconoscitore dello Strumento di cattura di Windows 11 e
    # legge meglio: misurato sullo stesso tratto di GTA V, 45 battute contro 46
    # ma con testo piu' pulito (`'I ma se ne avessi uno'` -> `'ma se ne avessi
    # uno'`, `'Che succede, fratello? t'` -> `'Che succede, fratello?'`) e
    # quasi-duplicati dal 13% al 9%. I duplicati contano piu' della qualita': in
    # diretta due letture diverse della stessa battuta diventano due voci
    # accodate, ed e' da li' che vengono i ritardi da due secondi.
    #
    # Non e' il default perche' i suoi tre file non sono ridistribuibili e vanno
    # copiati dalla macchina con `python -m tools.fetch_oneocr`. Senza quelli il
    # backend non parte, e un default che non parte sarebbe peggio di uno che
    # legge peggio.
    ocr_backend: str = "ppocr"  # ppocr | oneocr | none
    ocr_device: str = "cuda"  # cuda | cpu
    # **Quante volte al secondo si puo' pagare il riconoscimento.** Zero lo
    # spegne.
    #
    # Questo valore e' stato dichiarato per mesi e **non lo leggeva nessuno**.
    # Il cancello del diff avrebbe dovuto bastare — si legge solo quando la ROI
    # cambia — ma la ROI e' una striscia in mezzo allo schermo e dietro i
    # sottotitoli c'e' il gioco che si muove. Misurato su sessanta secondi di
    # scena, 1801 frame: il diff ne ferma 300 e l'OCR gira sugli altri, cioe' a
    # 25 Hz, a 34 ms l'uno. **Cinquantadue secondi di lavoro per sessanta di
    # scena** — contro 1,5 secondi di sintesi con Piper e una dozzina con
    # SuperTonic. La cecita' del thread video, che avevo attribuito alla
    # sintesi, veniva quasi tutta da qui.
    #
    #     tetto    letture OCR   sottotitoli aperti   battute dette   latenza p50
    #     nessuno      1521              33                31            533 ms
    #      18 Hz        809              33                31            533 ms
    #      15 Hz        626              32                30            533 ms
    #      12 Hz        560              32                30            533 ms
    #
    # A 18 Hz l'uscita e' **identica**: stesse trentuno battute, 190 coppie
    # d'accordo su 190 nel confronto delle voci, latenza uguale — e la meta' del
    # lavoro. Sotto si comincia a perdere qualche battuta corta dentro le
    # raffiche di dialogo (`'Non mi accontento.'`, 0,7 s in mezzo alla tirata di
    # Lamar), che e' poco ma e' piu' di niente.
    #
    # Il tetto **non vale mentre una candidata aspetta la conferma**: quelle
    # letture stanno sul percorso della latenza e sono al massimo
    # `stable_reads` per battuta. Colpisce solo le riletture di un sottotitolo
    # gia' a schermo e fermo, che servono a tenerlo vivo e a migliorarne il
    # testo e possono aspettare un diciottesimo di secondo.
    max_ocr_hz: float = 18.0


@dataclass
class AudioConfig:
    """Cattura dell'audio di gioco."""

    device: str = ""  # vuoto = device di loopback predefinito
    samplerate: int = 48000
    blocksize: int = 480  # 10 ms
    ring_seconds: float = 10.0
    # **Estrazione mid/side per isolare il parlato che va all'impronta.** Sta
    # dalla parte della **cattura** e non dell'uscita: non ha niente a che fare
    # con `mix.duck_db`, che e' l'altro uso del mid/side — quello che abbassa la
    # voce originale in cio' che si sente. I due si confondono facilmente perche'
    # chiamano la stessa funzione di `mix/center.py` per due scopi opposti:
    # qui si **legge** il centro, li' lo si **abbassa**.
    center_enabled: bool = True


@dataclass
class VadConfig:
    """Quando qualcuno comincia a parlare nell'audio del gioco."""

    backend: str = "energy"  # energy | silero (silero non ancora implementato)
    threshold: float = 0.5  # probabilita', per i backend a modello
    min_speech_ms: int = 150
    min_silence_ms: int = 250
    frame_ms: int = 20  # risoluzione della decisione, e quindi dell'onset
    # Il parlato non si riconosce da quanto e' forte ma da quanto **stacca** dal
    # rumore di fondo: l'audio di un gioco passa da una stanza silenziosa a un
    # inseguimento in tre secondi, e una soglia assoluta direbbe "parla sempre"
    # nel secondo caso e "non parla mai" nel primo. Stessa forma del contrasto
    # locale che trova i glifi.
    energy_margin_db: float = 9.0
    floor_window_ms: int = 3000  # su quanto passato si stima il fondo
    floor_percentile: int = 25
    floor_db: float = -55.0  # sotto questo livello e' silenzio comunque
    # Il fondo si stima mentre si tace, altrimenti una battuta lunga si
    # coprirebbe da sola. Ma "mentre si tace" da solo si blocca: se il rilevatore
    # resta attivo il fondo non si aggiorna piu', e non aggiornandosi resta
    # attivo. Misurato sull'audio di GTA V, il VAD dichiarava parlato l'87% del
    # tempo con 8 aperture al minuto — cioe' era acceso, non stava rilevando.
    # Oltre questa durata la presa di parola non e' piu' credibile e il fondo
    # riprende a stimarsi comunque: il blocco diventa limitato invece che
    # definitivo.
    floor_hold_ms: int = 4000


@dataclass
class SpeakerConfig:
    """Riconoscimento di chi parla.

    **Questi numeri erano punti di partenza dichiarati. Ora sono stati misurati,
    e due dei tre presupposti non hanno retto** (`tools/bench_speaker.py`, video
    `testGameplayFattoDaMe`, ECAPA-TDNN 192 dimensioni sul canale centrale):

    - su voci sintetiche pulite di identita' nota l'EER e' 0% da 1 s in su, 5%
      a 0,5 s e 23% a 0,3 s. **Il ginocchio sta a mezzo secondo**: la decisione a
      300 ms che il piano sperava non e' disponibile nemmeno nel caso facile, e
      la rete di sicurezza (`max_wait_ms`, voce provvisoria) non e' un
      accorgimento ma la strada principale;
    - sull'audio del gioco l'EER non scende sotto il 27% a nessuna durata, e i
      casi nulli lo raggiungono: due prese di parola diverse a meno di dieci
      secondi si somigliano **piu'** di due meta' della stessa. L'impronta li'
      sta descrivendo la scena, non la persona. La causa e' misurata: il parlato
      stacca dal fondo di circa +3 dB, e le stesse voci note sommate al fondo
      vero del gioco passano da 0% a 18% di EER fra +24 dB e 0 dB. Il rimedio
      sta **a monte** dell'impronta — estrarre meglio il parlato — non in un
      modello migliore;
    - `use_color_cue` assumeva che una riga grigia fosse un secondo personaggio.
      Su 675 battute bianche registrate dal vivo in 17 sessioni, le grigie sono
      **15, e nessuna e' dialogo**: sono `'11111'`, `"Tr'"`, `'IIFIL'`, e una
      volta l'interfaccia di un terminale entrata nella ROI. Il filtro del
      lessico ne ferma tredici su quindici; le due che passano vengono comunque
      pronunciate con la seconda voce. Su questo gioco e questa cattura il
      grigio non porta l'informazione che il vincolo vorrebbe usare.

    **La terza voce si e' poi rivelata falsa, e vale la pena dire come.** La
    seconda misura confrontava due ritagli **brevi** fra loro, e costruiva le
    coppie "persone diverse" prendendo due momenti qualunque: in un dialogo i
    personaggi si alternano, quindi meta' di quelle coppie erano la stessa
    persona. Quel numero non poteva salire nemmeno con un riconoscitore
    perfetto. Rifatta la domanda come la pone il tracker — un ritaglio breve
    contro il **centroide** di un personaggio, costruito sulle sue battute
    intere — la risposta e' un'altra: su 82 battute di GTA V etichettate
    all'ascolto, il personaggio giusto si sceglie nell'86,6% dei casi con 0,30 s
    di parlato, nel 93,9% con 0,50 s e nel **100% con 0,75 s**.

    `similarity` **e' 0,55, ed e' misurata**: e' la soglia con cui raggruppando
    126 battute di una scena i gruppi sono risultati, all'ascolto, una persona
    ciascuno, e si sono ritrovati identici a sei minuti e piu' scene di
    distanza. Vale pero' **solo per i ritagli interi**: applicata al poco
    parlato disponibile al momento di parlare aprirebbe un personaggio nuovo a
    ogni battuta. Per questo `listen/speaker.py` ha due porte e non una.
    """

    backend: str = "ecapa-onnx"  # ecapa-onnx | mfcc | none
    # **0,55 stava sull'orlo di un precipizio, e per mezza giornata ha fatto
    # sembrare rotto il riconoscimento a giorni alterni.** Tre passate della
    # stessa scena, stesso codice, stessa configurazione, rigiocate con
    # `tools/recluster.py` (38/38/34 battute etichettate all'ascolto):
    #
    #     soglia   battute con la voce giusta   con la voce sbagliata   mute
    #      0,46          29 / 29 / 23                 4 / 4 / 3         5 / 5 / 8
    #      0,48          29 / 29 / 23                 4 / 4 / 3         5 / 5 / 8
    #      0,50          29 / 29 / 23                 4 / 4 / 3         5 / 5 / 8
    #      0,52          29 / 29 / 23                 4 / 4 / 3         5 / 5 / 8
    #      0,54          29 / 30 / 23                 3 / 2 / 3         6 / 6 / 8
    #      0,55          30 / 22 / 15                 0 / 0 / 2         8 / 16 / 17
    #      0,58          18 / 18 / 13                 1 / 1 / 1        19 / 19 / 20
    #
    # A 0,54 le tre passate sono d'accordo; a 0,55 si separano di quindici
    # battute. Non e' rumore di misura: e' una **discontinuita'**, e la si e'
    # ritrovata a mano. La seconda battuta di Simeon somiglia alla prima 0,5648
    # in una passata e 0,5478 nell'altra — diciassette millesimi — e da quel
    # confronto dipende se Simeon esiste come identita' per tutta la scena. Le
    # sue sette battute successive prendono la voce giusta o restano mute.
    #
    # La ragione per cui il precipizio e' li' si legge nella distribuzione: su
    # 227 coppie di ritagli **della stessa persona** la somiglianza mediana e'
    # 0,489, con il novantesimo percentile a 0,641. Una soglia a 0,55 sta
    # **sopra la mediana**, cioe' piu' spesso che no un ritaglio del personagio
    # gia' noto non lo riconosce e ne apre uno nuovo.
    #
    # 0,48 sta in mezzo all'altopiano — sei centesimi dal precipizio in alto,
    # quattro dal bordo in basso — e non e' un valore che vince: e' un valore
    # che non dipende dalla passata. Il prezzo, dichiarato, e' qualche voce
    # sbagliata in piu' (si veda `name_min_score`, che lo ricompra).
    similarity: float = 0.48  # soglia coseno per "e' la stessa voce", sui ritagli INTERI
    # **Quanto audio guardare PRIMA della comparsa del sottotitolo.**
    # Al momento di decidere la battuta corrente non ha ancora audio: il testo
    # compare e si decide li'. Misurato su 82 battute etichettate all'ascolto,
    # scegliendo fra tre personaggi noti:
    #
    #     finestra                        sceglie giusto
    #     [t_on-0,35 ; t_on]   (solo prima)     76,5%
    #     [t_on-0,20 ; t_on+0,15]  (a cavallo)  88,9%
    #     [t_on      ; t_on+0,35]  (solo dopo)  89,0%
    #
    # Le ultime due sono equivalenti, ma la seconda costa **150 ms** di attesa
    # invece di 350: la voce originale comincia intorno alla comparsa del testo,
    # quindi i 200 ms precedenti contengono gia' il suo attacco. Finche' lo
    # scheduler non sa rinviare l'attacco, si usa solo la parte disponibile
    # subito — cioe' la prima riga, 76,5% — e la differenza fra 76 e 89 e' il
    # prezzo esatto di non aspettare.
    lead_ms: int = 200
    # **Quanto aspettare, dopo la comparsa del sottotitolo, prima di scegliere
    # la voce.** E' il numero piu' caro del progetto e va scelto con la tabella
    # in mano, non per gusto. Misurato sulle battute di una scena confrontate
    # con il giudizio dell'orecchio:
    #
    #     attesa    accordo   peggior personaggio
    #       0 ms     65,9%           0%
    #     150 ms     80,5%          68%
    #     350 ms     84,1%          73%
    #     500 ms     91,5%          86%
    #
    # La colonna che conta e' l'ultima. Con attesa zero **un personaggio su tre
    # e' sbagliato sempre**: il ritaglio disponibile e' l'audio *precedente* al
    # sottotitolo, cioe' quasi sempre chi parlava prima, e in un dialogo con
    # alternanza quello e' sistematicamente l'altro. Non e' rumore, e' un errore
    # con il segno sbagliato, e all'ascolto suona come voci messe a caso.
    #
    # Il prezzo e' latenza, tutta intera: la voce italiana attacca mezzo secondo
    # dopo il sottotitolo invece di 263 ms. Sfora il budget di 350 ms che il
    # piano si era dato — ma quel budget nasceva dall'idea che il ritardo fosse
    # la cosa piu' fastidiosa, e l'ascolto dice un'altra cosa: un ritardo
    # costante si dimentica dopo un minuto, una voce che salta da un personaggio
    # all'altro no. Si abbassa con `--set speaker.decide_after_ms=150`.
    decide_after_ms: int = 500
    min_clip_ms: int = 400  # sotto questa durata la decisione e' provvisoria
    max_wait_ms: int = 200  # quanto si puo' rinviare l'attacco per decidere meglio
    # **Unire due identita' che si sono rivelate la stessa persona.**
    # Senza, un personaggio che il tracker spezza in due resta spezzato per
    # sempre: misurato dal vivo, sedici identita' per tre personaggi reali,
    # Simeon sparso fra S3/S6/S8 e undici identita' con una battuta sola.
    # **Sotto questa somiglianza non si fa un nome.**
    #
    # La porta veloce sceglieva sempre qualcuno: il migliore fra i confermati, o
    # in mancanza di meglio l'ultimo che aveva parlato. Il ragionamento era che
    # inventare un personaggio e' sempre sbagliato mentre tirare a indovinare lo
    # e' una volta su due — ed era vero finche' le opzioni erano due. Adesso ce
    # n'e' una terza, la voce neutra, che non inventa e non mente.
    #
    # Quanto valga quella scelta e' misurato, confrontando la porta veloce con la
    # porta lenta — che vede il ritaglio intero, quindi e' il giudice migliore
    # disponibile — sulle 43 battute della scena del concessionario:
    #
    #     somiglianza   battute   la porta veloce indovina
    #      0,00-0,15       9              22%
    #      0,15-0,30       4               0%
    #      0,30-0,45       6              83%
    #      0,45-0,60      15              80%
    #      0,60-1,00       8             100%
    #
    # Il gradino e' netto e sta a 0,30: sotto, la porta veloce prende 2 battute
    # su 13; sopra, 25 su 29. Quelle 13 sono i primi trenta secondi della scena,
    # quando un solo personaggio e' confermato e quindi *tutti* ricevono il suo
    # nome e la sua voce — che e' esattamente la partenza lenta che si sente.
    #
    # **Attenzione a come e' costruita questa misura**: la porta lenta non e' la
    # verita', e' solo un giudice migliore. Nella fascia bassa i due non vanno
    # d'accordo, e questo da solo non direbbe quale dei due sbaglia — a dirlo e'
    # l'orecchio, che su quella scena sente tre persone diverse dove la porta
    # veloce ne nomina una sola.
    #
    # **E' salita a 0,35 insieme all'abbassamento di `similarity`, e le due cose
    # vanno lette insieme.** Con la soglia dell'identita' piu' bassa i centroidi
    # sono meno puri, quindi la porta veloce trova un nome piu' spesso — anche
    # quando non dovrebbe. Sulle tre passate, a `similarity` 0,48:
    #
    #     name_min   voce giusta      voce sbagliata      mute
    #       0,30     29 / 29 / 23        4 / 4 / 3       5 / 5 / 8
    #       0,33     29 / 29 / 23        2 / 1 / 3       7 / 8 / 8
    #       0,35     28 / 29 / 23        1 / 1 / 2       9 / 8 / 9
    #       0,40     27 / 28 / 21        1 / 1 / 2      10 / 9 / 11
    #
    # A 0,35 le voci sbagliate tornano al livello che aveva la vecchia
    # configurazione (1/1/2 contro 0/0/2) al prezzo di una battuta giusta. E'
    # lo scambio che l'orecchio chiede: una battuta muta e' un'assenza, una
    # battuta con la voce di un altro e' un errore che si sente.
    name_min_score: float = 0.35
    merge: bool = True
    # **Da quante battute un centroide e' una media invece che un campione.**
    # Sotto questo numero, confrontare due "centroidi" e' in realta' confrontare
    # due ritagli, e quel confronto appartiene all'altra distribuzione — quella
    # con mediana 0,489, non quella per cui `merge_similarity` e' stata
    # misurata. Con 0,70 applicata anche li', un'identita' da una battuta sola
    # non si riassorbiva **mai**: la cura scritta per la frammentazione non
    # partiva proprio nel caso per cui esiste (misurato: 0 fusioni su tre
    # passate, sedici identita' per tre personaggi).
    #
    # Con la soglia scelta in base alla maturita' dei due — `similarity` se uno
    # dei due e' giovane, `merge_similarity` se sono maturi entrambi — le
    # fusioni diventano 2/2/3 e le identita' scendono da 13/13/11 a 11/11/9,
    # senza una sola battuta tradita. E' la stessa forma dell'errore dei
    # caratteri al secondo: un numero misurato in un'unita' e usato in un'altra.
    merge_maturo: int = 3
    # La soglia della fusione **non e' `similarity` e sta piu' in alto**: li' si
    # confronta un ritaglio con un centroide, qui due centroidi fra loro, e due
    # medie si somigliano piu' di quanto un campione somigli alla propria media.
    #
    # **0,70 e' misurata**, sul banco (`tools/recluster.py`, 44 battute di GTA V
    # dal secondo 1240). La colonna che decide non e' la prima ma la seconda: le
    # stesse impronte **permutate fra le battute**, dove per costruzione non c'e'
    # piu' nessuna identita' da ritrovare.
    #
    #     soglia   fusioni vere   fusioni sul permutato
    #      0,45         7                  7
    #      0,50         5                  6
    #      0,55         2                  3
    #      0,60         1                  2
    #      0,625        1                  1
    #      0,65         1                  0
    #      0,70         1                  0
    #      0,75         1                  0
    #      0,775        0                  0
    #
    # Sotto 0,625 il rumore fonde quanto l'identita', e le sedici identita' che
    # diventano dieci sono dieci gruppi a caso: un conteggio che migliora mentre
    # la risposta peggiora. Sopra 0,775 non fonde piu' niente. Dentro la finestra
    # c'e' **una** fusione, sempre la stessa e sempre nel verso giusto (S9 in S11,
    # 0,76 fra i due centroidi finali, quattro battute che raggiungono quindici).
    merge_similarity: float = 0.70
    # **Quante battute si puo' restare sulla voce neutra aspettando di sapere il
    # sesso.** Una voce assegnata non si toglie piu', quindi darla al primo
    # respiro vuol dire deciderla su uno o due ritagli — e su questo audio
    # l'intonazione di un ritaglio solo puo' essere quella della musica: il
    # personaggio con quindici battute della scena del concessionario, un uomo,
    # riceveva `paola` e la teneva fino in fondo.
    #
    # Il tetto pero' serve: senza, in una scena rumorosa dove l'intonazione non
    # si stabilizza mai, tutti resterebbero sulla neutra — cioe' tutti con la
    # stessa voce, il difetto da cui si e' partiti.
    #
    # **Era tre, ed e' una battuta, perche' il rinvio aspettava una cosa che non
    # arriva.** Misurato su due passate della stessa scena, una sul banco e una
    # dal vivo: il genere e' ancora "non so" in **32 battute su 40** al momento
    # di parlare, e si risolve in una su sette. Il rinvio quindi non rinviava una
    # decisione difficile: rimandava una decisione che sarebbe stata presa col
    # ripiego comunque, e nel frattempo costava **sei battute** dette con la voce
    # d'attesa — le stesse sei in tutte e due le passate, fra cui tre di Simeon di
    # fila. Tre battute consecutive di un personaggio gia' riconosciuto dette da
    # una voce che non e' la sua si sentono come un errore di riconoscimento, e
    # infatti sono state segnalate come tale.
    #
    # A una battuta il rinvio conserva il suo unico merito vero — la primissima
    # battuta di qualcuno di cui non si e' ancora sentito niente non gli assegna
    # una voce per sempre — e perde il resto.
    gender_defer_max_lines: int = 1
    # Con che sesso si assegna la voce quando il tetto scade e non si sa ancora.
    # Maschile perche' l'intonazione presa sul mix del gioco e' spostata verso
    # l'alto: questa taratura sa dire "uomo" molto meglio di "donna", e un
    # ripiego alternato darebbe una voce femminile a un uomo una volta su due.
    # In una scena con personaggi femminili si mette "f", o si rifa' la taratura
    # delle soglie in `listen/speaker.py` su una registrazione che ne contenga.
    gender_fallback: str = "m"
    max_speakers: int = 16
    use_color_cue: bool = True
    use_alternation: bool = True  # isteresi conversazionale


@dataclass
class EmotionConfig:
    """Tre segnali deboli fusi: modello audio, testo, livello dell'originale."""

    backend: str = "emotion2vec"  # emotion2vec | level | none
    w_audio: float = 0.5
    w_text: float = 0.2
    w_level: float = 0.3
    max_gain_db: float = 4.0
    max_rate_delta: float = 0.12
    max_semitones: float = 1.5


@dataclass
class TtsConfig:
    """Sintesi. `tone` e' un backend finto che produce un bip: serve al banco di
    prova per misurare la catena senza scaricare nulla."""

    backend: str = "piper"  # piper | supertonic | kokoro | tone | silent
    # Vuoto = le native del backend scelto. Dichiararle serve solo a
    # restringere: la lista di Piper non ha senso per SuperTonic e viceversa.
    voices: tuple[str, ...] = ()
    pool_size: int = 6  # voci distinte ottenute variando pitch e velocita'
    samplerate: int = 22050
    # cpu | cuda | auto. **Lo legge solo Kokoro**, ed e' l'unico che ne ha
    # bisogno: Piper e SuperTonic girano su CPU per scelta, perche' cosi' non
    # competono con il gioco per la GPU.
    #
    # Questo campo e' rimasto **dichiarato e non letto da nessuno** per mesi,
    # come `max_ocr_hz` prima di lui. Un parametro in config che nessuno legge
    # non e' inerte: e' una promessa che la configurazione fa e che il codice
    # non mantiene, e chi la legge conclude di aver gia' provato una cosa che
    # non ha mai provato.
    #
    # `auto` prende CUDA se c'e' e **dichiara su stderr** quando ripiega: su CPU
    # Kokoro costa 725 ms a battuta invece di 207, e la differenza si sente.
    device: str = "auto"
    # Respiro fra una battuta e la successiva. Non e' estetica: due battute
    # attaccate senza stacco si sentono come una frase sola, e in un dialogo
    # fanno sembrare che parli sempre la stessa persona.
    gap_seconds: float = 0.12
    # Solo per SuperTonic. `steps` sono i passi di diffusione: quattro bastano,
    # otto costano il doppio e non migliorano niente di misurabile.
    steps: int = 4
    # **`speed` va tenuto uguale a `supertonic.DEFAULT_SPEED`, e c'e' una
    # verifica che lo controlla.** Il valore e' 1,05 perche' sopra quella soglia
    # il modello smette di articolare e comincia a saltare sillabe (la tabella e'
    # nel modulo del backend). Il vecchio 1,50 veniva da una calibrazione che
    # misurava la durata: un modello che salta pezzi di frase si accorcia
    # esattamente come uno che parla svelto.
    #
    # **Qui sta la lezione, che e' costata una prova dal vivo.** Questo numero
    # vive in due posti — il default del backend e questo campo — e chi
    # costruisce il motore passa *questo*. Abbassato solo l'altro, le prove sono
    # continuate a 1,50 mentre i commenti dicevano 1,05, e il difetto e' andato
    # in produzione con una spiegazione rassicurante attaccata sopra. Due
    # sorgenti per lo stesso numero non sono un doppione: sono la garanzia che
    # prima o poi divergano, e che a divergere sia quella che nessuno legge.
    speed: float = 1.05
    # Solo per Kokoro, e separati da `speed` di proposito: **un numero solo per
    # tutti i motori e' gia' costato due sessioni**. Valgono le stesse due regole
    # del campo qui sopra — `kokoro_speed` sta agganciato a
    # `kokoro.DEFAULT_SPEED` e c'e' una verifica che li tiene allineati, e
    # `kokoro_weights` deve stare in `kokoro.PESI`.
    #
    # I pesi sono in config e non solo nel modulo perche' `tools/dub.py` scrive
    # `config.json` in ogni cartella di `runs/`: quale set ha prodotto quel WAV
    # dev'essere leggibile dalla prova, non ricostruibile a memoria.
    kokoro_speed: float = 1.0
    kokoro_weights: str = "fp32"  # fp32 | fp16 | int8 | q8f16
    # **Programmare la battuta prima di averla tutta.** Oggi non lo fa nessun
    # motore: l'unico che consegnava a pezzi era Qwen, tolto dopo la prova dal
    # vivo. Il campo resta perche' la catena sa ancora farlo — `speak.base`
    # dichiara il protocollo, il mixer tiene una battuta aperta, la verifica
    # `streaming` gira su un motore finto — e chi montera' il prossimo motore
    # autoregressivo eredita tutto invece di riscriverlo.
    #
    # **Il prezzo, che resta scritto perche' e' quello che ha fatto cadere Qwen**:
    # programmando prima la durata non si conosce, quindi budget e fretta si
    # calcolano su `chars_per_second`. Se il motore produce piu' parlato di quanto
    # la scena abbia tempo, nessuno scheduler lo salva — la coda diverge.
    stream: bool = True
    # **Quanto in fretta si chiede al sintetizzatore di parlare**, prima di
    # sintetizzare, quando la finestra della battuta e' stretta.
    #
    # Non e' la stessa cosa di comprimere dopo. WSOLA ripete e butta via pezzi di
    # forma d'onda: a 1,5 le consonanti si perdono e all'ascolto la voce **si
    # mangia le parole**. Un TTS a cui si chiede di andare piu' svelto produce
    # invece parlato articolato, come un attore che parla in fretta invece di una
    # registrazione mandata avanti veloce.
    #
    # Il tetto e' basso di proposito: `length_scale` di Piper non e'
    # proporzionale (a 0,8 si sbaglia del 14%) e oltre un certo punto la voce
    # perde carattere. Si chiede al sintetizzatore la parte comoda
    # dell'accelerazione, e a WSOLA solo il residuo — che restando piccolo non
    # si sente.
    # Alzato a 1,45 e `timing.rate_max` abbassato a 1,20, per una ragione
    # misurata: WSOLA **perde la fine** di cio' che comprime. Il puntatore di
    # analisi insegue la periodicita' e puo' arretrare a ogni passo; quegli
    # arretramenti si sommano, e a fine battuta non ha mai letto l'ultimo tratto
    # dell'ingresso. Provato con un tono riconoscibile negli ultimi 200 ms: a
    # rate 1,20 e 1,35 di quel tono nell'uscita non resta niente, mentre durata
    # e ampiezza sono perfette — la fine non manca, e' **sostituita** da audio
    # ripetuto. E' il motivo per cui all'ascolto "taglia l'ultima parola delle
    # frasi lunghe".
    #
    # Ancorare il puntatore alla griglia ideale recupera la coda ma rovina cio'
    # per cui WSOLA esiste: il giro identita' in allungamento passa da uno
    # spettro di 0,0001 a 0,04. Misurate tutte e tre le varianti; nessuna le
    # prende entrambe, e la riparazione vera e' un lavoro a se'.
    #
    # Nel frattempo si sposta il lavoro su chi non ha quel difetto: il
    # sintetizzatore accelera articolando, e a WSOLA resta il minimo.
    # **Abbassato a 1,20 su richiesta d'ascolto: a 1,45 la lettura correva.**
    # Il numero non era sbagliato per come era stato scelto — 1,45 e' il punto
    # oltre il quale Piper perde carattere, e spostare il lavoro su di lui
    # serviva a togliere compressione a WSOLA, che perde le code. Ma "quanto in
    # fretta si puo' andare senza rovinare la voce" e "quanto in fretta e'
    # piacevole ascoltare" sono due domande diverse, e solo la prima si misura.
    #
    # Il prezzo si paga in **sforamenti**: una battuta lunga sotto un sottotitolo
    # corto finira' piu' spesso oltre la sua finestra. E' la direzione giusta in
    # cui sbagliare — `never_drop` esiste per questo — perche' una battuta che
    # invade di poco la successiva si capisce, mentre una battuta corsa non si
    # capisce e non si riascolta.
    #
    # **1,05 e non 1,20, e il perche' e' una misura di Piper.** `length_scale`
    # non e' proporzionale, e nella direzione opposta a quella che immaginavo:
    # sulla stessa frase, chiedendo 1,45 si ottiene 1,21, chiedendo 1,20 si
    # ottiene 1,02. Il tetto vale su cio' che si **ottiene**, quindi abbassarlo a
    # 1,20 lasciava la lettura quasi dov'era — l'anello di correzione chiedeva
    # semplicemente di piu'.
    #
    # **E 1,20 e' il fondo utile, non un compromesso.** Provato 1,05: la durata
    # della prima battuta passa da 3,57 s a 3,62 s — cinque centesimi — ma la
    # compressione di WSOLA sale al suo massimo su **tutte** le battute (p50 da
    # 1,000 a 1,250) e gli sforamenti da 14 a 38 su 46. Sotto 1,20 la voce non
    # rallenta: il lavoro passa a WSOLA, che comprime schiacciando invece di
    # articolare ed e' quello che mangia le fini delle parole. Si guadagnano
    # cinque centesimi di calma e si perde l'ultima sillaba di ogni frase.
    #
    # **Alzato a 1,55, e il numero non e' nuovo: e' quello che il progetto stava
    # gia' ascoltando senza saperlo.** Finche' `chars_per_second` era 17,4 —
    # contato in un'unita' diversa da quella in cui veniva usato — la stima delle
    # durate era corta di un quarto, e l'anello di correzione lo leggeva come "il
    # sintetizzatore e' pigro" e alzava il guadagno. Il risultato misurato su
    # quella configurazione, cioe' su tutte le prove d'ascolto fatte finora, e'
    # `dub.native_x1000` con **mediana 1558**: Piper articolava gia' il 56% piu'
    # svelto, e nessuno se n'e' lamentato.
    #
    # Corretta l'unita', l'accelerazione consegnata e' crollata a 1,16 e WSOLA e'
    # andato al tetto sul 68% delle battute — che e' esattamente la leva
    # sbagliata. Il tetto quindi non era prudenza: era il tappo che teneva fermo
    # un valore che nella pratica veniva scavalcato dall'altra parte.
    #
    #     tetto   accelerazione consegnata p50   battute con WSOLA al tetto
    #     1,20              1,04                          80%
    #     1,35              1,16                          68%
    #     1,50              1,18                          70%
    #     1,55              (si veda la prova sotto)
    #
    # **E adesso il campo arriva a 3,0, restando 1,55 di default.** L'intervallo
    # e' stato alzato da 2,5 a 3,0 su richiesta, per poter chiedere il triplo
    # senza toccare il codice. Cosa succede davvero chiedendolo, motore per
    # motore, perche' qui un tetto alzato non e' una velocita' ottenuta:
    #
    #     piper        nessun tetto proprio: esegue la fretta chiesta per intero
    #     kokoro       taglia a 1,30 (`VELOCITA_INTEGRA`), oltre salta sillabe
    #     supertonic   taglia a 1,10, per la stessa ragione misurata
    #
    # Il residuo fra quel che si chiede e quel che il motore fa non si perde:
    # cade su WSOLA, che si ferma a `timing.rate_max` e schiaccia invece di
    # articolare. Quindi con SuperTonic e Kokoro portare questo campo a 3,0
    # sposta lavoro fino al loro tetto e **non oltre**: il triplo, su quei due,
    # si puo' solo schiacciare.
    native_rate_max: float = 1.55
    # Caratteri al secondo alla velocita' nominale, per stimare quanto durera'
    # la battuta **prima** di sintetizzarla.
    #
    # **Era 17,4, e i caratteri erano quelli sbagliati.** Quel numero e' stato
    # misurato contando *tutti* i caratteri; qui viene diviso per
    # `spoken_length()`, che conta **solo lettere e cifre** — e in italiano sono
    # l'81% del testo. La stessa passata di Piper vale 17,0 car/s contando tutto
    # e 13,7 contando come conta chi lo usa. Ogni durata prevista risultava
    # quindi corta di un quarto, la catena chiedeva meno fretta di quella che
    # serviva, e il residuo lo raccoglieva WSOLA — cioe' proprio la leva che
    # mangia le parole. E' lo stesso errore di forma che il progetto ha gia'
    # preso due volte: **selezionare con un operatore e misurare con un altro.**
    #
    # Questo resta il punto di partenza dichiarato: il valore vero lo porta il
    # backend (`TtsBackend.chars_per_second`), perche' il passo e' una proprieta'
    # del motore e non della sessione, e la pipeline lo impara comunque dalle
    # battute a cui non ha chiesto fretta.
    chars_per_second: float = 13.7


@dataclass
class RepeatConfig:
    """L'ultimo cancello: la stessa frase non si dice due volte di fila.

    **Non e' un rimedio elegante, ed e' voluto.** I doppioni nascono a monte,
    quando il lettore chiude una battuta ancora a schermo e la riapre; quel
    difetto e' stato trovato e corretto (`vision.vanish_frames`), ma i percorsi
    che portano allo stesso sintomo sono piu' d'uno — la sostituzione, la
    somiglianza sotto budget, una lettura che migliora a meta' — e ognuno ha la
    sua diagnosi. Questo cancello non li diagnostica: li **taglia tutti**, nel
    solo punto in cui il difetto smette di essere un evento nel log e diventa una
    voce che si sente.

    Sta in fondo alla catena di proposito. Piu' in su interferirebbe con la
    durata misurata dei sottotitoli, che serve alla calibrazione del tempo: una
    battuta riletta e' comunque un'osservazione buona di *quanto* e' rimasta a
    schermo, e va conservata. Qui invece si decide solo se **pronunciarla**, e
    quella e' una domanda diversa.

    Le battute soppresse si contano (`dub.repeated`): un cancello silenzioso che
    per un difetto di soglia si mangiasse dialogo vero sarebbe peggio del
    problema, e il contatore e' l'unica cosa che lo rende visibile.
    """

    enabled: bool = True
    # Entro quanti secondi due letture quasi uguali sono la stessa battuta.
    # Sopra questo tempo si pronuncia: un personaggio che ripete davvero la
    # stessa frase esiste ("Via! Via! Via!"), e zittirlo sarebbe un difetto.
    # **Sei secondi non bastavano per gli obiettivi di missione.** Misurato su
    # una sessione di diciannove minuti, 385 battute, cercando le coppie di testo
    # quasi identico per distanza nel tempo:
    #
    #     finestra   coppie prese   quali
    #        6 s          0         —
    #       10 s          2         'Cerca Lamar.', 'Vai da'
    #       20 s          2         le stesse
    #       30 s          2         le stesse
    #       45 s          3         + 'Capisci cosa intendo?'
    #
    # Le prime due sono testi di obiettivo che restano a schermo a lungo e che
    # l'OCR rilegge dopo qualche secondo; la terza, a **35,5 s** di distanza, e'
    # Lamar che ripete davvero la stessa frase, e zittirla sarebbe un difetto.
    # Fra 6,8 e 35,5 c'e' molto spazio: venti secondi prendono i doppioni e
    # lasciano quindici secondi di margine alla ripetizione vera.
    window_s: float = 20.0
    # Quanto devono somigliarsi, confrontate sulle sole lettere e cifre.
    #
    # La forma di questo cancello viene da un'implementazione che il problema non
    # ce l'ha: RSTGameTranslation fa OCR dell'area, concatena il testo, lo
    # normalizza (minuscole, via punteggiatura e spazi), lo confronta con
    # l'ultimo e se somiglia sopra `textsimilar_threshold` **esce senza
    # tradurre**. Quel programma non ha nessun concetto di battuta "aperta" e
    # "chiusa" — ha solo il testo di adesso contro quello di prima — ed e' per
    # questo che non produce doppioni. La sua soglia predefinita e' 0,9.
    similarity: float = 0.90  # la soglia di RSTGameTranslation, che il difetto non ce l'ha
    # **E la domanda che il rapporto non sa porre: una e' un pezzo dell'altra?**
    # RSTGameTranslation non ha questo problema perche' non ha il concetto di
    # battuta aperta: confronta il testo di adesso con quello di prima, e un
    # frammento seguito dal testo intero per lui e' un aggiornamento, non due
    # battute. Qui invece sono due eventi, e il rapporto fra un frammento e il
    # testo intero e' basso per costruzione — meta' del lungo non ha
    # corrispondenza. Misurato su una sessione dal vivo, 13 riletture marcate a
    # mano contro 217 battute distinte:
    #
    #     rapporto >= 0,90        0 riletture su 13,  0 battute vere zittite
    #     rapporto >= 0,80        2 riletture su 13,  1 battuta vera zittita
    #     contenimento >= 0,80    8 riletture su 13,  0 battute vere zittite
    #
    # Quelle 13 valevano 15,2 secondi di parlato ridetto su 140, ed erano la
    # causa dell'accumulo di coda: la stessa battuta di Lamar letta tre volte
    # portava l'arretrato a 4,6 secondi.
    containment: float = 0.80
    # Sotto questa lunghezza il contenimento non si applica. Le battute molto
    # corte sono contenute l'una nell'altra per caso.
    containment_min_chars: int = 8


@dataclass
class TimingConfig:
    """Aggancio al parlato originale.

    `predict_a` e `predict_b` sono i coefficienti di `D = a + b * n_caratteri`,
    e si misurano con `tools/bench_timing.py --write profiles/<gioco>.json`.
    I valori qui sotto sono **dichiarati, non misurati**: servono solo a far
    partire una sessione su un gioco mai calibrato.
    """

    predict_a: float = 0.90
    predict_b: float = 0.045
    # Fascia di plausibilita' di una durata: fuori di qui non e' una battuta.
    # Sotto, e' il frammento di una battuta riaperta a meta'; sopra, e' un
    # sottotitolo rimasto a schermo perche' il gioco e' in pausa o in un filmato.
    # Serve alla previsione (che non deve restituire assurdita') e
    # all'apprendimento (che non deve impararle).
    min_duration: float = 0.6
    max_duration: float = 8.0
    rate_min: float = 0.85
    # Il tetto di **WSOLA**, misurato: con il puntatore di analisi corretto la
    # fine della battuta sopravvive fino a 1,25 (rapporto 55) e crolla da 1,30
    # in su (3,4, poi 1,7). Non e' una scelta di gusto, e' dove sta il gradino.
    # La fretta oltre questa soglia la fa il sintetizzatore, che articola
    # invece di schiacciare.
    #
    # **Il campo si puo' portare fino a 3,0, il default no.** L'intervallo
    # dichiarato in `core.schema.LIMITI` e' stato alzato da 2,0 a 3,0 su
    # richiesta: serve a poter provare il triplo, non a consigliarlo. Il gradino
    # misurato qui sopra non si e' spostato — a 1,30 la fine della battuta e'
    # gia' sostituita da audio ripetuto — quindi da 1,25 in su non si compra
    # velocita', si comprano parole mangiate, e a 3,0 se ne mangia due terzi.
    # Chi vuole parlato veloce **intero** alza `tts.native_rate_max`, che lo
    # chiede a chi articola.
    rate_max: float = 1.25
    lead_ms: int = 0  # anticipo/ritardo fisso sull'attacco
    # **Il ritardo che si accetta invece di recuperarlo, in millisecondi.**
    #
    # Il budget di una battuta era `finestra prevista - tempo gia' passato dalla
    # comparsa del sottotitolo`, e in quel "tempo gia' passato" c'e' anche cio'
    # che si paga **su ogni battuta allo stesso modo**: mezzo secondo di attesa
    # per sapere chi parla, piu' la sintesi. Un ritardo uguale per tutti non e'
    # un debito: sposta il doppiaggio all'indietro di un blocco e lascia intatto
    # il ritmo della conversazione. Sottrarlo dal budget significa invece
    # chiedere a ogni battuta di recuperare da sola un ritardo che tornera'
    # identico alla battuta dopo — e si recupera nell'unico modo disponibile,
    # comprimendo.
    #
    # Misurato sulle 44 battute della scena del concessionario, prima di
    # cambiare niente: la durata naturale dell'italiano e' 0,83 volte la
    # finestra del sottotitolo (mediana), quindi ci sta. Ma togliendo dalla
    # finestra i 500 ms di attesa, le battute che non ci stanno piu' passano da
    # 11 su 44 a **29 su 44**, e la compressione richiesta al p90 da 1,17 a
    # 2,42. E' li' che nasce `dub.rate_x1000` inchiodato a 1250 su **tutti** i
    # percentili.
    #
    # **Era 250 ms, ed era misurato — su una catena che costava la meta'.**
    # Quel numero era il ginocchio quando la parte che torna identica a ogni
    # battuta erano l'attesa del riconoscimento e la sintesi, cioe' ~670 ms.
    # Con la traduzione sulla strada critica quella parte e' **1,6-1,7 s**
    # (misurata, non stimata: la mediana di `t_scheduled - t_subtitle` sulle
    # battute che non erano in coda, in due sessioni dal vivo), e una scusa da
    # 250 ms su un costo fisso da 1690 lascia al budget briciole: `dub.rate_x1000`
    # a 1250 su **tutti** i percentili con il parlato che riempie meta' scena.
    #
    # Rigiocando la programmazione di quelle due sessioni — stessi tempi veri,
    # stessa durata del parlato, cambia solo la scusa (24 e 18 battute, si
    # riporta la **peggiore** delle due):
    #
    #     scusa    compressione p50    battute al tetto    latenza p95
    #      250          1,250                100%             2551 ms
    #      900          1,250                 62%             2574 ms
    #     1000          1,182                 25%             2660 ms
    #     1200          1,000                 17%             2771 ms
    #     1250          1,000                 17%             2771 ms
    #     1600          1,000                 12%             3080 ms di coda
    #
    # Il precipizio sta fra 900 e 1200 e l'altopiano comincia a 1200: **1250 e'
    # in mezzo all'altopiano**, non sul suo orlo — che e' la regola con cui in
    # questo progetto si sceglie una soglia. Oltre non si compra piu' niente e la
    # coda comincia a crescere.
    #
    # **E senza traduzione non peggiora**, che era il rischio (misurato adesso
    # sulla registrazione, 43 battute, Piper, italiano):
    #
    #     scusa    compressione p50   p95     latenza p95   sfori
    #      250          1,000        1,250      1031 ms       9
    #      750          1,000        1,248      1066 ms       4
    #     1250          1,000        1,133      1401 ms       4
    #     1750          1,000        1,143      1486 ms       4
    #
    # La mediana non si muove, il p95 della compressione **migliora**, gli
    # sfori si dimezzano, e si pagano 370 ms sul p95 della latenza. Da 1250 a
    # 1750 non cambia quasi niente: nessuna fuga in avanti della coda.
    #
    # La tabella vecchia, e il perche' del meccanismo, stanno nel docstring del
    # modulo `fuse/timing.py`.
    accepted_delay_ms: int = 1250
    # **Spento perche' misurato, non perche' non sia scritto.** Il piano dava per
    # buono che il sottotitolo compaia quando il gioco decide e la voce cominci
    # quando il personaggio apre la bocca, e che i due istanti non coincidano:
    # su GTA V non e' cosi'. `tools/bench_onset.py` misura lo sfasamento fra
    # l'onset del VAD e la comparsa del sottotitolo su due registrazioni, e trova
    # una mediana di -33 ms e -20 ms — cioe' i due istanti coincidono, e non c'e'
    # niente da correggere. L'eccesso sul caso e' +18,8% su una registrazione e
    # +10,7% sull'altra, quindi l'onset e' anche *disponibile* per una battuta su
    # cinque o su nove: agganciarcisi sposterebbe l'attacco di poche decine di
    # millisecondi quando ci azzecca, e di mezzo secondo quando l'accoppiamento
    # e' casuale. Su un gioco diverso la premessa puo' tornare vera: il banco
    # esiste per rifare la domanda, e questo campo per rispondere di si'.
    use_vad_onset: bool = False
    never_drop: bool = True  # oltre i limiti si sfora, non si scarta
    # Quando arriva un sottotitolo nuovo mentre la voce sta ancora dicendo il
    # precedente, si stringe il **residuo non ancora suonato** invece di far
    # aspettare quello nuovo. Non e' una previsione: l'arrivo della battuta dopo
    # e' un fatto osservato, e capita nell'istante in cui serve. Attacca il 34,9%
    # di battute che sul banco invaderebbero la successiva — l'unico sforamento
    # che fa danno, perche' due voci accavallate fanno perdere una riga.
    hurry_on_next: bool = True
    # **Sotto questo residuo non si stringe piu': si sfora.**
    # `hurry` mette tutta la compressione sulla coda, cioe' esattamente dove sta
    # l'ultima parola — e l'ultima parola e' quella che chiude il senso della
    # frase. Con la guardia a 150 ms si stringeva ancora quella, e all'ascolto
    # la battuta sembrava interrompersi. Mezzo secondo scarso e' una parola o
    # due: guadagnare due decimi accelerandole costa piu' di quanto rende,
    # perche' un doppiaggio che sfora di due decimi non lo nota nessuno mentre
    # una parola finale impastata si sente sempre.
    hurry_min_residue_ms: float = 600.0
    # **Quanta coda della battuta non passa mai dallo stiramento.** WSOLA perde
    # la fine di cio' che comprime — misurato, a rate 1,20 di un tono
    # riconoscibile negli ultimi 200 ms non resta niente — e dal vivo si sente
    # come "si ferma a 'questa roba stia' e non dice 'funzionando'". Finche' la
    # riparazione vera non c'e', l'ultima parola non ci passa: si comprime solo
    # il corpo e la fine si riattacca com'e' uscita dal sintetizzatore.
    #
    # **Spento a zero adesso che il puntatore di analisi e' stato corretto.**
    # Spezzare la battuta non chiudeva il buco: lo spostava. WSOLA perde la fine
    # di *qualunque* segmento riceve, quindi con il taglio in corpo+coda a
    # sparire era la fine del **corpo**, cioe' il mezzo della frase — dal vivo
    # si sentiva "l'inizio e la fine, non tutta la frase". Il codice resta
    # perche' documenta il ragionamento e serve se qualcuno alza `search_ms`.
    keep_tail_seconds: float = 0.0
    # Aggiornamento in linea dei coefficienti: `decay` e' quanto pesa il
    # passato a ogni nuova battuta (0,97 ≈ una memoria di una trentina), e
    # `max_drift` quanto la retta imparata puo' allontanarsi da quella del
    # profilo — la guardia contro l'imparare bene una cosa sbagliata.
    learn_decay: float = 0.97
    learn_min_samples: int = 12
    learn_max_drift: float = 0.35


@dataclass
class MixConfig:
    """Uscita audio. Il duck agisce sul solo canale centrale, dove sta il
    parlato: musica ed effetti restano intatti."""

    # **Di quanto si abbassa la voce originale mentre parla la nostra**, ed e'
    # il campo che risponde alla domanda «si puo' togliere la voce del gioco e
    # metterci la nostra?». Si', per quanto lo permette un filtro che non costa
    # niente: non si abbassa tutto l'audio, si abbassa il **solo canale
    # centrale** (`mix/center.py`), dove nei giochi sta il dialogo, mentre
    # musica, motori e ambiente stanno larghi e restano al loro volume.
    #
    # Non e' una separazione vera: un'esplosione centrata viene attenuata anche
    # lei. Ma costa quattro operazioni per campione e **non ha latenza**, mentre
    # una separazione neurale costerebbe piu' di tutto il resto della catena e
    # aggiungerebbe il ritardo del suo buffer, proprio dove il ritardo e' la
    # valuta scarsa. E' una scelta presa e scritta, non una cosa da fare.
    #
    # **Non c'e' un interruttore, e non serve**: a 0 dB il filtro e' spento, e
    # `audio.center_enabled` — che si somiglia — e' un'altra cosa, sta dalla
    # parte della cattura e riguarda l'impronta di chi parla.
    #
    # A **0 dB il filtro e' spento**, e lo e' per costruzione e non per un `if`:
    # con guadagno 1 la scomposizione mid/side ricompone l'ingresso campione per
    # campione (c'e' una verifica che lo chiede). Piu' si scende e piu' sparisce
    # l'originale, ma con lui anche cio' che gli sta vicino al centro.
    duck_db: float = -14.0
    # **Il volume della voce doppiata**, cioe' della nostra e non del gioco. Zero
    # vuol dire «come esce dal sintetizzatore», che e' il livello su cui sono
    # tarati i tre motori. Si alza quando il gioco copre la voce anche col
    # centro abbassato, e si abbassa quando la voce sovrasta la scena.
    #
    # **Ma non e' il volume generale**, e alzarlo troppo non e' gratis: la voce
    # si somma all'audio del gioco e la somma puo' superare il fondo scala. Li'
    # entra il limitatore morbido del mixer, che comprime i picchi invece di
    # tagliarli — quindi non si sente sporcare, si sente *schiacciare*, e il
    # contatore `mix.clipped` e' l'unica cosa che lo dice. Per alzare la voce
    # rispetto al gioco conviene prima scendere con `duck_db`.
    dub_gain_db: float = 0.0
    # **Quanto svelto scende, in millisecondi.** Il gioco non si abbassa quando
    # la voce parte: si abbassa **prima**, di questo tempo esatto, perche'
    # abbassarlo mentre la voce parte la lascerebbe coperta per i primi
    # quaranta millisecondi — quelli in cui l'orecchio decide se ha capito o no.
    # Quindi questo numero e' due cose insieme: quanto dura la discesa e quanto
    # anticipo si prende il mixer (`Mixer._starts_soon`). Alzandolo, la discesa
    # si sente meno ma il gioco comincia ad abbassarsi molto prima della voce.
    duck_attack_ms: int = 40
    # **Quanto svelto risale, in millisecondi.** Asimmetrico rispetto
    # all'attacco di proposito: bisogna fare spazio alla voce in fretta, ma
    # rialzare il gioco di scatto fra una battuta e l'altra si sente quanto non
    # abbassarlo. Chi lo accorcia sotto l'attacco ottiene il pompaggio descritto
    # in `duck_hold_ms` anche fra battute lontane.
    duck_release_ms: int = 220
    # **Quanto il duck resta giu' aspettando la battuta successiva.**
    # Senza questa attesa, nel dialogo fitto il gioco pompa: misurato dal vivo,
    # il 26% degli intervalli fra una battuta e la seguente vale 0,12 s — la
    # pausa di respiro fra due battute incatenate — e in 120 ms un rilascio da
    # 220 ms risale a meta' strada, per poi essere rischiacciato in 40 ms.
    # Sono oltre 8 dB su e giu' ogni centosessanta millisecondi, e non sulla
    # voce ma sull'**audio del gioco**: all'ascolto si taglia tutto, non solo il
    # doppiaggio. Quando i personaggi parlano lenti gli intervalli sono di
    # secondi e il difetto sparisce, che e' il motivo per cui si sente solo
    # nelle scene fitte.
    duck_hold_ms: float = 500.0
    # **Se l'audio del gioco passa da noi o no.** Acceso, il programma prende
    # l'audio catturato, ne abbassa il centro mentre parla e ci somma sopra la
    # voce: quello che esce dalla scheda scelta e' il doppiaggio finito, e il
    # gioco va ascoltato **solo** da li'. Spento, esce la sola voce italiana, e
    # il gioco lo si sente per conto suo — e' la strada di chi manda il gioco
    # alle casse e il doppiaggio alle cuffie, o di chi vuole registrare la sola
    # traccia doppiata. In quel caso il filtro sul centro non ha niente su cui
    # lavorare: il parlato originale resta come sta, perche' non passa di qui.
    passthrough: bool = True
    # **Quanti millisecondi di voce devono essere pronti prima che una battuta in
    # streaming cominci a suonare.** Vale solo per i motori che consegnano a
    # pezzi (oggi Qwen): per gli altri l'audio c'e' tutto e questo campo non fa
    # niente.
    #
    # Serve a un difetto trovato dal vivo e invisibile al banco: la battuta
    # partiva nell'istante in cui la sua generazione cominciava, quindi il mixer
    # versava silenzio e le parole arrivavano a goccia — **parole sminuzzate**.
    # Aspettare il cuscino costa un ritardo pari al cuscino, una volta per
    # battuta; non aspettarlo costa la battuta.
    prebuffer_ms: float = 350.0
    # **Dichiarato e non letto da nessuno**, ed e' scritto qui perche' un campo
    # che sembra fare qualcosa e non la fa e' peggio di un campo che manca. La
    # scheda su cui esce il doppiaggio si sceglie nella scheda «Preparazione»
    # (passo 3) o con `--output`, e finisce in `Opzioni.output`: nessuno legge
    # questo. Non e' esposto nel pannello proprio per questo — una manopola che
    # non muove niente e' peggio di una manopola che manca. Ottavo campo di
    # questa forma in questo progetto, dopo `max_ocr_hz`, `tts.device`,
    # `background_mode`, `overlay.ritardo`, il `region` di `make_screen`,
    # `profiles/ultima.json` e la `row_band` della calibrazione.
    output_device: str = ""


@dataclass
class UiConfig:
    enabled: bool = False
    log_dir: str = "runs"
    save_mix: bool = True
    # **La lingua della finestra, che non e' la lingua del doppiaggio.**
    # `translate.source` e `translate.target` decidono cosa viene *detto*;
    # questa decide cosa c'e' *scritto sui bottoni*. Confonderle e' facile e
    # costa una sessione: si mette `en` qui credendo di aver acceso la
    # traduzione, e la catena continua a doppiare in italiano.
    #
    # `auto` segue la lingua di Windows, e **se per quella lingua non c'e' un
    # catalogo torna all'italiano** invece di lasciare la finestra a meta'.
    # I cataloghi stanno in `ui/lingue/*.json`, sono scritti nel repo e si
    # rifanno con `tools/traduci_ui.py`: chiederli alla rete mentre la finestra
    # si apre vorrebbe dire una finestra in bianco quando la rete non c'e'.
    #
    # Si applica **a caldo**, come il tema: la finestra si ripercorre e i testi
    # cambiano senza riavviare niente.
    #
    # Non si traducono: il registro, la barra della misura e le **spiegazioni
    # dei parametri**. Quelle vengono dai commenti di questo file, misure
    # comprese, e passarle a un traduttore automatico e' esattamente il
    # «riscriverli e perdere le misure» contro cui esiste `core/schema.py`.
    #
    # **Il default e' `auto`**, cioe' chi apre il programma lo trova nella lingua
    # in cui usa il computer, senza sapere che questa manopola esiste. Su una
    # Windows italiana `auto` **e'** l'italiano, quindi per chi ha scritto il
    # programma non cambia niente e per tutti gli altri cambia tutto. La scelta
    # esplicita resta, e il tutorial iniziale la propone come primo passo.
    lingua: str = "auto"


@dataclass
class LabelConfig:
    """Chi parla, quando e' il **gioco** a scriverlo (`vision/label.py`).

    Spento di default, e deve esserlo: nessun gioco e' uguale a un altro e
    indovinare il formato del prefisso vuol dire, sul primo falso positivo,
    inventare un personaggio e bruciargli addosso una voce del pool. Chi accende
    questa sezione sa che gioco sta giocando.

    **Quando c'e', vale mezzo secondo.** Il nome dichiarato sostituisce il
    riconoscimento dall'audio, quindi cadono sia i `speaker.decide_after_ms` di
    attesa sia il calcolo dell'impronta — e quei 500 ms sono la voce piu' grossa
    della latenza (misurato: il doppio della sintesi, con Kokoro).

    GTA V i nomi non li scrive, quindi qui resta spenta e **non e' mai stata
    provata su materiale vero**: le verifiche sono su testo sintetico. E' la prima
    cosa da guardare quando arriva la registrazione di un altro gioco.
    """

    enabled: bool = False
    # Come il gioco scrive il nome. `nome:` -> «Franklin: come va»;
    # `[nome]` -> «[Franklin] come va»; `nome-` -> «Franklin - come va».
    form: str = "nome:"
    # Per i casi che non rientrano nelle tre forme. Deve dichiarare i gruppi
    # `(?P<nome>...)` e `(?P<testo>...)`; se c'e', vince su `form`.
    regex: str = ""
    # **I personaggi dichiarati, ed e' la guardia che conta.** Con l'elenco pieno
    # si accettano solo quei nomi, e un OCR che legge «Si, era lui» come nome
    # viene scartato invece di diventare un personaggio. Vuoto = si accetta
    # qualunque nome che superi le guardie di forma.
    names: tuple[str, ...] = ()
    # Se vero, senza `names` non si etichetta nulla. Per chi preferisce non
    # correre alcun rischio di falso positivo.
    require_names: bool = False
    max_name_len: int = 24
    # Un colore per personaggio: `{"Franklin": "#5ac8fa"}`. Si confronta col
    # colore medio dell'inchiostro della riga. Sopra `color_tolerance` (distanza
    # euclidea in RGB 0-255) non si decide — senza soglia il piu' vicino c'e'
    # sempre, e un sottotitolo bianco finirebbe al personaggio meno lontano dal
    # bianco.
    colors: dict = field(default_factory=dict)
    color_tolerance: float = 60.0

    # **Chi ha quale voce, deciso da te.** `{"Franklin": "riccardo"}`. Vince su
    # tutto: nessuna assegnazione automatica puo' toglierla.
    voices: dict = field(default_factory=dict)
    # **E chi non l'hai deciso tu, se la tiene comunque per sempre.** Quando un
    # personaggio ha un nome dichiarato dal gioco, la voce che gli tocca alla
    # prima battuta viene scritta qui e riletta alla sessione dopo — cosi'
    # Franklin ha la stessa voce oggi e domani.
    #
    # Senza questo file, l'ordine in cui i personaggi parlano decide chi prende
    # quale voce: chi apre la scena prende la prima voce del pool. Riaprendo il
    # gioco da un altro punto, lo stesso personaggio ne prende un'altra — cioe'
    # la voce non e' del personaggio, e' del turno. Con i nomi dal gioco quel
    # difetto si puo' togliere del tutto, e senza nomi non si potrebbe.
    #
    # Vuoto = non si ricorda niente fra una sessione e l'altra.
    cast_file: str = "runs/cast.json"


@dataclass
class CorrectConfig:
    """Correggere gli artefatti dell'OCR (`vision/correct.py`).

    **Spento, e il default non e' timidezza: e' una misura.** La correzione
    automatica e' gia' stata provata e bocciata — due giuste su otto, con errori
    del tipo `rapinato -> rovinato`. Qui si puo' riaccendere solo perche' adesso
    ci sono le guardie e la fiducia dichiarata, non perche' si sia cambiata idea.

    E il guadagno massimo e' piccolo, misurato su 4280 battute archiviate: gli
    errori davvero correggibili sono **circa una parola su settanta**, perche' le
    parole "non italiane" sono in maggioranza nomi propri (527 su 1230), forme
    vere non elencate e frammenti di HUD. Un correttore che sbaglia una volta su
    dieci fa piu' danno di quanto ripari.
    """

    # `nessuno` | `llm` (Gemma in-process) | `ollama` (**lo stesso modello che
    # traduce**: una sola attesa, una sola memoria occupata, e il modello sta
    # fuori dal venv).
    backend: str = "nessuno"
    ollama_model: str = ""  # vuoto = quello di `translate.ollama_model`
    ollama_host: str = ""  # vuoto = quello di `translate.ollama_host`
    # Sotto questa fiducia non si corregge. Alta di proposito: la domanda non e'
    # "e' probabile che sia questa" ma "sono disposto a farlo dire alla voce".
    min_confidence: float = 0.90
    max_distance: int = 2
    # Quante battute precedenti si danno al correttore. E' l'idea che rende
    # questo tentativo diverso da quello bocciato: senza contesto `farto` e'
    # vicino a `fatto`, `parto` e `tarto` e si sceglie a caso fra le vere.
    context_lines: int = 10
    llm_model: str = ""
    llm_device: str = "cpu"
    # Oltre questo tempo si rinuncia e si lascia il testo com'e'. La correzione
    # sta sul thread video, dove il costo **si amplifica invece di sommarsi**.
    llm_max_ms: float = 80.0


@dataclass
class TranslateConfig:
    """Tradurre il sottotitolo, e ridisegnarlo sopra l'originale.

    Spenta di default: su GTA V i sottotitoli sono gia' in italiano e tradurre
    sarebbe tradurre l'italiano in italiano.

    **`locale` e' il default quando si accende, e non per prestazioni.** `google`
    manda ogni sottotitolo ai server di Google, che e' il contrario dell'«uso
    completamente locale ed estrema privacy» che questo progetto si e' messo fra
    gli obiettivi. Si puo' scegliere, la scelta e' esplicita, e il backend lo
    dichiara su stderr quando parte.
    """

    enabled: bool = False
    # **Tre livelli, dal piu' leggero al piu' pesante**, piu' il servizio esterno:
    #
    #   `locale`  Argos/CTranslate2. Leggero, veloce, qualita' da traduttore
    #             automatico. Per PC senza potenza di calcolo da spendere.
    #   `llm`     Gemma 3 1B in locale su CPU. Piu' lento e piu' pesante, ma
    #             tiene il **contesto** delle battute precedenti — e lo stesso
    #             modello serve anche a ripulire l'OCR (`correct.backend=llm`),
    #             quindi si carica una volta e lavora per due.
    #   `google`  Nessun costo di calcolo, ma **i sottotitoli escono dalla
    #             macchina**. E' l'opzione per chi non ha potenza da spendere e
    #             accetta il baratto.
    #   `ollama`  parla con Ollama in HTTP: i modelli stanno fuori dal venv e si
    #             cambiano senza reinstallare niente. `TranslateGemma` e' il piu'
    #             fluente dei locali, ma si veda `preserve_register`.
    #
    # **Il default e' `locale` per il p95, non per il p50**, e il numero che
    # decide non e' quanto costa in media ma quanto costa nel caso peggiore.
    # La traduzione avviene **dentro** i 500 ms in cui si aspetta di sapere chi
    # parla (`core/anticipa.py`): tutto cio' che sta sotto quella soglia e'
    # gratis, tutto cio' che la supera si paga intero. Misurato su 120
    # sottotitoli veri dell'archivio, it->en:
    #
    #   backend   p50     p95      max      p95/p50
    #   locale     39 ms    67 ms    97 ms    1,70
    #   google    491 ms  1188 ms  2496 ms    2,42
    #   llm       589 ms   869 ms  1062 ms    1,47
    #
    # Argos ci sta dentro con un fattore 7, e sulle 160 battute piu' lunghe mai
    # lette (fino a 217 caratteri) il caso peggiore e' 220 ms. Google e'
    # **bimodale**: dal vivo ha dato 427 ms in una passata e 1077 in quella
    # dopo, stessa macchina — e una cosa che varia di un fattore dieci non si
    # puo' nascondere dentro una finestra fissa. Dal vivo: con google 9 battute
    # anticipate su 65 e latenza 1828 ms, con Argos **65 su 65** e 962 ms.
    # I 3937 ms di caricamento a freddo si pagano ad Avvia, non a battuta.
    #
    # E la domanda che viene **prima** della velocita' — il modello dice cio'
    # che c'e' scritto? — Argos la passa: 14 battute italiane volgari vere,
    # 14/14 col registro tenuto, zero rifiuti. La resa e' piu' ruvida di
    # google, ma e' un difetto di qualita', non di contenuto ammorbidito.
    backend: str = "locale"  # locale | llm | ollama | google | nessuno
    llm_model: str = ""  # vuoto = `models/llm/gemma-3-1b-it-Q4_K_M.gguf`
    ollama_model: str = "translategemma:4b"  # 4b | 12b | 27b, o un altro modello
    ollama_host: str = "http://127.0.0.1:11434"
    # **Chiedere al modello di non ammorbidire le parolacce.** Su questo materiale
    # non e' una questione di gusto: un modello che riscrive «Get the fuck out of
    # my car, asshole» in «Esci immediatamente dalla mia macchina, idiota»
    # consegna un doppiaggio che dice un'altra cosa rispetto a quello che c'e'
    # scritto a schermo — e nessun contatore lo mostra, perche' la traduzione
    # riesce benissimo.
    #
    # Misurato su sei battute volgari di GTA V (`tools/bench_translate.py
    # --parolacce`), quante uscite hanno tenuto il registro:
    #
    #     google                          6/6      (ma i dati escono)
    #     translategemma:4b  + registro   3/6
    #     translategemma:4b  template     0/6
    #     translategemma:12b template     0/6
    #     gemma-3-1b locale               1/6
    #
    # Acceso costa una traduzione un po' meno elegante — si tocca il template su
    # cui il modello e' stato addestrato — e vale la pena lo stesso.
    preserve_register: bool = True
    # **Quante battute precedenti dare al modello. Zero, e non e' pigrizia: e'
    # una misura contraria a quello che ci si aspettava.**
    #
    # L'idea era che il contesto permettesse di tradurre meglio. Provata con il
    # caso nullo giusto — stesse frasi, stesso modello, unica differenza il
    # contesto — su Gemma 3 1B:
    #
    #     traduzione   senza contesto 254 ms p50   con contesto 457 ms
    #     "Knock knock!"      senza -> "Chi e'?"   con -> "Knock knock!"
    #     "Are you kidding me?"           con -> ripete la traduzione di due
    #                                            battute prima, parola per parola
    #
    # Su nove confronti (cinque di traduzione, quattro di correzione) il contesto
    # non ha migliorato **nessun** caso e ne ha peggiorati due. Un modello da un
    # miliardo di parametri, con dieci righe davanti, ricopia invece di ragionare.
    #
    # Resta il campo, perche' con un modello piu' grande la risposta puo' essere
    # un'altra e va rimisurata invece che ereditata. Ma il default segue la
    # misura, non l'intenzione.
    context_lines: int = 0
    # **La lingua di partenza**, in codice ISO. L'elenco non sta in questo
    # commento: sono centotrentatre voci, e un elenco di centotrentatre nomi
    # dentro un commento non e' una spiegazione, e' una tabella che nessuno
    # rilegge. Sta in `translate/lingue.py`, e la finestra lo prende da li'
    # (`ui.qt_controlli.SceltaLingua`) con la casella in cui si digita per
    # filtrare — perche' con centotrentatre voci un menu liscio non si usa.
    #
    # `auto` lo capisce solo Google: i modelli offline sono **di** una coppia di
    # lingue, quindi con `locale` un `auto` diventa `en` e viene detto.
    source: str = "auto"
    # **La lingua di arrivo**, in codice ISO. Il menu che la offre dice la
    # verita' su due cose che altrimenti restano mute.
    #
    # La prima: cosa sa fare il backend scelto. Google le fa tutte;
    # `locale` (Argos) esiste solo per **coppie** pubblicate, e quella che manca
    # si scarica ad Avvia; `llm` e `ollama` dipendono dal modello montato. La
    # forma scelta e' **mostrarle tutte e dichiarare**, non filtrare: filtrare
    # richiederebbe un elenco chiuso per ogni backend, e per tre su quattro
    # quell'elenco non esiste — si toglierebbero scelte che funzionano e
    # passerebbero quelle che non funzionano, con l'aria di sapere. Quindi
    # `translate.lingue.copertura()` torna un elenco chiuso **solo dove lo e'
    # davvero** (Google) e altrove torna la frase che dice da cosa dipende.
    #
    # La seconda: se il sintetizzatore montato ha una voce per questa lingua.
    # Non ce l'ha quasi mai — Piper e SuperTonic parlano solo italiano, Kokoro
    # italiano e inglese — e senza avviso la battuta esce con una voce italiana
    # che pronuncia il giapponese: nessun errore, nessun contatore, audio che
    # esce. La regola sta in `speak.pool.ha_voce`, fuori dalla finestra.
    target: str = "it"
    # Oltre questo tempo la traduzione e' comunque usata ma **contata come
    # lenta**: sta sulla strada critica, e se succede spesso quel backend non e'
    # adatto. Vale anche da timeout di rete per `google`.
    #
    # 400 ms sono larghi per Google, che a connessione aperta risponde in **64 ms**
    # di mediana (misurato). L'apertura invece ha un tetto suo, molto piu' largo:
    # la prima stretta di mano di una sessione e' arrivata a 1304 ms, e con questo
    # tetto la prima battuta sarebbe uscita non tradotta.
    timeout_ms: float = 400.0
    # **Il tetto della rete, che e' un'altra cosa e per due sessioni e' stato la
    # stessa.** `timeout_ms` dice «oltre questo tempo la traduzione e' lenta» e
    # non scarta niente; questo dice «oltre questo tempo si rinuncia», e scarta.
    # Erano lo stesso numero, e il risultato e' che con 400 ms di tetto **una
    # battuta su tre restava in italiano**: la traduzione riusciva, arrivava a
    # 500 ms e veniva buttata via da un timeout di socket.
    #
    # E i 64 ms su cui i 400 erano stati tarati vengono da una misura fatta con
    # la rete ferma. Nel caso d'uso vero la rete **non** e' ferma: il gioco o il
    # video sono in riproduzione e si prendono la banda. Misurato con un video
    # YouTube in corso, Google risponde in 300-550 ms — cioe' proprio a cavallo
    # del tetto che avevamo messo.
    #
    # Due secondi sono larghi per la rete e stretti per il thread video, dove
    # questa chiamata sta: oltre, meglio la battuta in italiano che il lettore
    # di sottotitoli fermo.
    net_timeout_ms: float = 2000.0
    local_model: str = ""

    # -- come si vede a schermo -------------------------------------------
    # **La sostituzione grafica**: il testo tradotto viene ridisegnato sopra il
    # sottotitolo originale, dentro un riquadro pieno che lo copre. Senza il
    # riquadro si leggerebbero due testi sovrapposti, che e' peggio di nessuno
    # dei due.
    overlay: bool = True
    # Come si copre il sottotitolo originale sotto quello tradotto. **In tutti e
    # tre i casi si tocca solo l'inchiostro delle righe lette, non la ROI**:
    # spegnere una fascia larga mezzo schermo per coprire una riga di testo era
    # il difetto, non la soluzione.
    #
    #   `blur`     si sfoca il **rettangolo che circoscrive il sottotitolo**, sui
    #              pixel di ogni fotogramma: l'originale diventa illeggibile, la
    #              scena resta viva e non si tocca niente fuori da quel
    #              rettangolo. E' il default, ed e' la forma che ha funzionato
    #              dopo che due piu' complicate avevano fallito a schermo;
    #   `riquadro` un rettangolo pieno del colore di `background`;
    #   `nessuno`  non si copre niente: si scrive sopra e basta.
    background_mode: str = "blur"  # blur | riquadro | nessuno
    # **Come si ottiene il "buco" attorno al testo, e non e' un dettaglio di
    # gusto: e' l'unica cosa che puo' rendere l'overlay invisibile.**
    #
    #   `true`   il buco e' un **colore-chiave** dichiarato trasparente da
    #            Windows. E' la resa migliore — il gioco si vede vivo attraverso
    #            la finestra — ma richiede una finestra *layered*, e una finestra
    #            layered col colore-chiave **piu'** l'esclusione dalla cattura
    #            sono due modi diversi di dire al compositore «questa finestra e'
    #            speciale»: insieme, su alcune configurazioni, la finestra non
    #            compare affatto;
    #   `false`  la finestra e' **opaca** e il buco lo riempiono i pixel del
    #            gioco, che la catena ha gia' in mano. Piu' rozzo (la scena
    #            dietro resta ferma fra un rinfresco e l'altro, un decimo di
    #            secondo) ma **si vede sempre**, perche' e' una finestra normale.
    #
    # Se il sottotitolo tradotto non compare a schermo, questa e' la prima cosa
    # da spegnere.
    transparent: bool = True
    # Quanto sfocare. Per l'MP4 e' il raggio di `boxblur` in pixel del video; dal
    # vivo e' il raggio **su un inchiostro alto 40 px** (GTA V a 1080p) e segue
    # l'altezza dei glifi, cosi' lo stesso numero cancella allo stesso modo a
    # 1080p e a 1440p e su un gioco che scrive piu' grande.
    blur_strength: float = 12.0
    # **Il tradotto tiene la misura del sottotitolo che copre.** Spento (il
    # default) il testo nuovo prende lo spazio che gli serve e puo' essere piu'
    # largo dell'originale: l'inglese di «Come va, bello?» e' il doppio.
    # Acceso, comanda il **riquadro** e a cedere e' il corpo del carattere, che
    # si stringe finche' la traduzione non ci sta dentro — stessa posizione,
    # stessa altezza di riga, stesso colore.
    #
    # Misurato su una battuta vera: `'Come va, bello?'` (riquadro 220 px) contro
    # `'How are you doing, handsome?'` — spento corpo 29 e toppa 450x45, acceso
    # corpo 14 e toppa 238x45.
    #
    # **Il prezzo e' che il tradotto diventa piccolo**, e su una frase molto piu'
    # lunga dell'originale si legge peggio dell'originale che copre. Sotto il
    # pavimento del corpo non si stringe piu' e si lascia sforare: illeggibile e'
    # peggio di largo. E' per questo che il default e' spento — la scelta la fa
    # l'occhio, su un gioco vero, e non c'e' una misura che possa farla al posto
    # suo.
    misura_originale: bool = False
    # **Zero vuol dire «come il gioco», ed e' il default.** La misura del
    # carattere si prende dall'altezza dei glifi del sottotitolo che si sta
    # coprendo: cosi' la battuta tradotta si posa dove stava l'originale, della
    # stessa taglia, e sembra il sottotitolo del gioco invece di un cartello
    # appiccicato sopra. Un numero scelto da noi e' sbagliato per costruzione,
    # perche' ogni gioco scrive i sottotitoli come vuole.
    #
    # Diverso da zero: altezza come **frazione dell'altezza dello schermo**, in
    # frazione e non in punti, cosi' vale a 1080p e a 1440p.
    font_frac: float = 0.0
    font: str = "Arial"
    # **Vuoto vuol dire «come il gioco»**, per la stessa ragione della misura: si
    # usa il colore medio dei glifi originali, riportato alla sua luminosita'
    # vera. Su GTA V viene bianco; su un gioco che colora i personaggi, viene il
    # colore del personaggio. Diverso da vuoto: `#rrggbb`, e vince.
    color: str = ""
    # **Il fondo di `background_mode="riquadro"`. Vuoto = «come la scena».**
    #
    # E' la modalita' che il ritardo non ce l'ha **per costruzione**: una tinta
    # piatta non ha struttura, quindi non puo' mostrarla in ritardo. Il blur
    # invece fa vedere pixel del gioco, e farli vedere vuol dire copiarli —
    # cattura, processo, Tk, compositore — con un pavimento di due o tre
    # fotogrammi che nessuna ottimizzazione toglie. Verificato che il
    # compositore non lo puo' fare al posto nostro: su Windows 11 26200
    # `ACCENT_ENABLE_BLURBEHIND` e `ACCENT_ENABLE_ACRYLICBLURBEHIND` **tingono e
    # basta** — misurato con un fondo a righe da un pixel piu' uno scalino
    # chiaro/scuro, lo scalino passa da 99,9 a 3,8 e 9,5, cioe' la struttura
    # dietro non arriva.
    #
    # Con il campo vuoto la tinta si prende dalla **mediana dei pixel coperti**,
    # a ogni rinfresco: la toppa e' del colore di cio' che c'era, si aggiorna
    # come il blur e non puo' sembrare vecchia. Un `#rrggbb` esplicito vince.
    background: str = ""
    background_opacity: float = 1.0
    outline: float = 2.0
    # **Il pavimento del carattere, in punti.** Serve alla modalita' `schermo`,
    # dove il riquadro comanda e il corpo si adatta: una traduzione piu' lunga
    # dell'originale non allarga la toppa, si **stringe** per starci dentro.
    #
    # Ma stringere ha un fondo, e va detto qual e': sotto una certa misura il
    # testo non si legge, e una traduzione illeggibile e' peggio di una che
    # sfora — chi sfora almeno la si legge, e si capisce anche cos'e' successo.
    # Arrivati qui si smette di stringere e si lascia uscire dal riquadro.
    #
    # **Il numero viene dal contorno, non dal gusto**, e si misura con
    # `tools/bench_schermo.py --pavimento`. Il testo si disegna con un contorno
    # nero (`outline`, 2 px) *sopra* l'asta del glifo: in Arial grassetto l'asta
    # e' circa il 12% del corpo, quindi a corpo `c` restano `0,12*c` pixel di
    # inchiostro chiusi fra due bordi neri. Sotto il corpo in cui quell'asta vale
    # ancora un pixel pieno, il glifo **e'** il suo contorno: nero su nero.
    #
    # Misurato disegnando `Rimuovi il veicolo` a corpi calanti e contando che
    # quota dell'inchiostro sopravvive al contorno (la tabella sta nel banco).
    # Il default segue quella misura.
    corpo_min: int = 11
    # **Quanti giri di seguito senza sottotitolo prima di spegnere l'overlay.**
    #
    # L'OCR perde una riga per qualche fotogramma — una dissolvenza, una scena
    # troppo chiara, un frame saltato — e quella riga torna subito dopo. Chi
    # spegne al primo giro vuoto fa lampeggiare il tradotto; a 30 Hz otto giri
    # sono circa un quarto di secondo, cioe' piu' di qualunque buco visto nelle
    # letture e molto meno della pausa fra due battute.
    #
    # Si contano i **giri**, non i millisecondi: quello che deve sopravvivere e'
    # un buco di letture, e se il ciclo video rallenta rallentano anche le
    # letture — un timer a muro invece si accorcerebbe proprio quando il buco si
    # allunga.
    overlay_hold_frames: int = 8
    # **Quanto sta a schermo, come minimo, una battuta arrivata tardi.**
    #
    # Fra la lettura e la voce passano piu' di due secondi, e in quel tempo il
    # sottotitolo originale puo' essersene gia' andato. Prima quella traduzione
    # veniva **buttata**: nel log di una sessione dal vivo dell'utente si vede
    # `NASCOSTO` accanto a una battuta tradotta che non e' mai comparsa. Un buco
    # e' peggio di un ritardo — il giocatore ha letto quella riga un secondo fa e
    # sta ancora ascoltando la voce che la dice.
    #
    # Non si mostra comunque: solo se non e' **piu' vecchia** di quella gia' a
    # schermo, se no due battute si accavallerebbero.
    overlay_min_s: float = 1.2


@dataclass
class Config:
    profile: str = "gtav"
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    label: LabelConfig = field(default_factory=LabelConfig)
    correct: CorrectConfig = field(default_factory=CorrectConfig)
    translate: TranslateConfig = field(default_factory=TranslateConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    vad: VadConfig = field(default_factory=VadConfig)
    speaker: SpeakerConfig = field(default_factory=SpeakerConfig)
    repeat: RepeatConfig = field(default_factory=RepeatConfig)
    emotion: EmotionConfig = field(default_factory=EmotionConfig)
    tts: TtsConfig = field(default_factory=TtsConfig)
    timing: TimingConfig = field(default_factory=TimingConfig)
    mix: MixConfig = field(default_factory=MixConfig)
    ui: UiConfig = field(default_factory=UiConfig)

    # -- override ----------------------------------------------------------

    def set(self, path: str, value: Any) -> Any:
        """Imposta `sezione.campo` convertendo al tipo del campo.

        Solleva `KeyError` se il percorso non esiste: un refuso in `--set` deve
        fermare l'avvio, non essere ignorato in silenzio.
        """
        parts = path.split(".")
        target: Any = self
        for part in parts[:-1]:
            if not is_dataclass(target) or not hasattr(target, part):
                raise KeyError(f"percorso di config sconosciuto: {path!r}")
            target = getattr(target, part)
        leaf = parts[-1]
        if not is_dataclass(target) or not hasattr(target, leaf):
            raise KeyError(f"percorso di config sconosciuto: {path!r}")
        current = getattr(target, leaf)
        # **Una tupla vuota non dice di che cosa e' vuota.** `_coerce` deduce il
        # tipo degli elementi dal primo che trova, e su `()` non ne trova
        # nessuno: cadeva sul numero, quindi una lista di stringhe vuota non si
        # poteva riempire da `--set`. Il tipo dichiarato del campo lo sa, e sta a
        # un passo di distanza.
        if isinstance(current, tuple) and not current:
            for f in fields(target):
                if f.name == leaf and "str" in str(f.type):
                    current = ("",)
                    break
        coerced = _coerce(value, current, path)
        setattr(target, leaf, coerced)
        return coerced

    def get(self, path: str) -> Any:
        target: Any = self
        for part in path.split("."):
            if not hasattr(target, part):
                raise KeyError(f"percorso di config sconosciuto: {path!r}")
            target = getattr(target, part)
        return target

    def apply(self, overrides: list[str] | tuple[str, ...] | None) -> "Config":
        """Applica una lista di `chiave=valore`."""
        for item in overrides or ():
            if "=" not in item:
                raise ValueError(f"override malformato (serve chiave=valore): {item!r}")
            key, _, raw = item.partition("=")
            self.set(key.strip(), raw.strip())
        return self

    # -- serializzazione ---------------------------------------------------

    def to_dict(self) -> dict:
        return asdict(self)

    def dump(self) -> str:
        """Elenco piatto `sezione.campo = valore`, ordinato e diffabile.

        Il formato e' scelto per essere incollabile in un log di sessione: se
        una prova va male, la sua configurazione esatta e' una riga di testo.
        """
        out: list[str] = []

        def walk(prefix: str, obj: Any) -> None:
            for f in fields(obj):
                value = getattr(obj, f.name)
                name = f"{prefix}{f.name}"
                if is_dataclass(value):
                    walk(f"{name}.", value)
                else:
                    out.append(f"{name} = {_fmt(value)}")

        walk("", self)
        width = max((len(line.split(" = ")[0]) for line in out), default=0)
        return "\n".join(
            f"{line.split(' = ')[0].ljust(width)} = {line.split(' = ', 1)[1]}" for line in out
        )

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return p

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        """Carica un profilo. Le chiavi assenti restano ai default; una chiave
        sconosciuta e' un errore, non un refuso silenzioso.

        Le chiavi che cominciano per `_` sono l'eccezione: sono commenti e
        metadati, non configurazione. `tools/calibrate.py` ci scrive dentro la
        misura che ha prodotto i valori — quale video, quanti frame, che
        istogrammi — perche' un numero senza la sua misura e' di nuovo un
        numero indovinato, solo con piu' cifre decimali.
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        cfg = cls()
        for key, value in _flatten(data):
            if key.split(".")[0].startswith("_"):
                continue
            cfg.set(key, value)
        return cfg


PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"


def load_profile(name: str = "gtav", overrides: Any = None) -> Config:
    """Profilo del gioco come base, `--set` sopra.

    L'ordine conta: il profilo porta i valori **calibrati sul gioco**, `--set`
    serve a scostarsene per una prova singola senza sporcare il profilo. Sta
    qui e non in `main.py` perche' il banco di prova deve poter caricare
    esattamente la stessa configurazione del live: una misura fatta con soglie
    diverse da quelle che gireranno in gioco non misura il gioco.
    """
    path = PROFILES_DIR / f"{name}.json"
    cfg = Config.load(path) if path.exists() else Config()
    cfg.profile = name
    cfg.apply(overrides)
    return cfg


def _flatten(data: dict, prefix: str = "") -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    for key, value in data.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            out.extend(_flatten(value, f"{name}."))
        else:
            out.append((name, value))
    return out


def _coerce(value: Any, current: Any, path: str) -> Any:
    """Porta `value` al tipo di `current`. Il tipo corrente e' il contratto."""
    if isinstance(current, bool):
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("1", "true", "vero", "si", "on", "yes"):
            return True
        if text in ("0", "false", "falso", "no", "off"):
            return False
        raise ValueError(f"{path}: atteso un booleano, ricevuto {value!r}")
    if isinstance(current, int) and not isinstance(current, bool):
        return int(str(value).strip())
    if isinstance(current, float):
        return float(str(value).strip())
    if isinstance(current, tuple):
        items = value if isinstance(value, (list, tuple)) else str(value).split(",")
        proto = current[0] if current else 0.0
        return tuple(_coerce(x, proto, path) for x in items)
    if isinstance(current, dict):
        # **I due dizionari sono tabelle di personaggi**, e finche' `_coerce` non
        # li trattava non erano scrivibili da nessuna parte: ne' da `--set`, ne'
        # dal pannello, che infatti li mostrava spenti con scritto «non
        # modificabile». Cioe' `label.voices` — «chi ha quale voce, deciso da
        # te», la cosa che vince su tutto — si poteva dichiarare solo aprendo un
        # file di profilo a mano.
        #
        # La forma testuale e' `Franklin=riccardo, Lamar=paolo`: i nomi dei
        # personaggi possono avere spazi, quindi si divide sulle virgole e poi
        # sul **primo** uguale, non su ogni uguale.
        if isinstance(value, dict):
            return {str(k): str(v) for k, v in value.items()}
        fuori: dict[str, str] = {}
        for pezzo in str(value).split(","):
            pezzo = pezzo.strip()
            if not pezzo:
                continue
            chiave, sep, val = pezzo.partition("=")
            if not sep:
                raise ValueError(
                    f"{path}: atteso «nome=valore» separato da virgole, "
                    f"ricevuto {pezzo!r}"
                )
            fuori[chiave.strip()] = val.strip()
        return fuori
    if isinstance(current, str):
        return str(value)
    raise TypeError(f"{path}: tipo non gestito {type(current).__name__}")


def _fmt(value: Any) -> str:
    if isinstance(value, tuple):
        return ", ".join(_fmt(v) for v in value)
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, str) and value == "":
        return "(vuoto)"
    return str(value)
