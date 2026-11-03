#!/usr/bin/env python3
"""Limitless VGC - PROVA 8 di SOLA LETTURA (6 richieste lente, non salva niente).
Serve a vedere: i filtri dell'elenco dei tornei (nomi e valori), come si scorrono le pagine, la pagina di un torneo VECCHIO
(Sheffield 2017 se si trova) con le sue righe grezze. Identificazione onesta e senza dati personali."""
import html as _html
import random
import re
import sys
import time
import urllib.error
import urllib.request

UA = "tornei-vgc-bot (sito della community, con link alle fonti)"
BASE = "https://limitlessvgc.com"


def scarica(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as ex:
        return 0, str(ex)


def pausa():
    time.sleep(random.uniform(8, 15))


def righe_elenco(pag):
    """Righe dell'elenco tornei: (id, data, nome, giocatori, vincitore) dagli attributi data-*."""
    out = []
    for m in re.finditer(r"<tr\b[^>]*>", pag):
        tag = m.group(0)
        if "data-date" not in tag and "data-name" not in tag:
            continue
        def at(n):
            x = re.search(r'%s="([^"]*)"' % n, tag)
            return _html.unescape(x.group(1)) if x else ""
        resto = pag[m.end(): m.end() + 900]
        i = re.search(r'/tournaments/(\d+)', resto)
        out.append((i.group(1) if i else "", at("data-date"), at("data-name"), at("data-players"), at("data-winner")))
    return out


def elenco(titolo, url, cerca=None):
    st, pag = scarica(url)
    print("\n" + "=" * 60 + "\n%s\n%s -> risposta %s, %d byte\n" % (titolo, url, st, len(pag)) + "=" * 60, flush=True)
    if st != 200:
        return None, []
    r = righe_elenco(pag)
    print("righe di torneo trovate:", len(r))
    for x in r[:3]:
        print("   primo:", x)
    for x in r[-2:]:
        print("   ultimo:", x)
    link_pagina = sorted(set(re.findall(r'href="([^"]*[?&](?:page|p)=\d+[^"]*)"', pag)))[:6]
    print("link di paginazione:", link_pagina or "(nessuno)")
    trovato = [x for x in r if cerca and cerca.lower() in x[2].lower()]
    print("righe che contengono %r:" % cerca, trovato[:5] if cerca else "-")
    return pag, r


def main():
    print("PROVA 8 - Limitless VGC (solo lettura)")
    pag, r = elenco("1) elenco tornei, pagina di base", BASE + "/tournaments", "Sheffield")
    if pag:
        print("\n--- FILTRI: menu (select) con nome e primi valori ---")
        for m in re.finditer(r'(?is)<select\b([^>]*)>(.*?)</select>', pag):
            nome = re.search(r'name="([^"]*)"', m.group(1))
            opz = re.findall(r'(?is)<option\b[^>]*value="([^"]*)"[^>]*>(.*?)</option>', m.group(2))
            print("  select name=%r: %s" % (nome.group(1) if nome else "?", [(v, " ".join(re.sub(r"<[^>]+>", " ", t).split())) for v, t in opz][:14]))
        print("\n--- <form ...> e campi nascosti ---")
        for m in re.finditer(r'(?is)<form\b[^>]*>', pag):
            print("  ", m.group(0)[:200])
        print("\n--- PEZZO GREZZO: la prima riga dell'elenco ---")
        m = re.search(r"<tr\b[^>]*data-(?:date|name)", pag)
        if m:
            print(pag[m.start(): m.start() + 900])
    tutti = []
    for tit, path in (("2) con time=all", "/tournaments?time=all"), ("3) con limit=100", "/tournaments?limit=100"), ("4) con page=2", "/tournaments?page=2"), ("5) stagione 2016-2017", "/tournaments?time=2016-2017")):
        pausa()
        p2, r2 = elenco(tit, BASE + path, "Sheffield")
        tutti += r2
    scelto = next((x for x in tutti if "sheffield" in x[2].lower() and x[1].startswith("2017") and x[0]), None) or next((x for x in tutti if x[0]), None)
    tid = scelto[0] if scelto else "448"
    pausa()
    url = "%s/tournaments/%s" % (BASE, tid)
    st, t = scarica(url)
    print("\n" + "=" * 60 + "\n6) pagina di un torneo: %s (%s)\n%s -> risposta %s, %d byte\n" % (tid, scelto[2] if scelto else "predefinito", url, st, len(t)) + "=" * 60)
    if st == 200:
        print("<title>:", " ".join(re.sub(r"<[^>]+>", " ", (re.search(r"(?is)<title>(.*?)</title>", t) or [0, ""])[1]).split()))
        print("righe risultato (tr con data-rank):", len(re.findall(r"<tr\b[^>]*data-rank", t)))
        print("\n--- PEZZO GREZZO: dati del torneo (infobox) ---")
        m = re.search(r'(?is)<div[^>]*class="[^"]*infobox[^"]*"', t)
        print(t[m.start(): m.start() + 1800] if m else "(nessun .infobox)")
        print("\n--- PEZZO GREZZO: prime 3 righe dei risultati ---")
        pos = [m.start() for m in re.finditer(r"<tr\b[^>]*data-rank", t)][:3]
        for p in pos:
            print(t[p: p + 1100])
            print("   ....")
        print("\n--- ultima riga dei risultati ---")
        pos = [m.start() for m in re.finditer(r"<tr\b[^>]*data-rank", t)]
        print(t[pos[-1]: pos[-1] + 700] if pos else "(nessuna)")
    print("\nFine. Non e' stato salvato nessun file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
