import requests
from typing import List, Dict, Optional
from pathlib import Path
import time
from utils.logger import setup_logger
from utils.error_handler import retry_on_failure, AsanaAPIError
from config import settings

logger = setup_logger(__name__)

class AsanaClient:
    def __init__(self):
        if not settings.is_asana_configured():
            raise ValueError("Asana credentials not configured. Set ASANA_ACCESS_TOKEN and ASANA_PROJECT_GID environment variables.")
        
        self.access_token = settings.ASANA_ACCESS_TOKEN
        self.project_gid = settings.ASANA_PROJECT_GID
        self.base_url = "https://app.asana.com/api/1.0"
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json"
        }
        logger.info("Initialized Asana client")
    
    @retry_on_failure(max_attempts=3, delay=2.0, exceptions=(requests.RequestException,))
    def get_incomplete_tasks(self, tag_names: List[str]) -> List[Dict]:
        try:
            start_time = time.time()
            
            url = f"{self.base_url}/projects/{self.project_gid}/tasks"
            params = {
                "opt_fields": "name,tags.name,completed,gid,permalink_url"
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            
            all_tasks = response.json()['data']
            
            filtered_tasks = []
            for task in all_tasks:
                if task['completed']:
                    continue
                
                task_tags = [tag['name'] for tag in task.get('tags', [])]
                for target_tag in tag_names:
                    if target_tag in task_tags:
                        filtered_tasks.append({
                            'gid': task['gid'],
                            'name': task['name'],
                            'tag': target_tag,
                            'url': task.get('permalink_url', '')
                        })
                        break
            
            duration = (time.time() - start_time) * 1000
            logger.info(f"Found {len(filtered_tasks)} incomplete tasks with target tags in {duration:.2f}ms")
            return filtered_tasks
            
        except Exception as e:
            logger.error(f"Failed to get Asana tasks: {str(e)}")
            raise AsanaAPIError(f"Task retrieval failed: {str(e)}")
    
    @retry_on_failure(max_attempts=2, delay=2.0, exceptions=(requests.RequestException,))
    def upload_attachment(self, task_gid: str, file_path: Path) -> bool:
        try:
            start_time = time.time()
            
            url = f"{self.base_url}/tasks/{task_gid}/attachments"
            
            with open(file_path, 'rb') as f:
                files = {'file': (file_path.name, f, 'image/png')}
                headers = {"Authorization": f"Bearer {self.access_token}"}
                
                response = requests.post(url, headers=headers, files=files, timeout=30)
                response.raise_for_status()
            
            duration = (time.time() - start_time) * 1000
            logger.info(f"Uploaded {file_path.name} to task {task_gid} in {duration:.2f}ms")
            return True
            
        except Exception as e:
            logger.error(f"Failed to upload attachment: {str(e)}")
            raise AsanaAPIError(f"Attachment upload failed: {str(e)}")
    
    @retry_on_failure(max_attempts=2, delay=2.0, exceptions=(requests.RequestException,))
    def add_comment(self, task_gid: str, comment_text: str) -> bool:
        try:
            start_time = time.time()
            
            url = f"{self.base_url}/tasks/{task_gid}/stories"
            data = {
                "data": {
                    "text": comment_text
                }
            }
            
            response = requests.post(url, headers=self.headers, json=data, timeout=10)
            response.raise_for_status()
            
            duration = (time.time() - start_time) * 1000
            logger.info(f"Added comment to task {task_gid} in {duration:.2f}ms")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add comment: {str(e)}")
            raise AsanaAPIError(f"Comment addition failed: {str(e)}")
    
    @retry_on_failure(max_attempts=2, delay=2.0, exceptions=(requests.RequestException,))
    def move_to_complete(self, task_gid: str) -> bool:
        try:
            start_time = time.time()
            
            url = f"{self.base_url}/tasks/{task_gid}"
            data = {
                "data": {
                    "completed": True
                }
            }
            
            response = requests.put(url, headers=self.headers, json=data, timeout=10)
            response.raise_for_status()
            
            duration = (time.time() - start_time) * 1000
            logger.info(f"Marked task {task_gid} as complete in {duration:.2f}ms")
            return True
            
        except Exception as e:
            logger.error(f"Failed to complete task: {str(e)}")
            raise AsanaAPIError(f"Task completion failed: {str(e)}")
    
    @retry_on_failure(max_attempts=2, delay=1.0, exceptions=(requests.RequestException,))
    def get_task_info(self, task_gid: str) -> Optional[Dict]:
        try:
            url = f"{self.base_url}/tasks/{task_gid}"
            params = {"opt_fields": "completed,name"}
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            return response.json().get('data')
        except Exception as e:
            logger.warning(f"Failed to get task info: {str(e)}")
            return None
    
    def get_section_gid(self, section_name: str) -> Optional[str]:
        try:
            url = f"{self.base_url}/projects/{self.project_gid}/sections"
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            sections = response.json()['data']
            for section in sections:
                if section['name'].lower() == section_name.lower():
                    return section['gid']
            
            logger.warning(f"Section '{section_name}' not found")
            return None
            
        except Exception as e:
            logger.error(f"Failed to get section: {str(e)}")
            return None

