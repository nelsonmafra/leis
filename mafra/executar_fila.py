"""Executa a fila de coleta (mafra/fila.json) dentro de um orçamento de tempo.

Modos:
  coleta   -> roda tarefas 'pendente'/'em_andamento' com onde=actions, em ordem de prioridade,
              até acabar o orçamento. Tarefa termina sem erro -> 'concluida'.
  semanal  -> roda de novo as tarefas 'concluida' (atualização incremental: os coletores
              pulam o que já existe) e gera o boletim mafra/alteracoes/AAAA-MM-DD.md.

Cada tarefa grava e envia (commit + push) só as pastas dela. O log das últimas linhas
fica em mafra/logs/<id>.txt.
"""
import argparse
import datetime as dt
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FILA = RAIZ / "mafra" / "fila.json"
LOGS = RAIZ / "mafra" / "logs"
ALTERACOES = RAIZ / "mafra" / "alteracoes"
FUSO = dt.timezone(dt.timedelta(hours=-3))


def sh(*args, check=True, **kw):
    return subprocess.run(list(args), cwd=RAIZ, check=check, text=True, capture_output=True, **kw)


def ler_fila():
    return json.loads(FILA.read_text(encoding="utf-8"))


def gravar_fila(fila):
    FILA.write_text(json.dumps(fila, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def enviar(paths, mensagem):
    """Commit só dos caminhos dados e push com até 5 tentativas de rebase."""
    sh("git", "add", "-A", "--", *paths, check=False)
    if not sh("git", "diff", "--cached", "--quiet", check=False).returncode:
        return 0
    n = len(sh("git", "diff", "--cached", "--name-only").stdout.splitlines())
    sh("git", "commit", "-q", "-m", mensagem)
    for tentativa in range(5):
        if sh("git", "push", "origin", "HEAD:main", check=False).returncode == 0:
            return n
        sh("git", "pull", "--rebase", "-q", "origin", "main", check=False)
        time.sleep(5 * (tentativa + 1))
    raise RuntimeError("push falhou após 5 tentativas")


def rodar(tarefa, limite_seg, limite_itens):
    hoje = dt.datetime.now(FUSO).strftime("%d/%m/%Y")
    cmd = tarefa["comando"].format(hoje=hoje)
    if limite_itens:
        cmd += f" --limite {limite_itens}"
    sh("git", "sparse-checkout", "add", *tarefa["pastas"])
    LOGS.mkdir(parents=True, exist_ok=True)
    print(f"\n=== {tarefa['id']}: {cmd} (até {limite_seg // 60} min)", flush=True)
    inicio = time.time()
    proc = subprocess.Popen(cmd, shell=True, cwd=RAIZ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, start_new_session=True)
    cauda = []
    esgotou = False
    for linha in proc.stdout:
        print(linha, end="", flush=True)
        cauda = (cauda + [linha])[-60:]
        if time.time() - inicio > limite_seg:
            esgotou = True
            os.killpg(proc.pid, signal.SIGINT)
            try:
                proc.wait(timeout=120)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
            break
    codigo = proc.wait()
    (LOGS / f"{tarefa['id']}.txt").write_text("".join(cauda), encoding="utf-8")
    return codigo, esgotou, int(time.time() - inicio)


def titulo(path):
    try:
        cab = path.read_text(encoding="utf-8", errors="ignore")[:3000]
    except OSError:
        return path.name
    t = re.search(r'^titulo:\s*"?(.*?)"?\s*$', cab, re.M)
    e = re.search(r'^ementa:\s*"?(.*?)"?\s*$', cab, re.M)
    texto = t.group(1) if t else path.stem
    if e and e.group(1):
        texto += " — " + e.group(1)[:220]
    return texto


def boletim(fila):
    pastas = sorted({p for t in fila["tarefas"] for p in t["pastas"]})
    desde = (dt.datetime.now(FUSO) - dt.timedelta(days=8)).strftime("%Y-%m-%d")
    saida = sh("git", "log", f"--since={desde}", "--diff-filter=AM", "--name-status", "--format=", "--", *pastas,
               check=False).stdout
    novos, alterados = {}, {}
    for linha in saida.splitlines():
        partes = linha.split("\t")
        if len(partes) != 2 or not partes[1].endswith(".md"):
            continue
        destino = novos if partes[0] == "A" else alterados
        grupo = "/".join(partes[1].split("/")[:2])
        destino.setdefault(grupo, set()).add(partes[1])
    hoje = dt.datetime.now(FUSO)
    linhas = [f"# Alterações na legislação — semana até {hoje:%d/%m/%Y}", ""]
    if not novos and not alterados:
        linhas.append("Nenhuma norma nova ou alterada nas fontes monitoradas nesta semana.")
    for rotulo, dados in (("Normas novas", novos), ("Normas com texto alterado", alterados)):
        if not dados:
            continue
        linhas += [f"## {rotulo}", ""]
        for grupo in sorted(dados):
            arquivos = sorted(dados[grupo], reverse=True)
            linhas.append(f"### {grupo} ({len(arquivos)})")
            for a in arquivos[:300]:
                linhas.append(f"- [{titulo(RAIZ / a)}](../../{a})")
            if len(arquivos) > 300:
                linhas.append(f"- … e mais {len(arquivos) - 300}")
            linhas.append("")
    ALTERACOES.mkdir(parents=True, exist_ok=True)
    destino = ALTERACOES / f"{hoje:%Y-%m-%d}.md"
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    enviar(["mafra/alteracoes"], f"Boletim semanal de alterações {hoje:%d/%m/%Y}")
    print("boletim:", destino, flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--modo", choices=["coleta", "semanal"], default="coleta")
    ap.add_argument("--orcamento-min", type=int, default=330)
    ap.add_argument("--tarefa", default="", help="roda só esta tarefa (teste)")
    ap.add_argument("--limite", type=int, default=0, help="repassa --limite ao coletor (teste)")
    args = ap.parse_args()

    fim = time.time() + args.orcamento_min * 60
    fila = ler_fila()
    if args.tarefa:
        escolhidas = [t for t in fila["tarefas"] if t["id"] == args.tarefa]
    elif args.modo == "coleta":
        escolhidas = [t for t in fila["tarefas"] if t["onde"] == "actions" and t["comando"]
                      and t["status"] in ("pendente", "em_andamento")]
    else:
        escolhidas = [t for t in fila["tarefas"] if t["onde"] == "actions" and t["comando"]
                      and t["status"] == "concluida"]
    escolhidas.sort(key=lambda t: t["prioridade"])
    if not escolhidas:
        print("nada a fazer nesta execução", flush=True)

    for tarefa in escolhidas:
        restante = int(fim - time.time()) - 600  # 10 min de folga para gravar e enviar
        if restante < 600:
            print("orçamento de tempo esgotado; o restante fica para a próxima execução", flush=True)
            break
        codigo, esgotou, segundos = rodar(tarefa, restante, args.limite)
        quando = dt.datetime.now(FUSO).strftime("%Y-%m-%d %H:%M")
        n = enviar(tarefa["pastas"], f"Coleta {tarefa['id']} ({args.modo}) {quando}")
        tarefa["ultima_execucao"] = quando
        tarefa["ultimo_resultado"] = "tempo esgotado (continua)" if esgotou else f"código {codigo}"
        tarefa["arquivos_ultima_execucao"] = n
        tarefa["arquivos_acumulados"] = tarefa.get("arquivos_acumulados", 0) + n
        if args.modo == "coleta" and not args.limite:
            if not esgotou and codigo in (0, 1):
                # percorreu a fonte inteira; itens que a fonte não fornece ficam no _falhas do coletor
                tarefa["status"] = "concluida"
            else:
                tarefa["status"] = "em_andamento"
                tarefa["execucoes_sem_avanco"] = 0 if n else tarefa.get("execucoes_sem_avanco", 0) + 1
                if tarefa["execucoes_sem_avanco"] >= 5:
                    tarefa["status"] = "bloqueada"
        gravar_fila(fila)
        enviar(["mafra/fila.json", "mafra/logs"], f"Fila: {tarefa['id']} -> {tarefa['status']}")

    if args.modo == "semanal" and not args.tarefa:
        boletim(fila)
    return 0


if __name__ == "__main__":
    sys.exit(main())
