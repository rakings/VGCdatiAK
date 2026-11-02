#!/usr/bin/env python3
"""Terza prova di SOLA LETTURA (non salva nulla): 5 richieste lente.
Scopo: capire dove Pokedata tiene i dati dei VECCHI tornei (id a 7 cifre come 0000150), visto che l'indirizzo dei tornei nuovi
risponde con l'ultimo torneo (Danzica) quando non conosce l'id. Ogni risposta dell'API stampa QUALE torneo e' arrivato."""
import json
import random
import re
import sys
import time
import urllib.error
import urllib.request

UA = "tornei-vgc-bot (sito della community, con link alle fonti)"
PK = "https://www.pokedata.ovh"


def scarica(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return 0, str(e)


def pausa():
    time.sleep(random.uniform(8, 15))


def identita(txt):
    i = txt.find("{")
    if i < 0:
        return "(non e' JSON)"
    try:
        j = json.loads(txt[i:])
    except ValueError as e:
        return "(JSON non valido: %s)" % e
    t = j.get("tournament") if isinstance(j, dict) else None
    if not isinstance(t, dict):
        return "chiavi: %s (nessun «tournament»)" % (", ".join(list(j.keys())[:8]) if isinstance(j, dict) else type(j).__name__)
    d = t.get("date") or {}
    td = j.get("tournament_data")
    n = len(td[0]) if isinstance(td, list) and td and hasattr(td[0], "__len__") else "?"
    return "TORNEO RICEVUTO -> id=%s | nome=%s | data=%s | stato=%s | contenuto tournament_data[0]: %s elementi" % (
        t.get("id"), t.get("name"), d.get("start"), t.get("tournamentStatus"), n)


def api(percorso, etichetta):
    st, txt = scarica(PK + percorso)
    print("\n%s\n  %s -> risposta %s, %d byte" % (etichetta, percorso, st, len(txt)))
    if st == 200:
        print("  " + identita(txt), flush=True)


def pagina_vecchia(tid, nome):
    st, pag = scarica("%s/standingsVGC/%s/" % (PK, tid))
    print("\nPagina del vecchio torneo %s (%s): risposta %s, %d byte" % (tid, nome, st, len(pag)))
    if st != 200:
        return
    for ago in ("<tr", "<table", "fetch(", "XMLHttpRequest", "$.get", "$.ajax", "apiv3", "apiv2", ".json", "rk9"):
        print("  %-16s compare %d volte" % (ago, pag.count(ago)))
    blocchi = [b for b in re.findall(r"(?is)<script[^>]*>(.*?)</script>", pag) if re.search(r"fetch\(|XMLHttpRequest|\$\.get|\$\.ajax|apiv|\.json", b)]
    print("  script che leggono dati: %d" % len(blocchi))
    for b in blocchi[:3]:
        print("\n  --- script (primi 1500 caratteri) ---\n" + b.strip()[:1500])
    i = pag.find("<table")
    print("\n  --- primo pezzo della tabella (1200 caratteri) ---\n" + (pag[i:i + 1200] if i >= 0 else "(nessuna tabella)"))


def main():
    print("TERZA PROVA di sola lettura - 5 richieste, lente")
    api("/apiv3/vg/id/1000049/division/masters", "CONTROLLO (deve essere Seattle, id 1000049):")
    pausa()
    api("/apiv3/vg/id/150/division/masters", "VECCHIO id 150 (World Championship 2025?) con il formato dei nuovi:")
    pausa()
    api("/apiv3/id/0000150/vg", "VECCHIO id 0000150 con il formato dell'esempio della documentazione:")
    pausa()
    pagina_vecchia("0000150", "World Championship 2025")
    pausa()
    pagina_vecchia("0000056", "Malmo 2020")
    print("\nFine. Non e' stato salvato nessun file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
