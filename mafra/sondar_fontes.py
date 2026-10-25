"""Testa se as fontes oficiais respondem a partir de onde o script roda.

Uso: python3 mafra/sondar_fontes.py  -> grava mafra/sondagem.md
Só faz uma requisição leve por fonte (GET da página ou consulta de 5 itens).
"""
import datetime as dt
import json
import ssl
import time
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

SIJUT = {
    "tipoPesquisa": "formulario", "termo": "CGSN", "tipoData": "dataPublicacao",
    "dataInicio": "01/01/2006", "dataFim": "25/10/2026", "anoAto": "", "numeroAto": "",
    "apenasAtosVigentes": False, "apenasAtosInternos": False, "publicado": True, "internet": True,
    "orgaosSelecionados": "", "tiposAtosSelecionados": "", "refino": {}, "ordenacaoColuna": "publicacao",
    "ordenacaoDirecao": "desc", "paginacaoPaginaAtual": 1, "paginacaoQuantidadePorPagina": 5,
}

FONTES = [
    # (grupo, nome, url, corpo_json)
    ("Federal", "Receita Federal - Sijut (busca, termo CGSN)", "https://normas.receita.fazenda.gov.br/api/indexacao/ato/pesquisar", SIJUT),
    ("Federal", "Receita Federal - Sijut (texto dos atos)", "https://normasinternet2.receita.fazenda.gov.br/", None),
    ("Federal", "Diário Oficial da União", "https://www.in.gov.br/leiturajornal?data=23-10-2026&secao=do1", None),
    ("Federal", "Planalto (LC 123)", "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm", None),
    ("Federal", "normas.leg.br", "https://normas.leg.br/?urn=urn:lex:br:federal:lei.complementar:2006-12-14;123", None),
    ("Federal", "Senado - dados abertos", "https://legis.senado.leg.br/dadosabertos/legislacao/lista?ano=2026&tipo=LCP", None),
    ("Federal", "CONFAZ", "https://www.confaz.fazenda.gov.br/legislacao/convenios", None),
    ("SP", "SEFAZ-SP legislação (RICMS)", "https://legislacao.fazenda.sp.gov.br/Paginas/dec45490.aspx", None),
    ("SP", "ALESP", "https://www.al.sp.gov.br/norma/139216", None),
    ("Municipal", "Campinas - Biblioteca Jurídica", "https://bibjuri.campinas.sp.gov.br/", None),
    ("Municipal", "Campinas - portal / Diário Oficial", "https://portal-api.campinas.sp.gov.br/", None),
    ("Municipal", "São Paulo capital - legislação", "https://legislacao.prefeitura.sp.gov.br/", None),
    ("MG", "SEF-MG (RICMS)", "https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/ricms_2002_seco/", None),
    ("MS", "SEFAZ-MS", "https://www.sefaz.ms.gov.br/", None),
]


def sondar(url, corpo):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    cab = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "pt-BR,pt;q=0.9"}
    if dados:
        cab["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=dados, headers=cab)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=40, context=ssl.create_default_context()) as r:
            bruto = r.read()
            extra = ""
            if corpo is not None:
                try:
                    extra = f"total={json.loads(bruto).get('quantidadeTotal')}"
                except Exception:
                    extra = "resposta não-JSON"
            return r.status, len(bruto), time.time() - t0, extra
    except urllib.error.HTTPError as e:
        return e.code, 0, time.time() - t0, str(e.reason)[:60]
    except Exception as e:
        return "falha", 0, time.time() - t0, f"{type(e).__name__}: {str(e)[:80]}"


def main():
    linhas = [
        "# Sondagem de fontes",
        "",
        f"Executada em {dt.datetime.now(dt.timezone.utc):%d/%m/%Y %H:%M} UTC.",
        "",
        "| Grupo | Fonte | Resultado | Bytes | Segundos | Obs. |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for grupo, nome, url, corpo in FONTES:
        status, tam, seg, obs = sondar(url, corpo)
        ok = "✅" if status == 200 else "❌"
        linhas.append(f"| {grupo} | {nome} | {ok} {status} | {tam} | {seg:.1f} | {obs} |")
        print(grupo, nome, status, tam, f"{seg:.1f}s", obs, flush=True)
        time.sleep(1)
    Path(__file__).with_name("sondagem.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
