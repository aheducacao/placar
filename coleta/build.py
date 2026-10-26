#!/usr/bin/env python3
"""Placar Comercial AH: monta os números e publica criptografados.

Uso:
  python3 coleta/build.py plano          -> lista as consultas a rodar (com datas) e onde salvar cada resposta
  python3 coleta/build.py montar         -> lê coleta/raw/*.json, calcula e grava data.enc.json (precisa de PLACAR_CHAVE)

PLACAR_CHAVE = "login:senha" (a mesma que a página pede). Nunca grave a chave no repositório.
"""
import base64, json, os, re, sys, datetime as dt
from zoneinfo import ZoneInfo

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
RAW = os.path.join(AQUI, "raw")
TZ = ZoneInfo("America/Sao_Paulo")
FELIPE = "d1c2f9ae-9d66-4e42-a83d-3755a21add0b"
LETICIA = "2c70a62f-7002-4874-a6f2-19cbefca53e3"
VENDEDORES = [(FELIPE, "Felipe", "felipe"), (LETICIA, "Letícia", "souza")]
PERIODOS = ["hoje", "ontem", "7d", "semana", "mes"]
ROTULO = {"hoje": "Hoje", "ontem": "Ontem", "7d": "Últimos 7 dias", "semana": "Semana passada", "mes": "Este mês"}


def intervalos(agora=None):
    hoje = (agora or dt.datetime.now(TZ)).date()
    r = {
        "hoje": (hoje, hoje),
        "ontem": (hoje - dt.timedelta(days=1), hoje - dt.timedelta(days=1)),
        "7d": (hoje - dt.timedelta(days=6), hoje),
        "semana": (hoje - dt.timedelta(days=hoje.weekday() + 7), hoje - dt.timedelta(days=hoje.weekday() + 1)),
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
            {**q({"measures": ["TrackStage.changeStage"], "dimensions": ["Origin.name", "TrackStage.stage"],
                  "timeDimensions": [{"dimension": "TrackStage.date", "dateRange": dr}], "limit": 1000}), "salvar": f"{p}_etapas.json", "o_que": "payload.data"},
            {**q({"measures": ["DealActivity.meetingScheduledActivities", "DealActivity.meetingActivities", "DealActivity.noShowActivities",
                               "DealActivity.meetingRescheduledActivities"], "dimensions": ["Origin.name"],
                  "filters": [{"member": "Origin.name", "operator": "contains", "values": ["lian"]}],
                  "timeDimensions": [{"dimension": "DealActivity.completedAt", "dateRange": dr}], "limit": 50}), "salvar": f"{p}_reunioes.json", "o_que": "payload.data"},
            {**q({"measures": ["TrackStatus.changeStatus"], "dimensions": ["TrackStatus.dealId", "Deal.value", "Origin.name", "Contact.email", "Contact.name"],
                  "filters": [{"member": "TrackStatus.category", "operator": "equals", "values": ["DEAL_UPDATE_STATUS"]},
                              {"member": "TrackStatus.statusLabel", "operator": "equals", "values": ["Ganho"]},
                              {"member": "Origin.name", "operator": "contains", "values": ["lian"]}],
                  "timeDimensions": [{"dimension": "TrackStatus.date", "dateRange": dr}], "limit": 500}), "salvar": f"{p}_ganhos_alianca.json", "o_que": "payload.data"},
            {"tool": "ActiveCampaign list_contacts", "args": {"params": {"filters": {"created_after": f"{a}T00:00:00-03:00",
                 "created_before": f"{(dt.date.fromisoformat(b) + dt.timedelta(days=1)).isoformat()}T00:00:00-03:00"}, "limit": 1}},
             "salvar": f"{p}_leads.json", "o_que": "{\"total\": meta.total}"},
            {"tool": "ActiveCampaign run_campaign_performance_report", "args": {"params": {"module": "campaigns", "explore": "all_campaigns_performance",
                 "columns": ["campaign_name", "total_sends"], "params": {"view_distinct_campaigns_event_date_start": a, "view_distinct_campaigns_event_date_end": b}, "limit": 1}},
             "salvar": f"{p}_emails.json", "o_que": "summaryData (objeto inteiro)"},
        ]
    ini_mes = min(dt.date.fromisoformat(iv["mes"][0]), dt.date.fromisoformat(iv["hoje"][0]) - dt.timedelta(days=30))
    corte_utc = f"{ini_mes.isoformat()} 03:00:00"
    janela = min(dt.date.fromisoformat(iv["mes"][0]), dt.date.fromisoformat(iv["hoje"][0]) - dt.timedelta(days=13)).isoformat()
    calls += [
        {"tool": "Clint execute_indicator_query", "args": {"query": {"measures": ["Deal.count"], "dimensions": ["Contact.email", "Origin.name"],
            "timeDimensions": [{"dimension": "Deal.createdAt", "granularity": "day", "dateRange": [janela, iv["hoje"][1]]}],
            "timezone": "America/Sao_Paulo", "limit": 3000}}, "salvar": "clint_emails.json", "o_que": "payload.data"},
        {"tool": "Clint execute_indicator_query", "args": {"query": {"measures": ["Chat.withReply", "Chat.windowExpiredUnreplied"],
            "dimensions": ["Chat.userId"], "filters": [{"member": "Chat.userId", "operator": "equals", "values": ids}],
            "timezone": "America/Sao_Paulo"}}, "salvar": "fila.json", "o_que": "payload.data"},
    ]
    print(json.dumps({"intervalos": iv, "pasta": RAW, "consultas": calls}, ensure_ascii=False, indent=1))


# ---------- cálculo ----------

def produto(nome, clint=False):
    n = (nome or "").lower()
    if clint and n.startswith("marketing e vendas"):
        return "Formação de Vendedor"  # leads da imersão de marketing foram para a Formação
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
    if "palestra" in n:
        return "AH Summit Palestras"
    if "summit" in n:
        return "AH Summit"
    if "club" in n:
        return "AH Club"
    if "marketing e vendas" in n or "imersão de marketing" in n:
        return "Imersão Marketing e Vendas"
    return "Outros"


FOCO = ["AH Gestão", "Formação de Vendedor", "AH Club", "AH Summit Palestras"]
CHECKOUT = ("abandono", "compras em aberto", "cartão recusado", "cartao recusado", "compras expiradas")
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

    # vendas: direto da API da Guru (coleta/guru.py baixar), pela data de aprovação, como no painel da Guru
    METODO = {"credit_card": "Cartão de Crédito", "pix": "Pix", "billet": "Boleto", "bank_slip": "Boleto"}
    vend, reemb = {}, []
    for t in ler("guru.json", []) or []:
        if not t.get("confirmado"):
            continue
        dia = dt.datetime.fromtimestamp(int(t["confirmado"]), TZ).date().isoformat()
        item = {"dia": dia, "produto": produto(t.get("produto")), "valor": num(t.get("valor")),
                "pagamento": METODO.get(t.get("metodo"), "Outro"), "qtd": int(num(t.get("qtd")) or 1)}
        if t.get("status") == "approved":
            vend[t["id"]] = item
        elif t.get("status") in ("refunded", "chargedback", "chargeback"):
            reemb.append(item)
    vendas = list(vend.values())

    fila = {quem(r.get("Chat.userId")): r for r in (ler("fila.json", []) or [])}

    out = {"atualizado": agora.strftime("%d/%m às %H:%M"), "periodos": {}, "serie": []}
    for p in PERIODOS:
        a, b = iv[p]
        vs = [v for v in vendas if a <= v["dia"] <= b]
        por_prod = {}
        def linha(pn):
            return por_prod.setdefault(pn, {"produto": pn, "leads": 0, "atendidos": 0, "vendas": 0, "cadeiras": 0, "faturamento": 0.0})
        for v in vs:
            l = linha(v["produto"]); l["vendas"] += 1; l["cadeiras"] += v["qtd"]; l["faturamento"] += v["valor"]
        for r in ler(f"{p}_entradas.json", []) or []:
            nome = (r.get("Origin.name") or "")
            if not nome or nome.lower().startswith(NAO_LEAD):
                continue
            linha(produto(nome, True))["leads"] += int(num(r.get("Deal.count")))
        for r in ler(f"{p}_atendidos.json", []) or []:
            nome = r.get("Origin.name") or ""
            if not nome or nome.lower().startswith(NAO_LEAD):
                continue
            linha(produto(nome, True))["atendidos"] += int(num(r.get("Chat.count")))
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
        rs = [r for r in reemb if a <= r["dia"] <= b]
        produtos = sorted(por_prod.values(), key=lambda x: (x["produto"] not in FOCO + ["Aliança"], -x["faturamento"], -x["leads"], x["produto"]))
        for x in produtos:
            x["faturamento"] = round(x["faturamento"], 2)
        foco, ali = funis(p, por_prod)
        # Aliança é vendida fora da Guru: a linha dela usa os negócios ganhos na Clint
        extra_ali = 0.0
        x = por_prod.get("Aliança")
        if ali["vendas"] and (not x or not x["vendas"]):
            x = linha("Aliança")
            x.update({"vendas": ali["vendas"], "faturamento": ali["valor"], "cadeiras": ali.get("cadeiras") or 0, "fonte": "clint"})
            extra_ali = ali["valor"]
        out["periodos"][p] = {
            "rotulo": ROTULO[p], "de": a, "ate": b,
            "faturamento": round(fat, 2), "vendas": len(vs),
            "reembolsos": len(rs), "reembolsos_valor": round(sum(r["valor"] for r in rs), 2), "ticket": round(fat / len(vs), 2) if vs else 0,
            "leads_active": int(num(leads_ac.get("total") if isinstance(leads_ac, dict) else leads_ac)),
            "atendidos": sum(e["atendidos"] for e in equipe),
            "produtos": produtos,
            "pagamentos": sorted(pagamentos.values(), key=lambda x: -x["valor"]),
            "foco": foco, "alianca": ali, "extra_alianca": round(extra_ali, 2),
            "equipe": equipe,
            "emails": {"envios": int(num(em.get("total_sends"))), "abertura": num(em.get("open_rate")),
                       "clique": num(em.get("click_rate")), "cliques": int(num(em.get("total_unique_clicks"))),
                       "descadastros": int(num(em.get("total_unsubscribes")))},
        }
    # vendas por dia, produto e forma de pagamento (para o período livre na página)
    agg = {}
    for v in vendas:
        k = (v["dia"], v["produto"], v["pagamento"])
        x = agg.setdefault(k, [0, 0.0, 0, 0.0, 0]); x[0] += 1; x[1] += v["valor"]; x[4] += v["qtd"]
    for r in reemb:
        k = (r["dia"], r["produto"], r["pagamento"])
        x = agg.setdefault(k, [0, 0.0, 0, 0.0, 0]); x[2] += 1; x[3] += r["valor"]
    out["dias"] = [{"d": k[0], "p": k[1], "m": k[2], "n": x[0], "q": x[4], "v": round(x[1], 2), "r": x[2], "rv": round(x[3], 2)}
                   for k, x in sorted(agg.items())]
    out["desde"] = min([k[0] for k in agg] or [iv["mes"][0]])
    out["topo"] = topo(iv)
    # série diária do mês
    a, b = iv["mes"]
    d = dt.date.fromisoformat(a)
    while d.isoformat() <= b:
        vs = [v for v in vendas if v["dia"] == d.isoformat()]
        out["serie"].append({"dia": d.isoformat(), "vendas": len(vs), "faturamento": round(sum(v["valor"] for v in vs), 2)})
        d += dt.timedelta(days=1)
    return out


# ---------- tags do Active que NÃO são entrada de lead ----------
ENGAJAMENTO = {"engajado", "atividade recente", "não engajado", "nao engajado", "inativo"}
NAO_ENTRADA = re.compile(
    r"^(enrollment|start|finish|completed|certificate|payment_\w+|\d+_pct)-"   # plataforma de aulas
    r"|^member_"                                                               # entrada/saída/importação de membros
    r"|^compra-aprovada|^comprou|^compradores|cancelad"                        # quem já comprou ou cancelou
    r"|data de importa|c[oó]digo fonte|tag fantasma|disparo crm|check-in"      # importações e listas internas
    r"|^mentorandos|^leads-presentes|ja-faz-um-tempo|nunca-acessou|l2quente", re.I)


def barulho(nome):
    n = (nome or "").strip().lower()
    return n in ENGAJAMENTO or n == "typeform-integration" or bool(NAO_ENTRADA.search(n))


_MENTORIA = []


def mentoria():
    """Mapa (hash de e-mail/nome -> pessoas da empresa) da base da mentoria, se existir."""
    if not _MENTORIA:
        f = os.path.join(AQUI, "mentoria.enc.json")
        chave = os.environ.get("PLACAR_CHAVE")
        _MENTORIA.append(decifrar(json.load(open(f)), chave)["mapa"] if os.path.exists(f) and chave else None)
        sys.path.insert(0, AQUI)
    return _MENTORIA[0]


def funis(p, por_prod):
    """Funil dos produtos em foco e da Aliança, a partir das entradas, mudanças de etapa e atividades da Clint."""
    f = {pn: {"produto": pn, "leads": 0, "atendidos": 0, "responderam": 0, "aguardando": 0, "checkout": 0,
              "vendas": 0, "cadeiras": 0, "faturamento": 0.0} for pn in FOCO}
    for pn in FOCO:
        x = por_prod.get(pn) or {}
        for k in ("leads", "atendidos", "vendas", "cadeiras", "faturamento"):
            f[pn][k] = x.get(k, 0)
    for r in ler(f"{p}_entradas.json", []) or []:
        nome = (r.get("Origin.name") or "").lower()
        pn = produto(nome, True)
        if pn in f and nome.startswith(CHECKOUT):
            f[pn]["checkout"] += int(num(r.get("Deal.count")))
    a = {"inscricoes": 0, "atendidos": 0, "formulario": 0, "qualificados": 0, "agendadas_etapa": 0, "no_show_etapa": 0,
         "negociacao": 0, "nao_avancou": 0, "agendamentos": 0, "reagendamentos": 0, "realizadas": 0, "no_show": 0,
         "vendas": 0, "valor": 0.0, "sem_valor": 0}
    x = por_prod.get("Aliança") or {}
    a["inscricoes"], a["atendidos"] = x.get("leads", 0), x.get("atendidos", 0)
    for r in ler(f"{p}_etapas.json", []) or []:
        org = (r.get("Origin.name") or "").lower()
        st = (r.get("TrackStage.stage") or "").strip().lower()
        n = int(num(r.get("TrackStage.changeStage")))
        if not org or not st or org.startswith(NAO_LEAD):
            continue
        pn = produto(org, True)
        if pn in f:
            if st.startswith("conex") or st.startswith("respondeu"):
                f[pn]["responderam"] += n
            elif st.startswith("aguardando compra"):
                f[pn]["aguardando"] += n
        elif pn == "Aliança":
            chave = {"formulário respondido": "formulario", "qualificado para sessão estratégico": "qualificados",
                     "sessão estratégica agendada": "agendadas_etapa", "no-show": "no_show_etapa", "em negociação": "negociacao",
                     "não avançou após a sessão estratégica": "nao_avancou"}.get(st)
            if chave:
                a[chave] += n
    for r in ler(f"{p}_reunioes.json", []) or []:
        a["agendamentos"] += int(num(r.get("DealActivity.meetingScheduledActivities")))
        a["reagendamentos"] += int(num(r.get("DealActivity.meetingRescheduledActivities")))
        a["realizadas"] += int(num(r.get("DealActivity.meetingActivities")))
        a["no_show"] += int(num(r.get("DealActivity.noShowActivities")))
    vistos, cad = {}, {}
    mapa = mentoria()
    for r in ler(f"{p}_ganhos_alianca.json", []) or []:
        if r.get("TrackStatus.dealId"):
            vistos[r["TrackStatus.dealId"]] = num(r.get("Deal.value")) / 100
            n = None
            if mapa is not None:
                from mentoria import chave
                n = mapa.get(chave("e", r.get("Contact.email"))) or mapa.get(chave("n", r.get("Contact.name"))) \
                    or mapa.get(chave("n", (r.get("Contact.name") or "").split(" - ")[0]))
            cad[r["TrackStatus.dealId"]] = n
    a["vendas"] = len(vistos)
    a["cadeiras"] = sum(n or 1 for n in cad.values()) if mapa is not None else None
    a["fora_planilha"] = sum(1 for n in cad.values() if not n) if mapa is not None else None
    a["valor"] = round(sum(vistos.values()), 2)
    a["sem_valor"] = sum(1 for v in vistos.values() if not v)
    for pn in f:
        f[pn]["faturamento"] = round(f[pn]["faturamento"], 2)
    return [f[pn] for pn in FOCO], a


def topo(iv):
    """Leads do Active (coleta/active.py). A página calcula qualquer período a partir das linhas."""
    ac = ler("active.json")
    if not ac:
        return None
    inicio = dt.date.fromisoformat("2026-01-01")
    off = lambda d: (dt.date.fromisoformat(d) - inicio).days
    ac["linhas"] = [l for l in ac["linhas"] if not barulho(ac["tags"].get(str(l[2])))]
    usadas = sorted({l[2] for l in ac["linhas"]})
    idx = {t: i for i, t in enumerate(usadas)}
    nomes = [ac["tags"].get(str(t), f"tag {t}") for t in usadas]
    linhas = [[off(l[3]), idx[l[2]], l[1]] for l in ac["linhas"] if l[3] >= inicio.isoformat()]
    novos = [[off(n[1]), n[0]] for n in ac["novos"] if n[1] >= inicio.isoformat()]
    # passagem para o comercial: quem ganhou tag no período e tem negócio de lead criado na Clint no período
    emails = {int(k): v for k, v in (ac.get("emails") or {}).items()}
    clint = {}
    for r in ler("clint_emails.json", []) or []:
        em = (r.get("Contact.email") or "").strip().lower()
        org = (r.get("Origin.name") or "").lower()
        d = (r.get("Deal.createdAt.day") or r.get("Deal.createdAt") or "")[:10]
        if em and d and not org.startswith(NAO_LEAD):
            clint.setdefault(em, set()).add(d)
    passagem = {}
    if clint or emails:
        for p in PERIODOS:
            a, b = iv[p]
            pess = {l[1] for l in ac["linhas"] if a <= l[3] <= b}
            com = [c for c in pess if c in emails]
            na = [c for c in com if any(a <= d <= b for d in clint.get(emails[c], ()))]
            passagem[p] = {"pessoas": len(pess), "na_clint": len(na)}
    return {"inicio": inicio.isoformat(), "tags": nomes, "linhas": linhas, "novos": novos,
            "base_ativa": ac.get("base_ativa") or 0, "passagem": passagem}


def decifrar(env, chave):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    b = lambda x: base64.b64decode(x)
    k = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b(env["sal"]), iterations=env["it"]).derive(chave.encode())
    return json.loads(AESGCM(k).decrypt(b(env["iv"]), b(env["dados"]), None))


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
    elif cmd in ("cifrar", "decifrar") and len(sys.argv) == 4:
        chave = os.environ.get("PLACAR_CHAVE") or sys.exit("Falta PLACAR_CHAVE (login:senha).")
        with open(sys.argv[2]) as h:
            obj = json.load(h)
        with open(sys.argv[3], "w") as h:
            json.dump(cifrar(obj, chave) if cmd == "cifrar" else decifrar(obj, chave), h)
    else:
        print(__doc__)
