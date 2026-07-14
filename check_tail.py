import pandas as pd
df = pd.read_csv('Detailed_April_2026_Forecast_Cleaned.csv', nrows=500000)
print(df['Forecast_Date'].tail(10))
