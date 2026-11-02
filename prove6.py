#!/usr/bin/env python3
"""Sesta prova di SOLA LETTURA (non salva nulla): al massimo 6 richieste, lente.
La pagina «masters/» di un vecchio torneo Pokedata e' un guscio: la classifica la caricano gli script da un file .json.
Qui si stampano gli script della pagina e si legge il file .json che citano, per vedere com'e' fatto (giocatori, round, squadre?)."""
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
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


def pausa():
    time.sleep(random.uniform(8, 15))


def forma(j, margine=900):
    """Descrizione breve di un JSON: tipo, chiavi, lunghezze e il primo elemento."""
    if isinstance(j, dict):
        out = ["dizionario con %d chiavi: %s" % (len(j), ", ".join(list(j.keys())[:12]))]
        for k, v in list(j.items())[:8]:
            if isinstance(v, (list, dict)):
                out.append("  %s -> %s di %d elementi" % (k, "lista" if isinstance(v, list) else "dizionario", len(v)))
                primo = v[0] if isinstance(v, list) and v else (next(iter(v.items())) if isinstance(v, dict) and v else None)
                if primo is not None:
                    out.append("     primo elemento: " + json.dumps(primo, ensure_ascii=False)[:margine])
            else:
                out.append("  %s = %s" % (k, str(v)[:120]))
        return "\n".join(out)
    if isinstance(j, list):
        return "lista di %d elementi\n  primo elemento: %s" % (len(j), json.dumps(j[0], ensure_ascii=False)[:margine] if j else "-")
    return str(j)[:300]


def main():
    print("SESTA PROVA di sola lettura - al massimo 6 richieste, lente")
    for k, (url, nome) in enumerate(PAGINE):
        if k:
            pausa()
        st, html = scarica(url)
        print("\n" + "=" * 60 + "\n%s\n%s\nrisposta %s, %d byte\n" % (nome, url, st, len(html)) + "=" * 60, flush=True)
        if st != 200:
            continue
        inline = [b.strip() for b in re.findall(r"(?is)<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html) if b.strip()]
        esterni = re.findall(r'(?is)<script[^>]+src=["\']([^"\']+)', html)
        print("Script con codice nella pagina: %d | script esterni: %s" % (len(inline), esterni))
        for b in inline:
            print("\n----- SCRIPT (primi 3500 caratteri) -----\n" + b[:3500])
        refs = [r for r in re.findall(r'''["']([^"']*\.json[^"']*)["']''', html) if len(r) > 5]
        print("\nRiferimenti a file .json: %s" % refs)
        for r in refs[:1]:
            pausa()
            u = urllib.parse.urljoin(url, r)
            st2, txt = scarica(u)
            print("\n== %s -> risposta %s, %d byte" % (u, st2, len(txt)))
            if st2 == 200:
                try:
                    print(forma(json.loads(txt[txt.find("{") if txt.lstrip()[:1] != "[" else txt.find("["):])))
                except ValueError as e:
                    print("(non e' un JSON valido: %s) inizio: %s" % (e, txt[:500]))
        if not refs and esterni:
            for e in [x for x in esterni if "pokedata" in x or x.startswith("/") or not x.startswith("http")][:1]:
                pausa()
                u = urllib.parse.urljoin(url, e)
                st2, txt = scarica(u)
                print("\n== script esterno %s -> risposta %s, %d byte\n%s" % (u, st2, len(txt), txt[:3000]))
    print("\nFine. Non e' stato salvato nessun file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
