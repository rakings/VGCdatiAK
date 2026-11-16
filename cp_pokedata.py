#!/usr/bin/env python3
"""CP bar - classifica dei Championship Points da Pokedata (https://www.pokedata.ovh/2027/).
Poche richieste (3 pagine), lente e a tempi irregolari, con un'identificazione onesta e senza dati personali.
Senza --write e' una PROVA: legge e stampa quello che trova, ma non salva nulla.
Con --write salva in dati/cp/ (ultima classifica + una copia per giorno, solo se e' cambiata).

CLASSIFICA COMPLETA (tutti i giocatori, circa 126 pagine): per non pesare su Pokedata NON si legge a ogni giro.
  - ogni giro legge le prime 3 pagine (come sempre): primi 150 con la storia dei punti -> <nome>.json
  - SOLO se i primi 150 sono cambiati (cioe' dopo un torneo con punti), o se la copia completa ha piu' di 7 giorni,
    rilegge tutte le pagine, lentamente -> <nome>-tutti.json (posizione, nome, paese, punti: file leggero)
Con CP_OGNI_ORE=22 (lo mette il flusso automatico) un giro parte solo se dall'ultimo sono passate almeno 22 ore."""
import datetime
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
PAUSA_TUTTI = (4.0, 8.0)                      # lettura completa (molte pagine): pausa un po' piu' corta, sempre a tempi irregolari
TUTTI_MAX_PAGINE = 400                        # tetto di sicurezza (oggi sono circa 126)
TUTTI_OGNI_GIORNI = 7                         # lettura completa di sicurezza anche se i primi 150 non cambiano
STATO = os.path.join(OUT, "stato.json")       # quando e' stato fatto l'ultimo giro e l'ultima lettura completa


class Stop(Exception):
    pass


class Assente(Stop):
    """La pagina non esiste (404): per una stagione nuova vuol dire «la classifica non e' ancora partita»."""


def stagione_di(oggi):
    """La stagione di Pokedata cambia a settembre: da settembre 2026 ad agosto 2027 e' la «2027»."""
    return str(oggi.year + 1 if oggi.month >= 9 else oggi.year)


def url_pagina(game, region, division, n, stagione=None):
    q = "game=%s&region=%s&division=%s&search=&country=&page=%d" % (
        urllib.parse.quote(game), urllib.parse.quote(region), urllib.parse.quote(division), n)
    return "https://www.pokedata.ovh/%s/" % (stagione or STAGIONE) + "?" + q


def scarica(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (403, 429) or e.code >= 500:
            raise Stop("Pokedata ha risposto %s: mi fermo senza insistere" % e.code)
        if e.code == 404:
            raise Assente("Pokedata: pagina non trovata (%s)" % url)
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


def scegli_stagione(game, region, division, scarica_fn=scarica, oggi=None):
    """Prova la stagione di oggi; se la sua classifica non e' ancora partita (pagina assente, vuota o a zero punti) resta la precedente.
    Ritorna (stagione, prima_pagina_html) oppure (None, None). Costo normale: la prima pagina, che serve comunque."""
    oggi = oggi or datetime.date.today()
    nuova = stagione_di(oggi)
    for st in (nuova, str(int(nuova) - 1)):
        try:
            pag = scarica_fn(url_pagina(game, region, division, 1, st))
        except Assente:
            print("  stagione %s: la classifica non c'e' ancora" % st)
            continue
        r = righe_da_html(pag)
        if r and r[0]["cp"] > 0:
            return st, pag
        print("  stagione %s: classifica vuota o senza punti" % st)
    return None, None


def leggi_classifica(game, region, division, scarica_fn=scarica, pausa_fn=None, stagione=None, prima=None):
    pausa_fn = pausa_fn or (lambda: time.sleep(random.uniform(*PAUSA)))
    righe, totale = [], None
    for n in range(1, PAGINE + 1):
        pag = prima if (n == 1 and prima is not None) else scarica_fn(url_pagina(game, region, division, n, stagione))
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


def leggi_tutti(game, region, division, prime, totale, stagione, scarica_fn=scarica, pausa_fn=None):
    """Tutte le pagine dopo le prime 3 (gia' lette). Se Pokedata si ferma a meta', solleva Stop: la copia completa vecchia resta."""
    pausa_fn = pausa_fn or (lambda: time.sleep(random.uniform(*PAUSA_TUTTI)))
    righe = list(prime)
    ultima = min(TUTTI_MAX_PAGINE, -(-totale // 50) + 1) if totale else TUTTI_MAX_PAGINE
    for n in range(PAGINE + 1, ultima + 1):
        pausa_fn()
        r = righe_da_html(scarica_fn(url_pagina(game, region, division, n, stagione)))
        if not r:
            break
        righe += r
        if n % 20 == 0:
            print("  pagina %d: %d giocatori finora" % (n, len(righe)), flush=True)
    return righe


def controlla_tutti(righe):
    """Come controlla(), ma adatta a migliaia di nomi: tra tanti giocatori i nomi abbreviati uguali («Lucas M») sono normali,
    quindi i doppioni si contano su posto + nome (pagine ripetute darebbero gli stessi posti)."""
    p = []
    if righe and righe[0]["rank"] != 1:
        p.append("la classifica non parte dal primo posto")
    coppie = [(r["rank"], r["name"]) for r in righe]
    if len(set(coppie)) < len(coppie) * 0.98:
        p.append("troppe righe ripetute: le pagine potrebbero essere uguali")
    if any(righe[i]["cp"] < righe[i + 1]["cp"] for i in range(len(righe) - 1)):
        p.append("i punti non scendono con la posizione")
    return p


def serve_tutti(out, base, esito, oggi):
    """Lettura completa: dopo un cambiamento dei primi 150, se manca, o se e' piu' vecchia di TUTTI_OGNI_GIORNI."""
    if esito == "cambiata" or not os.path.exists(os.path.join(out, base + "-tutti.json")) \
            or not os.path.exists(os.path.join(out, base + "-storie.json")):
        return True
    st = carica_stato(out)
    ult = (st.get("tutti") or {}).get(base)
    try:
        return (oggi - datetime.date.fromisoformat(ult)).days >= TUTTI_OGNI_GIORNI
    except (TypeError, ValueError):
        return True


def salva_tutti(righe, totale, stagione, base, adesso, out=OUT):
    righe = [dict(r, pos=i + 1) for i, r in enumerate(righe)]
    d = {"fonte": "Pokedata", "stagione": stagione, "aggiornato": adesso, "giocatori_totali": totale, "n": len(righe),
         "campi": ["pos", "rank", "nome", "paese", "cp"], "r": [[r["pos"], r["rank"], r["name"], r["country"], r["cp"]] for r in righe]}
    cartella_st = os.path.join(out, "stagioni", stagione)
    os.makedirs(cartella_st, exist_ok=True)
    for p in (os.path.join(out, base + "-tutti.json"), os.path.join(cartella_st, base + "-tutti.json")):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
    # storia dei punti di TUTTI i giocatori (non solo dei primi 150), in un file a parte: il sito lo scarica solo
    # quando tocchi un giocatore oltre i primi 150. Chiave = posto nell'elenco (pos), voce = [cp, delta, "AAAA-MM-GG"].
    s = {"fonte": "Pokedata", "stagione": stagione, "aggiornato": adesso, "campi": ["cp", "delta", "data"],
         "s": {str(r["pos"]): [[x["cp"], x["delta"], x["data"]] for x in r.get("storia") or []] for r in righe if r.get("storia")}}
    for p in (os.path.join(out, base + "-storie.json"), os.path.join(cartella_st, base + "-storie.json")):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, separators=(",", ":"))


def carica_stato(out=OUT):
    try:
        with open(os.path.join(out, "stato.json"), encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def salva_stato(st, out=OUT):
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "stato.json"), "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


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


def costruisci(game, region, division, righe, totale, adesso=None, stagione=None):
    adesso = adesso or time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    righe = [dict(r, pos=i + 1) for i, r in enumerate(righe)]     # pos = posto nell'elenco (a pari punti il «rank» stampato si ripete)
    sg = righe[SOGLIA_POSIZIONE - 1] if len(righe) >= SOGLIA_POSIZIONE else None
    return {"fonte": "Pokedata", "url": url_pagina(game, region, division, 1, stagione), "stagione": stagione or STAGIONE,
            "game": game, "region": region, "division": division, "aggiornato": adesso, "giocatori_totali": totale,
            "soglia": {"posizione": SOGLIA_POSIZIONE, "cp": sg["cp"] if sg else None, "rank_stampato": sg["rank"] if sg else None,
                       "nota": "posizione stimata, non ufficiale"},
            "righe": righe, "tutti": nome_file(game, region, division) + "-tutti.json"}


def nome_file(game, region, division):
    return ("%s-%s-%s" % (game, region, division)).lower().replace(" ", "-")


def salva(dati, out=OUT, oggi=None):
    """Scrive sempre l'ultima classifica con la data del CONTROLLO e il totale dei giocatori; la data «aggiornato» (ultima variazione dei punti) e la
    copia del giorno in storico/ cambiano solo se i punti dei primi 150 sono cambiati. Ritorna "cambiata" oppure "controllata"."""
    oggi = oggi or time.strftime("%Y-%m-%d", time.gmtime())
    base = nome_file(dati["game"], dati["region"], dati["division"])
    os.makedirs(os.path.join(out, "storico", base), exist_ok=True)
    firma = hashlib.sha1(json.dumps([[r["pos"], r["name"], r["cp"]] for r in dati["righe"]]).encode()).hexdigest()
    ultimo = os.path.join(out, base + ".json")
    vecchio = None
    try:
        with open(ultimo, encoding="utf-8") as f:
            vecchio = json.load(f)
    except (OSError, ValueError):
        pass
    cambiata = not vecchio or vecchio.get("firma") != firma
    controllato = dati["aggiornato"]
    if not cambiata:
        dati = dict(dati, aggiornato=vecchio.get("aggiornato", dati["aggiornato"]))
    dati = dict(dati, firma=firma, controllato=controllato)
    cartella_st = os.path.join(out, "stagioni", dati["stagione"])
    os.makedirs(cartella_st, exist_ok=True)
    percorsi = [ultimo, os.path.join(cartella_st, base + ".json")] + ([os.path.join(out, "storico", base, oggi + ".json")] if cambiata else [])
    for p in percorsi:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(dati, f, ensure_ascii=False, separators=(",", ":"))
    aggiorna_indice(out, base, dati["stagione"], oggi)
    return "cambiata" if cambiata else "controllata"


def aggiorna_indice(out, base, corrente, oggi):
    """Archivio per stagione (solo da quando esiste): ogni stagione ha il suo file in stagioni/<anno>/. Quella in corso si aggiorna a ogni controllo;
    quando parte la classifica della stagione dopo, le precedenti si CHIUDONO (finale = true, con la data) e non si toccano piu'.
    indice.json elenca le stagioni, dalla piu' recente, per l'app."""
    elenco = []
    base_st = os.path.join(out, "stagioni")
    for st in sorted(os.listdir(base_st), reverse=True) if os.path.isdir(base_st) else []:
        p = os.path.join(base_st, st, base + ".json")
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        if st != corrente and not d.get("finale"):
            d = dict(d, finale=True, chiusa=oggi)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
        voce = {"stagione": st, "stato": "in corso" if st == corrente else "finale", "file": "stagioni/%s/%s.json" % (st, base),
                "soglia": (d.get("soglia") or {}).get("cp"), "aggiornato": d.get("aggiornato")}
        if st != corrente:
            voce["chiusa"] = d.get("chiusa")
        elenco.append(voce)
    nuovo = {"corrente": corrente, "stagioni": elenco}
    p = os.path.join(out, "indice.json")
    try:
        with open(p, encoding="utf-8") as f:
            if json.load(f) == nuovo:
                return
    except (OSError, ValueError):
        pass
    with open(p, "w", encoding="utf-8") as f:
        json.dump(nuovo, f, ensure_ascii=False, separators=(",", ":"))


def main(argv=None, scarica_fn=scarica, pausa_fn=None, oggi_fn=datetime.date.today):
    argv = sys.argv[1:] if argv is None else argv
    scrivi = "--write" in argv
    ogni = float(os.environ.get("CP_OGNI_ORE") or 0)
    if scrivi and ogni:   # giro automatico: parte solo se sono passate almeno CP_OGNI_ORE ore dall'ultimo
        ult = carica_stato().get("giro")
        try:
            passate = (time.time() - datetime.datetime.fromisoformat(ult).timestamp()) / 3600
        except (TypeError, ValueError):
            passate = 1e9
        if passate < ogni:
            print("Ultimo giro %.1f ore fa: il prossimo tra %.1f ore. Niente da fare." % (passate, ogni - passate))
            return 0
    print("%s - CP Pokedata %s (%d classifiche, %d richieste per i primi 150; la classifica completa solo se serve)" % (
        "SALVATAGGIO" if scrivi else "PROVA (non salva nulla)", STAGIONE, len(COMBOS), len(COMBOS) * PAGINE))
    errori = 0
    for game, region, division in COMBOS:
        print("\n%s %s %s" % (game, region, division))
        try:
            stagione, prima = scegli_stagione(game, region, division, scarica_fn, oggi_fn())
            if not stagione:
                print("Nessuna classifica trovata (ne' per la stagione nuova ne' per la precedente): non salvo.")
                errori += 1
                continue
            print("  stagione in corso: %s" % stagione)
            righe, totale = leggi_classifica(game, region, division, scarica_fn, pausa_fn, stagione, prima)
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
        dati = costruisci(game, region, division, righe, totale, stagione=stagione)
        sg = dati["soglia"]
        print("Letti %d giocatori (totale dichiarato: %s). Posizione %d dell'elenco: %s CP." % (
            len(righe), totale if totale is not None else "?", sg["posizione"], sg["cp"] if sg["cp"] is not None else "non trovata"))
        for r in dati["righe"][:3]:
            print("   pos %d (rank stampato %d)  %-26s %-4s %5d CP  (storia: %d voci)" % (r["pos"], r["rank"], r["name"][:26], r["country"][:4], r["cp"], len(r["storia"])))
        ripetuti = len(dati["righe"]) - len(set(r["rank"] for r in dati["righe"]))
        print("Posti stampati ripetuti (pari punti): %d su %d" % (ripetuti, len(dati["righe"])))
        if scrivi:
            esito = salva(dati, oggi=oggi_fn().isoformat())
            print("Classifica cambiata: salvata." if esito == "cambiata" else "Classifica invariata: aggiornati solo la data del controllo e il totale dei giocatori.")
            base = nome_file(game, region, division)
            if serve_tutti(OUT, base, esito, oggi_fn()):
                print("Classifica completa: la rileggo tutta (%s giocatori, lentamente)..." % (totale or "?"), flush=True)
                try:
                    tutti = leggi_tutti(game, region, division, righe, totale, stagione, scarica_fn, pausa_fn)
                    pr = controlla_tutti(tutti)
                    if totale and len(tutti) < totale * 0.9:
                        pr.append("letti solo %d giocatori su %d" % (len(tutti), totale))
                    if pr:
                        print("Classifica completa NON salvata (resta quella di prima):", "; ".join(pr))
                    else:
                        salva_tutti(tutti, totale, stagione, base, dati["aggiornato"])
                        st = carica_stato()
                        st.setdefault("tutti", {})[base] = oggi_fn().isoformat()
                        salva_stato(st)
                        print("Classifica completa salvata: %d giocatori." % len(tutti))
                except Stop as e:
                    print("Classifica completa interrotta (%s): resta quella di prima." % e)
            else:
                print("Classifica completa: non serve rileggerla (primi 150 invariati, copia recente).")
        else:
            print("PROVA finita: non e' stato salvato nulla.")
    if scrivi:
        st = carica_stato()
        st["giro"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes")
        salva_stato(st)
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
