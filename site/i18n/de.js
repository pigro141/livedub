/* ===========================================================================
   livedub — la vetrina in tedesco (de).

   Un catalogo e' un dizionario `{ stringa inglese -> stringa tradotta }`. La
   chiave **e'** la stringa inglese esattamente com'e' scritta in `en.js`:
   copiarla e cambiarla non traduce niente, aggiunge una voce che non risponde a
   nessuna domanda. Una chiave che qui non c'e' non sparisce dalla pagina — esce
   in inglese, e la riga sotto la barra dichiara quante ne mancano.

   Tre cose che non si traducono:
     - i segnaposto `{{COSI}}`: sono dati, e vanno lasciati dove stanno;
     - i tag `<b>`, `<i>`, `<code>`, `<a href>`: si copiano dov'erano;
     - i comandi e i percorsi (`core/config.py`, `installa.ps1`, `--profile`).

   E i segnaposto numerati `{0}` `{1}` `{2}` si possono **riordinare**: sono
   numerati apposta, perche' una frase tradotta cambia ordine.
   =========================================================================== */

(function () {
  var L = (window.LIVEDUB = window.LIVEDUB || {});
  L.cataloghi = L.cataloghi || {};

  L.cataloghi.de = {
    dir: "ltr",
    s: {
      /* Ancora vuoto: la traduzione in tedesco non e' stata scritta. */
    }
  };
})();
