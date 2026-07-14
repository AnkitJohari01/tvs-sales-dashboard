"""Quick debug script to trace exactly what happens in the pipeline."""
import pandas as pd
import sys

# Simulate what the user uploaded
csv_path = "april_2026_detailed_forecast.csv"
target_col = "Branch"

print(f"=== DEBUG: Loading {csv_path} ===")
df = pd.read_csv(csv_path, nrows=500)  # small sample for speed
print(f"Shape: {df.shape}")
print(f"Columns: {list(df.columns)}")
print(f"Dtypes:\n{df.dtypes}")
print(f"\nFirst 3 rows:\n{df.head(3)}")

# Check if target is numeric or categorical
print(f"\n=== TARGET COLUMN '{target_col}' ===")
print(f"  dtype: {df[target_col].dtype}")
print(f"  unique values: {df[target_col].nunique()}")
print(f"  sample values: {df[target_col].unique()[:10]}")
print(f"  is_numeric: {pd.api.types.is_numeric_dtype(df[target_col])}")

# What happens when we coerce it to numeric?
coerced = pd.to_numeric(df[target_col], errors="coerce")
print(f"\n  After pd.to_numeric(errors='coerce'):")
print(f"  NaN count: {coerced.isna().sum()} / {len(coerced)}")
print(f"  Non-NaN values: {coerced.dropna().head(5).tolist()}")

# Simulate the preprocessor
from forecasting_engine import DataPreprocessor
prep = DataPreprocessor()
date_col = prep.detect_date_column(df)
print(f"\n=== DATE DETECTION ===")
print(f"  Detected date column: {date_col}")

if date_col:
    dates = pd.to_datetime(df[date_col], errors="coerce")
    print(f"  Min date: {dates.min()}")
    print(f"  Max date: {dates.max()}")
    print(f"  Sample: {dates.head(3).tolist()}")

# Now try the full preprocess
print(f"\n=== FULL PREPROCESS ===")
try:
    df_test = pd.read_csv(csv_path, nrows=500)
    result = prep.preprocess(df_test, target_col)
    print(f"  Result shape: {result.shape}")
    print(f"  Date col: {prep.date_col}")
    print(f"  Target values (first 5): {result[target_col].head(5).tolist()}")
    print(f"  Target dtype: {result[target_col].dtype}")
    print(f"  Target all-zero? {(result[target_col] == 0).all()}")
    print(f"  Target median: {result[target_col].median()}")
except Exception as e:
    print(f"  ERROR: {e}")
    import traceback
    traceback.print_exc()
