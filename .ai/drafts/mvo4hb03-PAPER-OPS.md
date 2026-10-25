ibtrader autopilot              # triage + UI; opcional --use-ai (puerta IA, sin noticias)
ibtrader paper-reconcile        # desired vs data/paper_positions.json (+ slippage si hay ledger)
ibtrader paper-stack            # desired/held/drift → data/paper_stack.sqlite
ibtrader paper-vs-oos           # DD paper vs Sharpe/DD OOS asumidos (kill_recommend)
ibtrader slippage-report        # resumen de data/slippage_ledger.jsonl
ibtrader ibc-checklist          # checklist Gateway/IBC (manual; no instala)
ibtrader config-freeze          # --verify (default) o --write → paper_config_freeze.json
ibtrader paper-equity           # solo si el CLI existe; si no, equity via autopilot