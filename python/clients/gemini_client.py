import google.generativeai as genai
from typing import List, Dict, Optional
import time
from pathlib import Path
from PIL import Image
from utils.logger import setup_logger
from utils.error_handler import retry_on_failure, GeminiAPIError
from config import settings

logger = setup_logger(__name__)

genai.configure(api_key=settings.GEMINI_API_KEY)

class GeminiClient:
    def __init__(self, model_name: str = "gemini-2.0-flash", temperature: float = 0.3):
        self.model_name = model_name
        self.temperature = temperature
        self.model = genai.GenerativeModel(model_name)
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost = 0.0
        logger.info(f"Initialized Gemini client: {model_name} (temp={temperature})")
    
    @retry_on_failure(max_attempts=2, delay=3.0, exceptions=(Exception,))
    def generate_insights(self, prompt: str, chart_paths: List[Path]) -> Dict:
        try:
            start_time = time.time()
            
            content = [prompt]
            
            for chart_path in chart_paths:
                if chart_path.exists():
                    img = Image.open(chart_path)
                    content.append(img)
                    logger.info(f"Added chart to prompt: {chart_path.name}")
                else:
                    logger.warning(f"Chart not found: {chart_path}")
            
            generation_config = genai.types.GenerationConfig(
                temperature=self.temperature,
                max_output_tokens=1000,
                top_p=0.9
            )
            
            response = self.model.generate_content(
                content,
                generation_config=generation_config
            )
            
            insights_text = response.text
            
            if hasattr(response, 'usage_metadata'):
                self.input_tokens = response.usage_metadata.prompt_token_count
                self.output_tokens = response.usage_metadata.candidates_token_count
                self._calculate_cost()
            
            duration = (time.time() - start_time) * 1000
            logger.info(f"Generated insights in {duration:.2f}ms | "
                       f"Tokens: {self.input_tokens}→{self.output_tokens} | "
                       f"Cost: ${self.cost:.4f}")
            
            return {
                'insights': insights_text,
                'input_tokens': self.input_tokens,
                'output_tokens': self.output_tokens,
                'total_tokens': self.input_tokens + self.output_tokens,
                'cost': self.cost,
                'model': self.model_name,
                'temperature': self.temperature
            }
            
        except Exception as e:
            logger.error(f"Gemini API call failed: {str(e)}")
            raise GeminiAPIError(f"Insight generation failed: {str(e)}")
    
    def _calculate_cost(self):
        input_cost = (self.input_tokens / 1000) * 0.00125
        output_cost = (self.output_tokens / 1000) * 0.005
        self.cost = input_cost + output_cost
    
    def get_usage_stats(self) -> Dict:
        return {
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'total_tokens': self.input_tokens + self.output_tokens,
            'cost': self.cost
        }

