#!/usr/bin/env python3
"""Esplorazione di Pokedata - SOLO LETTURA.
Non salva nessun file e fa pochissime richieste (circa 8, con 2 secondi di pausa tra una e l'altra).
Serve a capire quali vecchi regionali esistono e se si possono leggere con lo stesso metodo del collettore.
Il risultato e' il log di questa esecuzione: copialo o fai una foto e mandalo a Claude."""
import json
import re
import time
import urllib.error
import urllib.request

UA = "tornei-vgc-bot (sito della community, con link alle fonti)"
BASE = "https://www.pokedata.ovh"
API = BASE + "/apiv3"
PAUSA = 2.0


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # rete, tempo scaduto, ecc.
        return 0, str(e)


def pulisci(html):
    html = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html).strip()


def attendi():
    time.sleep(PAUSA)


def sezione(titolo):
    print("\n" + "=" * 60)
    print(titolo)
    print("=" * 60, flush=True)


def elenco_api():
    sezione("1. Elenco dell'API (/vg/tournaments/)")
    st, txt = get(API + "/vg/tournaments/")
    print("risposta:", st, "| byte:", len(txt))
    try:
        data = json.loads(txt)["vg"]["data"]
    except Exception as e:
        print("non riesco a leggere l'elenco:", e)
        return []
    out = []
    for t in data:
        d = t.get("date") or {}
        out.append({"id": str(t.get("id")), "name": t.get("name") or "", "start": d.get("start") or "",
                    "status": t.get("tournamentStatus") or ""})
    out.sort(key=lambda e: e["start"])
    print("tornei nell'elenco:", len(out))
    if out:
        print("data piu' vecchia:", out[0]["start"], "| piu' recente:", out[-1]["start"])
        anni = {}
        for e in out:
            anni[e["start"][:4]] = anni.get(e["start"][:4], 0) + 1
        print("per anno:", dict(sorted(anni.items())))
        print("i 3 piu' vecchi:")
        for e in out[:3]:
            print("  id %s | %s | %s | %s" % (e["id"], e["start"], e["status"], e["name"]))
        ids = [e["id"] for e in out]
        print("id: da", min(ids), "a", max(ids))
    return out


def documentazione():
    sezione("2. Documentazione dell'API (/apiv3/help)")
    st, txt = get(API + "/help")
    print("risposta:", st, "| byte:", len(txt))
    if st == 200:
        t = pulisci(txt)
        print(t[:3500])
        if len(t) > 3500:
            print("... (testo tagliato: in tutto %d caratteri)" % len(t))


def pagina_elenco():
    sezione("3. Pagina con l'elenco storico (/standingsVGC)")
    st, txt = get(BASE + "/standingsVGC")
    print("risposta:", st, "| byte:", len(txt))
    if st != 200:
        return []
    links = re.findall(r'(?is)<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', txt)
    links = [(h.strip(), pulisci(t)) for h, t in links]
    torn = [(h, t) for h, t in links if re.search(r"(20\d\d|19\d\d)", t) and len(t) > 12]
    print("link in tutto:", len(links), "| link che sembrano tornei:", len(torn))
    print("primi 6:")
    for h, t in torn[:6]:
        print("  %s  ->  %s" % (t[:70], h))
    print("ultimi 6:")
    for h, t in torn[-6:]:
        print("  %s  ->  %s" % (t[:70], h))
    return torn


def prova_id(api_id, etichetta):
    st, txt = get("%s/vg/id/%s/division/masters" % (API, api_id))
    riga = "  %s | id %s | risposta %s | byte %d" % (etichetta, api_id, st, len(txt))
    try:
        j = json.loads(txt)
        if isinstance(j, dict):
            riga += " | chiavi: " + ", ".join(list(j.keys())[:8])
            for k in ("tournament_data", "standings", "players"):
                if isinstance(j.get(k), list):
                    riga += " | %s: %d righe" % (k, len(j[k]))
        elif isinstance(j, list):
            riga += " | lista di %d elementi" % len(j)
    except Exception:
        pass
    print(riga, flush=True)


def prove(elenco, torn):
    sezione("4. Prova di lettura dei dati (/vg/id/<id>/division/masters)")
    reg = [e for e in elenco if "Regional" in e["name"] and e["status"] == "finished"]
    if reg:
        prova_id(reg[0]["id"], "il piu' vecchio dell'elenco: " + reg[0]["name"][:40])
        attendi()
    nuovi = set(e["id"] for e in elenco)
    cand = []
    for h, t in torn:
        for n in re.findall(r"(?<![\d])(\d{4,9})(?![\d])", h):
            if n not in nuovi and n not in cand:
                cand.append(n)
    print("id trovati nei link della pagina storica, non presenti nell'elenco API:", len(cand), cand[:8])
    for n in cand[:3]:
        prova_id(n, "vecchio")
        attendi()


def main():
    elenco = elenco_api()
    attendi()
    documentazione()
    attendi()
    torn = pagina_elenco()
    attendi()
    prove(elenco, torn)
    print("\nFine. Non e' stato salvato nessun file.")


if __name__ == "__main__":
    main()
