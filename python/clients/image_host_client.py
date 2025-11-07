import requests
from pathlib import Path
from typing import List
from utils.logger import setup_logger

logger = setup_logger(__name__)

class ImageHostClient:
    """Upload images to freeimage.host for hosting"""
    
    def __init__(self):
        self.api_url = "https://freeimage.host/api/1/upload"
        self.api_key = "6d207e02198a847aa98d0a2a901485a5"
        logger.info("Initialized Image Host client")
    
    def upload_images(self, image_paths: List[Path]) -> List[str]:
        """Upload multiple images and return their URLs"""
        urls = []
        
        for image_path in image_paths:
            try:
                url = self._upload_single(image_path)
                if url:
                    urls.append(url)
                    logger.info(f"Uploaded {image_path.name}")
            except Exception as e:
                logger.warning(f"Failed to upload {image_path.name}: {e}")
        
        return urls
    
    def _upload_single(self, image_path: Path) -> str:
        """Upload single image"""
        with open(image_path, 'rb') as f:
            files = {'source': f}
            data = {'key': self.api_key, 'format': 'json'}
            
            response = requests.post(self.api_url, files=files, data=data, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            if result.get('status_code') == 200:
                return result['image']['url']
            else:
                raise Exception(f"Upload failed: {result.get('error', {}).get('message')}")

