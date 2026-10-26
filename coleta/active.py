#!/usr/bin/env python3
"""Leads do ActiveCampaign direto da API (a chave entra pelo cofre do ambiente "Placar AH", nunca no código).

  python3 coleta/active.py baixar  -> atualiza coleta/active_cache.enc.json (cifrado, vai pro repositório)
                                      e grava coleta/raw/active.json (aberto, NUNCA vai pro repositório)
  Precisa de PLACAR_CHAVE para abrir/fechar o cache.

O que entra: toda tag aplicada a um contato, MENOS o "barulho":
  - tags automáticas de engajamento (Engajado, Atividade Recente, Não Engajado, Inativo)
  - tags da plataforma de aulas (enrollment-, start-, 25_pct-, 50_pct-, 75_pct-, finish-, member_entered_group-)
  - typeform-integration (genérica, sempre vem junto com a específica)
"""
import json, os, re, sys, time, urllib.request, urllib.parse, urllib.error, datetime as dt
from zoneinfo import ZoneInfo

AC_URL = os.environ.get("AC_URL", "https://andersonhernandes86877.api-us1.com").rstrip("/") + "/api/3"
AQUI = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(AQUI, "raw")
CACHE = os.path.join(AQUI, "active_cache.enc.json")
TZ = ZoneInfo("America/Sao_Paulo")
INICIO = "2026-01-01"  # histórico guardado a partir daqui

sys.path.insert(0, AQUI)
from build import barulho  # a regra do que não é lead fica num lugar só


def get(path, params=None):
    url = AC_URL + path + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "placar-ah"})
    for tentativa in range(4):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and tentativa < 3:
                time.sleep(3 * (tentativa + 1)); continue
            sys.exit(f"Active respondeu {e.code} em {path}: {e.read().decode()[:300]}")
        except Exception as e:
            if tentativa < 3:
                time.sleep(3); continue
            sys.exit(f"Sem conexão com o Active ({path}): {str(e)[:200]}")


def dia(cdate):
    """'2026-10-26T08:43:25-05:00' -> dia em São Paulo"""
    return dt.datetime.fromisoformat(cdate).astimezone(TZ).date().isoformat()


CACHE_ABERTO = os.path.join(RAW, "active_cache.json")


def cripto(acao, origem, destino):
    """Cifra/decifra num processo separado: neste ambiente a biblioteca de criptografia
    quebra se for carregada depois de uma conexão HTTPS no mesmo processo."""
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(AQUI, "build.py"), acao, origem, destino], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"Falha ao {acao} o cache do Active: {(r.stderr or r.stdout)[-300:]}")


def abrir_cache(chave):
    if not os.path.exists(CACHE):
        return {"v": 1, "ultimo_ct": 0, "ultimo_contato": 0, "tags": {}, "linhas": [], "novos": []}
    os.makedirs(RAW, exist_ok=True)
    cripto("decifrar", CACHE, CACHE_ABERTO)
    with open(CACHE_ABERTO) as h:
        return json.load(h)


def baixar():
    chave = os.environ.get("PLACAR_CHAVE")
    if not chave:
        sys.exit("Falta PLACAR_CHAVE (login:senha).")
    c = abrir_cache(chave)
    tags = {int(k): v for k, v in c["tags"].items()}
    vistos = {l[0] for l in c["linhas"]}

    # 1) tags aplicadas desde a última vez (mais novas primeiro)
    novas, off, parar = [], 0, False
    while not parar:
        d = get("/contactTags", {"orders[cdate]": "desc", "limit": 100, "offset": off})
        itens = d.get("contactTags", [])
        if not itens:
            break
        for t in itens:
            ctid = int(t["id"])
            dd = dia(t["cdate"])
            if (c["ultimo_ct"] and ctid <= c["ultimo_ct"]) or dd < INICIO:
                parar = True
                continue
            novas.append((ctid, int(t["contact"]), int(t["tag"]), dd))
        off += 100
        if off > 200000:
            break
    # nomes das tags que ainda não conheço
    faltam = sorted({n[2] for n in novas} - set(tags))
    for i in range(0, len(faltam), 100):
        lote = faltam[i:i + 100]
        d = get("/tags", {"ids": ",".join(map(str, lote)), "limit": 100})
        for t in d.get("tags", []):
            tags[int(t["id"])] = t.get("tag") or ""
    for ctid, contato, tag, dd in novas:
        if ctid in vistos or barulho(tags.get(tag, "")):
            continue
        c["linhas"].append([ctid, contato, tag, dd]); vistos.add(ctid)
    if novas:
        c["ultimo_ct"] = max(c["ultimo_ct"], max(n[0] for n in novas))

    # 2) contatos novos na base (criados) desde a última vez
    params = {"orders[id]": "ASC", "limit": 100}
    if c["ultimo_contato"]:
        params["id_greater"] = c["ultimo_contato"]
    else:
        params["filters[created_after]"] = f"{INICIO}T00:00:00-03:00"
    ja = {n[0] for n in c["novos"]}
    off = 0
    while True:
        d = get("/contacts", {**params, "offset": off})
        itens = d.get("contacts", [])
        for x in itens:
            cid = int(x["id"])
            c["ultimo_contato"] = max(c["ultimo_contato"], cid)
            if cid not in ja and x.get("cdate"):
                dd = dia(x["cdate"])
                if dd >= INICIO:
                    c["novos"].append([cid, dd]); ja.add(cid)
        if len(itens) < 100:
            break
        off += 100

    # 3) base ativa hoje
    base = int((get("/contacts", {"status": 1, "limit": 1}).get("meta") or {}).get("total") or 0)

    # 4) e-mails só de quem ganhou tag na janela recente (para cruzar com a Clint); não vão pro cache
    hoje = dt.datetime.now(TZ).date()
    janela = min(hoje.replace(day=1), hoje - dt.timedelta(days=13)).isoformat()
    ids = sorted({l[1] for l in c["linhas"] if l[3] >= janela})
    emails = {}
    for i in range(0, len(ids), 100):
        lote = ids[i:i + 100]
        d = get("/contacts", {"ids": ",".join(map(str, lote)), "limit": 100, "status": -1})
        for x in d.get("contacts", []):
            if int(x["id"]) in lote and x.get("email"):
                emails[int(x["id"])] = x["email"].strip().lower()
    for cid in ids:  # se o filtro por ids não trouxe alguém, busca um a um
        if cid not in emails:
            x = (get(f"/contacts/{cid}") or {}).get("contact") or {}
            if x.get("email"):
                emails[cid] = x["email"].strip().lower()

    # grava cache cifrado (sem e-mail nem nome, só ids e datas)
    c["tags"] = {str(k): v for k, v in tags.items()}
    os.makedirs(RAW, exist_ok=True)
    with open(CACHE_ABERTO, "w") as h:
        json.dump(c, h)
    cripto("cifrar", CACHE_ABERTO, CACHE)
    with open(os.path.join(RAW, "active.json"), "w") as h:
        json.dump({"tags": c["tags"], "linhas": c["linhas"], "novos": c["novos"], "base_ativa": base,
                   "emails": {str(k): v for k, v in emails.items()}}, h, ensure_ascii=False)
    print("active ok", len(novas), "tags novas lidas,", len(c["linhas"]), "entradas guardadas,", len(c["novos"]), "contatos novos desde", INICIO)


if __name__ == "__main__":
    if sys.argv[1:2] == ["baixar"]:
        baixar()
    else:
        print(__doc__)
