#!/usr/bin/env python3
"""Quinta prova di SOLA LETTURA (non salva nulla): 2 richieste, lente.
La pagina di un vecchio torneo Pokedata e' solo un menu con tre pulsanti (Juniors / Seniors / Masters): i dati stanno nella pagina «masters/».
Qui si legge quella di due tornei (World Championship 2025 e Malmo 2020) per vedere com'e' fatta la tabella."""
import random
import re
import sys
import time
import urllib.error
import urllib.request

UA = "tornei-vgc-bot (sito della community, con link alle fonti)"
PAGINE = [("https://www.pokedata.ovh/standingsVGC/0000150/masters/", "World Championship 2025"),
          ("https://www.pokedata.ovh/standingsVGC/0000056/masters/", "Malmo 2020")]


def scarica(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return 0, str(e)


def righe_tabella(html):
    return re.findall(r"(?is)<tr[^>]*>.*?</tr>", html)


def main():
    print("QUINTA PROVA di sola lettura - 2 richieste, lente")
    for k, (url, nome) in enumerate(PAGINE):
        if k:
            time.sleep(random.uniform(8, 15))
        st, html = scarica(url)
        print("\n" + "=" * 60 + "\n%s\n%s\nrisposta %s, %d byte" % (nome, url, st, len(html)) + "\n" + "=" * 60, flush=True)
        if st != 200:
            continue
        tr = righe_tabella(html)
        for ago in ("<table", "<tr", "<th", "<td", "<script", "fetch(", "apiv", ".json", "href="):
            print("  %-10s compare %d volte" % (ago, html.count(ago)))
        i = html.find("<h2")
        print("\n----- TITOLO E INIZIO DELLA PAGINA (1200 caratteri) -----")
        print(html[i: i + 1200] if i >= 0 else "(nessun titolo h2)")
        print("\n----- RIGHE DELLA TABELLA: %d in tutto; le prime 3 INTERE -----" % len(tr))
        for r in tr[:3]:
            print(r[:1500])
            print("  ...")
        if len(tr) > 6:
            print("\n----- ULTIMA RIGA -----")
            print(tr[-1][:1500])
    print("\nFine. Non e' stato salvato nessun file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
