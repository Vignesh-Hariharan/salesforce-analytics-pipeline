import requests
from pathlib import Path
from typing import List
from utils.logger import setup_logger
from utils.error_handler import retry_on_failure
import base64

logger = setup_logger(__name__)

class ImageHostClient:
    """Upload images to Imgur for Slack compatibility"""
    
    def __init__(self):
        self.client_id = "546c25a59c58ad7"
        self.upload_url = "https://api.imgur.com/3/image"
        logger.info("Initialized Image Host client (Imgur)")
    
    def upload_images(self, image_paths: List[Path]) -> List[str]:
        """Upload multiple images and return their direct URLs"""
        urls = []
        
        for image_path in image_paths:
            try:
                url = self._upload_single(image_path)
                if url:
                    urls.append(url)
                    logger.info(f"Uploaded {image_path.name} to Imgur")
            except Exception as e:
                logger.warning(f"Failed to upload {image_path.name}: {e}")
        
        return urls
    
    @retry_on_failure(max_attempts=2, delay=1.0, exceptions=(requests.RequestException,))
    def _upload_single(self, image_path: Path) -> str:
        """Upload single image to Imgur and get direct URL"""
        with open(image_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
        
        headers = {
            'Authorization': f'Client-ID {self.client_id}'
        }
        
        payload = {
            'image': image_data,
            'type': 'base64'
        }
        
        response = requests.post(self.upload_url, headers=headers, data=payload, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        if result.get('success'):
            url = result['data']['link']
            logger.info(f"Imgur URL: {url}")
            return url
        else:
            raise Exception(f"Imgur upload failed: {result}")
