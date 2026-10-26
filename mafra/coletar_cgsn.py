"""Simples Nacional: baixa todos os atos do Comitê Gestor (CGSN) publicados no Sijut da Receita.

Reaproveita o coletor da Receita (scripts/baixar_rfb.py): mesmo formato, mesma pasta
(reguladores/rfb/<ano>/rfb-sijut-<id>.md) e mesma checagem de duplicatas. A diferença é o
recorte: só o órgão CGSN (id 51 no Sijut), em qualquer data, para não esperar a fila geral.
Retomável: pula o que já existe.

Uso: python3 -I mafra/coletar_cgsn.py [--rps 2] [--limite N]
"""
import argparse
import gzip
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import baixar_rfb as rfb  # noqa: E402
from comum import Rede  # noqa: E402

ORGAO_CGSN = "51"


def indice(rede):
    base = dict(tipoPesquisa="formulario", termo="", tipoData="dataPublicacao", dataInicio="01/01/1800",
                dataFim="31/12/2100", anoAto="", numeroAto="", apenasAtosVigentes=False, apenasAtosInternos=False,
                publicado=True, internet=True, orgaosSelecionados=ORGAO_CGSN, tiposAtosSelecionados="", refino={},
                ordenacaoColuna="publicacao", ordenacaoDirecao="desc", paginacaoPaginaAtual=1,
                paginacaoQuantidadePorPagina=100)
    atos, pagina, total = {}, 1, None
    while True:
        # sem cache: o índice tem que refletir a fonte de hoje (são só ~3 páginas)
        rede.limite.esperar()
        req = urllib.request.Request(rfb.BUSCA, data=json.dumps({**base, "paginacaoPaginaAtual": pagina}).encode(),
                                     headers={**rede.headers, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=45) as r:
            bruto = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                bruto = gzip.decompress(bruto)
            resp = json.loads(bruto)
        total = int(resp["quantidadeTotal"])
        if not resp.get("atos"):
            break
        for a in resp["atos"]:
            atos[str(a["idAto"])] = {k: a.get(k) for k in ("idAto", "numeroAto", "anoAto", "dataAto",
                                                             "dataPublicacao", "tipoAto", "urlVisualizacao")}
        if len(atos) >= total:
            break
        pagina += 1
    print(f"índice CGSN: {len(atos)}/{total}", flush=True)
    return list(atos.values()), total


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rps", type=float, default=2)
    ap.add_argument("--limite", type=int, default=0)
    args = ap.parse_args()
    rede = Rede(args.rps)
    atos, total = indice(rede)
    rfb.equivalentes()
    contagem, erros = {"ok": 0, "skip": 0, "equivalente": 0, "pendente_estrutura": 0}, 0
    for item in atos:
        try:
            resultado = rfb.processar(rede, item)
            contagem[resultado] += 1
            print(resultado, item["idAto"], contagem, flush=True)
        except Exception as exc:
            erros += 1
            with (rfb.RAIZ / "_falhas_sijut.jsonl").open("a") as f:
                f.write(json.dumps({"fonte": "rfb-sijut-cgsn", "idAto": item["idAto"], "erro": str(exc)},
                                   ensure_ascii=False) + "\n")
            print("erro", item["idAto"], str(exc), flush=True)
            if rfb.acesso_recusado(exc):
                return 2
        if args.limite and sum(contagem.values()) + erros >= args.limite:
            break
    print("FIM CGSN", contagem, "erros", erros, "índice", len(atos), "/", total, flush=True)
    return 0 if len(atos) == total and not erros else 1


if __name__ == "__main__":
    sys.exit(main())
