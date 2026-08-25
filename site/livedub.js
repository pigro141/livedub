/* ===========================================================================
   livedub — la vetrina: scelta della lingua, tema, e il disegno della pagina.

   Nessuna libreria, nessun `fetch`, nessuna compilazione. I cataloghi arrivano
   come `<script src>` normali, e non come JSON: `fetch("i18n/en.json")` da un
   file aperto con doppio clic (`file://`) e' bloccato dal CORS, quindi la
   pagina resterebbe **bianca senza errore** proprio a chi la apre dal disco.
   Uno `<script>` classico li' funziona.

   ## Dove sta il testo

   In `site/i18n/en.js`, e li' soltanto: quel file e' **insieme la struttura
   della pagina e il suo testo inglese**. Il markup di `index.html` non contiene
   una parola. Gli altri cataloghi (`it.js`, `de.js`, ...) sono dizionari
   `{ stringa inglese -> stringa tradotta }`: la chiave **e'** l'inglese, come
   in `ui/lingua.py` la chiave e' la stringa italiana del sorgente. Stessa
   scelta, stessa ragione — non ci sono identificatori da inventare, e una
   stringa nuova nel sorgente compare da sola fra le **mancanti** invece di
   sparire.

   ## E quando manca si dice

   Una lingua senza catalogo, o con un catalogo a meta', non fa finta di
   niente: la riga sotto la barra dichiara che si sta leggendo l'inglese e
   perche'. E' `ui.lingua.perche_italiano` portato qui — un ripiego che non si
   dichiara e' peggio di un errore.
   =========================================================================== */

(function () {
  "use strict";

  var L = (window.LIVEDUB = window.LIVEDUB || {});
  L.cataloghi = L.cataloghi || {};

  /* Le sette lingue, nell'ordine del menu. Il nome e' quello che quella lingua
     da' a se stessa: chi cerca il giapponese cerca 日本語, non "Japanese". */
  var LINGUE = [
    { c: "en", nome: "English" },
    { c: "it", nome: "Italiano" },
    { c: "de", nome: "Deutsch" },
    { c: "es", nome: "Español" },
    { c: "fr", nome: "Français" },
    { c: "ja", nome: "日本語" },
    { c: "zh", nome: "中文" }
  ];
  var BASE = "en";
  L.LINGUE = LINGUE;

  var codici = LINGUE.map(function (x) { return x.c; });
  var lingua = BASE;
  var mancanti = [];      /* le stringhe che il catalogo attivo non ha */
  var chieste = 0;

  /* ---------------------------------------------------------------------
     La memoria, e il fatto che possa non esserci

     `localStorage` solleva in una finestra privata e in certe configurazioni:
     leggerlo senza rete di sicurezza vorrebbe dire una pagina bianca invece di
     una preferenza dimenticata.
     --------------------------------------------------------------------- */
  function ricorda(chiave, valore) {
    try { window.localStorage.setItem(chiave, valore); } catch (e) { /* pazienza */ }
  }
  function ricordato(chiave) {
    try { return window.localStorage.getItem(chiave); } catch (e) { return null; }
  }

  /* ---------------------------------------------------------------------
     Quale lingua: la scelta esplicita, poi quella ricordata, poi il browser
     --------------------------------------------------------------------- */
  function daUrl() {
    var m = /[?&]lang=([A-Za-z-]+)/.exec(window.location.search);
    return m ? normalizza(m[1]) : null;
  }
  function normalizza(tag) {
    if (!tag) return null;
    tag = String(tag).toLowerCase();
    if (codici.indexOf(tag) >= 0) return tag;
    var corto = tag.split("-")[0];            /* `de-AT` -> `de`, `zh-Hans` -> `zh` */
    return codici.indexOf(corto) >= 0 ? corto : null;
  }
  function dalBrowser() {
    var elenco = navigator.languages && navigator.languages.length
      ? navigator.languages : [navigator.language || ""];
    for (var i = 0; i < elenco.length; i++) {
      var c = normalizza(elenco[i]);
      if (c) return c;
    }
    return null;
  }
  function scegliLingua() {
    return daUrl() || normalizza(ricordato("livedub.lang")) || dalBrowser() || BASE;
  }

  /* ---------------------------------------------------------------------
     La traduzione di una stringa
     --------------------------------------------------------------------- */
  function T(s) {
    if (typeof s !== "string" || !s) return s || "";
    if (lingua === BASE) return s;
    var cat = L.cataloghi[lingua];
    var v = cat && cat.s ? cat.s[s] : null;
    chieste++;
    if (v) return v;
    if (mancanti.indexOf(s) < 0) mancanti.push(s);
    return s;                                  /* si ripiega sull'inglese, e si conta */
  }
  L.T = T;

  /* ---------------------------------------------------------------------
     I segnaposto

     `{{NOME}}` non si traduce e non si inventa: si **vede**. Finche' c'e', in
     quel punto della pagina non c'e' ancora nessun dato — ed e' esattamente
     l'informazione che serve a chi la sta riempiendo.
     --------------------------------------------------------------------- */
  var RE_POSTO = /\{\{([A-Z0-9_]+)\}\}/g;

  function ricco(s) {
    return T(s).replace(RE_POSTO, function (_, nome) {
      return '<span class="posto" title="segnaposto da riempire">{{' + nome + "}}</span>";
    });
  }

  function el(tag, classe, html) {
    var e = document.createElement(tag);
    if (classe) e.className = classe;
    if (html != null) e.innerHTML = html;
    return e;
  }

  /* ---------------------------------------------------------------------
     I blocchi
     --------------------------------------------------------------------- */
  function disegnaBlocco(b) {
    switch (b.t) {
      case "p":
        return el("p", b.classe || null, ricco(b.x));

      case "h3":
        return el("h3", null, ricco(b.x));

      case "nota": {
        var n = el("div", "nota" + (b.ambra ? " ambra" : ""));
        (b.righe || [b.x]).forEach(function (r) { n.appendChild(el("p", null, ricco(r))); });
        return n;
      }

      case "video": {
        var f = el("figure");
        var v = document.createElement("video");
        v.controls = true; v.preload = "metadata"; v.playsInline = true;
        if (b.muto) v.muted = true;
        if (b.poster) v.poster = b.poster;
        var src = document.createElement("source");
        src.src = b.src; src.type = "video/mp4";
        v.appendChild(src);
        v.appendChild(document.createTextNode(T("Your browser cannot play this video.")));
        f.appendChild(v);
        if (b.x) f.appendChild(el("figcaption", null, ricco(b.x)));
        return f;
      }

      case "passi": {
        var ol = el("ol", "passi");
        (b.voci || []).forEach(function (v) {
          var li = document.createElement("li");
          li.appendChild(el("b", null, ricco(v.b)));
          li.appendChild(el("p", null, ricco(v.p)));
          ol.appendChild(li);
        });
        return ol;
      }

      case "tabella": {
        var box = el("div", "tab-scorre");
        var t = document.createElement("table");
        if (b.testa) {
          var thead = document.createElement("thead");
          var tr = document.createElement("tr");
          b.testa.forEach(function (c) { tr.appendChild(el("th", null, ricco(c))); });
          thead.appendChild(tr); t.appendChild(thead);
        }
        var tb = document.createElement("tbody");
        (b.righe || []).forEach(function (riga) {
          var tr2 = document.createElement("tr");
          riga.forEach(function (c) { tr2.appendChild(el("td", null, ricco(c))); });
          tb.appendChild(tr2);
        });
        t.appendChild(tb); box.appendChild(t);
        return box;
      }

      case "griglia": {
        var g = el("div", "griglia");
        (b.voci || []).forEach(function (v) {
          var fi = el("figure");
          var im = document.createElement("img");
          im.src = v.img; im.alt = T(v.alt || ""); im.loading = "lazy";
          fi.appendChild(im);
          if (v.x) fi.appendChild(el("figcaption", null, ricco(v.x)));
          g.appendChild(fi);
        });
        return g;
      }

      case "codice": {
        var pre = document.createElement("pre");
        pre.appendChild(el("code", null, b.x));   /* i comandi non si traducono */
        return pre;
      }

      case "posto": {
        var d = el("div", "posto-blocco");
        d.appendChild(el("div", null, "{{" + b.nome + "}}"));
        if (b.forma) d.appendChild(el("small", null, T(b.forma)));
        return d;
      }

      case "sostegno": {
        var s = el("div", "sostegno");
        s.appendChild(el("h2", null, ricco(b.titolo)));
        s.appendChild(el("p", null, ricco(b.x)));
        if (b.bottone) s.appendChild(disegnaBlocco({ t: "bottoni", voci: [b.bottone] }));
        if (b.postilla) s.appendChild(el("p", "postilla", ricco(b.postilla)));
        return s;
      }

      case "bottoni": {
        var w = el("div", "bottoni");
        (b.voci || []).forEach(function (v) {
          var a = el("a", "btn" + (v.pieno ? " pieno" : ""), ricco(v.x));
          a.href = v.href;
          if (/^https?:/.test(v.href)) { a.rel = "noopener"; }
          w.appendChild(a);
        });
        return w;
      }

      default:
        return el("p", null, ricco(b.x || ""));
    }
  }

  /* ---------------------------------------------------------------------
     La pagina
     --------------------------------------------------------------------- */
  function disegnaTestata(h) {
    var head = el("header", "testata");
    var w = el("div", "avvolge");
    var logo = document.createElement("img");
    logo.className = "logo"; logo.src = h.logo; logo.alt = T(h.logoAlt || "");
    logo.width = 96; logo.height = 96;
    w.appendChild(logo);
    w.appendChild(el("h1", null, ricco(h.titolo)));
    w.appendChild(el("p", "occhiello", ricco(h.occhiello)));
    w.appendChild(el("p", "sotto", ricco(h.sotto)));

    var m = el("div", "marche");
    (h.marche || []).forEach(function (x) { m.appendChild(el("span", "marca", ricco(x))); });
    w.appendChild(m);
    w.appendChild(disegnaBlocco({ t: "bottoni", voci: h.bottoni || [] }));

    if (h.immagine) {
      var f = el("figure", "vetrina-testata");
      ["chiaro", "scuro"].forEach(function (tema) {
        var im = document.createElement("img");
        im.className = "solo-" + tema;
        im.src = tema === "chiaro" ? h.immagine.chiaro : h.immagine.scuro;
        im.alt = T(h.immagine.alt || "");
        f.appendChild(im);
      });
      w.appendChild(f);
    }
    head.appendChild(w);
    return head;
  }

  function disegnaSezione(s) {
    var sec = document.createElement("section");
    sec.id = s.id;
    var w = el("div", "avvolge");
    if (s.etichetta) w.appendChild(el("div", "etichetta", T(s.etichetta)));
    /* Una sezione «nuda» non ha testata: il blocco che contiene se la porta
       dietro (la tessera del sostegno). Senza questo ramo uscirebbe un `<h2>`
       vuoto, che non si vede e occupa una riga. */
    if (s.titolo) w.appendChild(el("h2", null, ricco(s.titolo)));
    if (s.lede) w.appendChild(el("p", "lede", ricco(s.lede)));
    (s.blocchi || []).forEach(function (b) { w.appendChild(disegnaBlocco(b)); });
    sec.appendChild(w);
    return sec;
  }

  function disegnaPiede(p) {
    var f = document.createElement("footer");
    var w = el("div", "avvolge");
    (p.righe || []).forEach(function (r) { w.appendChild(el("p", null, ricco(r))); });
    var links = el("p", "piede-righe");
    (p.link || []).forEach(function (v, i) {
      if (i) links.appendChild(document.createTextNode("·"));
      var a = el("a", null, ricco(v.x));
      a.href = v.href; a.rel = "noopener";
      links.appendChild(a);
    });
    w.appendChild(links);
    if (p.nota) w.appendChild(el("p", "piede-nota", ricco(p.nota)));
    f.appendChild(w);
    return f;
  }

  function disegnaSezioniBarra(pagina) {
    var nav = document.getElementById("sezioni");
    nav.innerHTML = "";
    pagina.sezioni.forEach(function (s) {
      if (!s.nav) return;
      var a = el("a", null, T(s.nav));
      a.href = "#" + s.id;
      nav.appendChild(a);
    });
  }

  /* ---------------------------------------------------------------------
     La riga che dichiara il ripiego
     --------------------------------------------------------------------- */
  function dichiaraLingua() {
    var barra = document.getElementById("avviso-lingua");
    var cat = L.cataloghi[lingua];
    var voci = cat && cat.s ? Object.keys(cat.s).length : 0;

    if (lingua === BASE || (voci && mancanti.length === 0)) {
      barra.hidden = true;
      return;
    }
    var nome = (LINGUE.filter(function (x) { return x.c === lingua; })[0] || {}).nome || lingua;
    var testo;
    if (!voci) {
      testo = T("This page is not translated into {0} yet — you are reading the English original.")
        .replace("{0}", "<b>" + nome + "</b>");
    } else {
      testo = T("The {0} translation is not finished: {1} of {2} strings are still in English.")
        .replace("{0}", "<b>" + nome + "</b>")
        .replace("{1}", "<b>" + mancanti.length + "</b>")
        .replace("{2}", String(chieste));
    }
    barra.querySelector(".avvolge").innerHTML = testo;
    barra.hidden = false;
  }

  /* ---------------------------------------------------------------------
     Il tema
     --------------------------------------------------------------------- */
  function temaEffettivo() {
    var scelto = ricordato("livedub.theme");
    if (scelto === "light" || scelto === "dark") return scelto;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark" : "light";
  }
  function applicaTema(t) {
    if (t) document.documentElement.setAttribute("data-theme", t);
    else document.documentElement.removeAttribute("data-theme");
  }
  function giraTema() {
    var nuovo = temaEffettivo() === "dark" ? "light" : "dark";
    ricorda("livedub.theme", nuovo);
    applicaTema(nuovo);
  }
  L.applicaTema = applicaTema;

  /* ---------------------------------------------------------------------
     Il montaggio
     --------------------------------------------------------------------- */
  function disegna() {
    var pagina = L.pagina;
    mancanti = []; chieste = 0;

    var root = document.documentElement;
    root.setAttribute("lang", lingua);
    root.setAttribute("dir", (L.cataloghi[lingua] && L.cataloghi[lingua].dir) || "ltr");

    document.title = T(pagina.titoloPagina);
    var d = document.querySelector('meta[name="description"]');
    if (d) d.setAttribute("content", T(pagina.descrizione));

    var main = document.getElementById("pagina");
    main.innerHTML = "";
    main.appendChild(disegnaTestata(pagina.testata));
    pagina.sezioni.forEach(function (s) { main.appendChild(disegnaSezione(s)); });
    main.appendChild(disegnaPiede(pagina.piede));

    disegnaSezioniBarra(pagina);
    document.getElementById("marchio-nome").textContent = pagina.nome;
    dichiaraLingua();
  }

  function cambiaLingua(c) {
    lingua = c;
    ricorda("livedub.lang", c);
    /* L'indirizzo dice quale lingua si sta leggendo: cosi' il link che si
       copia porta la stessa pagina a chi lo riceve, ed e' l'indirizzo che gli
       `hreflang` in testa dichiarano. Su `file://` `replaceState` puo'
       sollevare, e non e' un buon motivo per perdere la pagina. */
    try {
      var u = new URL(window.location.href);
      u.searchParams.set("lang", c);
      window.history.replaceState(null, "", u.toString());
    } catch (e) { /* pazienza */ }
    disegna();
  }

  function montaMenu() {
    var sel = document.getElementById("lingua");
    LINGUE.forEach(function (x) {
      var o = document.createElement("option");
      o.value = x.c; o.textContent = x.nome;
      o.lang = x.c;
      sel.appendChild(o);
    });
    sel.value = lingua;
    sel.addEventListener("change", function () { cambiaLingua(sel.value); });
    document.getElementById("tema").addEventListener("click", giraTema);
  }

  /* `?theme=light|dark` forza il tema per una visita sola, senza toccare ne'
     la preferenza ricordata ne' le impostazioni del sistema. Serve a
     **guardare** la pagina nei due temi — che in questo progetto e' il modo in
     cui si verifica cio' che si vede (`tools/scatta.py` fa lo stesso con la
     finestra, forzando `tema.attuale`). Tre righe, e tolgono la sola scusa per
     non guardare il tema che non si usa. */
  function temaDaUrl() {
    var m = /[?&]theme=(light|dark)/.exec(window.location.search);
    return m ? m[1] : null;
  }

  function avvia() {
    if (!L.pagina) {
      document.getElementById("pagina").innerHTML =
        '<div class="avvolge" style="padding:60px 24px">' +
        "<p>The page content did not load. Check that <code>site/i18n/en.js</code> is next to " +
        "<code>index.html</code>.</p></div>";
      return;
    }
    lingua = scegliLingua();
    applicaTema(temaDaUrl() || ricordato("livedub.theme"));
    montaMenu();
    disegna();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", avvia);
  } else {
    avvia();
  }
})();
