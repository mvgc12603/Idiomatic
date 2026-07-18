import json
import logging
import os
import re
from html import unescape
from typing import Any
from urllib.parse import quote_plus

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from openai import OpenAI
from pydantic import BaseModel, Field, field_validator

from idiom_database import find_database_matches, infer_target_language as infer_dictionary_target_language

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("idiom-tool")

APP_VERSION = "1.5.0-ollama-idiom-lookup"
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
IDIOM_FALLBACK_PROVIDER = os.getenv("IDIOM_FALLBACK_PROVIDER", LLM_PROVIDER).strip().lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b")
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY", "").strip()
DEEPL_API_URL = os.getenv(
    "DEEPL_API_URL",
    "https://api-free.deepl.com" if DEEPL_API_KEY.endswith(":fx") else "https://api.deepl.com"
).rstrip("/")
ENABLE_WEB_RETRIEVAL = os.getenv("ENABLE_WEB_RETRIEVAL", "true").strip().lower() in {"1", "true", "yes", "on"}
ENABLE_UNVERIFIED_AI_FALLBACK = os.getenv("ENABLE_UNVERIFIED_AI_FALLBACK", "false").strip().lower() in {"1", "true", "yes", "on"}
REQUIRE_WEB_EVIDENCE_FOR_AI_FALLBACK = os.getenv("REQUIRE_WEB_EVIDENCE_FOR_AI_FALLBACK", "false").strip().lower() in {"1", "true", "yes", "on"}
OPENAI_REQUEST_TIMEOUT_SECONDS = float(os.getenv("OPENAI_REQUEST_TIMEOUT_SECONDS", "20"))
OLLAMA_REQUEST_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_REQUEST_TIMEOUT_SECONDS", "60"))
DEEPL_REQUEST_TIMEOUT_SECONDS = float(os.getenv("DEEPL_REQUEST_TIMEOUT_SECONDS", "12"))
WEB_SEARCH_TIMEOUT_SECONDS = float(os.getenv("WEB_SEARCH_TIMEOUT_SECONDS", "8"))
MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "280"))


class IdiomSuggestionRequest(BaseModel):
    context_text: str = Field(..., min_length=1, max_length=5000)
    target_language: str = Field(default="auto", min_length=2, max_length=80)
    phrase: str | None = Field(default=None, max_length=700)
    tone_hint: str | None = Field(default=None, max_length=500)

    @field_validator("context_text", "target_language", "phrase", "tone_hint", mode="before")
    @classmethod
    def strip_string_fields(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class IdiomSuggestion(BaseModel):
    suggested_idiom: str
    explanation: str
    confidence_score: float = Field(ge=0.0, le=1.0)


class IdiomSuggestionResponse(BaseModel):
    suggestions: list[IdiomSuggestion]
    fallback_message: str | None = None


SUGGESTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "suggestions": {
            "type": "array",
            "minItems": 0,
            "maxItems": 2,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "suggested_idiom": {
                        "type": "string",
                        "minLength": 1
                    },
                    "explanation": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 140
                    },
                    "confidence_score": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1
                    }
                },
                "required": [
                    "suggested_idiom",
                    "explanation",
                    "confidence_score"
                ]
            }
        }
    },
    "required": [
        "suggestions"
    ]
}


SYSTEM_PROMPT = (
    "You are an expert multilingual idiom translator, cross-cultural writing assistant, and tone editor. "
    "Analyze this text. The user is trying to write an idiom or a rough literal translation from another language. "
    "Identify their underlying meaning, then find the real culturally matching idiom in the target language that fits the writing tone. "
    "and return a clean JSON array containing 'suggested_idiom', 'explanation', and 'confidence_score'. "
    "The service will wrap that array in a JSON object named 'suggestions' for transport. "
    "When target_language is 'auto', infer the target language from the user's surrounding sentence outside brackets. "
    "If the bracketed phrase is in a different language from the surrounding sentence, translate the idiomatic meaning into the surrounding sentence's language. "
    "Literal word-by-word translation is forbidden. Do not translate the nouns, verbs, or imagery of the source expression. "
    "Only return an expression that a native speaker would recognize as a real idiom, proverb, or natural fixed phrase. "
    "When web evidence is provided, use it to identify the source idiom's meaning and common target-language equivalents, but ignore irrelevant search results. "
    "For fallback requests, act like an idiom dictionary lookup, not a translation engine. "
    "If you know the source meaning but do not know a real target-language equivalent, return an empty suggestions array. "
    "If an idiom would sound forced, return a natural non-idiomatic phrase and explain why. "
    "Return at most two suggestions. Keep each explanation under 18 words. "
    "Return no markdown and no commentary outside the JSON data."
)


OLLAMA_IDIOM_LOOKUP_PROMPT = (
    "You are an idiom dictionary researcher. Your job is not literal translation. "
    "For a source idiom, proverb, saying, or rough literal phrase, identify the underlying meaning first, "
    "then return the real target-language idiom, proverb, or natural fixed phrase that native speakers actually use for that meaning. "
    "Do not translate source words, imagery, animals, objects, body parts, food, weather, or verbs word-by-word. "
    "A literal translation is a wrong answer unless it is independently a known target-language idiom. "
    "If you cannot identify a real target-language equivalent, return an empty suggestions array. "
    "If web evidence is provided, use it as lookup evidence; if it conflicts with your memory, prefer the well-known idiom equivalent. "
    "Return JSON only with a 'suggestions' array. Keep explanations short and state the meaning matched."
)


app = FastAPI(
    title="Contextual Idiom Translator API",
    version="1.0.0",
    description="Translates rough cross-lingual idioms into culturally appropriate target-language idioms."
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(chrome-extension://.*|http://localhost(:\d+)?|http://127\.0\.0\.1(:\d+)?)$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def sanitize_error(message: str) -> str:
    return re.sub(r"sk-[A-Za-z0-9_-]+", "sk-...", message)


def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    return OpenAI(
        api_key=api_key,
        timeout=OPENAI_REQUEST_TIMEOUT_SECONDS,
        max_retries=1
    )


def normalize_search_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("[", " ").replace("]", " ")).strip()


def strip_html(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(without_tags)).strip()


def infer_language_hint(text: str) -> str:
    normalized = f" {normalize_search_text(text).lower()} "
    spanish_markers = [
        " el ", " la ", " los ", " las ", " que ", " pero ", " estaba ", " estoy ",
        " lloviendo ", " llovendo ", " cantaros ", " cantaros", " vaso ", " gota ",
        " calma ", " manteniendo ", " para ", " con ", " sin "
    ]
    english_markers = [
        " the ", " and ", " but ", " would ", " out ", " last ", " straw ", " raining ",
        " cats ", " dogs ", " bucket ", " calm ", " trying ", " with ", " without "
    ]
    spanish_score = sum(1 for marker in spanish_markers if marker in normalized)
    english_score = sum(1 for marker in english_markers if marker in normalized)
    if spanish_score > english_score:
        return "Spanish"
    if english_score > spanish_score:
        return "English"
    return "unknown"


def infer_target_language_hint(payload: IdiomSuggestionRequest) -> str:
    requested = payload.target_language.strip()
    if requested.lower() not in {"auto", "detect", "infer"}:
        return requested

    inferred = infer_dictionary_target_language(payload.context_text, payload.phrase, payload.target_language)
    return inferred.title()


def build_search_queries(payload: IdiomSuggestionRequest) -> list[str]:
    phrase = normalize_search_text(payload.phrase or payload.context_text)
    if not phrase:
        return []

    source_language = infer_language_hint(phrase)
    target_language = infer_target_language_hint(payload)
    language_cue = source_language if source_language != "unknown" else ""

    query_templates = [
        "{phrase} idiom meaning",
        "{phrase} saying meaning",
        "{phrase} equivalent idiom in {target_language}",
        "{phrase} {language_cue} modismo significado",
        "{phrase} {language_cue} refran significado"
    ]

    queries: list[str] = []
    for template in query_templates:
        query = normalize_search_text(
            template.format(
                phrase=phrase,
                source_language=source_language,
                target_language=target_language,
                language_cue=language_cue
            )
        )
        if query and query not in queries:
            queries.append(query)
    return queries[:4]


def parse_duckduckgo_results(html_text: str, max_results: int = 4) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    blocks = re.split(r'<div[^>]+class="[^"]*result[^"]*"[^>]*>', html_text)
    for block in blocks[1:]:
        title_match = re.search(r'class="[^"]*result__a[^"]*"[^>]*>(.*?)</a>', block, flags=re.DOTALL | re.IGNORECASE)
        snippet_match = re.search(r'class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</(?:a|div)>', block, flags=re.DOTALL | re.IGNORECASE)
        if not title_match:
            continue
        title = strip_html(title_match.group(1))
        snippet = strip_html(snippet_match.group(1)) if snippet_match else ""
        if title:
            results.append({
                "title": title[:180],
                "snippet": snippet[:280]
            })
        if len(results) >= max_results:
            break
    return results


def search_web_for_phrase(payload: IdiomSuggestionRequest) -> str:
    if not ENABLE_WEB_RETRIEVAL:
        return ""

    evidence_lines: list[str] = []
    headers = {
        "User-Agent": "Mozilla/5.0 IdiomTool/1.1"
    }

    with httpx.Client(timeout=WEB_SEARCH_TIMEOUT_SECONDS, follow_redirects=True, headers=headers, trust_env=False) as client:
        for query in build_search_queries(payload):
            try:
                response = client.get(
                    "https://duckduckgo.com/html/",
                    params={
                        "q": query
                    }
                )
                response.raise_for_status()
                results = parse_duckduckgo_results(response.text, max_results=3)
                if not results:
                    continue
                evidence_lines.append(f"Query: {query}")
                for index, result in enumerate(results, start=1):
                    snippet = f" - {result['snippet']}" if result["snippet"] else ""
                    evidence_lines.append(f"{index}. {result['title']}{snippet}")
            except Exception as search_error:
                logger.warning("Web search failed for query %r: %s", query, search_error)

            if len(evidence_lines) >= 12:
                break

    return "\n".join(evidence_lines[:12])


def build_user_prompt(payload: IdiomSuggestionRequest, web_evidence: str = "") -> str:
    rough_phrase = payload.phrase or "Infer the rough idiom from the context."
    tone_hint = payload.tone_hint or "Infer tone from the surrounding sentence."
    resolved_target_language = infer_target_language_hint(payload)
    evidence_section = (
        f"\nWeb evidence from phrase searches:\n{web_evidence}\n"
        if web_evidence
        else "\nWeb evidence from phrase searches: none available.\n"
    )
    return (
        f"Target language: {payload.target_language}\n"
        f"Resolved output language from surrounding sentence: {resolved_target_language}\n"
        f"Rough idiom or literal phrase: {rough_phrase}\n"
        f"Tone guidance: {tone_hint}\n\n"
        "Task:\n"
        "1. Determine what the rough phrase means in context.\n"
        "2. Infer source language if needed.\n"
        "3. Output must be in the resolved output language above when target_language is auto.\n"
        "4. Look up the idiomatic meaning, then choose the target-language idiom by meaning, not by source words.\n"
        "5. Use web evidence to correct literal mistranslations, partial phrases, spelling mistakes, and culturally specific equivalents.\n"
        "6. Never translate the words literally unless the result is also a real idiom in the target language.\n"
        "7. If evidence is weak or ambiguous, return an empty suggestions array.\n"
        "8. Return one or two culturally natural suggestions sorted by usefulness.\n"
        "9. Each confidence_score must be a number between 0 and 1.\n\n"
        "Examples of the intended behavior:\n"
        "- French phrase 'les gouts et les couleurs ne se discutent pas' in Spanish context -> 'sobre gustos no hay nada escrito'.\n"
        "- Spanish phrase 'llover a cantaros' in English context -> 'raining cats and dogs' or 'pouring rain', never 'raining pitchers'.\n"
        "- Spanish phrase 'meter la pata' in English context -> 'put one's foot in it', never 'put the paw'.\n"
        "- French phrase 'mettre la charrue avant les boeufs' in English context -> 'put the cart before the horse'.\n"
        "- If no real equivalent is known, return {\"suggestions\": []}.\n"
        f"{evidence_section}\n"
        f"Context text:\n{payload.context_text}"
    )


def build_ollama_idiom_lookup_prompt(payload: IdiomSuggestionRequest, web_evidence: str = "") -> str:
    rough_phrase = payload.phrase or "Infer the rough idiom from the context."
    tone_hint = payload.tone_hint or "Infer tone from the surrounding sentence."
    resolved_target_language = infer_target_language_hint(payload)
    evidence_section = web_evidence if web_evidence else "No web evidence was found. Use idiom knowledge only; do not guess literally."
    return (
        f"Target language request: {payload.target_language}\n"
        f"Resolved output language from surrounding sentence: {resolved_target_language}\n"
        f"Phrase to look up: {rough_phrase}\n"
        f"Tone/context guidance: {tone_hint}\n"
        f"Full context: {payload.context_text}\n\n"
        "Lookup method:\n"
        "1. Decide the language and idiomatic meaning of the phrase.\n"
        "2. Output must be in the resolved output language above; ignore the bracketed phrase's language for output language.\n"
        "3. Find the real target-language idiom or fixed phrase for that meaning.\n"
        "4. Return no suggestion if you only know a literal translation.\n"
        "5. Return no suggestion if the expression would sound invented, awkward, or translated.\n\n"
        "Good mappings:\n"
        "- 'llover a cantaros' -> English 'raining cats and dogs' or 'pouring rain'.\n"
        "- 'meter la pata' -> English 'put one's foot in it'.\n"
        "- 'estar entre la espada y la pared' -> English 'between a rock and a hard place'.\n"
        "- 'les gouts et les couleurs ne se discutent pas' -> Spanish 'sobre gustos no hay nada escrito'.\n"
        "- In Spanish sentence 'no me gusta, pero [the last straw]' -> Spanish 'la gota que colmo el vaso'.\n"
        "- In Spanish sentence 'quiero decir [kick the bucket]' -> Spanish 'estirar la pata'.\n"
        "- 'mettre la charrue avant les boeufs' -> English 'put the cart before the horse'.\n\n"
        "Bad literal answers to reject:\n"
        "- 'raining pitchers', 'raining jugs', 'put the paw', 'put the leg', 'between the sword and the wall'.\n"
        "- Any answer that preserves source imagery when the target language uses different imagery.\n\n"
        "Confidence rules:\n"
        "- 0.85-0.95 only for a well-known idiom equivalent.\n"
        "- 0.72-0.84 for a natural fixed phrase equivalent.\n"
        "- Below 0.72 means return no suggestion.\n\n"
        f"Web lookup evidence:\n{evidence_section}\n\n"
        "Return JSON exactly like:\n"
        "{\"suggestions\":[{\"suggested_idiom\":\"...\",\"explanation\":\"Equivalent for meaning: ...\",\"confidence_score\":0.85}]}\n"
        "or {\"suggestions\":[]}."
    )


def parse_json_payload(raw_text: str) -> dict[str, Any]:
    cleaned = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL | re.IGNORECASE).strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()

    json_match = re.search(r"(\{.*\}|\[.*\])", cleaned, flags=re.DOTALL)
    if json_match:
        cleaned = json_match.group(1)

    parsed = json.loads(cleaned)
    if isinstance(parsed, list):
        return {"suggestions": parsed}
    if isinstance(parsed, dict):
        return parsed
    raise ValueError("The model returned JSON that was neither an object nor an array.")


def parse_response_text(response: Any) -> dict[str, Any]:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return parse_json_payload(output_text)

    output_items = getattr(response, "output", None) or []
    for item in output_items:
        content_items = getattr(item, "content", None) or []
        for content in content_items:
            text = getattr(content, "text", None)
            if text:
                return parse_json_payload(text)

    raise ValueError("OpenAI response did not include parseable text output.")


def validate_suggestions(raw_data: dict[str, Any]) -> list[IdiomSuggestion]:
    raw_suggestions = raw_data.get("suggestions", [])
    if not isinstance(raw_suggestions, list):
        raise ValueError("OpenAI JSON did not include a suggestions array.")

    suggestions: list[IdiomSuggestion] = []
    for item in raw_suggestions:
        try:
            suggestions.append(IdiomSuggestion.model_validate(item))
        except Exception as validation_error:
            logger.warning("Dropped invalid model suggestion: %s", validation_error)
    return suggestions


def request_structured_suggestions(client: OpenAI, payload: IdiomSuggestionRequest, web_evidence: str) -> list[IdiomSuggestion]:
    response = client.responses.create(
        model=DEFAULT_MODEL,
        input=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": build_user_prompt(payload, web_evidence)
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "idiom_suggestions",
                "strict": True,
                "schema": SUGGESTION_SCHEMA
            }
        },
        max_output_tokens=MAX_OUTPUT_TOKENS
    )
    return validate_suggestions(parse_response_text(response))


def request_json_mode_suggestions(client: OpenAI, payload: IdiomSuggestionRequest, web_evidence: str) -> list[IdiomSuggestion]:
    response = client.responses.create(
        model=DEFAULT_MODEL,
        input=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": build_user_prompt(payload, web_evidence)
            }
        ],
        text={
            "format": {
                "type": "json_object"
            }
        },
        max_output_tokens=MAX_OUTPUT_TOKENS
    )
    return validate_suggestions(parse_response_text(response))


def request_openai_suggestions(payload: IdiomSuggestionRequest, web_evidence: str) -> list[IdiomSuggestion]:
    client = get_openai_client()

    try:
        return request_structured_suggestions(client, payload, web_evidence)
    except Exception as structured_error:
        logger.warning(
            "Structured OpenAI idiom request failed, trying JSON mode: %s",
            sanitize_error(f"{structured_error.__class__.__name__}: {structured_error}")
        )

    return request_json_mode_suggestions(client, payload, web_evidence)


def request_ollama_suggestions(payload: IdiomSuggestionRequest, web_evidence: str) -> list[IdiomSuggestion]:
    response = httpx.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": OLLAMA_IDIOM_LOOKUP_PROMPT
                },
                {
                    "role": "user",
                    "content": build_ollama_idiom_lookup_prompt(payload, web_evidence)
                }
            ],
            "format": SUGGESTION_SCHEMA,
            "stream": False,
            "think": False,
            "keep_alive": "10m",
            "options": {
                "temperature": 0.0,
                "top_p": 0.9,
                "num_ctx": 4096,
                "num_predict": MAX_OUTPUT_TOKENS
            }
        },
        timeout=OLLAMA_REQUEST_TIMEOUT_SECONDS
    )
    response.raise_for_status()
    response_data = response.json()
    message = response_data.get("message", {})
    content = message.get("content", "")
    if not content:
        content = response_data.get("response", "")
    if not content:
        raise ValueError("Ollama returned an empty response.")
    return validate_suggestions(parse_json_payload(content))


def deepl_target_language_code(language_name: str) -> str:
    normalized = language_name.strip().lower()
    target_codes = {
        "english": "EN-US",
        "en": "EN-US",
        "en-us": "EN-US",
        "en-gb": "EN-GB",
        "spanish": "ES",
        "es": "ES",
        "french": "FR",
        "fr": "FR"
    }
    return target_codes.get(normalized, language_name.strip().upper())


def request_deepl_suggestions(payload: IdiomSuggestionRequest) -> list[IdiomSuggestion]:
    if not DEEPL_API_KEY:
        raise RuntimeError("DEEPL_API_KEY is not configured.")

    target_language = infer_target_language_hint(payload)
    phrase = payload.phrase or payload.context_text
    response = httpx.post(
        f"{DEEPL_API_URL}/v2/translate",
        headers={
            "Authorization": f"DeepL-Auth-Key {DEEPL_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "text": [phrase],
            "target_lang": deepl_target_language_code(target_language),
            "context": payload.context_text,
            "model_type": "prefer_quality_optimized"
        },
        timeout=DEEPL_REQUEST_TIMEOUT_SECONDS
    )
    response.raise_for_status()
    translations = response.json().get("translations", [])
    if not translations:
        return []

    translated_text = str(translations[0].get("text", "")).strip()
    if not translated_text:
        return []

    return [
        IdiomSuggestion(
            suggested_idiom=translated_text,
            explanation="DeepL translation fallback; not verified against the idiom dictionary.",
            confidence_score=0.62
        )
    ]


def filter_unverified_suggestions(
    payload: IdiomSuggestionRequest,
    suggestions: list[IdiomSuggestion],
    minimum_confidence: float = 0.72
) -> list[IdiomSuggestion]:
    normalized_phrase = normalize_search_text(payload.phrase or payload.context_text).lower()
    source_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", normalized_phrase)
        if len(token) > 3
    }
    literal_warning_terms = {
        "literal",
        "word-by-word",
        "word by word",
        "direct translation",
        "not an idiom",
        "not idiomatic"
    }
    filtered: list[IdiomSuggestion] = []
    for suggestion in suggestions:
        normalized_suggestion = normalize_search_text(suggestion.suggested_idiom).lower()
        if not normalized_suggestion or normalized_suggestion == normalized_phrase:
            continue
        if suggestion.confidence_score < minimum_confidence:
            continue
        if "[" in suggestion.suggested_idiom or "]" in suggestion.suggested_idiom:
            continue
        explanation = suggestion.explanation.lower()
        if any(term in explanation for term in literal_warning_terms):
            continue
        suggestion_tokens = {
            token
            for token in re.findall(r"[a-z0-9]+", normalized_suggestion)
            if len(token) > 3
        }
        if source_tokens and suggestion_tokens and len(source_tokens & suggestion_tokens) / max(len(suggestion_tokens), 1) > 0.6:
            continue
        filtered.append(suggestion)
    return filtered[:2]


def generate_suggestions(payload: IdiomSuggestionRequest) -> list[IdiomSuggestion]:
    if IDIOM_FALLBACK_PROVIDER in {"none", "off", "disabled", "dictionary", "dictionary_only"}:
        return []
    if IDIOM_FALLBACK_PROVIDER == "deepl":
        return request_deepl_suggestions(payload)

    web_evidence = search_web_for_phrase(payload)
    if web_evidence:
        logger.info("Using web evidence for idiom phrase: %s", payload.phrase or payload.context_text[:80])
    elif REQUIRE_WEB_EVIDENCE_FOR_AI_FALLBACK and IDIOM_FALLBACK_PROVIDER in {"ollama", "local", "openai", "auto"}:
        logger.info("Skipping AI fallback because no web evidence was found for: %s", payload.phrase or payload.context_text[:80])
        return []

    if IDIOM_FALLBACK_PROVIDER in {"ollama", "local"}:
        suggestions = request_ollama_suggestions(payload, web_evidence)
        return suggestions if ENABLE_UNVERIFIED_AI_FALLBACK else filter_unverified_suggestions(payload, suggestions)
    if IDIOM_FALLBACK_PROVIDER == "openai":
        suggestions = request_openai_suggestions(payload, web_evidence)
        return suggestions if ENABLE_UNVERIFIED_AI_FALLBACK else filter_unverified_suggestions(payload, suggestions)
    if IDIOM_FALLBACK_PROVIDER == "auto":
        if os.getenv("OPENAI_API_KEY"):
            suggestions = request_openai_suggestions(payload, web_evidence)
        else:
            suggestions = request_ollama_suggestions(payload, web_evidence)
        return suggestions if ENABLE_UNVERIFIED_AI_FALLBACK else filter_unverified_suggestions(payload, suggestions)
    raise RuntimeError("IDIOM_FALLBACK_PROVIDER must be one of: none, deepl, ollama, local, openai, auto.")


def generate_database_suggestions(payload: IdiomSuggestionRequest) -> tuple[list[IdiomSuggestion], float, str]:
    raw_suggestions, match_score, resolved_target_language = find_database_matches(
        context_text=payload.context_text,
        phrase=payload.phrase,
        target_language=payload.target_language
    )
    suggestions = [IdiomSuggestion.model_validate(item) for item in raw_suggestions]
    return suggestions, match_score, resolved_target_language


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "version": APP_VERSION,
        "fallback_provider": IDIOM_FALLBACK_PROVIDER,
        "ollama_model": OLLAMA_MODEL if IDIOM_FALLBACK_PROVIDER in {"ollama", "local", "auto"} else "",
        "openai_model": DEFAULT_MODEL if IDIOM_FALLBACK_PROVIDER in {"openai", "auto"} else "",
        "deepl": "configured" if DEEPL_API_KEY else "not configured",
        "web_retrieval": "enabled" if ENABLE_WEB_RETRIEVAL else "disabled",
        "web_evidence_required_for_ai": "enabled" if REQUIRE_WEB_EVIDENCE_FOR_AI_FALLBACK else "disabled",
        "retrieval_order": "coded dictionary, then Ollama idiom-equivalent lookup with web evidence when available"
    }


@app.get("/debug/search")
def debug_search(phrase: str, context: str = "", target_language: str = "auto") -> dict[str, Any]:
    payload = IdiomSuggestionRequest(
        context_text=context or phrase,
        phrase=phrase,
        target_language=target_language,
        tone_hint="Debug search evidence."
    )
    return {
        "queries": build_search_queries(payload),
        "evidence": search_web_for_phrase(payload)
    }


@app.get("/debug/database")
def debug_database(phrase: str, context: str = "", target_language: str = "auto") -> dict[str, Any]:
    payload = IdiomSuggestionRequest(
        context_text=context or phrase,
        phrase=phrase,
        target_language=target_language,
        tone_hint="Debug database match."
    )
    suggestions, match_score, resolved_target_language = generate_database_suggestions(payload)
    return {
        "resolved_target_language": resolved_target_language,
        "best_match_score": round(match_score, 3),
        "suggestions": [suggestion.model_dump() for suggestion in suggestions]
    }


@app.get("/test", response_class=HTMLResponse)
def test_page() -> str:
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Idiom Translator Test</title>
    <style>
      body {
        margin: 0;
        min-height: 100vh;
        background: #f5f7fb;
        color: #172033;
        font-family: Arial, sans-serif;
      }

      main {
        max-width: 820px;
        margin: 0 auto;
        padding: 40px 20px;
      }

      h1 {
        margin: 0 0 10px;
        font-size: 24px;
      }

      p {
        margin: 0 0 18px;
        color: #526071;
      }

      textarea,
      [contenteditable="true"] {
        box-sizing: border-box;
        width: 100%;
        min-height: 150px;
        margin: 0 0 18px;
        padding: 14px;
        border: 1px solid #bcc6d6;
        border-radius: 8px;
        background: #ffffff;
        color: #172033;
        font: 16px/1.5 Arial, sans-serif;
        outline: none;
      }

      textarea:focus,
      [contenteditable="true"]:focus {
        border-color: #265dff;
        box-shadow: 0 0 0 3px rgba(38, 93, 255, 0.14);
      }
    </style>
  </head>
  <body>
    <main>
      <h1>Idiom Translator Test</h1>
      <p>Type a bracketed rough idiom, then pause.</p>
      <textarea autofocus>I would go out but [esta lloviendo a cantaros]</textarea>
      <div contenteditable="true">estaba manteniendo la calma pero eso fue [the last straw]</div>
    </main>
  </body>
</html>"""


@app.post("/suggest-idiom", response_model=IdiomSuggestionResponse)
def suggest_idiom(payload: IdiomSuggestionRequest) -> IdiomSuggestionResponse:
    try:
        database_suggestions, match_score, resolved_target_language = generate_database_suggestions(payload)
        if database_suggestions:
            return IdiomSuggestionResponse(
                suggestions=database_suggestions,
                fallback_message=(
                    "Matched coded multilingual idiom dictionary "
                    f"for {resolved_target_language} with confidence {match_score:.2f}."
                )
            )

        suggestions = generate_suggestions(payload)
        if not suggestions:
            return IdiomSuggestionResponse(
                suggestions=[],
                fallback_message=(
                    "We don't have that idiom in our dictionary yet. "
                    "Ollama did not find a real idiom equivalent, so no literal translation is shown."
                )
            )
        return IdiomSuggestionResponse(
            suggestions=suggestions,
            fallback_message=(
                "We don't have that idiom in our dictionary yet, "
                f"but Ollama looked for a real idiom equivalent."
            )
        )
    except RuntimeError as configuration_error:
        logger.warning("LLM configuration error: %s", configuration_error)
        return IdiomSuggestionResponse(
            suggestions=[],
            fallback_message=str(configuration_error)
        )
    except httpx.ConnectError:
        logger.exception("Could not connect to Ollama at %s", OLLAMA_BASE_URL)
        return IdiomSuggestionResponse(
            suggestions=[],
            fallback_message=f"Local Ollama is not running at {OLLAMA_BASE_URL}. Start Ollama and run: ollama pull {OLLAMA_MODEL}"
        )
    except httpx.HTTPStatusError as error:
        logger.exception("Fallback provider request failed: %s", error)
        return IdiomSuggestionResponse(
            suggestions=[],
            fallback_message="The fallback provider request failed. Dictionary matches will still work."
        )
    except Exception as error:
        logger.exception("Idiom suggestion failed: %s", sanitize_error(f"{error.__class__.__name__}: {error}"))
        return IdiomSuggestionResponse(
            suggestions=[],
            fallback_message="Idiom suggestions are temporarily unavailable. Please try again in a moment."
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
