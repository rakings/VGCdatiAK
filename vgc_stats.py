#!/usr/bin/env python3
"""VGC Stats - raccolta dati dei regionali VGC dalla API di Pokedata (pokedata.ovh/apiv3).

L'autore di Pokedata ha dato il permesso di usare i suoi dati, anche in tempo reale.
Solo libreria standard. UNA richiesta per regionale (classifica + squadre + swiss tutto insieme).

Uso:
  python3 vgc_stats.py --list                    elenco di tutti i regionali (1 richiesta)
  python3 vgc_stats.py --id 1000076              PROVA su un regionale: non salva nulla
  python3 vgc_stats.py --id 1000076 --write      salva in vgcstats/1000076/
  python3 vgc_stats.py --auto --write            raccoglie i regionali IN CORSO e quelli finiti non ancora raccolti
  python3 vgc_stats.py --live --write --commit   controlli ripetuti finche' un regionale e' in corso (vedi sotto)
  python3 vgc_stats.py --live --max-cycles 1     PROVA: un solo controllo, non salva nulla
  python3 vgc_stats.py --cf-test                 PROVA di Cloudflare: carica i dati gia' presenti e dice se ha funzionato
Modo live: controlla ogni 3-5 minuti (a caso). Se trova dati nuovi li salva (e con --commit li pubblica),
poi NON controlla per 12 minuti e al ritorno controlla subito. (Pubblicazioni: al massimo una ogni 12 minuti,
cioe' al massimo 5 all'ora: GitHub Pages ne accetta in modo morbido 10 all'ora per tutta la repo.) Quando il regionale finisce salva e si chiude;
se non c'e' nessun regionale in corso si ferma subito. Si ferma da solo dopo 345 minuti (il flusso ne concede 355).
Cloudflare (facoltativo): se sono impostati CF_PAGES_PROJECT, CLOUDFLARE_API_TOKEN e CLOUDFLARE_ACCOUNT_ID, a ogni salvataggio con
dati nuovi i file vengono caricati anche su Cloudflare Pages (banda illimitata: regge anche tanta gente). Su GitHub allora si salva
al massimo ogni 30 minuti (e alla fine), come copia di riserva. Se Cloudflare non riesce, si salva subito su GitHub e l'app usa quello.
Senza --write e' sempre una prova: stampa un riepilogo e non salva niente.
"""
import argparse
import calendar
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter

UA = "tornei-vgc-bot (sito della community, con link alle fonti)"
API = "https://www.pokedata.ovh/apiv3"
OUT = "vgcstats"
TOP = 256            # squadre complete (strumenti, mosse, nature) per i primi 256
DELAY = 2.0          # secondi tra una richiesta e l'altra
# Regolamento in base alla data di inizio del regionale (DA VERIFICARE: aggiorna le date se serve).
# Quando esce un nuovo regolamento (es. M-D) basta aggiungere una riga in cima.
REG_WINDOWS = [("M-C", "2026-09-01"), ("M-B", "2026-07-01"), ("M-A", "2026-05-25")]
RESULT = {3: "W", 0: "L", 1: "T"}
KNOWN = {"id", "subid", "name", "ability", "item", "badges", "stat alignment", "teratype"}
FORMS = {"Male": "-M", "Female": "-F", "Alolan Form": "-Alola", "Hisuian Form": "-Hisui",
         "Galarian Form": "-Galar", "Paldean Form": "-Paldea", "Paldean Form - Blaze Breed": "-Paldea-Fire",
         "Paldean Form - Aqua Breed": "-Paldea-Water", "Bloodmoon": "-Bloodmoon", "Family of Four": "-Four",
         "Family of Three": "", "Curly Form": "", "Droopy Form": "-Droopy", "Stretchy Form": "-Stretchy",
         "Unremarkable Form": "", "Masterpiece Form": "-Masterpiece"}


class Stop(Exception):
    """Pokedata ci ha chiesto di fermarci: ci fermiamo subito."""


class Budget(Exception):
    pass


used = 0
budget = 3
cut_state = {}         # id regionale -> True se nell'ultimo controllo era in corso la Top 8
mese_pieno = False      # True se nel mese in corso sono gia' iniziati almeno EVENTI_MESE_PIENO tornei
turno_nuovo = False       # True se in questo giro e' comparso un round nuovo (pairings appena pubblicati)
fine_avvisati = set()     # regionali per cui e' gia' comparso l'avviso «finale finita da piu' di un'ora»
avvisati = set()         # regionali per cui e' gia' comparso l'avviso «finito ma ancora vivo»
cut_active = False     # True se almeno un regionale in corso e' nella fase a eliminazione diretta
last_status = {}       # id regionale -> stato letto nell'ultimo controllo (running / finished)
unpushed = False       # True se un salvataggio e' stato fatto ma non ancora pubblicato
any_changed = False   # True se un giro normale (elenco / auto / singolo regionale) ha salvato qualcosa: poi si aggiorna anche Cloudflare
last_git = None        # momento dell'ultima pubblicazione su GitHub (con Cloudflare attivo si salva su GitHub piu' di rado)


def fetch_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def get_json(url):
    """Scarica e legge il JSON (Pokedata a volte mette un avviso PHP prima del JSON: lo ignoriamo)."""
    global used
    if used >= budget:
        raise Budget()
    used += 1
    time.sleep(DELAY)
    try:
        text = fetch_text(url)
    except urllib.error.HTTPError as e:
        if e.code in (403, 429) or e.code >= 500:
            raise Stop("Pokedata ha risposto %s per %s" % (e.code, url))
        raise
    i = text.find("{")
    if i < 0:
        raise Stop("risposta inattesa da Pokedata per %s" % url)
    return json.loads(text[i:])


# ---------- nomi e regolamento ----------

unknown_forms = set()


def showdown_name(raw):
    """'Basculegion [Male]' -> 'Basculegion-M', 'Ninetales [Alolan Form]' -> 'Ninetales-Alola'."""
    m = re.match(r"^(.*?)\s*\[(.+)\]$", raw.strip())
    if not m:
        return raw.strip()
    base, form = m.group(1), m.group(2)
    if form in FORMS:
        return base + FORMS[form]
    unknown_forms.add(raw)
    return base + "-" + form.split()[0]


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def reg_of(start):
    for reg, since in REG_WINDOWS:
        if start and start >= since:
            return reg
    return "old"


def person(raw):
    """'Louis Fontvieille [FR]' -> {'name': 'Louis Fontvieille', 'cc': 'FR'}"""
    if not raw:
        return None
    m = re.match(r"^(.*?)\s*\[([A-Za-z]{2,3})\]$", raw.strip())
    return {"name": m.group(1), "cc": m.group(2).upper()} if m else {"name": raw.strip(), "cc": ""}


def city_of(name):
    m = re.match(r"^(?:\d{4} )?(?:(.+?) )?Pok.mon VGC (.*)$", name)
    if not m:
        return name, ""
    return (m.group(1) or m.group(2)), m.group(2)


# ---------- elaborazione di un regionale ----------

def process(data):
    """Dal JSON di Pokedata a giocatori, squadre e swiss."""
    info = data["tournament"]
    block = next((b for b in data["tournament_data"] if b.get("division") == "masters"), None)
    if not block:
        raise ValueError("divisione masters non trovata")
    raw = block["data"]
    swiss_total = (info.get("roundNumbers") or {}).get("masters") or 0
    plain = {}
    pid_of = {}
    for i, p in enumerate(raw):
        pid_of[i] = i + 1
    # tavoli: (round, tavolo) -> giocatori (risolve anche gli omonimi)
    tables = {}
    for i, p in enumerate(raw):
        for r, e in (p.get("rounds") or {}).items():
            if e.get("table") is not None:
                tables.setdefault((int(r), e["table"]), []).append(i)
    per_round = Counter()
    for p in raw:
        for r in (p.get("rounds") or {}):
            per_round[int(r)] += 1
    # fase 2 = dove il numero di giocatori crolla (il taglio dopo il primo giorno)
    day1, best = 0, 0.0
    for r in sorted(per_round):
        nxt = per_round.get(r + 1)
        if nxt and per_round[r] > 0:
            drop = 1.0 - nxt / per_round[r]
            if drop > best:
                best, day1 = drop, r
    if best < 0.4:
        day1 = 0
    players, swiss, teams = [], {}, {}
    for i, p in enumerate(raw):
        pid = i + 1
        m = re.match(r"^(.*?)\s*\[([A-Za-z]{2,3})\]$", p["name"])
        name, cc = (m.group(1), m.group(2).upper()) if m else (p["name"], "")
        rec = p.get("record") or {}
        rounds = p.get("rounds") or {}
        played = sorted(int(r) for r in rounds)
        entry = []
        for r in range(1, max(played or [0]) + 1):
            e = rounds.get(str(r))
            if not e:
                entry.append(None)
                continue
            if e.get("table") is None:
                entry.append("0B")
                continue
            others = [x for x in tables.get((r, e["table"]), []) if x != i]
            code = RESULT.get(e.get("result"), "?")
            entry.append("%d%s" % (others[0] + 1, code) if len(others) == 1 else "-1%s" % code)
        swiss[pid] = entry
        mons = []
        for t in p.get("teamlist") or []:
            nm = showdown_name(t.get("name", ""))
            extra = {k: v for k, v in t.items() if k not in KNOWN and v not in (None, "")}
            if t.get("teratype"):
                extra["Tera Type"] = t["teratype"]
            mons.append({"slug": slug(nm), "name": nm, "item": t.get("item") or "", "ability": t.get("ability") or "",
                         "nature": t.get("stat alignment") or "", "moves": [x for x in (t.get("badges") or []) if x],
                         "extra": extra})
        placing = p.get("placing") or pid
        players.append({"tp_id": pid, "name": name, "country": cc, "placement": placing, "wins": rec.get("wins", 0),
                        "losses": rec.get("losses", 0), "ties": rec.get("ties", 0),
                        "day2": 1 if day1 and played and max(played) > day1 else 0,
                        "topcut": 1 if swiss_total and played and max(played) > swiss_total else 0,
                        "team": ",".join(m_["slug"] for m_ in mons), "trainer": p.get("Trainer name")})
        if mons and placing <= TOP:
            teams[str(pid)] = mons
    return info, players, teams, swiss, day1, swiss_total


# ---------- statistiche ----------

def top_pairs(counter, n=None):
    return [[k, v] for k, v in counter.most_common(n)]


def compute(players, teams, names):
    rows = {}
    for p in players:
        slugs = {s for s in (p.get("team") or "").split(",") if s}
        for s in slugs:
            r = rows.setdefault(s, {"count": 0, "wins": 0, "losses": 0, "top256": 0, "day2": 0, "cut": 0, "partners": Counter()})
            r["count"] += 1
            r["wins"] += p["wins"]
            r["losses"] += p["losses"]
            r["top256"] += 1 if p["placement"] <= TOP else 0
            r["day2"] += 1 if p.get("day2") else 0
            r["cut"] += 1 if p.get("topcut") else 0
            for o in slugs:
                if o != s:
                    r["partners"][o] += 1
    det = {}
    for tp, team in teams.items():
        for mon in team:
            d = det.setdefault(mon["slug"], {"sample": 0, "nature": Counter(), "item": Counter(), "ability": Counter(),
                                              "moves": Counter(), "extra": {}, "players": []})
            d["sample"] += 1
            d["players"].append(int(tp))
            for key in ("nature", "item", "ability"):
                if mon[key]:
                    d[key][mon[key]] += 1
            for mv in mon["moves"]:
                d["moves"][mv] += 1
            for label, val in mon["extra"].items():
                d["extra"].setdefault(label, Counter())[str(val)] += 1
    out = []
    for s, r in sorted(rows.items(), key=lambda kv: -kv[1]["count"]):
        d = det.get(s)
        item = {"slug": s, "name": names.get(s) or s.replace("-", " ").title(), "count": r["count"], "wins": r["wins"],
                "losses": r["losses"], "top256": r["top256"], "day2": r["day2"], "cut": r["cut"],
                "partners": top_pairs(r["partners"], 15), "sample": 0}
        if d:
            item.update({"sample": d["sample"], "nature": top_pairs(d["nature"]), "item": top_pairs(d["item"]),
                         "ability": top_pairs(d["ability"]), "moves": top_pairs(d["moves"]),
                         "extra": {k: top_pairs(v) for k, v in d["extra"].items()}, "players": d["players"]})
        out.append(item)
    return out


# ---------- file ----------

def dump(path, obj):
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return True


def dump_stamped(path, obj):
    """Come dump, ma se cambia solo la data "updated" non riscrive il file: cosi' non nasce un salvataggio (e una pubblicazione) inutile."""
    old = load(path, None)
    if isinstance(old, dict) and {k: v for k, v in old.items() if k != "updated"} == {k: v for k, v in obj.items() if k != "updated"}:
        return False
    return dump(path, obj)


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


DATE_MANUALI = "date_manuali.json"  # facoltativo, nella cartella principale: {"id": {"start": "AAAA-MM-GG", "end": "AAAA-MM-GG"}}


def completa_date(events, oggi=None):
    """Se Pokedata non da' la data di un regionale, la si prende (in ordine): dal file date_manuali.json, dai dati gia' salvati,
    oppure, se il regionale e' in corso, dal giorno di oggi (il giorno in cui lo vediamo partire; la fine si aggiorna ogni giorno).
    Senza data il regolamento risulterebbe 'old' e il regionale uscirebbe dai totali del regolamento attuale.
    Se Pokedata la da', non cambia niente."""
    oggi = oggi or time.strftime("%Y-%m-%d", time.gmtime())
    man = load(DATE_MANUALI, {})
    if not isinstance(man, dict):
        man = {}
    for e in events:
        if e["start"]:
            continue
        m = man.get(str(e["id"])) or {}
        if not isinstance(m, dict):
            m = {}
        prec = load(os.path.join(OUT, str(e["id"]), "meta.json"), {})
        start = m.get("start") or prec.get("date") or ""
        if not start and e["status"] == "running":
            start = oggi
        if not start:
            continue
        in_corso = e["status"] == "running" and not m.get("end")
        e["start"] = start
        e["end"] = e["end"] or (oggi if in_corso else (m.get("end") or prec.get("end") or start))
        e["reg"] = reg_of(start)
    return events


def list_events():
    data = get_json(API + "/vg/tournaments/")
    out = []
    for t in data["vg"]["data"]:
        city, kind = city_of(t["name"])
        start = (t.get("date") or {}).get("start") or ""
        out.append({"id": t["id"], "name": t["name"], "city": city, "kind": kind, "start": start,
                    "end": (t.get("date") or {}).get("end") or "", "status": t.get("tournamentStatus"),
                    "players": (t.get("players") or {}).get("masters", 0), "decklists": t.get("decklists", 0),
                    "rounds": (t.get("roundNumbers") or {}).get("masters", 0), "reg": reg_of(start),
                    "winner": (t.get("winners") or {}).get("masters"), "rk9": t.get("rk9link"), "updated": t.get("lastUpdated") or "",
                    "winners": {d: person((t.get("winners") or {}).get(d)) for d in ("masters", "seniors", "juniors")},
                    "players_div": t.get("players") or {}})
    completa_date(out)
    out.sort(key=lambda e: e["start"], reverse=True)
    return out


# ---------- storico: i vecchi tornei di Pokedata (prima del nuovo sistema di id) ----------

STORICO_URL = "https://www.pokedata.ovh/standingsVGC/"      # elenco storico: un pulsante per torneo, con id a 7 cifre (0000195)
STORICO_FINO_A = "2025-09-13"                               # dal 13/09/2025 i tornei hanno gia' il nuovo sistema (1000034...): si prendono dal collettore normale
MESI_EN = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
           "september": 9, "october": 10, "november": 11, "december": 12}
RE_PULSANTE = re.compile(r"(?s)<button[^>]+onclick=\"location\.href='(\d{7})/'\"[^>]*>(.*?)</button>")
RE_NOME_DATA = re.compile(r"^(.+?)\s+[-\u2013]\s+([A-Za-z]+\s+\d{1,2}(?:\s*[-\u2013]\s*(?:[A-Za-z]+\s+)?\d{1,2})?\s*,\s*\d{4})$")
RE_DATA_EN = re.compile(r"^([A-Za-z]+)\s+(\d{1,2})(?:\s*[-\u2013]\s*(?:([A-Za-z]+)\s+)?(\d{1,2}))?\s*,\s*(\d{4})$")


def parse_data_en(txt):
    """'February 27-March 1, 2026' -> ('2026-02-27', '2026-03-01'); 'March 7, 2020' -> ('2020-03-07', '2020-03-07'). Altrimenti None."""
    m = RE_DATA_EN.match(" ".join(txt.split()))
    if not m:
        return None
    m1, d1, m2, d2, y = m.groups()
    a, b = MESI_EN.get(m1.lower()), MESI_EN.get((m2 or m1).lower())
    if not a or not b:
        return None
    y = int(y)
    return "%04d-%02d-%02d" % (y, a, int(d1)), "%04d-%02d-%02d" % (y + 1 if b < a else y, b, int(d2 or d1))


def kind_citta_storico(name):
    low = name.lower()
    if "world" in low:
        kind = "World Championship"
    elif "international" in low:
        kind = "International Championships"
    elif "regional" in low:
        kind = "Regional Championships"
    else:
        kind = "Special Championships"
    if "world" in low:
        y = re.search(r"\b(20\d\d)\b", name)
        return "World Championship" + (" " + y.group(1) if y else ""), kind
    n = re.sub(r"^\d{4}\s+", "", name)
    m = re.search(r"Regional Championship\s*[\u2013-]\s*(.+)$", n)           # «Pokemon Oceania VG Regional Championship - Brisbane»
    if m:
        return m.group(1).strip(), kind
    n = re.sub(r"(?i)^pok[eé]mon\s+", "", n)
    n = re.split(r"(?i)\s+(?:pok[eé]mon\s+)?(?:VGC?|VG)\b|\s+Regional|\s+International|\s+World|\s+Championship|\s+\d{4}$", n)[0].strip()
    return (n or name), kind


def list_events_storico(testo=None):
    """Elenco dei vecchi tornei dalla pagina storica di Pokedata (nome, date e id). 1 sola richiesta. Solo quelli prima del nuovo sistema."""
    if testo is None:
        time.sleep(DELAY)
        testo = fetch_text(STORICO_URL)
    out, visti = [], set()
    for tid, grezzo in RE_PULSANTE.findall(testo):
        riga = " ".join(re.sub(r"<[^>]+>", " ", grezzo).replace("&amp;", "&").split())
        m = RE_NOME_DATA.match(riga)
        d = parse_data_en(m.group(2)) if m else None
        if not d or tid in visti or d[0] >= STORICO_FINO_A:
            continue
        visti.add(tid)
        name = m.group(1)
        city, kind = kind_citta_storico(name)
        out.append({"id": tid, "name": name, "city": city, "kind": kind, "start": d[0], "end": d[1], "status": "finished",
                    "players": 0, "decklists": 0, "rounds": 0, "reg": reg_of(d[0]), "winner": None, "rk9": None, "updated": "",
                    "winners": {}, "players_div": {}, "storico": True})
    out.sort(key=lambda e: e["start"], reverse=True)
    return out


def controlla_torneo(ev, info):
    """Per lo storico: Pokedata, se non conosce l'id chiesto, risponde con l'ULTIMO torneo invece di un errore. Si controlla che il torneo
    ricevuto sia davvero quello chiesto, altrimenti ci si ferma prima di salvare qualsiasi cosa."""
    def num(x):
        d = re.sub(r"\D", "", str(x or ""))
        return int(d) if d else None
    ricevuto = num(info.get("id"))
    if ricevuto is None or ricevuto != num(ev["id"]):
        raise Stop("per l'id %s Pokedata ha risposto con un altro torneo (id %s, «%s»): l'id vecchio non si legge con questo indirizzo"
                   % (ev["id"], info.get("id"), info.get("name")))


def storico(write, quanti):
    events = list_events_storico()
    meta_di = lambda e: load(os.path.join(OUT, e["id"], "meta.json"), {})
    fatti = [e for e in events if meta_di(e).get("complete")]
    todo = [e for e in events if not (meta_di(e).get("complete") or meta_di(e).get("skip"))][:quanti]
    print("Tornei nello storico (prima del %s): %d | gia' raccolti: %d | da raccogliere ora: %d" % (STORICO_FINO_A, len(events), len(fatti), len(todo)))
    for e in todo:
        print("-> %s  %s  (%s)" % (e["id"], e["name"], e["start"]))
    try:
        for e in todo:
            try:
                mark(collect(e, write))
            except (Budget, Stop):
                raise
            except Exception as ex:                       # un torneo con dati strani non deve fermare gli altri
                print("SALTO %s (%s): %s" % (e["id"], e["name"], ex))
                if write:
                    dump(os.path.join(OUT, e["id"], "meta.json"), {"id": e["id"], "name": e["name"], "skip": str(ex)[:200], "complete": False})
    except Budget:
        print("Raggiunto il massimo di richieste di questo giro: gli altri al prossimo.")
    if write:
        mark(save_index(events))
    if not write:
        print("\nPROVA finita: non e' stato salvato nulla.")
    return 0


def current_reg(events):
    today = time.strftime("%Y-%m-%d", time.gmtime())
    for e in events:                       # il piu' recente gia' iniziato: decide il regolamento "attuale"
        if e["start"] and e["start"] <= today:
            return e["reg"]
    return events[0]["reg"] if events else None


def save_winners(events):
    """Vincitori di ogni regionale (3 divisioni) con gli italiani in evidenza. Fonte: Pokedata."""
    out = []
    for e in events:
        if e["status"] != "finished":
            continue
        w = e.get("winners") or {}
        it = [{"div": d, "name": p["name"]} for d, p in w.items() if p and p["cc"] == "IT"]
        top = load(os.path.join(OUT, e["id"], "italiani.json"), [])
        out.append({"id": e["id"], "city": e["city"], "kind": e["kind"], "start": e["start"], "reg": e["reg"],
                    "players": e["players"], "winners": w, "italian_winners": it, "italians_top": top})
    return dump_stamped(os.path.join(OUT, "vincitori.json"), {"source": "Pokedata", "source_url": "https://www.pokedata.ovh",
                                                              "updated": time.strftime("%Y-%m-%d %H:%M", time.gmtime()), "events": out})


def save_index(events):
    """Elenco di tutti i regionali + regolamento attuale (si aggiorna da solo quando ne parte uno nuovo)."""
    done = {e["id"] for e in events if load(os.path.join(OUT, e["id"], "meta.json"), {}).get("players")}
    for e in events:
        e["collected"] = e["id"] in done
    a = dump_stamped(os.path.join(OUT, "index.json"), {"current": current_reg(events), "updated": time.strftime("%Y-%m-%d %H:%M", time.gmtime()),
                                                         "source": "Pokedata", "events": [{k: v for k, v in e.items() if k not in ("winners", "players_div", "updated", "forzato", "storico", "fine_forzata")} for e in events]})
    return save_winners(events) or a


def cut_phase(swiss):
    """Top 8 in corso? Nei turni a eliminazione diretta restano in gara 8 giocatori (quarti), poi 4 (semifinali), poi 2 (finale):
    si riconosce contando quanti giocatori hanno almeno N turni. Durante la swiss i numeri sono molto piu' alti."""
    if not swiss:
        return False
    R = max((len(v) for v in swiss.values()), default=0)
    if R < 3:
        return False

    def cnt(r):
        return sum(1 for v in swiss.values() if len(v) >= r)
    n = cnt(R)
    if n == 8:
        return True
    if n == 4:
        return cnt(R - 1) == 8
    if n == 2:
        return cnt(R - 1) == 4 and cnt(R - 2) == 8
    return False


def finale_decisa(swiss):
    """True se la Top 8 e' arrivata alla finale (2 giocatori in gara) e il risultato e' scritto: uno W e uno L."""
    if not swiss or not cut_phase(swiss):
        return False
    R = max((len(v) for v in swiss.values()), default=0)
    fin = [v[-1] for v in swiss.values() if len(v) >= R]
    if len(fin) != 2 or any(not x for x in fin):
        return False
    return sorted(x[-1] for x in fin) == ["L", "W"]


def collect(ev, write):
    tid = ev["id"]
    data = get_json("%s/vg/id/%s/division/masters" % (API, tid))
    info, players, teams, swiss, day1, swiss_total = process(data)
    if ev.get("storico"):
        controlla_torneo(ev, info)
        ev["players"], ev["rounds"] = len(players), swiss_total
        ev["winners"] = {d: person((info.get("winners") or {}).get(d)) for d in ("masters", "seniors", "juniors")}
    names = {m["slug"]: m["name"] for t in teams.values() for m in t}
    for p in players:
        for s in (p["team"] or "").split(","):
            names.setdefault(s, s.replace("-", " ").title())
    stats = compute(players, teams, names)
    status = info.get("tournamentStatus")
    if ev.get("fine_forzata"):
        status = "finished"
    elif ev.get("forzato") and status == "finished":
        status = "running"
    last_status[tid] = status
    cut_state[tid] = cut_phase(swiss)
    cut = sum(p["topcut"] for p in players)
    day2 = sum(p["day2"] for p in players)
    print("\n%s - %s - %s - %d giocatori, %d round" % (ev["name"], info.get("date", {}).get("start"), status, len(players), swiss_total))
    print("Squadre: %d (Top %d) - fase 2 stimata: %d (dopo il round %d) - top cut trovati: %d" % (len(teams), TOP, day2, day1, cut))
    print("%-18s %6s %7s %7s %6s %4s" % ("Pokemon", "Usati", "Vitt.%", "Top256", "Fase2", "Cut"))
    for s in stats[:10]:
        tot = s["wins"] + s["losses"]
        print("%-18s %6d %6.2f%% %7d %6d %4d" % (s["name"][:18], s["count"], 100.0 * s["wins"] / tot if tot else 0, s["top256"], s["day2"], s["cut"]))
    if unknown_forms:
        print("Forme non riconosciute (controlla il paste): %s" % ", ".join(sorted(unknown_forms)))
    unres = sum(1 for e in swiss.values() for x in e if x and x.startswith("-1"))
    print("Scontri senza avversario risolto: %d" % unres)
    if not write:
        return False
    folder = os.path.join(OUT, tid)
    old = load(os.path.join(folder, "meta.json"), {})
    finale_alle = (old.get("finale_alle") or int(time.time())) if finale_decisa(swiss) else None
    global turno_nuovo
    if old.get("rounds") and swiss_total > old["rounds"]:
        turno_nuovo = True
    meta = {"id": tid, "name": ev["name"], "city": ev["city"], "date": ev["start"], "end": ev["end"], "reg": ev["reg"],
            "players": len(players), "rounds": swiss_total, "status": status, "complete": status == "finished", "finale_alle": finale_alle,
            "teams": len(teams), "top": TOP, "day1_rounds": day1, "day2_players": day2, "cut_players": cut, "source": "Pokedata (apiv3), dati RK9",
            "players_fields": ["id", "name", "country", "placement", "wins", "losses", "day2", "cut", "team"],
            "swiss": "per giocatore, una voce per round: id avversario + esito (W vinta, L persa, T pari, B bye; -1 = avversario non risolto)",
            "updated": time.strftime("%Y-%m-%d %H:%M", time.gmtime())}
    pl = [[p["tp_id"], p["name"], p["country"], p["placement"], p["wins"], p["losses"], p["day2"], p["topcut"], p["team"]]
          for p in sorted(players, key=lambda x: x["placement"])]
    tm = {k: [[m["slug"], m["name"], m["item"], m["ability"], m["nature"], m["moves"], m["extra"]] for m in v] for k, v in teams.items()}
    ita = [[p["placement"], p["name"], p["wins"], p["losses"]] for p in sorted(players, key=lambda x: x["placement"])
           if p["country"] == "IT" and p["placement"] <= 32]
    ch = [dump(os.path.join(folder, "italiani.json"), ita), dump(os.path.join(folder, "players.json"), pl),
          dump(os.path.join(folder, "pokemon.json"), stats), dump(os.path.join(folder, "teams.json"), tm),
          dump(os.path.join(folder, "swiss.json"), {"rounds": swiss_total, "p": {str(k): v for k, v in swiss.items()}})]
    # "updated" cambia SOLO se e' cambiato qualcosa in qualsiasi file di questo regionale: l'app controlla solo meta.json
    # (un file minuscolo) e ricarica il resto soltanto quando questa data cambia. Cosi' con tanta gente il carico resta basso.
    if not any(ch) and {k: v for k, v in old.items() if k != "updated"} == {k: v for k, v in meta.items() if k != "updated"}:
        meta["updated"] = old.get("updated", meta["updated"])
    ch.append(dump(os.path.join(folder, "meta.json"), meta))
    print("File salvati in %s/ (%s)" % (folder, "cambiati" if any(ch) else "nessuna modifica"))
    return any(ch)

# ---------- modo live ----------

LIVE_MIN = 3 * 60          # secondi: controlli a intervalli casuali tra 3 e 5 minuti
LIVE_MAX = 5 * 60
LIVE_PAUSA = 10 * 60       # dopo un salvataggio con dati nuovi: nessun controllo per 10 minuti, poi uno subito (misurato al Day 1 di Danzica: ~4 pubblicazioni/ora con 12 minuti)
LIVE_PAUSA_PIENO = 12 * 60  # dal 4° torneo del mese in poi la pausa sale a 12 minuti (per non avvicinarsi al limite di pubblicazioni di Cloudflare)
EVENTI_MESE_PIENO = 4
LIVE_RILANCIO_DA = 292 * 60  # dopo 4 ore e 52 di lavoro: il cambio turno avviene al primo round nuovo (pairings appena usciti); la finestra fino al limite dura 53 minuti, quanto un round
FINALE_ORE = 1             # dopo la finale della Top 8 (risultato scritto) si continua per 1 ora, poi ultimo salvataggio e stop
FINITO_PRESTO_ORE = 3      # Pokedata puo' segnare "finito" un regionale in due fasi mentre il giorno 2 e' ancora da giocare: se lo avevamo visto in corso e i suoi dati sono stati aggiornati da meno di 3 ore, si continua a seguirlo
LIVE_PAUSA_CUT = 5 * 60    # durante la Top 8 (quarti, semifinali, finale): la pausa dopo un salvataggio con dati nuovi e' di 5 minuti
                           # (e' il numero che decide quanto e' "live" il sito: piu' basso = piu' veloce ma piu' pubblicazioni all'ora)
LIVE_MAX_RUN = 345 * 60    # si ferma da solo prima del limite di 355 minuti del flusso
LIVE_GIT_EVERY = 2 * 60 * 60   # con Cloudflare attivo: su GitHub si salva al massimo ogni 2 ore (e alla fine)
GIT_RETRY_AFTER = 15 * 60       # se il salvataggio su GitHub fallisce: nuovo tentativo dopo 15 minuti (non a ogni controllo)
git_block = 0                   # fino a che ora non riprovare dopo un errore


def mark(x):
    global any_changed
    any_changed = any_changed or bool(x)
    return x


def cf_enabled():
    return bool(os.environ.get("CF_PAGES_PROJECT", "").strip() and os.environ.get("CLOUDFLARE_API_TOKEN") and os.environ.get("CLOUDFLARE_ACCOUNT_ID"))


def cf_deploy():
    """Carica la cartella vgcstats/ su Cloudflare Pages con wrangler. True se riuscito; altrimenti si usa GitHub."""
    project = os.environ.get("CF_PAGES_PROJECT", "").strip()
    stage = tempfile.mkdtemp(prefix="vgcs_cf_")
    try:
        if os.path.isdir(OUT):
            shutil.copytree(OUT, stage, dirs_exist_ok=True)
        with open(os.path.join(stage, "_headers"), "w", encoding="utf-8") as f:   # permette all'app di leggere i file da un altro indirizzo
            f.write("/*\n  Access-Control-Allow-Origin: *\n  Cache-Control: public, max-age=0, must-revalidate\n")
        r = subprocess.run(["wrangler", "pages", "deploy", stage, "--project-name", project, "--branch", "main", "--commit-dirty=true"],
                           capture_output=True, text=True, timeout=240)
        if r.returncode == 0:
            print("Dati pubblicati su Cloudflare (%s)." % project)
            return True
        print("Cloudflare non riuscito: %s" % (r.stderr or r.stdout).strip()[-300:])
        return False
    except (OSError, subprocess.SubprocessError) as e:
        print("Cloudflare non riuscito: %s" % str(e)[:200])
        return False
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def cf_test():
    if not cf_enabled():
        print("Cloudflare non e' configurato: servono la variabile CF_PAGES_PROJECT e i segreti CLOUDFLARE_API_TOKEN e CLOUDFLARE_ACCOUNT_ID.")
        return 1
    ok = cf_deploy()
    if ok:
        print("Prova riuscita. Apri https://%s.pages.dev/index.json per vedere i dati." % os.environ.get("CF_PAGES_PROJECT", "").strip())
    return 0 if ok else 1


def publish(changed, commit, final, now=time.time):
    """Pubblica i dati: Cloudflare a ogni salvataggio nuovo (se attivo), GitHub subito o ogni 2 ore se Cloudflare ha funzionato."""
    global last_git, git_block
    cf_ok = bool(changed and cf_enabled() and cf_deploy())
    if not commit:
        return
    if cf_ok and not final and not unpushed and last_git is not None and now() - last_git < LIVE_GIT_EVERY:
        print("Dati gia' online su Cloudflare: il salvataggio su GitHub puo' attendere.")
        return
    if unpushed and not final and now() < git_block:
        print("Salvataggio su GitHub in pausa dopo l'errore: riprovo piu' tardi (i dati sono comunque online).")
        return
    ok = git_publish()
    last_git = now()
    git_block = now() + GIT_RETRY_AFTER if ok is False else 0


def _gitout(r):
    return ((r.stderr or "") + " " + (r.stdout or "")).strip().replace("\n", " | ")[:260]


def git_reapply(run, message):
    """Ultima risorsa: si scarica la versione attuale del repo e si rimettono sopra i file dei dati
    (il bot e' l'unico che li scrive; gli altri file del repo restano come li hai caricati tu). Ritorna True o il motivo dell'errore."""
    tmp = tempfile.mkdtemp()
    try:
        b = run("git", "symbolic-ref", "--short", "HEAD")
        br = b.stdout.strip()
        if b.returncode != 0 or not br:
            return "ramo non trovato"
        shutil.copytree(OUT, os.path.join(tmp, "d"))
        f = run("git", "fetch", "origin", br)
        if f.returncode != 0:
            return "fetch: " + _gitout(f)
        run("git", "rebase", "--abort")
        r = run("git", "reset", "--hard", "FETCH_HEAD")
        if r.returncode != 0:
            return "reset: " + _gitout(r)
        shutil.copytree(os.path.join(tmp, "d"), OUT, dirs_exist_ok=True)
        run("git", "add", "-A", OUT)
        if run("git", "diff", "--staged", "--quiet").returncode != 0:
            c = run("git", "commit", "-m", message)
            if c.returncode != 0:
                return "commit: " + _gitout(c)
        q = run("git", "push")
        return True if q.returncode == 0 else "push: " + _gitout(q)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def git_publish(message="VGC Stats: aggiornamento dati (live)"):
    """Salva e pubblica la cartella vgcstats/ con git. Se il repo e' cambiato nel frattempo (per esempio hai caricato dei file),
    si riallinea da solo; se non riesce, stampa il motivo e riprova piu' tardi."""
    global unpushed

    def run(*cmd):
        return subprocess.run(cmd, capture_output=True, text=True)
    run("git", "config", "user.name", "bot")
    run("git", "config", "user.email", "bot@users.noreply.github.com")
    run("git", "add", "-A", OUT)
    if run("git", "diff", "--staged", "--quiet").returncode != 0:
        c = run("git", "commit", "-m", message)
        if c.returncode != 0:
            print("Salvataggio git non riuscito: %s" % _gitout(c)[:200])
            return False
        unpushed = True
    if not unpushed:
        return True
    last = ""
    for _ in range(3):
        p = run("git", "pull", "--rebase", "--autostash", "-X", "theirs")
        if p.returncode == 0:
            q = run("git", "push")
            if q.returncode == 0:
                unpushed = False
                print("Dati pubblicati.")
                return True
            last = "push: " + _gitout(q)
        else:
            last = "pull: " + _gitout(p)
            run("git", "rebase", "--abort")
        r = git_reapply(run, message)
        if r is True:
            unpushed = False
            print("Dati pubblicati (dopo aver riallineato il repo).")
            return True
        last += " || riallineamento: " + str(r)
        time.sleep(5)
    print("Pubblicazione non riuscita (%s)." % last[:420])
    return False


def recent_unfinished(events, days=3, limit=2):
    """Regionali finiti da poco e non ancora raccolti per intero: servono per l'ultimo salvataggio."""
    lim = time.strftime("%Y-%m-%d", time.gmtime(time.time() - days * 86400))
    out = [e for e in events if e["status"] == "finished" and e["players"] and (e["end"] or e["start"] or "9999-12-31") >= lim
           and not load(os.path.join(OUT, e["id"], "meta.json"), {}).get("complete")]
    return out[:limit]


def parse_utc(txt):
    """'2026-11-01 08:36:44' (ora UTC, come la scrive Pokedata) -> secondi, oppure None."""
    try:
        return calendar.timegm(time.strptime(txt[:19], "%Y-%m-%d %H:%M:%S"))
    except (ValueError, TypeError):
        return None


def ancora_vivo(e, t=None):
    """Pokedata dice 'finito', ma lo avevamo visto in corso, non e' stato completato e i dati si muovono ancora: di solito e' la
    pausa tra i due giorni o la fase 2. Conta l'ultimo cambiamento dei NOSTRI dati (meta.updated) oppure l'orario di Pokedata
    (che pero' viene scritto una volta sola, quando segna 'finito', quindi da solo non basta). Si continua a seguirlo."""
    if e.get("status") != "finished":
        return False
    meta = load(os.path.join(OUT, e["id"], "meta.json"), {})
    if meta.get("status") != "running" or meta.get("complete"):
        return False
    t = time.time() if t is None else t
    for txt in (e.get("updated") or "", (meta.get("updated") or "")[:16] + ":00" if meta.get("updated") else ""):
        ts = parse_utc(txt)
        if ts is not None and -600 <= t - ts < FINITO_PRESTO_ORE * 3600:
            return True
    return False


def eventi_forzati(t=None):
    """Id dei regionali da considerare 'in corso' a mano: file forza_live.txt nella radice del repo, una riga per torneo:
    id [ultimo giorno AAAA-MM-GG in UTC]   (le righe con # o gia' scadute sono ignorate)."""
    oggi = time.strftime("%Y-%m-%d", time.gmtime(t if t is not None else time.time()))
    out = set()
    try:
        with open(os.environ.get("VGC_FORZA_FILE") or "forza_live.txt") as f:
            for riga in f:
                parti = riga.split("#")[0].split()
                if parti and not (len(parti) > 1 and parti[1] < oggi):
                    out.add(parti[0])
    except OSError:
        pass
    return out


def eventi_del_mese(events, t=None):
    """Quanti tornei sono iniziati nel mese in corso (UTC), compreso quello in corso (che puo' non avere ancora la data)."""
    g = time.gmtime(t if t is not None else time.time())
    mese, oggi = "%04d-%02d" % (g.tm_year, g.tm_mon), time.strftime("%Y-%m-%d", g)
    n = 0
    for e in events:
        st = (e.get("start") or "")[:10]
        if st and st[:7] == mese and st <= oggi:
            n += 1
        elif not st and e.get("status") == "running":
            n += 1
    return n


def live_cycle(write):
    """Un controllo. Ritorna (dati_cambiati, ancora_in_corso)."""
    global used, cut_active, mese_pieno, turno_nuovo
    turno_nuovo = False
    used = 0                                   # il limite di richieste vale per ogni controllo
    events = list_events()
    pieno = eventi_del_mese(events) >= EVENTI_MESE_PIENO
    if pieno != mese_pieno:
        mese_pieno = pieno
        if pieno:
            print("Tornei di questo mese: %d. La pausa sale a %d minuti per non avvicinarsi al limite di Cloudflare." % (eventi_del_mese(events), LIVE_PAUSA_PIENO // 60))
    forzati = eventi_forzati()
    for e in events:
        meta_e = load(os.path.join(OUT, e["id"], "meta.json"), {})
        fa = meta_e.get("finale_alle")
        if fa and time.time() - fa >= FINALE_ORE * 3600:
            e["status"] = "finished"
            e["fine_forzata"] = True
            if not meta_e.get("complete") and e["id"] not in fine_avvisati:
                fine_avvisati.add(e["id"])
                print("La finale della Top 8 di %s e' finita da piu' di %d ora: ultimo salvataggio e poi mi fermo." % (e["name"], FINALE_ORE))
        elif e["id"] in forzati:
            e["status"] = "running"
            e["forzato"] = True
            if e["id"] not in avvisati:
                avvisati.add(e["id"])
                print("%s tenuto in corso a mano (file forza_live.txt): lo seguo fino alla finale della Top 8 o alla data scritta nel file." % e["name"])
        elif ancora_vivo(e):
            e["status"] = "running"
            e["forzato"] = True
            if e["id"] not in avvisati:
                avvisati.add(e["id"])
                print("Pokedata segna «finito» %s, ma i dati sono stati aggiornati da meno di %d ore: continuo a seguirlo." % (e["name"], FINITO_PRESTO_ORE))
    running = [e for e in events if e["status"] == "running"]
    todo = running + [e for e in recent_unfinished(events) if e not in running]
    if not todo:
        print("Nessun regionale in corso e niente da completare.")
        return False, False
    changed = False
    ended = False
    try:
        for e in todo:
            if collect(e, write):
                changed = True
            st = last_status.get(e["id"])
            if st and st != e["status"]:
                ended = ended or st == "finished"
                e["status"] = st
        if ended:                              # appena finito: elenco aggiornato (vincitori) per l'ultimo salvataggio
            events = list_events()
    except Budget:
        print("Raggiunto il massimo di richieste di questo controllo: il resto al prossimo.")
    if write and save_index(events):
        changed = True
    cut_active = any(e["status"] == "running" and cut_state.get(e["id"]) for e in events)
    return changed, any(e["status"] == "running" for e in events)


def segnala_rilancio():
    """Il tempo del lavoro sta per finire ma il torneo continua: lascia un segno e il flusso lancia subito il turno dopo,
    senza aspettare il programma di GitHub (che puo' ritardare anche di mezz'ora o saltare un giro)."""
    nome = os.environ.get("VGC_RILANCIA_FILE") or (".vgc_rilancia" if os.environ.get("GITHUB_ACTIONS") == "true" else "")
    if nome:
        try:
            with open(nome, "w") as f:
                f.write("1")
        except OSError:
            pass


def live(write, commit, max_cycles=0, max_run=LIVE_MAX_RUN, now=time.time, sleep=time.sleep, rnd=random.uniform):
    t0 = now()
    n = 0
    guasti = 0                                 # controlli di fila falliti per un problema di rete
    while True:
        n += 1
        stop = None
        try:
            changed, going = live_cycle(write)
            guasti = 0
        except Stop as e:
            stop, changed, going = e, False, False
        except (OSError, ValueError) as e:       # rete, tempo scaduto, risposta illeggibile: si riprova al giro dopo
            guasti += 1
            print("Controllo %d non riuscito (%s). Tentativo %d di 4." % (n, str(e)[:120], guasti))
            if guasti >= 4:
                print("Troppi errori di fila: mi fermo, riparte il prossimo giro programmato.")
                return 1
            if max_cycles and n >= max_cycles:
                return 1
            wait = rnd(LIVE_MIN, LIVE_MAX)
            if now() - t0 + wait > max_run:
                print("Limite di tempo quasi raggiunto: mi fermo e lancio subito il turno successivo.")
                segnala_rilancio()
                return 0
            sleep(wait)
            continue
        final = bool(stop) or not going or bool(max_cycles and n >= max_cycles)
        if write and (changed or unpushed or stop):
            publish(changed, commit, final, now)
        if stop:
            print("STOP: %s - mi fermo qui" % stop)
            return 1
        if not going:
            print("Nessun regionale in corso: mi fermo.")
            return 0
        if max_cycles and n >= max_cycles:
            return 0
        if write and turno_nuovo and now() - t0 >= LIVE_RILANCIO_DA:
            print("Round nuovo appena iniziato dopo %d minuti di lavoro: cambio turno adesso, i primi risultati arrivano tra almeno 20 minuti." % ((now() - t0) // 60))
            if commit and cf_enabled():
                git_publish()
            segnala_rilancio()
            return 0
        pausa = LIVE_PAUSA_PIENO if mese_pieno else LIVE_PAUSA
        wait = (LIVE_PAUSA_CUT if cut_active else pausa) if (write and changed) else rnd(LIVE_MIN, LIVE_MAX)
        if now() - t0 + wait > max_run:
            print("Limite di tempo quasi raggiunto: mi fermo e lancio subito il turno successivo.")
            if write and commit and cf_enabled():
                git_publish()
            segnala_rilancio()
            return 0
        print("Controllo %d fatto%s. Prossimo tra %.0f minuti." % (n, (" (dati nuovi salvati)" if (write and changed) else "") + (" - Top 8 in corso" if cut_active else ""), wait / 60.0))
        sleep(wait)


def main():
    global budget
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true", help="elenco di tutti i regionali")
    g.add_argument("--id", help="id Pokedata del regionale, es. 1000076")
    g.add_argument("--auto", action="store_true", help="regionali in corso + finiti non ancora raccolti")
    g.add_argument("--live", action="store_true", help="controlli ripetuti finche' un regionale e' in corso")
    g.add_argument("--storico", action="store_true", help="vecchi tornei (prima di settembre 2025) dalla pagina storica di Pokedata")
    g.add_argument("--cf-test", action="store_true", help="prova di Cloudflare: carica i dati gia' presenti")
    ap.add_argument("--write", action="store_true", help="salva i file in vgcstats/ (senza: prova senza salvare nulla)")
    ap.add_argument("--commit", action="store_true", help="con --live --write: pubblica i dati con git dopo ogni salvataggio")
    ap.add_argument("--max-cycles", type=int, default=0, help="con --live: massimo numero di controlli (0 = senza limite)")
    ap.add_argument("--max-events", type=int, default=2, help="con --auto: quanti regionali finiti non raccolti per giro")
    a = ap.parse_args()
    budget = int(os.environ.get("VGC_BUDGET", "6"))
    print("Versione del collettore: 2026-11-02t STORICO con controllo del torneo ricevuto (mette da solo la data di partenza se Pokedata non la da' (file date_manuali.json per le eccezioni), rilancio automatico: cambio turno al primo round nuovo dopo 4 ore e 52, segue il regionale anche se Pokedata lo segna «finito» troppo presto o se scrivi il suo id in forza_live.txt, si ferma 1 ora dopo la finale della Top 8, salvataggio su GitHub robusto, pausa 10 minuti (12 dal 4° torneo del mese), Top 8 ogni 5 minuti)")
    print("%s - massimo %d richieste" % ("SALVATAGGIO" if a.write else "PROVA (non salva nulla)", budget))
    try:
        if a.cf_test:
            return cf_test()
        if a.storico:
            return storico(a.write, a.max_events)
        if a.live:
            return live(a.write, a.commit, a.max_cycles)
        if a.list or a.auto:
            events = list_events()
            print("Regionali trovati: %d - regolamento attuale: %s" % (len(events), current_reg(events)))
            for e in events[:8]:
                m = (e.get("winners") or {}).get("masters")
                print("  %s  %-22s %-9s %5d giocatori  %-5s vincitore: %s%s" % (e["start"], e["city"][:22], e["status"], e["players"], e["reg"],
                      m["name"] if m else "-", " [ITALIA]" if m and m["cc"] == "IT" else ""))
            if a.list:
                if a.write:
                    print("Elenco salvato." if mark(save_index(events)) else "Elenco invariato.")
                return 0
            todo = [e for e in events if e["status"] == "running"]
            todo += [e for e in events if e["status"] == "finished" and e["players"]
                     and not load(os.path.join(OUT, e["id"], "meta.json"), {}).get("complete")][:a.max_events]
            print("Da raccogliere ora: %s" % (", ".join(e["city"] for e in todo) or "niente"))
            for e in todo:
                mark(collect(e, a.write))
            if a.write:
                mark(save_index(events))
            return 0
        events = list_events()
        ev = next((e for e in events if e["id"] == a.id), None)
        if not ev:
            print("Regionale %s non trovato nell'elenco di Pokedata." % a.id)
            return 1
        mark(collect(ev, a.write))
        if a.write:
            mark(save_index(events))
        if not a.write:
            print("\nPROVA finita: non e' stato salvato nulla.")
        return 0
    except Budget:
        print("Raggiunto il massimo di richieste: rilancia.")
        return 0
    except Stop as e:
        print("STOP: %s - mi fermo qui" % e)
        return 1
    finally:
        if a.write and any_changed and cf_enabled():     # giro normale che ha salvato: Cloudflare non deve restare indietro
            cf_deploy()


if __name__ == "__main__":
    sys.exit(main())
