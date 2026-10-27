#!/usr/bin/env python3
"""Cadeiras da Aliança: quantas pessoas cada empresa tem na base da mentoria.

  PLACAR_CHAVE=... python3 coleta/mentoria.py <arquivo exportado da planilha "Base de dados AH Mentoria 2026">

Lê a aba "Base de dados 2026", conta as pessoas por empresa e grava coleta/mentoria.enc.json
só com resumos (hash do e-mail e do nome -> número de pessoas da empresa), cifrado.
Nenhum nome, e-mail ou telefone vai para o repositório.
"""
import csv, hashlib, io, json, os, re, sys, unicodedata, collections

AQUI = os.path.dirname(os.path.abspath(__file__))
ABA = "Base de dados 2026"


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s).strip()


def chave(tipo, valor):
    return hashlib.sha256(f"{tipo}:{norm(valor)}".encode()).hexdigest()[:20]


def ler_aba(caminho):
    txt = open(caminho, encoding="utf-8").read()
    partes = re.split(r"^## Sheet name: (.*)$", txt, flags=re.M)
    if len(partes) > 1:
        abas = {partes[i].strip(): partes[i + 1] for i in range(1, len(partes), 2)}
        txt = abas.get(ABA) or sys.exit(f"Não achei a aba '{ABA}'.")
    return list(csv.reader(io.StringIO(txt.strip())))


def main(caminho):
    chave_placar = os.environ.get("PLACAR_CHAVE") or sys.exit("Falta PLACAR_CHAVE (login:senha).")
    linhas = ler_aba(caminho)
    cab = [c.strip() for c in linhas[0]]
    iE, iN, iC = cab.index("E-mail"), cab.index("Nome Completo"), cab.index("Empresa")
    pessoas = [r for r in linhas[1:] if len(r) > iC and (norm(r[iN]) or norm(r[iE]))]
    tam = collections.Counter(norm(r[iC]) for r in pessoas if norm(r[iC]))
    mapa = {}
    for r in pessoas:
        n = tam.get(norm(r[iC]), 1) or 1
        for tipo, v in (("e", r[iE]), ("n", r[iN])):
            if norm(v):
                mapa[chave(tipo, v)] = n
    sys.path.insert(0, AQUI)
    from build import cifrar
    with open(os.path.join(AQUI, "mentoria.enc.json"), "w") as h:
        json.dump(cifrar({"mapa": mapa, "pessoas": len(pessoas), "empresas": len(tam)}, chave_placar), h)
    print("mentoria ok:", len(pessoas), "pessoas em", len(tam), "empresas")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
    else:
        from pyok import garantir; garantir()
        main(sys.argv[1])
