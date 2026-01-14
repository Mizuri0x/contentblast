import os
from openai import OpenAI
from typing import Dict
import json

class ContentRepurposer:
    """
    AI-powered content repurposing engine.
    Uses Groq (super fast, free tier).
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.client = None  # Lazy initialization
        self.model = "llama-3.3-70b-versatile"

    def _get_client(self):
        """Lazy initialization of OpenAI client."""
        if self.client is None:
            key = self.api_key or os.getenv("OPENAI_API_KEY")
            if not key:
                raise ValueError("OPENAI_API_KEY not set. Please configure environment variables.")
            self.client = OpenAI(
                api_key=key,
                base_url=os.getenv("OPENAI_API_BASE", "https://api.groq.com/openai/v1")
            )
        return self.client

    def repurpose(self, content: str, content_type: str = "article") -> Dict:
        """
        Main repurposing function.
        Takes content and returns multiple formatted outputs.
        """

        system_prompt = """You are a social media content expert. Your task is to repurpose content into multiple formats.

Rules:
- Keep the core message but adapt tone for each platform
- Twitter/X: Short, punchy, use hooks, max 280 chars each
- LinkedIn: Professional, insightful, storytelling
- Instagram: Casual, engaging, emoji-friendly
- Email: Personal, value-focused, clear CTA
- TikTok: Trendy, hook-first, conversational

IMPORTANT: Respond ONLY with valid JSON. No markdown, no code blocks, no explanations."""

        user_prompt = f"""Repurpose this {content_type} into social media content:

---
{content}
---

Respond with this exact JSON structure (no markdown!):
{{
    "twitter_threads": ["tweet1", "tweet2", "tweet3", "tweet4", "tweet5"],
    "linkedin_post": "full linkedin post here",
    "instagram_captions": ["caption1", "caption2", "caption3"],
    "email_newsletter": {{
        "subject": "email subject",
        "body": "email body"
    }},
    "tiktok_scripts": ["script1", "script2"],
    "youtube_description": "youtube description",
    "key_hashtags": ["hashtag1", "hashtag2", "hashtag3", "hashtag4", "hashtag5"]
}}"""

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )

            result_text = response.choices[0].message.content.strip()

            # Clean up response - remove markdown code blocks if present
            if result_text.startswith("```"):
                lines = result_text.split("\n")
                result_text = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])
            if result_text.startswith("json"):
                result_text = result_text[4:].strip()
            if result_text.endswith("```"):
                result_text = result_text[:-3].strip()

            # Parse JSON response
            result = json.loads(result_text)
            result["success"] = True
            result["tokens_used"] = response.usage.total_tokens if response.usage else 0

            return result

        except json.JSONDecodeError as e:
            return {"success": False, "error": f"JSON parsing error: {str(e)}", "raw": result_text if 'result_text' in dir() else "No response"}
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def estimate_cost(self, content: str) -> Dict:
        """
        Groq is FREE!
        """
        input_tokens = len(content) / 4 + 500
        output_tokens = 1500

        return {
            "estimated_tokens": int(input_tokens + output_tokens),
            "estimated_cost_usd": 0.00
        }
