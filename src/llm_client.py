from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Type

import boto3
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


class LLMClient:
    """Bedrock-only client for structured outputs."""

    def __init__(self) -> None:
        self.provider = os.getenv("MODEL_PROVIDER", "bedrock").strip().lower()
        self.bedrock_model_id = os.getenv(
            "BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0"
        )
        self.bedrock_inference_profile = os.getenv("BEDROCK_INFERENCE_PROFILE_ARN")
        self.aws_region = os.getenv("AWS_REGION", "us-east-1")

        if self.provider != "bedrock":
            raise RuntimeError(
                "This project is configured for Bedrock-only. Set MODEL_PROVIDER=bedrock."
            )
        self.bedrock_client = boto3.client("bedrock-runtime", region_name=self.aws_region)

    def parse_structured(
        self,
        *,
        model_name: str | None,
        system_prompt: str,
        user_content: Any,
        response_model: Type[BaseModel],
        temperature: float = 0.0,
        max_tokens: int = 2000,
    ) -> BaseModel:
        return self._parse_with_bedrock(
            system_prompt=system_prompt,
            user_content=user_content,
            response_model=response_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _parse_with_bedrock(
        self,
        *,
        system_prompt: str,
        user_content: Any,
        response_model: Type[BaseModel],
        temperature: float,
        max_tokens: int,
    ) -> BaseModel:
        schema_json = json.dumps(response_model.model_json_schema(), ensure_ascii=False, indent=2)
        strict_instruction = (
            "Return ONLY valid JSON matching this schema. "
            "Do not include markdown, code fences, or extra text.\n\n"
            f"JSON Schema:\n{schema_json}"
        )

        messages = [{"role": "user", "content": self._to_bedrock_content(user_content)}]
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "system": f"{system_prompt}\n\n{strict_instruction}",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        response = self.bedrock_client.invoke_model(
            modelId=self.bedrock_inference_profile or self.bedrock_model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )

        payload = json.loads(response["body"].read())
        text_parts: List[str] = []
        for block in payload.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        raw_text = "".join(text_parts).strip()
        raw_text = self._strip_code_fences(raw_text)
        return response_model.model_validate_json(raw_text)

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3 and lines[-1].strip() == "```":
                return "\n".join(lines[1:-1]).strip()
        return text

    @staticmethod
    def _to_bedrock_content(user_content: Any) -> List[Dict[str, Any]]:
        # Support text-only prompts as a single message
        if isinstance(user_content, str):
            return [{"type": "text", "text": user_content}]

        # Convert OpenAI-style multimodal content to Anthropic Bedrock content blocks.
        converted: List[Dict[str, Any]] = []
        if isinstance(user_content, list):
            for part in user_content:
                part_type = part.get("type")
                if part_type == "text":
                    converted.append({"type": "text", "text": part.get("text", "")})
                elif part_type == "image_url":
                    url = (part.get("image_url") or {}).get("url", "")
                    marker = "data:image/png;base64,"
                    if url.startswith(marker):
                        converted.append(
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": url[len(marker):],
                                },
                            }
                        )
        return converted or [{"type": "text", "text": str(user_content)}]
