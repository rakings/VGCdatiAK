#!/usr/bin/env python3
"""Limitless VGC - PROVA DI SOLA LETTURA per lo storico dei giocatori. Fa 4 richieste con pause lente (robots.txt, elenco dei tornei,
un torneo, lo storico completo di un giocatore). Non salva nessun file: stampa nel log com'e' fatto il sito, con pezzi di pagina grezzi.
Idea: lo storico di ogni giocatore si puo' ricostruire dalle pagine dei TORNEI (circa 450 in tutto, una volta sola) invece che da
migliaia di profili. Questa prova serve a verificarlo. Identificazione onesta e senza dati personali."""
import html as _html
import random
import re
import sys
import time
import urllib.error
import urllib.request

UA = "tornei-vgc-bot (sito della community, con link alle fonti)"
BASE = "https://limitlessvgc.com"
TORNEO = "448"      # Regional Gdansk 2026 (dal profilo di un giocatore)
GIOCATORE = "3"


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


def id_link(pagina, parte):
    """Numeri trovati nei link del tipo /<parte>/<numero> (senza doppioni, in ordine di apparizione)."""
    visti, out = set(), []
    for n in re.findall(r'href="(?:https?://limitlessvgc\.com)?/%s/(\d+)(?:["/?#])' % parte, pagina):
        if n not in visti:
            visti.add(n)
            out.append(n)
    return out


def pezzo_grezzo(pagina, parte, prima=250, dopo=650):
    m = re.search(r'href="(?:https?://limitlessvgc\.com)?/%s/\d+' % parte, pagina)
    if not m:
        return "(nessun link /%s/ trovato)" % parte
    return pagina[max(0, m.start() - prima): m.start() + dopo]


def pausa():
    time.sleep(random.uniform(8, 15))


def main():
    print("PROVA di sola lettura - 4 richieste a %s" % BASE)
    st, txt = scarica(BASE + "/robots.txt")
    print("\n== 1. robots.txt: risposta %s" % st)
    print(txt[:900] if st == 200 else "(non disponibile)")
    pausa()
    st, pag = scarica(BASE + "/tournaments")
    print("\n== 2. Elenco tornei: risposta %s, %d byte" % (st, len(pag)))
    if st == 200:
        ids = id_link(pag, "tournaments")
        print("Tornei trovati nei link:", len(ids), "| id piu' basso/alto:", (min(map(int, ids)), max(map(int, ids))) if ids else "-")
        print("Pagine successive (paginazione)?:", "si" if re.search(r"page=\d+|class=\"[^\"]*pag", pag) else "non vista")
        print("Inizio del testo:", pulisci(pag)[:400])
    pausa()
    st, pag = scarica("%s/tournaments/%s" % (BASE, TORNEO))
    print("\n== 3. Un torneo (%s): risposta %s, %d byte" % (TORNEO, st, len(pag)))
    if st == 200:
        gi = id_link(pag, "players")
        print("Giocatori con link al profilo:", len(gi), "| primi 5 id:", gi[:5])
        print("Inizio del testo:", pulisci(pag)[:600])
        print("\nPezzo GREZZO attorno al primo giocatore:")
        print(pezzo_grezzo(pag, "players"))
    pausa()
    st, pag = scarica("%s/players/%s/results" % (BASE, GIOCATORE))
    print("\n== 4. Storico completo del giocatore %s: risposta %s, %d byte" % (GIOCATORE, st, len(pag)))
    if st == 200:
        tn = id_link(pag, "tournaments")
        print("Tornei nello storico:", len(tn), "| primi 5 id:", tn[:5])
        print("Inizio del testo:", pulisci(pag)[:600])
        print("\nPezzo GREZZO attorno al primo torneo:")
        print(pezzo_grezzo(pag, "tournaments"))
    print("\nFine. Non e' stato salvato nessun file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
