#!/usr/bin/env python3
"""Limitless VGC: storico dei risultati dei giocatori (i primi classificati di ogni torneo), letto dalle pagine dei TORNEI.

- Poche richieste, lente (pausa di 6-14 secondi), identificazione onesta, nessun dato personale, si ferma al primo rifiuto (403/429/5xx).
- Dati grezzi in limitless/ (elenco.json e t/<id>.json); file per il sito in vgcstats/limitless.json:
    {"v":1,"source":"Limitless VGC","source_url":..., "t":[[id,nome,data,giocatori,tipo,formato],...], "p":[[nome,paese,[[numero torneo in t, posto],...]],...]}
- Si puo' riprendere in ogni momento: cio' che e' gia' stato letto non si rilegge (tranne i tornei degli ultimi 7 giorni)."""
import argparse
import datetime
import gzip
import html as _html
import json
import os
import random
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request

UA = "tornei-vgc-bot (sito della community, con link alle fonti)"
BASE = "https://limitlessvgc.com"
DIR = "limitless"
FILE_SITO = os.path.join("vgcstats", "limitless.json")
STAGIONI = ["2526", "2425", "2324", "2223", "2122", "2021", "1920", "1819", "1718", "1617", "1516", "1415", "1314", "1213", "1112"]
ERE = ["modern", "legacy"]
TIPI = {"regional": "Regional Championships", "international": "International Championships", "worlds": "World Championship",
        "special": "Special Championships", "national": "National Championships", "players_cup": "Players Cup", "mbl": "Master Ball League"}
PAUSA = (6.0, 14.0)
GIORNI_RECENTI = 7
GIORNI_CONTROLLO = 6


class Stop(Exception):
    pass


class Contesto:
    def __init__(self, budget, scarica=None, pausa=None, oggi=None):
        self.budget, self.usate = budget, 0
        self._scarica = scarica or scarica_rete
        self.pausa = pausa or (lambda: time.sleep(random.uniform(*PAUSA)))
        self.oggi = oggi or datetime.date.today()
        self.primo = True

    def get(self, url):
        if self.usate >= self.budget:
            raise Stop("budget")
        if not self.primo:
            self.pausa()
        self.primo = False
        self.usate += 1
        st, testo = self._scarica(url)
        if st in (403, 429) or st >= 500 or st == 0:
            raise Stop("Limitless ha risposto %s per %s: mi fermo senza insistere" % (st, url))
        if st != 200:
            raise ValueError("risposta %s per %s" % (st, url))
        return testo


def scarica_rete(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
            if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                body = gzip.decompress(body)
            return r.status, body.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


# ------------------------------------------------------------------ lettura delle pagine

def _attr(tag, nome):
    m = re.search(r'\b%s="([^"]*)"' % re.escape(nome), tag)
    return _html.unescape(m.group(1)).strip() if m else ""


def righe_elenco(pag):
    """Righe dell'elenco tornei: dict(id, data, nome, giocatori, vincitore, paese, formato)."""
    out = []
    for m in re.finditer(r"<tr\b[^>]*>", pag):
        tag = m.group(0)
        if "data-date" not in tag or "data-name" not in tag:
            continue
        i = re.search(r'href="(?:https?://limitlessvgc\.com)?/tournaments/(\d+)["/?#]', pag[m.end(): m.end() + 1200])
        if not i:
            continue
        try:
            giocatori = int(_attr(tag, "data-players") or 0)
        except ValueError:
            giocatori = 0
        out.append({"id": int(i.group(1)), "data": _attr(tag, "data-date"), "nome": _attr(tag, "data-name"), "giocatori": giocatori,
                    "vincitore": _attr(tag, "data-winner"), "paese": _attr(tag, "data-country"), "formato": _attr(tag, "data-format")})
    return out


def righe_risultati(pag):
    """Righe dei risultati di un torneo: (posto, nome, paese)."""
    out = []
    for m in re.finditer(r"<tr\b[^>]*data-rank=[^>]*>", pag):
        tag = m.group(0)
        try:
            rank = int(_attr(tag, "data-rank"))
        except ValueError:
            continue
        nome = _attr(tag, "data-name")
        if nome:
            out.append((rank, " ".join(nome.split()), _attr(tag, "data-country").upper()))
    return out


def tipo_da_nome(nome):
    n = nome.lower()
    if re.search(r"world", n):
        return "worlds"
    if re.search(r"\b(euic|naic|laic|ocic|aic)\b|international", n):
        return "international"
    if "national" in n:
        return "national"
    if "special event" in n or n.startswith("special"):
        return "special"
    if "players cup" in n:
        return "players_cup"
    if "master ball" in n:
        return "mbl"
    if n.startswith("regional") or "regional" in n:
        return "regional"
    return ""


# ------------------------------------------------------------------ stato su disco

def carica(p, default):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def salva(p, dati, compatto=False):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    testo = json.dumps(dati, ensure_ascii=False, separators=(",", ":") if compatto else None, indent=None if compatto else 1, sort_keys=not compatto)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(testo)
    os.replace(tmp, p)


def stato():
    s = carica(os.path.join(DIR, "elenco.json"), {})
    s.setdefault("t", {})
    s.setdefault("tipo", {})
    s.setdefault("fatte", [])
    s.setdefault("controllo", 0)
    s.setdefault("tipi_validi", True)
    return s


def salva_stato(s):
    salva(os.path.join(DIR, "elenco.json"), s)


# ------------------------------------------------------------------ scoperta dell'elenco dei tornei

def pagine_elenco(ctx, parametri, lavoro=None):
    """Scorre l'elenco (show=100, poi page=2, 3...) finche' compaiono tornei nuovi. Ritorna la lista di righe."""
    viste, tutte = set(), []
    for pagina in range(1, 40):
        url = "%s/tournaments?%s&show=100&page=%d" % (BASE, parametri, pagina)
        righe = righe_elenco(ctx.get(url))
        nuove = [r for r in righe if r["id"] not in viste]
        if not nuove:
            break
        for r in nuove:
            viste.add(r["id"])
        tutte += nuove
        if lavoro:
            lavoro(nuove)
    return tutte


def scopri(ctx, s):
    """Prima scoperta: tutte le stagioni, poi i filtri per tipo (per sapere se e' Regionale, Internazionale, ...). Riprendibile."""
    compiti = [("s:%s" % st, "time=%s" % st) for st in STAGIONI] + [("t:%s:%s" % (t, e), "type=%s&time=%s" % (t, e)) for t in TIPI for e in ERE]
    for chiave, par in compiti:
        if chiave in s["fatte"]:
            continue
        if chiave.startswith("s:"):
            def aggiungi(righe):
                for r in righe:
                    s["t"][str(r["id"])] = r
        else:
            tipo = chiave.split(":")[1]
            def aggiungi(righe, tipo=tipo):
                for r in righe:
                    s["t"].setdefault(str(r["id"]), r)
                    s["tipo"].setdefault(str(r["id"]), [])
                    if tipo not in s["tipo"][str(r["id"])]:
                        s["tipo"][str(r["id"])].append(tipo)
        pagine_elenco(ctx, par, aggiungi)
        s["fatte"].append(chiave)
        salva_stato(s)
    # i filtri per tipo servono solo se sono affidabili: un torneo non puo' essere di due tipi diversi
    doppi = sum(1 for v in s["tipo"].values() if len(v) > 1)
    s["tipi_validi"] = not s["tipo"] or doppi <= 0.02 * len(s["tipo"])
    if not s["tipi_validi"]:
        print("Attenzione: il filtro per tipo di Limitless non sembra affidabile (%d tornei con piu' tipi): uso solo il nome del torneo." % doppi)
    s["controllo"] = int(time.time())
    salva_stato(s)


def stagione_corrente(oggi):
    y = oggi.year if oggi.month >= 9 else oggi.year - 1
    return "%02d%02d" % (y % 100, (y + 1) % 100)


def controlla_nuovi(ctx, s):
    """Controllo veloce (dopo la prima scoperta): solo la stagione in corso."""
    nuovi = 0
    for r in pagine_elenco(ctx, "time=%s" % stagione_corrente(ctx.oggi)):
        if str(r["id"]) not in s["t"]:
            nuovi += 1
        s["t"][str(r["id"])] = r
    s["controllo"] = int(time.time())
    salva_stato(s)
    return nuovi


def tipo_di(s, tid):
    t = s["tipo"].get(tid) if s.get("tipi_validi") else None
    if t and len(t) == 1:
        return t[0]
    return tipo_da_nome(s["t"][tid]["nome"])


# ------------------------------------------------------------------ lettura dei tornei

def da_leggere(s, oggi):
    """Tornei senza file, piu' quelli degli ultimi giorni (i risultati possono completarsi). Prima i piu' recenti."""
    out = []
    for tid, r in s["t"].items():
        if not os.path.exists(os.path.join(DIR, "t", "%s.json" % tid)):
            out.append(tid)
            continue
        try:
            d = datetime.date.fromisoformat(r["data"])
        except ValueError:
            continue
        if 0 <= (oggi - d).days <= GIORNI_RECENTI:
            letto = carica(os.path.join(DIR, "t", "%s.json" % tid), {}).get("letto", "")
            if letto != oggi.isoformat():
                out.append(tid)
    return sorted(out, key=lambda t: s["t"][t]["data"], reverse=True)


def leggi_torneo(ctx, s, tid):
    pag = ctx.get("%s/tournaments/%s" % (BASE, tid))
    righe = righe_risultati(pag)
    r = s["t"][tid]
    dati = {"id": int(tid), "nome": r["nome"], "data": r["data"], "giocatori": r["giocatori"], "formato": r["formato"], "tipo": tipo_di(s, tid),
            "letto": ctx.oggi.isoformat(), "r": [[a, b, c] for a, b, c in righe]}
    if not righe:
        print("   (torneo %s «%s»: nessun risultato nella pagina)" % (tid, r["nome"]))
    salva(os.path.join(DIR, "t", "%s.json" % tid), dati, compatto=True)
    return len(righe)


# ------------------------------------------------------------------ file per il sito

def norm(x):
    x = unicodedata.normalize("NFKD", x or "")
    return re.sub(r"\s+", " ", "".join(c for c in x if not unicodedata.combining(c)).lower()).strip()


def costruisci(oggi=None):
    tornei, persone = [], {}
    cartella = os.path.join(DIR, "t")
    files = sorted(os.listdir(cartella)) if os.path.isdir(cartella) else []
    schede = [carica(os.path.join(cartella, f), {}) for f in files if f.endswith(".json")]
    schede = [x for x in schede if x.get("r")]
    schede.sort(key=lambda x: (x["data"], x["id"]))
    for k, x in enumerate(schede):
        tornei.append([x["id"], x["nome"], x["data"], x["giocatori"], TIPI.get(x["tipo"], "Other"), x.get("formato", "")])
        for rank, nome, cc in x["r"]:
            p = persone.setdefault((norm(nome), cc), [nome, cc, []])
            p[2].append([k, rank])
    elenco = sorted(persone.values(), key=lambda p: (norm(p[0]), p[1]))
    return {"v": 1, "source": "Limitless VGC", "source_url": BASE, "aggiornato": (oggi or datetime.date.today()).isoformat(), "t": tornei, "p": elenco}


def scrivi_sito(oggi=None):
    dati = costruisci(oggi)
    if not dati["t"]:
        print("Nessun torneo letto: non scrivo il file per il sito.")
        return None
    salva(FILE_SITO, dati, compatto=True)
    righe = sum(len(p[2]) for p in dati["p"])
    print("File per il sito: %d tornei, %d giocatori, %d risultati, %.0f KB." % (len(dati["t"]), len(dati["p"]), righe, os.path.getsize(FILE_SITO) / 1024))
    return dati


def cerca(nome, dati):
    if not dati:
        return
    k = norm(nome)
    trovati = [p for p in dati["p"] if k in norm(p[0])]
    print("\nRisultati per «%s»: %d giocatore/i" % (nome, len(trovati)))
    for p in trovati[:5]:
        print("  %s [%s]" % (p[0], p[1]))
        for t, rank in sorted(p[2], key=lambda r: dati["t"][r[0]][2], reverse=True):
            x = dati["t"][t]
            print("     %s  %-45s %-28s %s°" % (x[2], x[1][:45], x[4], rank))


# ------------------------------------------------------------------ programma

def main(argv=None, ctx=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="scrive i file (senza, e' solo una prova che non salva niente)")
    ap.add_argument("--auto", action="store_true", help="per l'avvio automatico: se non c'e' niente da fare, esce subito")
    ap.add_argument("--tornei", type=int, default=60, help="quante pagine di tornei leggere in questo giro")
    ap.add_argument("--richieste", type=int, default=0, help="massimo di richieste in tutto (0 = tornei + 60 per l'elenco)")
    ap.add_argument("--cerca", default="", help="nome da cercare nel log alla fine")
    a = ap.parse_args(argv)
    ctx = ctx or Contesto(a.richieste or (a.tornei + 60))
    if not a.write:
        print("PROVA (non salva nulla): leggo solo la prima pagina dell'elenco.")
        righe = righe_elenco(ctx.get("%s/tournaments?time=%s&show=100&page=1" % (BASE, stagione_corrente(ctx.oggi))))
        for r in righe[:5]:
            print("  ", r)
        return 0
    s = stato()
    try:
        scoperta_fatta = all(k in s["fatte"] for k in ["s:%s" % x for x in STAGIONI] + ["t:%s:%s" % (t, e) for t in TIPI for e in ERE])
        if not scoperta_fatta:
            print("Prima scoperta dell'elenco dei tornei (si puo' riprendere): fatte %d pagine di elenco." % len(s["fatte"]))
            scopri(ctx, s)
        elif a.auto and not da_leggere(s, ctx.oggi) and time.time() - s["controllo"] < GIORNI_CONTROLLO * 86400:
            print("Niente da fare: tutto letto e controllato da meno di %d giorni." % GIORNI_CONTROLLO)
            return 0
        else:
            n = controlla_nuovi(ctx, s)
            print("Controllo dei tornei nuovi: %d nuovi." % n)
        lista = da_leggere(s, ctx.oggi)
        print("Tornei noti: %d | da leggere ora: %d" % (len(s["t"]), len(lista)))
        letti = 0
        for tid in lista[: a.tornei]:
            n = leggi_torneo(ctx, s, tid)
            letti += 1
            print("%3d  %-8s %s  %s  (%d risultati)" % (letti, tid, s["t"][tid]["data"], s["t"][tid]["nome"][:50], n))
    except Stop as e:
        print("Mi fermo qui: %s" % e)
    except ValueError as e:
        print("Pagina inattesa, mi fermo: %s" % e)
    dati = scrivi_sito(ctx.oggi)
    mancanti = len(da_leggere(s, ctx.oggi))
    print("Richieste fatte: %d. Tornei ancora da leggere: %d." % (ctx.usate, mancanti))
    if a.cerca:
        cerca(a.cerca, dati)
    return 0


if __name__ == "__main__":
    sys.exit(main())
