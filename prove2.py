#!/usr/bin/env python3
"""Seconda prova di SOLA LETTURA (non salva nessun file): 9 richieste in tutto, lente (8-15 secondi tra una e l'altra).
Serve a vedere i pezzi di pagina che mancano per scrivere i collettori veri:
  A) Pokedata: com'e' fatta la pagina storica e se i vecchi tornei (id piccoli) rispondono;
  B) Victory Road: abbinamenti, dettaglio dei round di un giocatore e calendario;
  C) Limitless: elenco tornei con la paginazione e l'intestazione di un torneo.
Identificazione onesta e senza dati personali."""
import html as _html
import json
import random
import re
import sys
import time
import urllib.error
import urllib.request

UA = "tornei-vgc-bot (sito della community, con link alle fonti)"
PK = "https://www.pokedata.ovh"
VR = "https://circuit.victoryroad.pro"
LM = "https://limitlessvgc.com"


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


def titolo(t):
    print("\n" + "=" * 60 + "\n" + t + "\n" + "=" * 60, flush=True)


def pulisci(h):
    h = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    return " ".join(_html.unescape(h).split())


def pezzo(pagina, ago, prima=300, dopo=1500, occorrenza=1, regex=False):
    """Ritorna un pezzo GREZZO della pagina attorno alla n-esima occorrenza di 'ago' (o un messaggio se non c'e')."""
    it = list(re.finditer(ago, pagina)) if regex else list(re.finditer(re.escape(ago), pagina))
    if len(it) < occorrenza:
        return "(non trovato: %r, occorrenze %d)" % (ago, len(it))
    i = it[occorrenza - 1].start()
    return pagina[max(0, i - prima): i + dopo]


def json_riassunto(txt):
    i = txt.find("{")
    if i < 0:
        return "(non e' JSON) " + txt[:200]
    try:
        j = json.loads(txt[i:])
    except ValueError as e:
        return "(JSON non valido: %s)" % e
    out = ["chiavi in cima: %s" % ", ".join(list(j.keys())[:8])]
    for k, v in j.items():
        if isinstance(v, dict):
            d = v.get("data") if isinstance(v.get("data"), list) else None
            if d is not None:
                ids = [str(x.get("id")) for x in d if isinstance(x, dict)]
                date = sorted(((x.get("date") or {}).get("start") or "") for x in d if isinstance(x, dict))
                date = [x for x in date if x]
                out.append("  %s.data: %d voci | id da %s a %s | date da %s a %s" % (
                    k, len(d), min(ids) if ids else "-", max(ids) if ids else "-", date[0] if date else "-", date[-1] if date else "-"))
            else:
                out.append("  %s: dizionario con chiavi %s" % (k, ", ".join(list(v.keys())[:6])))
        elif isinstance(v, list):
            out.append("  %s: lista di %d" % (k, len(v)))
    return "\n".join(out)


def sezione_pokedata():
    titolo("A. POKEDATA")
    st, pag = scarica(PK + "/standingsVGC")
    print("pagina storica: risposta %s, %d byte" % (st, len(pag)))
    if st == 200:
        for nome in ("onclick=", "data-id=", "data-url=", "<option", "<li", "href=\"/standings", "<a "):
            print("  %-22s compare %d volte" % (nome, pag.count(nome)))
        print("\nPezzo GREZZO attorno a «Louisville» (un torneo recente):")
        print(pezzo(pag, "Louisville", 500, 1100))
        print("\nPezzo GREZZO attorno a «Toronto Pok» (un torneo piu' vecchio, dal 2023):")
        print(pezzo(pag, "Malmo VG Regionals", 500, 900))
    for percorso in ("/apiv3/tournaments", "/apiv3/tournaments/vg", "/apiv3/vg/id/100/division/masters"):
        pausa()
        st, txt = scarica(PK + percorso)
        print("\n%s -> risposta %s, %d byte" % (percorso, st, len(txt)))
        if st == 200:
            print(json_riassunto(txt))


def sezione_vr():
    titolo("B. VICTORY ROAD")
    st, pag = scarica(VR + "/tournament/vr-oct26-4/pairings")
    print("abbinamenti: risposta %s, %d byte" % (st, len(pag)))
    if st == 200:
        print("\nPezzo GREZZO della sezione «Round 1» nel corpo della pagina:")
        print(pezzo(pag, r"(?i)<h[1-6][^>]*>\s*Round 1\b", 200, 1800, regex=True) if re.search(r"(?i)<h[1-6][^>]*>\s*Round 1\b", pag) else pezzo(pag, "Round 1", 300, 1800, occorrenza=3))
        print("\nPezzo GREZZO attorno a «Top cut» (tabellone):")
        print(pezzo(pag, "Top cut", 200, 1500, occorrenza=3))
    pausa()
    st, pag = scarica(VR + "/tournament/vr-oct26-4")
    print("\nclassifica (di nuovo): risposta %s, %d byte" % (st, len(pag)))
    if st == 200:
        fine = pag.find("</tr>", pag.find('class="es-cut tiene-detalle"'))
        print("\nPezzo GREZZO subito DOPO la riga del primo giocatore (il dettaglio dei suoi round):")
        print(pag[fine: fine + 2200])
    pausa()
    st, pag = scarica(VR + "/")
    print("\ncalendario: risposta %s, %d byte" % (st, len(pag)))
    if st == 200:
        print("\nPezzo GREZZO attorno a «VR October Challenge #4» nel calendario:")
        print(pezzo(pag, "VR October Challenge #4", 700, 1300))


def sezione_limitless():
    titolo("C. LIMITLESS")
    st, pag = scarica(LM + "/tournaments")
    print("elenco tornei: risposta %s, %d byte" % (st, len(pag)))
    if st == 200:
        print("\nPezzo GREZZO attorno alla paginazione («page=»):")
        print(pezzo(pag, "page=", 400, 900))
        print("\nPezzo GREZZO della riga del torneo 448 nell'elenco:")
        print(pezzo(pag, "/tournaments/448", 500, 900))
    pausa()
    st, pag = scarica(LM + "/tournaments/448")
    print("\ntorneo 448: risposta %s, %d byte" % (st, len(pag)))
    if st == 200:
        print("\nPezzo GREZZO dell'intestazione del torneo (titolo, data, numero giocatori):")
        print(pezzo(pag, "758", 700, 900))
        print("\nLink «Roster / Results / Pairings» del torneo:")
        print(pezzo(pag, "Roster", 300, 500))


def main():
    print("SECONDA PROVA di sola lettura - 9 richieste, lente")
    sezione_pokedata()
    pausa()
    sezione_vr()
    pausa()
    sezione_limitless()
    print("\nFine. Non e' stato salvato nessun file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
