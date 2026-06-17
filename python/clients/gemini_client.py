import time
from pathlib import Path
from typing import Dict, List

from google import genai
from google.genai import types
from PIL import Image

from config import settings
from utils.error_handler import retry_on_failure, GeminiAPIError
from utils.logger import setup_logger

logger = setup_logger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash-lite"
MAX_OUTPUT_TOKENS = 1000

# Google list prices for gemini-2.5-flash-lite, USD per 1M tokens. Used only to
# record an approximate spend in the pipeline_runs audit log.
INPUT_COST_PER_1M = 0.10
OUTPUT_COST_PER_1M = 0.40


class GeminiClient:
    def __init__(self, model_name: str = DEFAULT_MODEL, temperature: float = 0.3):
        if not settings.GEMINI_API_KEY:
            raise GeminiAPIError("GEMINI_API_KEY is not set")
        self.model_name = model_name
        self.temperature = temperature
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost = 0.0
        logger.info(f"Initialized Gemini client: {model_name} (temp={temperature})")

    @retry_on_failure(max_attempts=2, delay=3.0, exceptions=(GeminiAPIError,))
    def generate_insights(self, prompt: str, chart_paths: List[Path]) -> Dict:
        contents: list = [prompt]
        for chart_path in chart_paths:
            if chart_path.exists():
                contents.append(Image.open(chart_path))
                logger.info(f"Added chart to prompt: {chart_path.name}")
            else:
                logger.warning(f"Chart not found: {chart_path}")

        start = time.time()
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=self.temperature,
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                    top_p=0.9,
                ),
            )
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise GeminiAPIError(f"Insight generation failed: {e}") from e

        usage = getattr(response, "usage_metadata", None)
        if usage:
            self.input_tokens = usage.prompt_token_count or 0
            self.output_tokens = usage.candidates_token_count or 0
            self.cost = self._calculate_cost()

        logger.info(
            f"Generated insights in {(time.time() - start) * 1000:.0f}ms | "
            f"Tokens: {self.input_tokens}->{self.output_tokens} | "
            f"Cost: ${self.cost:.4f}"
        )

        return {
            'insights': response.text or "",
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'total_tokens': self.input_tokens + self.output_tokens,
            'cost': self.cost,
            'model': self.model_name,
            'temperature': self.temperature,
        }

    def _calculate_cost(self) -> float:
        return ((self.input_tokens / 1_000_000) * INPUT_COST_PER_1M
                + (self.output_tokens / 1_000_000) * OUTPUT_COST_PER_1M)
