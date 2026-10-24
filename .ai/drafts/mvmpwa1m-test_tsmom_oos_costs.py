import sys
import os

# Add the project root to the path if necessary, or assume local imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ibtrader.research.tsmom_runner import run_tsmom_research
from ibtrader.settings import AppSettings
import pandas as pd


def _wf_data():
    """
    Fixture function to generate synthetic 320 business day OHLCV data for SPY.
    This replaces the need for an external fixture file or network download.
    
    Returns:
        df: A pandas DataFrame with columns ['date', 'open', 'high', 'low', 'close', 'volume'].
    """
    import numpy as np
    
    # Generate 320 business days starting from a recent date
    end_date = pd.Timestamp("2023-06-01")
    start_date = end_date - pd.offsets.BusinessDay(320)
    
    dates = pd.date_range(start=start_date, end=end_date, freq='B')
    n_days = len(dates)
    
    # Generate synthetic OHLCV data
    base_price = 400.0
    prices = np.cumsum(np.random.randn(n_days)) * 2 + base_price
    
    open_prices = prices[:-1]
    close_prices = prices[1:]
    
    # Ensure high/low bounds
    high_prices = np.maximum(open_prices, close_prices) + np.abs(np.random.randn(n_days-1)) * 0.5
    low_prices = np.minimum(open_prices, close_prices) - np.abs(np.random.randn(n_days-1)) * 0.5
    
    # Generate random volume
    volumes = np.random.randint(100000, 500000, size=n_days)
    
    df = pd.DataFrame({
        'date': dates,
        'open': open_prices,
        'high': high_prices,
        'low': low_prices,
        'close': close_prices,
        'volume': volumes
    }, index=dates)
    
    return df


def test_run_tsmom_research_oos_has_avg_cost_bps():
    """
    Test that run_tsmom_research returns OOS metrics including avg_cost_bps_per_order.
    
    Steps:
    1. Initialize AppSettings.
    2. Generate fixture data (_wf_data).
    3. Call run_tsmom_research with settings, data, ticker='SPY', lookbacks=[21], n_folds=2.
    4. Assert that the first row of results has a key 'avg_cost_bps_per_order'.
    5. Verify that if present, the value is numeric (can be 0).
    """
    
    # Prepare settings
    settings = AppSettings()
    
    # Prepare data
    df = _wf_data()
    
    # Run TSMOM research
    try:
        results_df = run_tsmom_research(
            settings=settings,
            data=df,
            ticker='SPY',
            lookbacks=[21],
            n_folds=2
        )
        
        # Check if the DataFrame is not empty and has 'oos' column
        assert not results_df.empty, "Results dataframe is empty."
        
        # Ensure we are accessing the first row
        first_row = results_df.iloc[0]
        
        # Assert that 'avg_cost_bps_per_order' key exists in the first row (which might be a dict or Series)
        # Depending on how run_tsmom_research structures its output, it often returns a DataFrame where
        # each row corresponds to a model/fold configuration. We assume standard structure.
        
        # If results_df columns are strings like 'oos.avg_cost_bps_per_order' or the row is a dict:
        # Let's handle common return types from such research runners.
        # Common case 1: DataFrame with column names like "oos", then sub-selection happens internally.
        # Common case 2: Dictionary of lists, converted to DF later.
        
        # Robust check: Look for the key in the row data regardless of container type
        found_key = False
        target_value = None
        
        if isinstance(first_row, dict):
            assert 'oos' in first_row, "Missing 'oos' key in first row."
            oos_data = first_row['oos']
            if isinstance(oos_data, dict) and 'avg_cost_bps_per_order' in oos_data:
                found_key = True
                target_value = oos_data['avg_cost_bps_per_order']
        
        elif isinstance(first_row, pd.Series):
            # Check if column name contains the key or if it's nested in attribute access (less likely for direct .iloc)
            # If the DF has columns like 'oos.avg_cost_bps_per_order'
            col_name = 'oos.avg_cost_bps_per_order' if 'oos.avg_cost_bps_per_order' in first_row.index else None
            if col_name is not None and col_name in first_row.index:
                found_key = True
                target_value = first_row[col_name]
            
            # Fallback: check if the value itself contains the key (nested series)
            # Or assume the column name is simply 'avg_cost_bps_per_order' inside an 'oos' context if flattened
            for col in first_row.index:
                if 'avg_cost_bps_per_order' in str(col):
                    found_key = True
                    target_value = first_row[col]
                    break
        
        else:
            # Fallback for any other iterable structure
            assert False, "Unexpected return type from run_tsmom_research."

        # Assert assertion
        assert found_key, f"Key 'avg_cost_bps_per_order' was not found in the OOS metrics of the first row."
        
        # Optionally print or assert value is numeric if possible (value can be 0)
        if target_value is not None:
            assert isinstance(target_value, (int, float)), f"Value of avg_cost_bps_per_order should be numeric, got {type(target_value)}"

    except Exception as e:
        pytest.fail(f"Test failed with exception: {e}")


if __name__ == "__main__":
    test_run_tsmom_research_oos_has_avg_cost_bps()
    print("Test passed.")