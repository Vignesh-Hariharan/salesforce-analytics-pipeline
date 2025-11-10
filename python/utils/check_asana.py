import os
import requests
import json

token = os.getenv('ASANA_ACCESS_TOKEN')
project = os.getenv('ASANA_PROJECT_GID')

headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
url = f"https://app.asana.com/api/1.0/projects/{project}/tasks"
params = {"opt_fields": "name,tags.name,completed,gid,permalink_url"}

resp = requests.get(url, headers=headers, params=params, timeout=10)
resp.raise_for_status()

all_tasks = resp.json()['data']
tags = ['sales-pipeline-health', 'rep-performance', 'revenue-forecast']
filtered = []

for task in all_tasks:
    if task['completed']:
        continue
    task_tags = [t['name'] for t in task.get('tags', [])]
    for tag in tags:
        if tag in task_tags:
            filtered.append({
                'gid': task['gid'],
                'name': task['name'],
                'tag': tag,
                'url': task.get('permalink_url', '')
            })
            break

with open('tasks.json', 'w') as f:
    json.dump(filtered, f)

print(f"Found {len(filtered)} tasks")

