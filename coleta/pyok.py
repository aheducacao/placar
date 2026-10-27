"""Garante um Python em que a criptografia funciona antes de rodar os scripts.

O ambiente da rotina às vezes vem com o `python3` padrão sem a biblioteca de
criptografia funcionando (ex.: binário compilado para outra versão do Python).
`garantir()` testa o Python atual; se não servir, procura outro já instalado;
se nenhum servir, cria um ambiente próprio fora do repositório e instala a
biblioteca. Depois reinicia o mesmo comando com o Python bom.
"""
import os, shutil, subprocess, sys

TESTE = "from cryptography.hazmat.primitives.ciphers.aead import AESGCM; AESGCM(b'0'*32)"
VENV = os.path.expanduser("~/.placar-venv")
MARCA = "PLACAR_PY_OK"


def _funciona(py):
    try:
        return subprocess.run([py, "-c", TESTE], capture_output=True, timeout=60).returncode == 0
    except Exception:
        return False


def _candidatos():
    vistos = []
    for c in [sys.executable, os.path.join(VENV, "bin", "python"), "/usr/bin/python3",
              "/usr/local/bin/python3", *(shutil.which(f"python3.{m}") or "" for m in range(14, 9, -1)),
              shutil.which("python3") or ""]:
        if c and os.path.exists(c) and os.path.realpath(c) not in [os.path.realpath(v) for v in vistos]:
            vistos.append(c)
    return vistos


def _criar_venv():
    py_venv = os.path.join(VENV, "bin", "python")
    for base in _candidatos():
        if base == py_venv:
            continue
        try:
            shutil.rmtree(VENV, ignore_errors=True)
            subprocess.run([base, "-m", "venv", VENV], check=True, capture_output=True, timeout=300)
            subprocess.run([py_venv, "-m", "pip", "install", "-q", "cryptography"], check=True,
                           capture_output=True, timeout=600)
            if _funciona(py_venv):
                return py_venv
        except Exception:
            continue
    return None


def garantir():
    if os.environ.get(MARCA) == sys.executable:
        return
    bom = next((c for c in _candidatos() if _funciona(c)), None) or _criar_venv()
    if not bom:
        sys.exit("Nenhum Python com criptografia funcionando, e não consegui instalar (pip).")
    os.environ[MARCA] = bom
    if os.path.realpath(bom) == os.path.realpath(sys.executable):
        return
    sys.stdout.flush(); sys.stderr.flush()
    os.execv(bom, [bom, os.path.abspath(sys.argv[0]), *sys.argv[1:]])
