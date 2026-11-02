"""Lettura delle pagine del VR Circuit (circuit.victoryroad.pro): classifica e abbinamenti di un torneo, e conversione nel formato
che il collettore dei regionali gia' conosce. Sono funzioni pure (niente rete), cosi' si possono provare con pagine salvate."""
import html as _html
import re
from html.parser import HTMLParser

VOID = {"img", "br", "input", "link", "meta", "hr", "source", "wbr", "col", "area", "base", "embed", "param", "track"}


class Nodo:
    __slots__ = ("tag", "attrs", "figli", "padre")

    def __init__(self, tag, attrs=None, padre=None):
        self.tag, self.attrs, self.figli, self.padre = tag, attrs or {}, [], padre

    def classi(self):
        return (self.attrs.get("class") or "").split()


class _Costruttore(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.radice = Nodo("#radice")
        self.cur = self.radice
        self.salta = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.salta += 1
            return
        n = Nodo(tag, {k: (v or "") for k, v in attrs}, self.cur)
        self.cur.figli.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        if tag in ("script", "style"):
            return
        self.cur.figli.append(Nodo(tag, {k: (v or "") for k, v in attrs}, self.cur))

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.salta = max(0, self.salta - 1)
            return
        n = self.cur
        while n is not None and n.tag != tag:
            n = n.padre
        if n is not None and n.padre is not None:
            self.cur = n.padre

    def handle_data(self, data):
        if not self.salta and data:
            self.cur.figli.append(data)


def albero(testo):
    c = _Costruttore()
    c.feed(testo)
    c.close()
    return c.radice


def trova(nodo, tag=None, classe=None):
    out = []
    stack = [nodo]
    while stack:
        n = stack.pop()
        for f in reversed([x for x in n.figli if isinstance(x, Nodo)]):
            stack.append(f)
        if n is not nodo and (tag is None or n.tag == tag) and (classe is None or classe in n.classi()):
            out.append(n)
    return out


def _ordine(nodo):
    """Stessa lista di trova(), ma in ordine di comparsa nella pagina."""
    out = []

    def giu(n):
        for f in n.figli:
            if isinstance(f, Nodo):
                out.append(f)
                giu(f)
    giu(nodo)
    return out


def trova_ord(nodo, tag=None, classe=None):
    return [n for n in _ordine(nodo) if (tag is None or n.tag == tag) and (classe is None or classe in n.classi())]


def testo(nodo):
    parti = []

    def giu(n):
        for f in n.figli:
            if isinstance(f, str):
                parti.append(f)
            else:
                giu(f)
    giu(nodo)
    return " ".join(" ".join(parti).split())


def testo_diretto(nodo):
    return " ".join(" ".join(f for f in nodo.figli if isinstance(f, str)).split())


def primo(nodo, tag=None, classe=None):
    r = trova_ord(nodo, tag, classe)
    return r[0] if r else None


# ---------------------------------------------------------------- classifica

def _record(t):
    m = re.match(r"^\s*(\d+)\s*[\u2013\u2014-]\s*(\d+)(?:\s*[\u2013\u2014-]\s*(\d+))?\s*$", t or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)) if m else (0, 0, 0)


def _slug_img(src):
    m = re.search(r"/pokemons/([^/?#]+?)\.(?:webp|png|jpg)", src or "")
    return m.group(1) if m else ""


def nome_dal_slug(slug):
    """'raichu-mega-x' -> 'Raichu-Mega-X' (il nome della specie nel file delle squadre)."""
    return "-".join(p.capitalize() if not p.isdigit() else p for p in slug.split("-"))


def leggi_classifica(pagina):
    """Ritorna (giocatori, meta). Ogni giocatore: id, pos, name, cc, country, w, l, t, cut, team=[{name, slug, item}], team_url."""
    radice = albero(pagina)
    giocatori = []
    for tr in trova_ord(radice, "tr"):
        if "data-id" not in tr.attrs:
            continue
        td_pos, td_rec = primo(tr, "td", "c-pos"), primo(tr, "td", "c-rec")
        jug = primo(tr, "span", "jug")
        if not (td_pos and jug):
            continue
        try:
            pos = int(testo(td_pos))
        except ValueError:
            continue
        pais = primo(tr, "span", "jug-pais")
        flag = primo(pais, "img") if pais else None
        w, l, t = _record(testo(td_rec) if td_rec else "")
        team = []
        for slot in trova_ord(tr, "span", "mon-slot"):
            tit = slot.attrs.get("title", "")
            nm, _, item = tit.partition(" @ ")
            im = primo(slot, "img", "mon")
            sl = _slug_img(im.attrs.get("src", "")) if im else ""
            team.append({"name": nm.strip(), "slug": sl, "item": item.strip()})
        a = primo(tr, "a", "team")
        giocatori.append({"id": tr.attrs.get("data-id", ""), "pos": pos, "name": testo_diretto(jug), "cc": (tr.attrs.get("data-c") or "").upper(),
                          "country": flag.attrs.get("title", "") if flag else "", "w": w, "l": l, "t": t,
                          "cut": tr.attrs.get("data-cut") == "1", "team": team, "team_url": a.attrs.get("href", "") if a else ""})
    plain = testo(radice)
    meta = {}
    t = primo(radice, "title")
    meta["titolo"] = testo(t) if t else ""
    for chiave, rx in (("giocatori", r"(\d[\d,.]*)\s+Players"), ("paesi", r"(\d+)\s+Countries"), ("swiss", r"(\d+)\s+Swiss rounds"), ("cut", r"(\d+)\s+Top cut")):
        m = re.search(rx, plain)
        meta[chiave] = int(re.sub(r"\D", "", m.group(1))) if m else None
    m = re.search(r"Updated[^|]{0,60}?\(\w+ time\)", plain)
    meta["aggiornato"] = m.group(0) if m else ""
    return giocatori, meta


# --------------------------------------------------------------- abbinamenti

def _esito(n):
    c = n.classi()
    return True if "gana" in c else False if "pierde" in c else None


def leggi_abbinamenti(pagina):
    """Ritorna (round, cut): round = {numero: [{tavolo, j:[{name, win}]}]}; cut = {colonna: [{bye, j:[{name, win}], riga}]}, piu' le etichette."""
    radice = albero(pagina)
    rounds, cut, etichette = {}, {}, {}
    for sec in trova_ord(radice, "section", "rd-sec"):
        dr = sec.attrs.get("data-ronda", "")
        if dr.isdigit():
            pares = []
            for par in trova_ord(sec, "div", "par"):
                n = primo(par, "span", "par-n")
                try:
                    tav = int(testo(n)) if n else None
                except ValueError:
                    tav = None
                js = []
                for pj in trova_ord(par, "div", "pj"):
                    nm = primo(pj, "span", "pj-nombre")
                    if nm and testo(nm):
                        js.append({"name": testo(nm), "win": _esito(pj)})
                if js:
                    pares.append({"tavolo": tav, "j": js})
            rounds[int(dr)] = pares
        elif dr == "top-cut":
            for cab in trova_ord(sec, "div", "cq-cab"):
                m = re.search(r"grid-column:\s*(\d+)", cab.attrs.get("style", ""))
                if m:
                    etichette[int(m.group(1))] = testo(cab)
            for slot in trova_ord(sec, "div", "cq-slot"):
                st = slot.attrs.get("style", "")
                mc, mr = re.search(r"grid-column:\s*(\d+)", st), re.search(r"grid-row:\s*(\d+)", st)
                if not mc:
                    continue
                for m in trova_ord(slot, "div", "cq-m"):
                    js = []
                    for j in trova_ord(m, "div", "cq-j"):
                        nm = primo(j, "span", "cq-nombre")
                        if nm and testo(nm):
                            js.append({"name": testo(nm), "win": _esito(j)})
                    cut.setdefault(int(mc.group(1)), []).append({"bye": "cq-bye" in m.classi(), "j": js, "riga": int(mr.group(1)) if mr else 0})
    for c in cut:
        cut[c].sort(key=lambda x: x["riga"])
    return rounds, cut, etichette


def finale_decisa(cut):
    """La finale e' l'ultima colonna del tabellone: decisa quando ha due giocatori e uno e' segnato vincitore."""
    if not cut:
        return False
    ultima = cut[max(cut)]
    return any(len(m["j"]) == 2 and any(x["win"] for x in m["j"]) for m in ultima)


# --------------------------------------------------------------- conversione

def _chiave(s):
    return " ".join(str(s).split()).lower()


def _res(w):
    return 3 if w is True else 0 if w is False else None


def converti(giocatori, rounds, cut, ev, finito=False):
    """Mette giocatori, round e tabellone nella forma del JSON dei regionali (cosi' process() fa il resto)."""
    idx, doppi = {}, set()
    for i, g in enumerate(giocatori):
        k = _chiave(g["name"])
        if k in idx:
            doppi.add(k)
        idx.setdefault(k, i)
    raw = []
    for g in giocatori:
        raw.append({"name": "%s [%s]" % (g["name"], g["cc"]) if g["cc"] else g["name"], "placing": g["pos"],
                    "record": {"wins": g["w"], "losses": g["l"], "ties": g["t"]}, "rounds": {},
                    "teamlist": [{"name": nome_dal_slug(t["slug"]) if t["slug"] else t["name"], "item": t["item"]} for t in g["team"]]})

    def metti(round_n, tavolo, j):
        if len(j) == 1:
            i = idx.get(_chiave(j[0]["name"]))
            if i is not None:
                raw[i]["rounds"][str(round_n)] = {"name": "BYE", "result": 3, "table": None}
            return
        if len(j) != 2:
            return
        a, b = j
        for x, y in ((a, b), (b, a)):
            i = idx.get(_chiave(x["name"]))
            if i is not None and _chiave(x["name"]) not in doppi:
                raw[i]["rounds"][str(round_n)] = {"name": y["name"], "result": _res(x["win"]), "table": tavolo}

    n_swiss = max(rounds) if rounds else 0
    for n, pares in rounds.items():
        for par in pares:
            metti(n, par["tavolo"], par["j"])
    for k, col in enumerate(sorted(cut), start=1):
        for t, m in enumerate(cut[col], start=1):
            metti(n_swiss + k, t, m["j"])
    totale = n_swiss + len(cut)
    vincitore = next((p["name"] for p in raw if p["placing"] == 1), None) if finito else None
    return {"tournament": {"id": ev["id"], "name": ev["name"], "date": {"start": ev.get("start", ""), "end": ev.get("end", "")},
                           "tournamentStatus": "finished" if finito else "running", "roundNumbers": {"masters": totale},
                           "winners": {"masters": vincitore}},
            "tournament_data": [{"division": "masters", "data": raw}]}, sorted(doppi)
