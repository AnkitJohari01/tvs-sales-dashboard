"""Debug: show all columns from the uploaded CSV to understand naming patterns."""
import pandas as pd
import sys, os

# Try to find the file
files_to_check = [
    "extended_3year_sales_dataset.csv",
    "april_2026_detailed_forecast.csv",
    "Detailed_April_2026_Forecast_Cleaned.csv",
    "april_2026_daily_forecast_bounds.csv",
]

for f in files_to_check:
    path = os.path.join(".", f)
    if os.path.exists(path):
        print(f"\n{'='*60}")
        print(f"FILE: {f}")
        df = pd.read_csv(path, nrows=3)
        print(f"Columns ({len(df.columns)}):")
        for i, col in enumerate(df.columns):
            dtype = df[col].dtype
            sample = df[col].iloc[0] if len(df) > 0 else "N/A"
            print(f"  [{i:2d}] {col:30s}  dtype={str(dtype):10s}  sample={sample}")
    else:
        print(f"NOT FOUND: {f}")

# Also check what files exist
print(f"\n{'='*60}")
print("All CSV/XLSX files in project root:")
for f in os.listdir("."):
    if f.endswith(('.csv', '.xlsx', '.pkl')):
        size = os.path.getsize(f) / (1024*1024)
        print(f"  {f} ({size:.1f} MB)")
