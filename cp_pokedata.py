#!/usr/bin/env python3
"""CP bar - classifica dei Championship Points da Pokedata (https://www.pokedata.ovh/2027/).
Poche richieste (3 pagine), lente e a tempi irregolari, con un'identificazione onesta e senza dati personali.
Senza --write e' una PROVA: legge e stampa quello che trova, ma non salva nulla.
Con --write salva in dati/cp/ (ultima classifica + una copia per giorno, solo se e' cambiata)."""
import hashlib
import html as _html
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "tornei-vgc-bot (sito della community, con link alle fonti)"
BASE = "https://www.pokedata.ovh/2027/"
STAGIONE = "2027"
COMBOS = [("VG", "Europe", "Masters")]       # (gioco, regione, divisione): se ne possono aggiungere altri
PAGINE = 3                                    # 3 pagine da circa 50 giocatori = primi 150
SOGLIA_POSIZIONE = 90                         # ultimo posto utile (stima NON ufficiale)
OUT = os.path.join("dati", "cp")
PAUSA = (6.0, 14.0)                           # secondi tra una richiesta e l'altra, a caso


class Stop(Exception):
    pass


def url_pagina(game, region, division, n):
    q = "game=%s&region=%s&division=%s&search=&country=&page=%d" % (
        urllib.parse.quote(game), urllib.parse.quote(region), urllib.parse.quote(division), n)
    return BASE + "?" + q


def scarica(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (403, 429) or e.code >= 500:
            raise Stop("Pokedata ha risposto %s: mi fermo senza insistere" % e.code)
        raise Stop("Pokedata ha risposto %s per %s" % (e.code, url))
    except Exception as e:
        raise Stop("pagina non raggiungibile (%s)" % e)


def testo(cella):
    cella = re.sub(r"(?s)<[^>]+>", " ", cella)
    return " ".join(_html.unescape(cella).split())


RE_RANK = re.compile(r"^\d{1,6}$")
RE_CP = re.compile(r"^([\d.,]+)\s*CP$")
RE_STORIA = re.compile(r"^([\d.,]+)\s*CP(?:\s*\(([+-]?\d+)\))?\s+(\d{8})$")


def num(s):
    return int(re.sub(r"[^\d]", "", s) or 0)


def righe_da_html(pagina):
    """Legge le righe della classifica. Ritorna una lista di dizionari; le righe che non sembrano giocatori si saltano."""
    out = []
    for tr in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", pagina):
        celle = [testo(c) for c in re.findall(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>", tr)]
        i = next((k for k, c in enumerate(celle) if RE_RANK.match(c)), None)
        if i is None or i + 2 >= len(celle):
            continue
        nome = celle[i + 1]
        paese = celle[i + 2]
        punti = next((num(m.group(1)) for c in celle[i + 3:] for m in [RE_CP.match(c)] if m), None)
        if not nome or punti is None:
            continue
        storia = []
        for c in celle[i + 3:]:
            m = RE_STORIA.match(c)
            if m:
                d = m.group(3)
                storia.append({"cp": num(m.group(1)), "delta": int(m.group(2)) if m.group(2) else None,
                               "data": "%s-%s-%s" % (d[:4], d[4:6], d[6:])})
        out.append({"rank": int(celle[i]), "name": nome, "country": paese, "cp": punti, "storia": storia})
    return out


def totale_giocatori(pagina):
    m = re.search(r"([\d.,]+)\s+players\s+found", testo(pagina))
    return num(m.group(1)) if m else None


def leggi_classifica(game, region, division, scarica_fn=scarica, pausa_fn=None):
    pausa_fn = pausa_fn or (lambda: time.sleep(random.uniform(*PAUSA)))
    righe, totale = [], None
    for n in range(1, PAGINE + 1):
        pag = scarica_fn(url_pagina(game, region, division, n))
        r = righe_da_html(pag)
        if n == 1:
            totale = totale_giocatori(pag)
        print("  pagina %d: %d righe%s" % (n, len(r), (" (primo: %s, %d CP)" % (r[0]["name"], r[0]["cp"])) if r else ""), flush=True)
        if not r:
            break
        righe += r
        if n < PAGINE:
            pausa_fn()
    return righe, totale


def controlla(righe):
    """Ritorna un elenco di problemi: se non e' vuoto NON si salva."""
    p = []
    if len(righe) < 30:
        p.append("trovate solo %d righe (ne aspettavo almeno 30)" % len(righe))
    if righe and righe[0]["rank"] != 1:
        p.append("la classifica non parte dal primo posto (parte da %d)" % righe[0]["rank"])
    nomi = [r["name"] for r in righe]
    if len(set(nomi)) < len(nomi) * 0.95:
        p.append("troppi nomi ripetuti: le pagine potrebbero essere uguali")
    pts = [r["cp"] for r in righe]
    if any(pts[i] < pts[i + 1] for i in range(len(pts) - 1)):
        p.append("i punti non scendono con la posizione")
    return p


def costruisci(game, region, division, righe, totale, adesso=None):
    adesso = adesso or time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    righe = [dict(r, pos=i + 1) for i, r in enumerate(righe)]     # pos = posto nell'elenco (a pari punti il «rank» stampato si ripete)
    sg = righe[SOGLIA_POSIZIONE - 1] if len(righe) >= SOGLIA_POSIZIONE else None
    return {"fonte": "Pokedata", "url": url_pagina(game, region, division, 1), "stagione": STAGIONE,
            "game": game, "region": region, "division": division, "aggiornato": adesso, "giocatori_totali": totale,
            "soglia": {"posizione": SOGLIA_POSIZIONE, "cp": sg["cp"] if sg else None, "rank_stampato": sg["rank"] if sg else None,
                       "nota": "posizione stimata, non ufficiale"},
            "righe": righe}


def nome_file(game, region, division):
    return ("%s-%s-%s" % (game, region, division)).lower().replace(" ", "-")


def salva(dati, out=OUT, oggi=None):
    """Scrive l'ultima classifica e una copia del giorno, ma solo se i punti sono cambiati. Ritorna True se ha scritto."""
    oggi = oggi or time.strftime("%Y-%m-%d", time.gmtime())
    base = nome_file(dati["game"], dati["region"], dati["division"])
    os.makedirs(os.path.join(out, "storico", base), exist_ok=True)
    firma = hashlib.sha1(json.dumps([[r["pos"], r["name"], r["cp"]] for r in dati["righe"]]).encode()).hexdigest()
    ultimo = os.path.join(out, base + ".json")
    try:
        with open(ultimo, encoding="utf-8") as f:
            vecchio = json.load(f)
        if vecchio.get("firma") == firma:
            return False
    except (OSError, ValueError):
        pass
    dati = dict(dati, firma=firma)
    for p in (ultimo, os.path.join(out, "storico", base, oggi + ".json")):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(dati, f, ensure_ascii=False, separators=(",", ":"))
    return True


def main(argv=None, scarica_fn=scarica, pausa_fn=None):
    argv = sys.argv[1:] if argv is None else argv
    scrivi = "--write" in argv
    print("%s - CP Pokedata %s (%d classifiche, massimo %d richieste)" % (
        "SALVATAGGIO" if scrivi else "PROVA (non salva nulla)", STAGIONE, len(COMBOS), len(COMBOS) * PAGINE))
    errori = 0
    for game, region, division in COMBOS:
        print("\n%s %s %s" % (game, region, division))
        try:
            righe, totale = leggi_classifica(game, region, division, scarica_fn, pausa_fn)
        except Stop as e:
            print("STOP:", e)
            return 1
        problemi = controlla(righe)
        if problemi:
            print("NON SALVO, qualcosa non torna:")
            for p in problemi:
                print("  -", p)
            errori += 1
            continue
        dati = costruisci(game, region, division, righe, totale)
        sg = dati["soglia"]
        print("Letti %d giocatori (totale dichiarato: %s). Posizione %d dell'elenco: %s CP." % (
            len(righe), totale if totale is not None else "?", sg["posizione"], sg["cp"] if sg["cp"] is not None else "non trovata"))
        for r in dati["righe"][:3]:
            print("   pos %d (rank stampato %d)  %-26s %-4s %5d CP  (storia: %d voci)" % (r["pos"], r["rank"], r["name"][:26], r["country"][:4], r["cp"], len(r["storia"])))
        ripetuti = len(dati["righe"]) - len(set(r["rank"] for r in dati["righe"]))
        print("Posti stampati ripetuti (pari punti): %d su %d" % (ripetuti, len(dati["righe"])))
        if scrivi:
            print("Salvato." if salva(dati) else "Invariato: nessun file toccato.")
        else:
            print("PROVA finita: non e' stato salvato nulla.")
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
