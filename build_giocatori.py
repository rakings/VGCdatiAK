#!/usr/bin/env python3
"""Costruisce vgcstats/giocatori.json: per ogni giocatore, i tornei FINITI e raccolti in cui ha giocato (posto, vittorie, sconfitte).
Legge solo i file gia' salvati (players.json e meta.json di ogni torneo): nessuna richiesta a siti esterni.
Formato compatto: {"v":1,"ids":[id dei tornei],"p":[[nome,paese,[[numero del torneo in ids,posto,vittorie,sconfitte],...]],...]}"""
import glob
import json
import os
import re
import sys
import unicodedata

OUT = sys.argv[1] if len(sys.argv) > 1 else "vgcstats"      # cartella dei dati: vgcstats (regionali) oppure vr (tornei VR)


def carica(p, default):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", s).strip()


MANUALI = "risultati_manuali.json"      # risultati aggiunti a mano (nella cartella principale della repo)


def leggi_manuali(percorso=MANUALI):
    """Risultati che non sono in nessun archivio (tornei prima del 2018, eventi locali...). Righe sbagliate vengono saltate con un avviso."""
    lista = carica(percorso, [])
    out = []
    for i, x in enumerate(lista if isinstance(lista, list) else [], 1):
        try:
            nome, torneo = str(x["nome"]).strip(), str(x["torneo"]).strip()
            if not nome or not torneo:
                raise ValueError("nome o torneo vuoto")
            d = str(x.get("data") or "")
            if d and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
                raise ValueError("la data deve essere come 2017-03-05")
            out.append({"n": nome, "cc": str(x.get("paese") or "").upper(), "t": torneo, "k": str(x.get("tipo") or "Regional Championships"),
                        "d": d, "a": int(x["anno"]) if x.get("anno") else (int(d[:4]) if d else 0), "pl": x.get("posto"),
                        "r": str(x.get("esito") or ""), "e": str(x.get("etichetta") or ""), "c": str(x.get("colore") or "")})
        except (KeyError, ValueError, TypeError) as ex:
            print("%s, voce %d da correggere (%s): saltata." % (percorso, i, ex))
    return out


def costruisci(out=None):
    out = out or OUT
    ids, persone, righe_tot = [], {}, 0
    for mp in sorted(glob.glob(os.path.join(out, "*", "meta.json"))):
        tid = os.path.basename(os.path.dirname(mp))
        if not carica(mp, {}).get("complete"):
            continue                                   # un torneo in corso non entra nell'indice: lo si cerca dal vivo
        righe = carica(os.path.join(out, tid, "players.json"), [])
        if not isinstance(righe, list) or not righe:
            continue
        k = len(ids)
        ids.append(tid)
        for r in righe:
            if not isinstance(r, list) or len(r) < 6 or not r[1]:
                continue
            chiave = (norm(r[1]), r[2] or "")          # stesso nome e stesso paese = stessa persona
            p = persone.setdefault(chiave, [r[1], r[2] or "", []])
            p[2].append([k, r[3], r[4], r[5]])
            righe_tot += 1
    elenco = sorted(persone.values(), key=lambda x: norm(x[0]))
    dati = {"v": 1, "ids": ids, "p": elenco}
    if out == "vgcstats":
        man = leggi_manuali()
        if man:
            dati["x"] = man
    return dati, righe_tot


def main():
    dati, righe = costruisci()
    if not dati["ids"] and not dati.get("x"):
        print("Nessun torneo completo trovato in %s: non scrivo niente." % OUT)
        return 0
    testo = json.dumps(dati, ensure_ascii=False, separators=(",", ":"))
    percorso = os.path.join(OUT, "giocatori.json")
    try:
        with open(percorso, encoding="utf-8") as f:
            if f.read() == testo:
                print("giocatori.json invariato (%d tornei, %d giocatori)." % (len(dati["ids"]), len(dati["p"])))
                return 0
    except OSError:
        pass
    tmp = percorso + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(testo)
    os.replace(tmp, percorso)
    print("giocatori.json scritto: %d tornei, %d giocatori, %d partecipazioni, %d risultati a mano, %.0f KB." % (len(dati["ids"]), len(dati["p"]), righe, len(dati.get("x", [])), len(testo.encode()) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
