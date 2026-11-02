#!/usr/bin/env python3
"""Quarta prova di SOLA LETTURA (non salva nulla): al massimo 4 richieste, lente.
Le pagine dei vecchi tornei di Pokedata (es. /standingsVGC/0000150/) sono minuscole (2 KB) e senza tabella: qui si stampa
la pagina INTERA e si guardano gli eventuali file collegati (script, cornici, reindirizzamenti) per capire da dove arrivano i dati."""
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "tornei-vgc-bot (sito della community, con link alle fonti)"
PAGINA = "https://www.pokedata.ovh/standingsVGC/0000150/"


def scarica(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace"), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, "", url
    except Exception as e:
        return 0, str(e), url


def pausa():
    time.sleep(random.uniform(8, 15))


def collegamenti(html, base):
    """Indirizzi collegati alla pagina: script, cornici, reindirizzamenti, fogli di stile e link."""
    trovati = []
    for tag, rx in (("script", r'<script[^>]+src=["\']([^"\']+)'), ("cornice", r'<iframe[^>]+src=["\']([^"\']+)'),
                    ("reindirizza", r'http-equiv=["\']refresh["\'][^>]+content=["\'][^"\']*url=([^"\']+)'),
                    ("link", r'<link[^>]+href=["\']([^"\']+)'), ("a", r'<a[^>]+href=["\']([^"\']+)')):
        for u in re.findall(rx, html, flags=re.I):
            trovati.append((tag, urllib.parse.urljoin(base, u.strip())))
    visti, out = set(), []
    for t, u in trovati:
        if u not in visti:
            visti.add(u)
            out.append((t, u))
    return out


def main():
    print("QUARTA PROVA di sola lettura - massimo 4 richieste, lente")
    st, html, finale = scarica(PAGINA)
    print("\nPagina %s\nrisposta %s, %d byte, indirizzo finale: %s" % (PAGINA, st, len(html), finale))
    print("\n----- PAGINA INTERA -----\n" + html[:4000] + "\n----- FINE PAGINA -----", flush=True)
    if st != 200:
        return 0
    col = collegamenti(html, finale)
    print("\nCollegamenti trovati nella pagina:")
    for t, u in col:
        print("  [%s] %s" % (t, u))
    da_leggere = [(t, u) for t, u in col if t in ("script", "cornice", "reindirizza") and "pokedata" in u][:3]
    for t, u in da_leggere:
        pausa()
        st2, txt, fin2 = scarica(u)
        print("\n== [%s] %s -> risposta %s, %d byte" % (t, u, st2, len(txt)))
        if st2 == 200:
            print(txt[:3000])
            if len(txt) > 3000:
                print("... (tagliato: in tutto %d caratteri)" % len(txt))
    print("\nFine. Non e' stato salvato nessun file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
