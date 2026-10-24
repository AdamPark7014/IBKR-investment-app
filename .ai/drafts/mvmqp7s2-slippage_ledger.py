DEFAULT_LEDGER_PATH = "data/slippage_ledger.jsonl"

def slip_bps(side: str, decision_px: float, fill_px: float) -> float:
    """Calculate slippage in basis points. Positive value indicates adverse slippage."""
    if side.upper() == "BUY":
        return ((fill_px / decision_px) - 1) * 1e4
    elif side.upper() == "SELL":
        return ((decision_px / fill_px) - 1) * 1e4
    else:
        raise ValueError(f"Invalid side: {side}. Must be 'BUY' or 'SELL'.")

def record_slip(path: str, *, symbol: str, side: str, decision_px: float, fill_px: float, qty: float, source: str = "sim"):
    """Append a slippage record to the JSONL ledger."""
    import json
    from datetime import datetime
    
    entry = {
        "decision_ts": datetime.utcnow().isoformat(),
        "symbol": symbol,
        "side": side,
        "decision_px": decision_px,
        "fill_px": fill_px,
        "qty": qty,
        "source": source,
        "slip_bps": slip_bps(side, decision_px, fill_px)
    }
    
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")

def summarize(path: str, window_days: int = 30, by_symbol: bool = False):
    """Summarize slippage statistics for the given path."""
    from datetime import datetime, timedelta
    
    def _read_entries(window_days: int):
        cutoff_date = (datetime.utcnow() - timedelta(days=window_days)).isoformat()
        
        entries = []
        with open(path, "r") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if entry.get("decision_ts", "") >= cutoff_date:
                        entries.append(entry)
                except json.JSONDecodeError:
                    continue
        return entries
    
    entries = _read_entries(window_days)
    
    if not entries:
        return {
            "n": 0,
            "mean_slip_bps": None,
            "p95_slip_bps": None,
            "by_symbol": {}
        }
    
    slips = [e["slip_bps"] for e in entries]
    n = len(slips)
    mean_slip = sum(slips) / n
    
    sorted_slips = sorted(slips)
    p95_index = int(0.95 * (n - 1)) if n > 0 else 0
    p95_slip = sorted_slips[min(p95_index, n - 1)]
    
    result = {
        "n": n,
        "mean_slip_bps": mean_slip,
        "p95_slip_bps": p95_slip
    }
    
    if by_symbol:
        symbol_stats = {}
        for entry in entries:
            sym = entry["symbol"]
            slip = entry["slip_bps"]
            if sym not in symbol_stats:
                symbol_stats[sym] = {"slips": [], "count": 0}
            symbol_stats[sym]["slips"].append(slip)
            symbol_stats[sym]["count"] += 1
        
        final_by_symbol = {}
        for sym, data in symbol_stats.items():
            slips_list = data["slips"]
            final_by_symbol[sym] = {
                "n": len(slips_list),
                "mean_slip_bps": sum(slips_list) / len(slips_list) if slips_list else None,
                "p95_slip_bps": sorted(slips_list)[int(0.95 * (len(slips_list) - 1))] if slips_list else None
            }
        result["by_symbol"] = final_by_symbol
    
    return result