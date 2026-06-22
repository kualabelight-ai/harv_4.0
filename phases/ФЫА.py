import json
from pathlib import Path

project_file = Path("sites/steelborg/domains/kz/projects/2/c13f34fb-dd53-4524-8034-e112bbffe213.json")
with open(project_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

phase5 = data.get('app_data', {}).get('phase5', {})
results = phase5.get('results', {})
print(f"Phase5 results в файле: {len(results)}")