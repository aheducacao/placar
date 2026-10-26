#!/usr/bin/env python3
"""Vendas direto da API da Guru (a chave entra pelo cofre do ambiente "Placar AH", nunca no código).

  python3 coleta/guru.py sonda  -> testa a API e grava coleta/sonda.enc.json (só estrutura e campos sem dados pessoais)
  python3 coleta/guru.py baixar -> grava coleta/raw/guru.json com as transações dos últimos ~40 dias
"""
import json, os, sys, time, urllib.request, urllib.parse, urllib.error, datetime as dt

BASE = "https://digitalmanager.guru/api/v2"
AQUI = os.path.dirname(os.path.abspath(__file__))
SEGURO = {"id", "status", "type", "method", "installments", "name", "offer", "total", "gross", "net", "value",
          "unit_value", "total_value", "quantity", "currency", "created_at", "ordered_at", "confirmed_at",
          "canceled_at", "updated_at", "refunded_at", "warranty_until", "marketplace_name", "code"}


def get(path, params=None):
    url = BASE + path + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "placar-ah"})
    for tentativa in range(3):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and tentativa < 2:
                time.sleep(5); continue
            corpo = e.read().decode()[:300]
            return e.code, {"erro": corpo}
        except Exception as e:  # rede
            return 0, {"erro": str(e)[:300]}


def limpar(o, prof=0):
    """Mantém a estrutura e só os valores de campos sem dados pessoais."""
    if isinstance(o, dict):
        return {k: (limpar(v, prof + 1) if isinstance(v, (dict, list)) else (v if k in SEGURO else f"<{type(v).__name__}>"))
                for k, v in o.items()}
    if isinstance(o, list):
        return [limpar(x, prof + 1) for x in o[:3]]
    return o


def todas(params):
    itens, cursor, paginas = [], None, 0
    while True:
        p = dict(params)
        if cursor:
            p["cursor"] = cursor
        st, d = get("/transactions", p)
        if st != 200:
            return st, d, itens
        itens += d.get("data", [])
        paginas += 1
        cursor = d.get("next_cursor")
        if not d.get("has_more_pages") or not cursor or paginas > 400:
            return 200, d, itens


def sonda():
    out = {}
    tentativas = {
        "confirmado": {"confirmed_at_ini": "2026-10-19", "confirmed_at_end": "2026-10-25"},
        "pedido": {"ordered_at_ini": "2026-10-19", "ordered_at_end": "2026-10-25"},
    }
    for nome, params in tentativas.items():
        st, ultimo, itens = todas(params)
        resumo = {"http": st, "chaves_resposta": list(ultimo.keys()) if isinstance(ultimo, dict) else str(type(ultimo)),
                  "qtd": len(itens), "exemplo": limpar(itens[0]) if itens else limpar(ultimo)}
        por_status = {}
        for t in itens:
            s = t.get("status")
            pay = t.get("payment") or {}
            v = pay.get("total") or pay.get("gross") or (t.get("invoice") or {}).get("value") or 0
            x = por_status.setdefault(str(s), {"qtd": 0, "soma": 0})
            x["qtd"] += 1; x["soma"] = round(x["soma"] + float(v or 0), 2)
        resumo["por_status"] = por_status
        out[nome] = resumo
    chave = os.environ.get("PLACAR_CHAVE")
    sys.path.insert(0, AQUI)
    from build import cifrar
    with open(os.path.join(AQUI, "sonda.enc.json"), "w") as h:
        json.dump(cifrar(out, chave), h)
    print(json.dumps({k: {"http": v["http"], "qtd": v["qtd"], "por_status": v["por_status"]} for k, v in out.items()}, ensure_ascii=False))


def baixar(desde="2025-01-01"):
    from zoneinfo import ZoneInfo
    hoje = dt.datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    ini = desde
    st, ultimo, itens = todas({"confirmed_at_ini": ini, "confirmed_at_end": hoje.isoformat()})
    if st != 200:
        sys.exit(f"Guru respondeu {st}: {json.dumps(ultimo)[:300]}")
    out = []
    for t in itens:
        pay = t.get("payment") or {}
        prod = t.get("product") or {}
        out.append({"id": t.get("id"), "status": t.get("status"),
                    "confirmado": (t.get("dates") or {}).get("confirmed_at"),
                    "valor": pay.get("total") or 0, "metodo": pay.get("method") or "",
                    "parcelas": ((pay.get("installments") or {}).get("qty")) or 1,
                    "produto": prod.get("name") or ""})
    os.makedirs(os.path.join(AQUI, "raw"), exist_ok=True)
    with open(os.path.join(AQUI, "raw", "guru.json"), "w") as h:
        json.dump(out, h, ensure_ascii=False)
    print("guru ok", len(out), "transações desde", ini)


if __name__ == "__main__":
    if sys.argv[1:2] == ["sonda"]:
        sonda()
    elif sys.argv[1:2] == ["baixar"]:
        baixar()
    else:
        print(__doc__)
