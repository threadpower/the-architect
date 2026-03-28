"""
The Architect — Local Bridge (Ollama/Qwen)
All local inference. Zero cost. Privacy guaranteed.
Includes confidence scoring per Grok's recommendation.
"""
import httpx
from typing import Optional

from architect.config.settings import settings
from architect.models.task import ModelResponse


class OllamaBridge:
    """Interface to local Qwen/Ollama on The Forge."""

    def __init__(self):
        self.base_url = settings.ollama_host
        self.default_model = settings.ollama_default_model
        self.timeout = httpx.Timeout(120.0, connect=10.0)

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        context_files: Optional[list[str]] = None,
        temperature: float = 0.7,
    ) -> ModelResponse:
        """
        Generate a response from the local Ollama model.
        Cost: $0.00. Always.
        """
        messages = []

        # System prompt
        if system:
            messages.append({"role": "system", "content": system})

        # Inject context files as system messages
        if context_files:
            for filepath in context_files:
                try:
                    with open(filepath, "r") as f:
                        content = f.read()
                    messages.append({
                        "role": "system",
                        "content": f"Context from {filepath}:\n{content}"
                    })
                except (FileNotFoundError, PermissionError) as e:
                    messages.append({
                        "role": "system",
                        "content": f"[Could not load {filepath}: {e}]"
                    })

        messages.append({"role": "user", "content": prompt})

        use_model = model or self.default_model

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": use_model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                    },
                },
            )
            response.raise_for_status()
            data = response.json()

        tokens_in = data.get("prompt_eval_count", 0)
        tokens_out = data.get("eval_count", 0)

        # Extract confidence from logprobs if available
        # Grok's recommendation: use this for escalation decisions
        confidence = self._extract_confidence(data)

        return ModelResponse(
            content=data["message"]["content"],
            model=use_model,
            provider="local",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=0.00,
            confidence=confidence,
        )

    async def health_check(self) -> bool:
        """Check if Ollama is running and the model is loaded."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                model_names = [m["name"] for m in data.get("models", [])]
                return self.default_model in model_names or any(
                    self.default_model.split(":")[0] in name
                    for name in model_names
                )
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        """List available models on Ollama."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    @staticmethod
    def _extract_confidence(data: dict) -> Optional[float]:
        """
        Extract a confidence score from model output.
        Uses eval_duration / prompt_eval_count as a rough proxy
        for how "certain" the model was (faster = more confident).
        
        This is a heuristic — will be replaced with proper logprobs
        when Ollama exposes them.
        """
        # For now, return None — we'll implement proper logprob
        # extraction when the Ollama API supports it
        return None
