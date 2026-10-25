# Coleta Mafra

Automação deste repositório, mantida pela Mafra Assessoria Contábil e Empresarial.

- `fila.json`: o que falta baixar, em ordem de prioridade. A ordem segue a carteira de clientes (regimes, estados, municípios e atividades).
- `executar_fila.py`: roda a fila dentro de um limite de tempo e grava só as pastas de cada tarefa.
- `.github/workflows/coleta-madrugada.yml`: roda todo dia às 03:00 (Brasília) até não sobrar tarefa pendente.
- `.github/workflows/verificacao-semanal.yml`: roda todo domingo às 04:00, atualiza o que já foi concluído e grava o boletim em `alteracoes/AAAA-MM-DD.md`.
- `sondagem.md`: quais fontes oficiais respondem a partir do GitHub. As que bloqueiam acesso de fora do Brasil ficam marcadas `onde: mac-mini` na fila.

Os textos têm caráter informativo e não substituem a publicação oficial.
