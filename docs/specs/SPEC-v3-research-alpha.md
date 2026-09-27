# V3 — RESEARCH / ALPHA LABORATORY (owner-authorized)

**Status:** ACTIVE  
**Authorized by:** Adam (owner), chat 2026-09-26/27 — request for `/research` institucional + multi-agent implementation.  
**Base correctness head (do not rewrite history):** `0577f2f` (P6–P9 correction round APPROVED).  
**Working branch:** `cursor/v3-research-alpha-de83`

---

## 0. Relationship to REGLA CERO

`SPEC-v2-final-correction-round.md` REGLA CERO remains binding for the **correctness** line (`cursor/ibkr-algo-trader-35c8` / `cursor/p6-p9-hardening-report-35c8`).

This V3 document **opens a separate research phase** on a **new branch**. On this branch only:

* strategy parameters, signals, filters, and feature candidates **MAY** be changed for research;
* every claim of improvement MUST be backed by **walk-forward / purged OOS** evidence;
* the correctness head MUST NOT be force-pushed or silently altered.

---

## 1. Honest objective (non-negotiable)

Goal: build an **institutional-grade research laboratory** and evaluate alpha candidates with the same discipline used by systematic desks — not to claim “almost never lose.”

Forbidden claims:

* guaranteed profits;
* “almost never lose”;
* in-sample-only superiority over Buy&Hold presented as edge.

Allowed outcomes:

* candidate rejected (most likely);
* candidate passes OOS gates with documented costs;
* infrastructure improvements even when no alpha is found.

---

## 2. What “Wall Street heavy” means here

Implement process, not mythology:

1. **Research → Spec → Code → Backtest → Walk-forward → Risk → Paper → Live**
2. **Transaction-cost aware** evaluation (commission + slippage already in engine)
3. **No look-ahead**; expanding/refit regimes; embargo where applicable
4. **Experiment registry** (config hash, dataset hash, commit, metrics)
5. **Candidate strategies** behind a clear interface; selection only on validation, report on OOS
6. **Diagnostics** for overfitting, turnover, restriction lockouts

---

## 3. Deliverables for this round

### Docs

* `docs/research/INSTITUTIONAL_SYSTEMATIC_STACK.md` — synthesis of institutional practices (sourced)
* This SPEC

### Code (minimum)

* `src/ibtrader/research/` package:
  * experiment runner
  * candidate registry
  * OOS gate helpers
* At least **two** research candidates beyond baseline SMA 10/30 (e.g. dual-SMA grid research report + trend+regime gated variant) evaluated via existing walk-forward / backtest APIs
* CLI: `ibtrader research-run` (fixture-safe)
* Tests for registry, gates, and CLI smoke
* No committed `data/KILL_SWITCH`; no real-cache mutation

### Gates to mark a candidate “interesting”

All of:

* OOS Sharpe ≥ 0 **after** costs on stitched walk-forward; AND
* OOS max DD not worse than B&H max DD by > 5 absolute pp without justification; AND
* trade_count ≥ 5 on stitched OOS; AND
* no kill-switch / cumulative-loss lockout dominating the sample (>50% bars restricted → reject)

Passing gates ≠ deploy. Passing gates = “worth owner-PC re-run.”

---

## 4. Multi-agent work split

* Agent A — research synthesis (docs)
* Agent B — research package + experiment registry
* Agent C — candidate strategies + WF evaluation harness
* Agent D — CLI + tests + CI hygiene

Merge only after local ruff/mypy/pytest green.

---

## 5. STOP condition for this V3 slice

Stop when:

* SPEC + research doc committed;
* research package + ≥1 CLI path + tests green on CI;
* honest report lists candidates PASS/FAIL under §3 gates;
* PR opened against `dev` or stacked on correctness PR as draft research PR.

Do **not** merge V3 into the correctness-only narrative as “APPROVED edge.”
