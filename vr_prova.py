#!/usr/bin/env python3
"""VR Circuit - PROVA DI SOLA LETTURA. Fa 2 richieste (classifica e abbinamenti dell'ultimo torneo finito), con una pausa in mezzo.
Non salva nessun file: stampa nel log quello che riesce a leggere e un pezzetto della pagina, cosi' si vede com'e' fatta davvero.
Identificazione onesta e senza dati personali."""
import html as _html
import random
import re
import sys
import time
import urllib.error
import urllib.request

UA = "tornei-vgc-bot (sito della community, con link alle fonti)"
BASE = "https://circuit.victoryroad.pro"
TORNEO = "vr-oct26-4"


def scarica(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return 0, str(e)


def pulisci(h):
    h = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    return " ".join(_html.unescape(h).split())


def giocatori(pagina):
    """Ogni giocatore ha un link vrpastes che racchiude le icone della squadra: il testo che lo precede (dopo il link del giocatore
    prima) contiene posto, nome, paese e record. Metodo prudente: se la pagina e' fatta diversamente, la prova lo fa vedere."""
    out, inizio = [], 0
    for m in re.finditer(r'(?is)<a[^>]+href="(https://www\.vrpastes\.com/[^"]+)"[^>]*>(.*?)</a>', pagina):
        pezzo = pagina[inizio:m.start()]
        squadra = m.group(2)
        inizio = m.end()
        tok = pulisci(pezzo).split()
        ir = next((k for k in range(len(tok) - 1, -1, -1) if re.fullmatch(r"\d+[\u2013\u2014-]\d+", tok[k])), None)
        posto = nome = ""
        record = ""
        if ir is not None:
            record = tok[ir].replace("\u2013", "-").replace("\u2014", "-")
            ip = next((k for k in range(ir - 1, -1, -1) if re.fullmatch(r"\d{1,3}", tok[k])), None)
            if ip is not None:
                posto = int(tok[ip])
                nome = " ".join(tok[ip + 1:ir])
        bandiera = re.search(r'<img[^>]+?(?:title|alt)="([^"]+)"[^>]*flags/', pezzo) or re.search(r'<img[^>]+?flags/[^>]*?(?:title|alt)="([^"]+)"', pezzo)
        paese = bandiera.group(1) if bandiera else ""
        if paese and nome.endswith(paese):
            nome = nome[: -len(paese)].strip()
        pk = re.findall(r'<img[^>]+?src="[^"]*/pokemons/([^"/]+?)\.webp"', squadra)
        it = re.findall(r'<img[^>]+?src="[^"]*/items/([^"/]+?)\.webp"', squadra)
        out.append({"posto": posto, "nome": nome, "paese": paese, "record": record, "pokemon": pk, "strumenti": it,
                    "link": m.group(1), "pezzo": pezzo + m.group(0)[:200]})
    return out


def main():
    print("PROVA di sola lettura - 2 richieste a %s" % BASE)
    st, pag = scarica("%s/tournament/%s" % (BASE, TORNEO))
    print("\n== Classifica: risposta %s, %d byte" % (st, len(pag)))
    if st != 200:
        print("Non riesco a leggerla: mi fermo.")
        return 1
    t = pulisci(pag)
    agg = re.search(r"Updated[^|]{0,60}", t)
    dichiarati = re.search(r"(\d+)\s+Players", t)
    print("Scritta di aggiornamento nella pagina:", agg.group(0).strip() if agg else "(non trovata)")
    print("Giocatori dichiarati dalla pagina:", dichiarati.group(1) if dichiarati else "(non trovati)")
    g = giocatori(pag)
    print("Giocatori letti con il mio metodo:", len(g))
    for x in g[:3]:
        print("  %s | %s | %s | %s | %d pokemon, %d strumenti" % (x["posto"], x["nome"], x["paese"], x["record"], len(x["pokemon"]), len(x["strumenti"])))
        print("     squadra:", ", ".join(x["pokemon"]))
    if g:
        print("\nPezzo di pagina GREZZO del primo giocatore (serve a me per capire com'e' fatta):")
        print(g[0]["pezzo"][-1400:])
    time.sleep(random.uniform(8, 15))
    st2, pag2 = scarica("%s/tournament/%s/pairings" % (BASE, TORNEO))
    print("\n== Abbinamenti: risposta %s, %d byte" % (st2, len(pag2)))
    if st2 == 200:
        t2 = pulisci(pag2)
        print("Volte che compare «Round»:", len(re.findall(r"Round", t2)))
        print("Inizio del testo:", t2[:500])
        print("\nPezzo GREZZO dopo la prima occorrenza di «Round»:")
        i = pag2.find("Round")
        print(pag2[i:i + 1200] if i >= 0 else "(nessuna)")
    print("\nFine. Non e' stato salvato nessun file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
