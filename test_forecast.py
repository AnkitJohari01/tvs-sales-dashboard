import urllib.request, json, sys

url = 'https://tvs-sales-dashboard.onrender.com/forecast'
payload = json.dumps({"start_date": "2026-04-01", "days": 30}).encode('utf-8')
req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'}, method='POST')

try:
    response = urllib.request.urlopen(req, timeout=120)
    data = json.loads(response.read().decode('utf-8'))
    print(f"Status: OK")
    print(f"Model: {data.get('model')}")
    print(f"Total rows: {data.get('total_rows')}")
    print(f"Forecast array length: {len(data.get('forecast', []))}")
    if data.get('forecast'):
        print(f"First row keys: {list(data['forecast'][0].keys())}")
        print(f"First row: {data['forecast'][0]}")
except Exception as e:
    print(f"Error: {e}")
    if hasattr(e, 'read'):
        body = e.read().decode('utf-8')
        print(f"Response body: {body}")
