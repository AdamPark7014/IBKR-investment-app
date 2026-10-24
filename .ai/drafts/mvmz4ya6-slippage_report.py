from slippage_ledger import SlippageLedger

def summarize_cli(ledger, columns=None):
    """
    CLI wrapper for the SlippageLedger.summarize method.
    Calls the ledger's summarize function and returns its result dictionary unchanged.
    """
    result = ledger.summarize(columns=columns)
    return result