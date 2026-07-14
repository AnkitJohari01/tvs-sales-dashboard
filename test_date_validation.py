import pandas as pd

def _is_valid_date_column(series: pd.Series) -> bool:
    sample = series.dropna().head(50)
    if len(sample) == 0:
        return False
    try:
        parsed = pd.to_datetime(sample, errors="coerce", format='mixed')
        valid = parsed.dropna()
        print(f"Valid length: {len(valid)} / {len(sample)}")
        if len(valid) < len(sample) * 0.5:
            return False
        years = valid.dt.year
        print(f"Years: min={years.min()}, max={years.max()}")
        if years.min() < 1990 or years.max() > 2100:
            return False
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

# Test cases
test_cases = [
    pd.Series(["2023-01-01", "2023-01-02", "2023-01-03"]),
    pd.Series(["01/01/2023", "02/01/2023", "03/01/2023"]),
    pd.Series(["01-Jan-2023", "02-Jan-2023", "03-Jan-2023"]),
    pd.Series(["2023-01-01 12:00:00", "2023-01-02 12:00:00", "2023-01-03 12:00:00"]),
    pd.Series(["1970-01-01", "1970-01-02", "1970-01-03"]), # UNIX epoch failure
    pd.Series([14251271, 14251272, 14251273]), # InvoiceNo
]

for i, tc in enumerate(test_cases):
    print(f"\nTest Case {i+1}:")
    print(_is_valid_date_column(tc))
