#!/usr/bin/env python3
"""Placar Comercial AH: monta os números e publica criptografados.

Uso:
  python3 coleta/build.py plano          -> lista as consultas a rodar (com datas) e onde salvar cada resposta
  python3 coleta/build.py montar         -> lê coleta/raw/*.json, calcula e grava data.enc.json (precisa de PLACAR_CHAVE)

PLACAR_CHAVE = "login:senha" (a mesma que a página pede). Nunca grave a chave no repositório.
"""
import base64, json, os, sys, datetime as dt
from zoneinfo import ZoneInfo

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
RAW = os.path.join(AQUI, "raw")
TZ = ZoneInfo("America/Sao_Paulo")
FELIPE = "d1c2f9ae-9d66-4e42-a83d-3755a21add0b"
LETICIA = "2c70a62f-7002-4874-a6f2-19cbefca53e3"
VENDEDORES = [(FELIPE, "Felipe", "felipe"), (LETICIA, "Letícia", "souza")]
PERIODOS = ["hoje", "ontem", "7d", "mes"]
ROTULO = {"hoje": "Hoje", "ontem": "Ontem", "7d": "Últimos 7 dias", "mes": "Este mês"}


def intervalos(agora=None):
    hoje = (agora or dt.datetime.now(TZ)).date()
    r = {
        "hoje": (hoje, hoje),
        "ontem": (hoje - dt.timedelta(days=1), hoje - dt.timedelta(days=1)),
        "7d": (hoje - dt.timedelta(days=6), hoje),
        "mes": (hoje.replace(day=1), hoje),
    }
    return {k: (a.isoformat(), b.isoformat()) for k, (a, b) in r.items()}


def plano():
    iv = intervalos()
    ids = [FELIPE, LETICIA]
    atend = [{"member": "Message.type", "operator": "equals", "values": ["Atendente"]},
             {"member": "Message.userId", "operator": "equals", "values": ids}]
    calls = []
    for p in PERIODOS:
        a, b = iv[p]
        dr = [a, b]
        q = lambda body: {"tool": "Clint execute_indicator_query", "args": {"query": {**body, "timezone": "America/Sao_Paulo"}}}
        calls += [
            {**q({"measures": ["Chat.count", "Message.count"], "dimensions": ["User.name"], "filters": atend,
                  "timeDimensions": [{"dimension": "Message.createdAt", "dateRange": dr}]}), "salvar": f"{p}_equipe.json", "o_que": "payload.data"},
            {**q({"measures": ["ChatResponseInterval.count", "ChatResponseInterval.medianResponseTime"], "dimensions": ["User.name"],
                  "filters": [{"member": "User.name", "operator": "contains", "values": ["Felipe", "Souza"]}],
                  "timeDimensions": [{"dimension": "ChatResponseInterval.repliedAt", "dateRange": dr}]}), "salvar": f"{p}_tempo.json", "o_que": "payload.data"},
            {**q({"measures": ["Chat.count"], "dimensions": ["Origin.name"], "filters": atend,
                  "timeDimensions": [{"dimension": "Message.createdAt", "dateRange": dr}], "limit": 300}), "salvar": f"{p}_atendidos.json", "o_que": "payload.data"},
            {**q({"measures": ["Deal.count"], "dimensions": ["Origin.name"],
                  "timeDimensions": [{"dimension": "Deal.createdAt", "dateRange": dr}], "limit": 300}), "salvar": f"{p}_entradas.json", "o_que": "payload.data"},
            {**q({"measures": ["DealActivity.count"], "dimensions": ["DealActivity.userId", "DealActivity.activity_type_label"],
                  "filters": [{"member": "DealActivity.userId", "operator": "equals", "values": ids}],
                  "timeDimensions": [{"dimension": "DealActivity.completedAt", "dateRange": dr}]}), "salvar": f"{p}_atividades.json", "o_que": "payload.data"},
            {"tool": "ActiveCampaign list_contacts", "args": {"params": {"filters": {"created_after": f"{a}T00:00:00-03:00",
                 "created_before": f"{(dt.date.fromisoformat(b) + dt.timedelta(days=1)).isoformat()}T00:00:00-03:00"}, "limit": 1}},
             "salvar": f"{p}_leads.json", "o_que": "{\"total\": meta.total}"},
            {"tool": "ActiveCampaign run_campaign_performance_report", "args": {"params": {"module": "campaigns", "explore": "all_campaigns_performance",
                 "columns": ["campaign_name", "total_sends"], "params": {"view_distinct_campaigns_event_date_start": a, "view_distinct_campaigns_event_date_end": b}, "limit": 1}},
             "salvar": f"{p}_emails.json", "o_que": "summaryData (objeto inteiro)"},
        ]
    ini_mes = min(dt.date.fromisoformat(iv["mes"][0]), dt.date.fromisoformat(iv["hoje"][0]) - dt.timedelta(days=30))
    corte_utc = f"{ini_mes.isoformat()} 03:00:00"
    calls += [
        {"tool": "Clint execute_indicator_query", "args": {"query": {"measures": ["Deal.count"],
            "dimensions": ["DealCheckout.product_name", "DealCheckout.purchase_full_price",
                           "DealCheckout.payment_type", "DealCheckout.purchase_paid_at"],
            "filters": [{"member": "DealCheckout.purchase_status", "operator": "equals", "values": ["Aprovada"]},
                        {"member": "DealCheckout.purchase_paid_at", "operator": "gte", "values": [corte_utc]}],
            "timezone": "America/Sao_Paulo", "limit": 1000}}, "salvar": "vendas.json", "o_que": "payload.data"},
        {"tool": "Clint execute_indicator_query", "args": {"query": {"measures": ["Chat.withReply", "Chat.windowExpiredUnreplied"],
            "dimensions": ["Chat.userId"], "filters": [{"member": "Chat.userId", "operator": "equals", "values": ids}],
            "timezone": "America/Sao_Paulo"}}, "salvar": "fila.json", "o_que": "payload.data"},
    ]
    print(json.dumps({"intervalos": iv, "pasta": RAW, "consultas": calls}, ensure_ascii=False, indent=1))


# ---------- cálculo ----------

def produto(nome):
    n = (nome or "").lower()
    if "gestão de pessoas" in n or "gestao de pessoas" in n:
        return "Imersão Gestão de Pessoas"
    if "alian" in n:
        return "Aliança"
    if "caixa preta" in n:
        return "Caixa Preta"
    if "fvc" in n or "vendedor" in n:
        return "Formação de Vendedor"
    if "gest" in n:
        return "AH Gestão"
    if "summit" in n or "palestra" in n:
        return "AH Summit"
    if "club" in n:
        return "AH Club"
    if "marketing e vendas" in n or "imersão de marketing" in n:
        return "Imersão Marketing e Vendas"
    return "Outros"


NAO_LEAD = ("compras", "assinaturas", "cartão recusado", "cartao recusado", "reembolso", "participantes",
            "acompanhamento", "onboarding", "mentorandos", "abandono")


def ler(nome, padrao=None):
    f = os.path.join(RAW, nome)
    if not os.path.exists(f):
        return padrao
    with open(f) as h:
        d = json.load(h)
    if isinstance(d, dict) and "payload" in d:
        d = d["payload"].get("data", [])
    if isinstance(d, dict) and "data" in d and isinstance(d["data"], list):
        d = d["data"]
    return d


num = lambda x: float(x) if x not in (None, "") else 0.0


def quem(nome_ou_id):
    s = (nome_ou_id or "").lower()
    for uid, nome, chave in VENDEDORES:
        if s == uid or chave in s:
            return nome
    return None


def montar():
    iv = intervalos()
    agora = dt.datetime.now(TZ)

    # vendas (uma linha por transação; a Clint repete a mesma compra em vários funis)
    vend = {}
    for r in ler("vendas.json", []) or []:
        pago = r.get("DealCheckout.purchase_paid_at") or ""
        if not pago or str(r.get("Deal.count", "1")) == "0":
            continue
        chave = "|".join([pago, r.get("DealCheckout.product_name") or "", str(r.get("DealCheckout.purchase_full_price"))])
        local = dt.datetime.fromisoformat(pago.replace(" ", "T")).replace(tzinfo=dt.timezone.utc).astimezone(TZ)
        vend[chave] = {"dia": local.date().isoformat(), "produto": produto(r.get("DealCheckout.product_name")),
                       "valor": num(r.get("DealCheckout.purchase_full_price")), "pagamento": r.get("DealCheckout.payment_type") or "Outro"}
    vendas = list(vend.values())

    fila = {quem(r.get("Chat.userId")): r for r in (ler("fila.json", []) or [])}

    out = {"atualizado": agora.strftime("%d/%m às %H:%M"), "periodos": {}, "serie": []}
    for p in PERIODOS:
        a, b = iv[p]
        vs = [v for v in vendas if a <= v["dia"] <= b]
        por_prod = {}
        def linha(pn):
            return por_prod.setdefault(pn, {"produto": pn, "leads": 0, "atendidos": 0, "vendas": 0, "faturamento": 0.0})
        for v in vs:
            l = linha(v["produto"]); l["vendas"] += 1; l["faturamento"] += v["valor"]
        for r in ler(f"{p}_entradas.json", []) or []:
            nome = (r.get("Origin.name") or "")
            if not nome or nome.lower().startswith(NAO_LEAD):
                continue
            linha(produto(nome))["leads"] += int(num(r.get("Deal.count")))
        for r in ler(f"{p}_atendidos.json", []) or []:
            nome = r.get("Origin.name") or ""
            if not nome or nome.lower().startswith(NAO_LEAD):
                continue
            linha(produto(nome))["atendidos"] += int(num(r.get("Chat.count")))
        pagamentos = {}
        for v in vs:
            pg = {"Cartão de Crédito": "Cartão", "Pix": "Pix", "Boleto": "Boleto"}.get(v["pagamento"], "Outro")
            x = pagamentos.setdefault(pg, {"forma": pg, "vendas": 0, "valor": 0.0}); x["vendas"] += 1; x["valor"] += v["valor"]

        eq = {quem(r.get("User.name")): r for r in (ler(f"{p}_equipe.json", []) or [])}
        tp = {quem(r.get("User.name")): r for r in (ler(f"{p}_tempo.json", []) or [])}
        equipe = []
        for uid, nome, _ in VENDEDORES:
            at = [r for r in (ler(f"{p}_atividades.json", []) or []) if r.get("DealActivity.userId") == uid]
            f = fila.get(nome) or {}
            med = (tp.get(nome) or {}).get("ChatResponseInterval.medianResponseTime")
            equipe.append({
                "nome": nome,
                "atendidos": int(num((eq.get(nome) or {}).get("Chat.count"))),
                "mensagens": int(num((eq.get(nome) or {}).get("Message.count"))),
                "resposta_min": round(num(med) / 60, 1) if med not in (None, "") else None,
                "ligacoes": int(sum(num(r.get("DealActivity.count")) for r in at if "liga" in (r.get("DealActivity.activity_type_label") or "").lower())),
                "atividades": int(sum(num(r.get("DealActivity.count")) for r in at)),
                "esperando": int(num(f.get("Chat.withReply"))),
                "janela_vencida": int(num(f.get("Chat.windowExpiredUnreplied"))),
            })
        leads_ac = ler(f"{p}_leads.json", {}) or {}
        em = ler(f"{p}_emails.json", {}) or {}
        if isinstance(em, dict) and "summaryData" in em:
            em = em["summaryData"]
        fat = sum(v["valor"] for v in vs)
        produtos = sorted(por_prod.values(), key=lambda x: (-x["faturamento"], -x["leads"], x["produto"]))
        for x in produtos:
            x["faturamento"] = round(x["faturamento"], 2)
        out["periodos"][p] = {
            "rotulo": ROTULO[p], "de": a, "ate": b,
            "faturamento": round(fat, 2), "vendas": len(vs), "ticket": round(fat / len(vs), 2) if vs else 0,
            "leads_active": int(num(leads_ac.get("total") if isinstance(leads_ac, dict) else leads_ac)),
            "atendidos": sum(e["atendidos"] for e in equipe),
            "produtos": produtos,
            "pagamentos": sorted(pagamentos.values(), key=lambda x: -x["valor"]),
            "equipe": equipe,
            "emails": {"envios": int(num(em.get("total_sends"))), "abertura": num(em.get("open_rate")),
                       "clique": num(em.get("click_rate")), "cliques": int(num(em.get("total_unique_clicks"))),
                       "descadastros": int(num(em.get("total_unsubscribes")))},
        }
    # série diária do mês
    a, b = iv["mes"]
    d = dt.date.fromisoformat(a)
    while d.isoformat() <= b:
        vs = [v for v in vendas if v["dia"] == d.isoformat()]
        out["serie"].append({"dia": d.isoformat(), "vendas": len(vs), "faturamento": round(sum(v["valor"] for v in vs), 2)})
        d += dt.timedelta(days=1)
    return out


def cifrar(obj, chave):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    sal, iv = os.urandom(16), os.urandom(12)
    it = 400000
    k = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=sal, iterations=it).derive(chave.encode())
    ct = AESGCM(k).encrypt(iv, json.dumps(obj, ensure_ascii=False).encode(), None)
    b = lambda x: base64.b64encode(x).decode()
    return {"v": 1, "it": it, "sal": b(sal), "iv": b(iv), "dados": b(ct)}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "plano":
        plano()
    elif cmd == "montar":
        chave = os.environ.get("PLACAR_CHAVE")
        if not chave:
            sys.exit("Falta PLACAR_CHAVE (login:senha).")
        dados = montar()
        with open(os.path.join(RAIZ, "data.enc.json"), "w") as h:
            json.dump(cifrar(dados, chave), h)
        if "--mostrar" in sys.argv:
            print(json.dumps(dados, ensure_ascii=False, indent=1))
        print("ok", dados["atualizado"])
    else:
        print(__doc__)
