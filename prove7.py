#!/usr/bin/env python3
"""Prova di SOLA LETTURA sulla home e sul calendario del VR Circuit (non salva niente, 2 richieste lente).
Serve a vedere dove il sito tiene: nome, giorno e ora del PROSSIMO torneo, il conto alla rovescia, il montepremi accumulato e i link.
Identificazione onesta e senza dati personali."""
import html as _html
import random
import re
import sys
import time
import urllib.error
import urllib.request

UA = "tornei-vgc-bot (sito della community, con link alle fonti)"
SITO = "https://circuit.victoryroad.pro"


def scarica(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as ex:
        return 0, str(ex)


def pezzo(pag, ago, prima=300, dopo=1800, n=1):
    it = list(re.finditer(ago, pag, flags=re.I))
    if len(it) < n:
        return "(non trovato: %s)" % ago
    i = it[n - 1].start()
    return pag[max(0, i - prima): i + dopo]


def sezione(titolo, st, pag):
    print("\n" + "=" * 60 + "\n%s: risposta %s, %d byte\n" % (titolo, st, len(pag)) + "=" * 60, flush=True)


def home():
    st, pag = scarica(SITO + "/")
    sezione("HOME", st, pag)
    if st != 200:
        return
    print("--- date e orari scritti in attributi o tag (datetime, data-*, ISO) ---")
    trovati = set()
    for m in re.finditer(r'(?:datetime|data-[a-z-]+|content)="([^"]*20\d\d-\d\d-\d\d[^"]*)"', pag):
        trovati.add(m.group(0)[:160])
    for m in re.finditer(r"20\d\d-\d\d-\d\dT\d\d:\d\d(?::\d\d)?(?:\.\d+)?Z?", pag):
        trovati.add(m.group(0))
    for t in sorted(trovati)[:20]:
        print("  ", t)
    if not trovati:
        print("   (nessuna)")
    print("\n--- script che parlano di conto alla rovescia o di date (primi 1500 caratteri) ---")
    n = 0
    for b in re.findall(r"(?is)<script[^>]*>(.*?)</script>", pag):
        if re.search(r"countdown|starts|2026-11-07|Date\(|getTime|next", b, re.I) and len(b.strip()) > 20:
            print(b.strip()[:1500])
            print("   ....")
            n += 1
            if n >= 3:
                break
    if not n:
        print("   (nessuno)")
    print("\n--- PEZZO GREZZO attorno a «Next tournament» ---")
    print(pezzo(pag, r"next\s+tournament", 200, 2600))
    print("\n--- PEZZO GREZZO attorno a «Accumulated pot» ---")
    print(pezzo(pag, r"accumulated\s+pot", 300, 1500))
    print("\n--- link nella pagina (testo -> indirizzo), primi 25 ---")
    for h, t in re.findall(r'(?is)<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', pag)[:25]:
        print("  %-38s -> %s" % (" ".join(_html.unescape(re.sub(r"<[^>]+>", " ", t)).split())[:38], h))


def calendario():
    st, pag = scarica(SITO + "/calendar")
    sezione("CALENDARIO (/calendar)", st, pag)
    if st != 200:
        return
    print("Compare «VR November Challenge»:", len(re.findall(r"November Challenge", pag)), "volte")
    print("\n--- PEZZO GREZZO attorno al primo torneo del calendario ---")
    print(pezzo(pag, r"November Challenge", 500, 1800))
    print("\n--- link a tornei (/tournament/...) ---")
    for l in sorted(set(re.findall(r'href="([^"]*tournament/[^"]+)"', pag)))[:20]:
        print("  ", l)


def main():
    print("PROVA home e calendario del VR Circuit - sola lettura")
    home()
    time.sleep(random.uniform(8, 15))
    calendario()
    print("\nFine. Non e' stato salvato nessun file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
