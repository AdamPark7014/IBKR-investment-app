# Institutional systematic stack — research synthesis (V3)

**Purpose:** Document how serious systematic desks actually build and reject trading systems, and map that onto IBKR-investment-app.  
**Not a promise of edge.** Most researched ideas fail OOS; that is the point of the lab.

Sources consulted (public):

* QuantJourney — walk-forward vs slice-diagnostics; research workflow gates  
  <https://backtester.quantjourney.cloud/research/walkforward-case-study>  
  <https://backtester.quantjourney.cloud/research/strategy-research-workflow>
* Practitioner write-up on quant HF signal vetting (costs, OOS length, decay)  
  <https://youngandcalculated.substack.com/p/how-quant-hedge-funds-actually-build>
* López de Prado — purged/embargo CV, CPCV, PBO (AFML / SSRN 2326253)
* AQR — momentum/trend evidence + live trading-cost realism  
  <https://www.aqr.com/Insights/Research/Journal-Article/Fact-Fiction-and-Momentum-Investing>  
  <https://www.aqr.com/Insights/Research/Working-Paper/Implementing-Momentum-What-Have-We-Learned>
* Example open research frameworks emphasizing WFO + cost realism  
  <https://github.com/DaruFinance/quant-research-framework>

---

## 1. What giants actually optimize

They do **not** primarily optimize “make CAGR huge and never lose.” They optimize a **pipeline**:

1. **Hypothesis** with an economic loser (who pays you?).
2. **Point-in-time data** + lineage (no silent fills, no future peek).
3. **Features / signals** with known horizon (decay / half-life).
4. **Costs first** (commission, spread, slippage, impact, funding).
5. **Validation geometry fixed before search** (walk-forward folds, purge/embargo).
6. **Multiple-testing control** (log every trial; DSR / PBO-style skepticism).
7. **Capacity / liquidity** checks before scaling.
8. **Paper → staged capital** — research alpha ≠ production alpha.

A signal that is strong gross and dies net-of-cost is rejected early.

---

## 2. Walk-forward: evidence vs diagnostics

Institutional distinction that matter for this repo:

| Mode | What it is | Claim allowed |
|------|------------|---------------|
| **Slice diagnostics** | One full-period run, then cut the equity path | “Where did PnL concentrate?” — **not** OOS discipline |
| **Per-fold re-fit WFO** | Re-train/select inside each fold; stitch OOS | Legitimate OOS path for that selection rule |

Our P9 `walk_forward_sma` is the second kind (grid search on val, frozen params on test, stitched OOS). V3 research **must keep using that**, not single-shot full-sample Sharpe shopping.

---

## 3. Leakage controls (López de Prado family)

For labels with horizon / overlapping outcomes:

* **Purge** overlapping label windows between train and test.
* **Embargo** a gap after test to kill serial dependence.
* **CPCV** builds many OOS paths (distribution of Sharpes), not one lucky path.
* **PBO / CSCV** estimates probability that the *selected* config is overfit.

V3 slice: document + gate helpers; full CPCV engine can land in a later slice. Existing purged CV tests in the repo remain the baseline.

---

## 4. Cost & capacity realism (AQR lesson)

Academic portfolios that ignore patient execution **overstate** costs for institutions *or* understate impact for small accounts — both errors exist. For IBKR retail/paper:

* Keep **engine commission + slippage on by default** in research runs.
* Stress **2× costs**; if the candidate dies, reject.
* Prefer medium holding periods when turnover explodes Sharpe.

---

## 5. Mapping onto this codebase

| Institutional piece | Already in repo | V3 adds |
|---------------------|-----------------|---------|
| Next-open execution | backtest engine | — |
| Risk FSM / kill / stops | risk package | research rejects lockout-dominated runs |
| Walk-forward SMA | `validation/walkforward.py` | multi-candidate research runner |
| Artifacts + hashes | `ops/artifacts.py` | experiment JSONL registry |
| Suspicious diagnostics | `diagnostics/suspicious.py` | OOS gate object |
| Regime GMM | `regime/gmm.py` | optional candidate with regime gate |

---

## 6. Honest expectation for SMA-on-SPY

Owner-PC baselines already show **B&H >> SMA** on recent SPY OOS. Institutional process applied to a single-name SMA book often yields:

* **Reject** under OOS gates, or
* Modest positive Sharpe with wide uncertainty — not “never lose.”

V3 success = **lab that can reject honestly**, plus any candidate that clears SPEC-v3 §3 gates for owner-PC re-run.

---

## 7. Research slices (status)

| Slice | Status |
|-------|--------|
| Cost-ladder stress (1× / 2× / 3× slippage) | **DONE** — `research.cost_stress` + suite track |
| Embargo width sensitivity report | **DONE** — `research.embargo_sensitivity` |
| Multi-asset universe (not only SPY) | **DONE** — `research.multi_asset` (SPY/QQQ/IWM/EFA/TLT) |
| Time-series momentum candidate (TSMOM) | **DONE** — `strategy.tsmom` + `research.tsmom_runner` |
| Mean-reversion (Bollinger) family | **DONE** — `research.mean_reversion_runner` |
| PBO estimate across the logged trial grid | **DONE** — CSCV-lite `research.pbo` + `pbo_sma` |
| CPCV-lite OOS Sharpe path distribution | **DONE** — `research.cpcv` + `cpcv_sma` |
| Deflated Sharpe Ratio (DSR) | **DONE** — `research.dsr` + `dsr_sma` |
| Turnover fragility diagnostic | **DONE** — `research.turnover_diag` |
| Honest PASS/FAIL report aggregator | **DONE** — `research.report` → `honest_report` |
| Multi-factor market analyzer (triage) | **DONE** — `research.market_analyzer` (WARDEN-X7 multi-engine) + CLI `market-analyze` |
| WARDEN research command panel | **DONE** — `research.panel` + CLI `research-panel` (HTML mission surface) |
| Loss-mitigation overlays (trend / stop / DD / vol) | **DONE** — `research.loss_mitigation` |
| Cross-sectional momentum rotation | **DONE** — `research.xsection_runner` |

Do not skip to “live large size” without paper evidence.

### Phase-2 reading notes

* **PBO** asks whether the *selected* trial underperforms peers OOS (selection risk).
* **DSR** asks whether the selected Sharpe beats what multiple-testing luck alone would produce.
* **CPCV-lite** asks whether OOS Sharpe is stable across combinatorial fold paths.
* A candidate can PASS §3 gates and still be `PASS_GATES_BUT_DIAGNOSTICS_SKEPTICAL` in `honest_report`.

### Loss mitigation & market analyzer (honest charter)

* Goal: **lose less / avoid hostile regimes first** — not “ganar muchísimo.”
* `market-analyze` emits AVOID / WATCH / RESEARCH_CANDIDATE only.
* `RESEARCH_CANDIDATE` ≠ buy order. It means: worth owner-PC walk-forward re-run.
* Overlays that improve max DD but kill Sharpe are still useful research outcomes.
