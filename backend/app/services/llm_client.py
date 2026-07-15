"""
LLM client for the Autonomous Scheduler.

Thin async wrapper that abstracts our two LLM providers:

    Primary  : Groq (free tier, fast)         — llama-3.1-8b-instant for parsing,
                                                  llama-3.3-70b-versatile for chat
    Fallback : Google Gemini (gemini-2.0-flash) when Groq rate-limits or 5xx's

Two public coroutines are exposed:

    parse_call(...)  - structured-output (JSON) extraction. Used by NLParser,
                       intent classification, energy/priority/duration inference,
                       summary generation. Validates the response is JSON and
                       retries once with a stricter prompt if malformed.

    chat_call(...)   - free-form conversational reply. Used by the chat router
                       and scheduling-rationale generator. Optionally streams.

Both calls log per-request metrics (provider, model, prompt_tokens,
completion_tokens, intent) so we can track per-user cost.
- so this is to simply know that per se if i am having more gemini logs than groq 
groq is cutting me off 
- or what is the token usage per customer how can I optimize cost based on that 
from shifting from X model to Y model 





API keys are read lazily inside the call so importing this module never crashes
even when the env is empty (useful for local dev and CI without secrets).
"""

import json
import logging
import os
from typing import AsyncIterator, Optional, Union

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# ============================================================================
# Public exception types
# ============================================================================

#explaining these errors
class LLMError(Exception):
    """Base class for any LLM-related failure surfaced to callers."""

# this is called when the setup is broken 
# like the API key missing or import failed 
# so in this case the msg is clear shift to the Fallback
# model gemini - and this means that groq wont even be Tried


class LLMRateLimitError(LLMError):
    """Both providers rate-limited or otherwise unavailable."""


#this is like the proper nuke it is only called when
#both the providers have reached their limit and so 
#may return that the servive is not in use for 1 minute
#try 1 min later 



#error is called when kinda everything is down 
class LLMSchemaError(LLMError):
    """Provider returned non-JSON or JSON that doesn't satisfy the schema."""


#this is nothing but the schema error
#so if even after the stric prompt and both providers bieng in ue
#the return text is garbage ie not in the json format then this error is returned


# ============================================================================
# Internal helpers
# ============================================================================


def _parser_model() -> str:
    """Model name used for structured-output calls. Default: Groq llama-3.1-8b-instant."""
    return os.getenv("MODEL_PARSER", "llama-3.1-8b-instant")


def _chat_model() -> str:
    """Model name used for free-form replies. Default: Groq llama-3.3-70b-versatile."""
    return os.getenv("MODEL_CHAT", "llama-3.3-70b-versatile")




#in the fallback there is only one model in use as this model handels both 
#the chat and the parsing 
def _fallback_model() -> str:
    """Gemini model used when Groq is unavailable. Default: gemini-2.0-flash."""
    return os.getenv("MODEL_FALLBACK", "gemini-2.0-flash")



#this is the requirement to get the key 
def _require_groq_key() -> str:
    key = os.getenv("GROQ_API_KEY")
    if not key or key.startswith("your_"):
        raise LLMError("GROQ_API_KEY not set")
    return key




def _require_gemini_key() -> str:
    key = os.getenv("GOOGLE_API_KEY")
    if not key or key.startswith("your_"):
        raise LLMError("GOOGLE_API_KEY not set")
    return key




#so this is to check for the conditions when we have to fallback to the other model 
def _is_rate_limit_or_5xx(exc: Exception) -> bool:
    """
    Decide whether an exception from Groq is worth a Gemini fallback.



    the 5xx errors means that your requests were valid but the servers could not 
    process them - due to an unexpected problem 
    
    Groq raises `groq.RateLimitError` for 429s. For 5xx errors it raises
    `groq.InternalServerError` / `groq.APIStatusError`. We match by class
    name so we don't have to import every error class explicitly.

    """


    #429 - you hit the free tier limit 
    #500 - gorq server crashed 
    # APIStatusError - bad HTTP status from groq 
    #API connnection error - couldnt reach groq
    #API time out error - groq took too long to respond


#these are the errors to check from 
    errors = {"RateLimitError", "InternalServerError", "APIStatusError",
          "APIConnectionError", "APITimeoutError"}

    name = type(exc).__name__#this is to avoid the crashouts because of the lazy import structure of the file 
    if name in errors:
        return True
    # Some SDKs expose .status_code; treat 429 and 5xx as fallback-worthy.
    status = getattr(exc, "status_code", None)
    if status is not None and (status == 429 or 500 <= status < 600):
        #if the status code is this - then fallback to the gemini model 

        return True #this simply means fall back to gemini
    return False 


'''
the significance of the return false in the 
above code block is very simple 


say if the errors were in the format 

400 - bad request
401 - unauthorized 
403  - forbidden 
404 - not found
422 - unprocessable entiry 


so in these errors the fault was not of the service provider
but some bug in the code so even changing to the gemini model wont help 
so in this case dont chose any model instead return an error

'''



'''
Significane of these log calls 
these log calls are simply for the cost optimization 
and profit maximising pov 
these are to know when was the groq model differed to the gemini model 
so this is to know which model is the best to keep 
and should i switch from teh X model to Y model 
most important part helps us get the cost per user


using the prompt tokens you can calculate the per usage costings

'''
def _log_call(*, provider: str, model: str, intent: str,
              prompt_tokens: Optional[int], completion_tokens: Optional[int]) -> None:
    """Emit a structured log line per LLM call. Used for cost tracking."""
    logger.info(
        "llm_call",
        extra={
            "llm": {
                "provider": provider,
                "model": model,
                "intent": intent,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            }
        },
    )


# ============================================================================
# parse_call — structured output (JSON)
# ============================================================================


async def parse_call(
    *,
    system_prompt: str,#instruction to the LLM - you are task parser ---
    user_message: str,#the actual user message
    schema: dict,#JSON schema which is returned back 
    max_tokens: int = 512,#cap on these amount of tokens
    intent: str = "parse", #this is to know for what use the model was calles for the logging
    #the main use could be to calculate the token burning for one use case
    #ok so this is to know which model was called for what intent say groq for ? -
    # chat or gemini as fallback for - parsing the task is as to know which task burns the most tokens 



) -> dict:
    """
    Run a structured-output LLM call and return the parsed JSON dict.

    Tries Groq first (MODEL_PARSER); on rate-limit / 5xx falls back to Gemini
    (MODEL_FALLBACK). If the returned text isn't valid JSON, retries once with
    a stricter "respond with JSON only" instruction. Raises LLMSchemaError if
    the second attempt also fails.

    The `schema` dict is a JSON schema describing the expected shape. Groq
    accepts only `{"type": "json_object"}`, but Gemini honours the full schema
    via its `response_schema` knob.
    """
    # --- attempt 1: Groq -c
    try:
        text = await _groq_parse(system_prompt, user_message, max_tokens, intent)
    except LLMError:
        # Key missing or import failed — go straight to Gemini.
        text = await _gemini_parse(system_prompt, user_message, schema, max_tokens, intent)
    except Exception as exc:
        if _is_rate_limit_or_5xx(exc):#go to gemini if rate hit
            text = await _gemini_parse(system_prompt, user_message, schema, max_tokens, intent)
        else:#this means that some other error hit 
            raise LLMError(f"Groq parse_call failed: {exc}") from exc

    # --- parse JSON ---
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass  # fall through to retry 
        #this would pass further upon to retry 

    # --- attempt 2: stricter retry ---
    stricter_prompt = (
        system_prompt
        + "\n\nIMPORTANT: respond with a single valid JSON object and nothing else. "
        "No prose. No markdown fences. No commentary."
    )
    try:
        text = await _groq_parse(stricter_prompt, user_message, max_tokens, intent)
    except LLMError: 
        text = await _gemini_parse(stricter_prompt, user_message, schema, max_tokens, intent)
    except Exception as exc:
        if _is_rate_limit_or_5xx(exc):#from groqs side
            text = await _gemini_parse(stricter_prompt, user_message, schema, max_tokens, intent)
        else:#this handles the user error like error 400
            raise LLMError(f"Groq parse_call failed on retry: {exc}") from exc

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMSchemaError(f"Model returned non-JSON after retry: {text!r}") from exc


async def _groq_parse(system_prompt: str, user_message: str,
                      max_tokens: int, intent: str) -> str:
    """Single Groq parse attempt. Raises on any error; caller decides fallback."""
    from groq import AsyncGroq  # imported lazily so import-time stays light

    client = AsyncGroq(api_key=_require_groq_key())
    model = _parser_model()
    # Groq requires the word "json" in messages when using json_object format
    sys_content = system_prompt if "json" in system_prompt.lower() else system_prompt + "\nRespond with JSON."
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": sys_content},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
        max_tokens=max_tokens,
        temperature=0.0,
    )


    #this would give the token counts 
    usage = getattr(resp, "usage", None)
    _log_call(
        provider="groq",
        model=model,
        intent=intent,
        prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
        completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
    )
    return resp.choices[0].message.content or ""


'''
this is the groq response structure 


{
  "choices": [
    {
      "message": {
        "content": "{\"title\": \"gym\", \"duration_minutes\": 60, ...}"
      }
    }
  ]
}



and this is the resp 
resp (ChatCompletion)
├── id: "chatcmpl-abc123"                    # unique ID for this request
├── object: "chat.completion"                # always this string
├── created: 1705312000                      # unix timestamp
├── model: "llama-3.1-8b-instant"            # model that actually ran
├── choices: [                               # list (usually 1 item)
│   └── [0] (Choice)
│       ├── index: 0
│       ├── message (Message)
│       │   ├── role: "assistant"
│       │   └── content: '{"title": "gym", "duration_minutes": 60, ...}'
│       └── finish_reason: "stop"            # "stop" = done, "length" = hit max_tokens
│   ]
├── usage (Usage)                            # ← what we read for logging
│   ├── prompt_tokens: 280                   # tokens in your input (system + user message)
│   ├── completion_tokens: 95                # tokens the LLM generated
│   └── total_tokens: 375                    # sum of both
└── system_fingerprint: "fp_abc123"          # internal Groq version identifier

'''



#gemini resp structure
'''
resp (GenerateContentResponse)
├── text: '{"title": "gym", "duration_minutes": 60, ...}'    # ← shortcut to the output
├── candidates: [
│   └── [0] (Candidate)
│       ├── content (Content)
│       │   ├── role: "model"
│       │   └── parts: [
│       │       └── [0] (Part)
│       │           └── text: '{"title": "gym", ...}'
│       │       ]
│       ├── finish_reason: "STOP"
│       └── safety_ratings: [...]
│   ]
├── usage_metadata (UsageMetadata)                           # ← token counts
│   ├── prompt_token_count: 280
│   ├── candidates_token_count: 95
│   └── total_token_count: 375
└── prompt_feedback: None                                    # safety filter info

'''


async def _gemini_parse(system_prompt: str, user_message: str, schema: dict,
                        max_tokens: int, intent: str) -> str:
    """Gemini fallback for structured calls."""
    import google.generativeai as genai

    genai.configure(api_key=_require_gemini_key())
    model_name = _fallback_model()
    # Gemini's "response_schema" path is fussy about JSON-Schema dialects;
    # asking for application/json without the schema is more forgiving and
    # works fine when the system prompt itself describes the shape.
    model = genai.GenerativeModel(
        model_name,
        system_instruction=system_prompt,
        generation_config={
            "response_mime_type": "application/json", 
            "max_output_tokens": max_tokens,
            "temperature": 0.0,
        },
    )
    resp = await model.generate_content_async(user_message)
    usage = getattr(resp, "usage_metadata", None)
    _log_call(
        provider="gemini",
        model=model_name,
        intent=intent,
        prompt_tokens=getattr(usage, "prompt_token_count", None) if usage else None,
        completion_tokens=getattr(usage, "candidates_token_count", None) if usage else None,
    )
    return resp.text or ""


# ============================================================================
# chat_call — free-form output, optionally streaming
# ============================================================================


async def chat_call(
    *,
    system_prompt: str,#you are a helpful schedulin assitent
    messages: list[dict],#[{"role":"user" , "content":".."},{"role":"assistant" , "content":".."} , {"role":"user" , "content":"..."} , {"role":"assistant" , "content":"..."}]
    stream: bool = False,#this is the streaming from the SSE provided
    intent: str = "chat",
    system_prompt_cache_key: Optional[str] = None,#this is for caching maybe for the gemini use in future
) -> Union[str, AsyncIterator[str]]:
    """
    Free-form chat call. Uses MODEL_CHAT (Groq llama-3.3-70b-versatile by default).

    `messages` is a list of `{"role": "user"|"assistant", "content": str}` dicts
    in chronological order. The system prompt is passed separately so the
    caller never has to think about role ordering.

    When `stream=True` returns an async iterator of token strings; otherwise
    returns the full response as a single string. Falls back to Gemini on
    Groq rate-limit / 5xx.

    `system_prompt_cache_key` is forwarded to Gemini's cached_content path
    when set; Groq has no caching API as of late 2024 so we ignore it there.
    """


    if stream:
        return _chat_stream(system_prompt, messages, intent)

    try:
        return await _groq_chat(system_prompt, messages, intent)
    except LLMError:
        return await _gemini_chat(system_prompt, messages, intent, system_prompt_cache_key)
    except Exception as exc:
        if _is_rate_limit_or_5xx(exc):
            return await _gemini_chat(system_prompt, messages, intent, system_prompt_cache_key)
        raise LLMError(f"Groq chat_call failed: {exc}") from exc


async def _groq_chat(system_prompt: str, messages: list[dict], intent: str) -> str:
    from groq import AsyncGroq

    client = AsyncGroq(api_key=_require_groq_key())
    model = _chat_model()
    resp = await client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system_prompt}, *messages],
        temperature=0.7,#moderate creaticity - this is the knob for creativity
        #this has a slight variety every time 

    )
    usage = getattr(resp, "usage", None)
    _log_call(
        provider="groq",
        model=model,
        intent=intent,
        prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
        completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
    )
    return resp.choices[0].message.content or ""


async def _gemini_chat(system_prompt: str, messages: list[dict], intent: str,
                       cache_key: Optional[str]) -> str:
    import google.generativeai as genai

    genai.configure(api_key=_require_gemini_key())
    model_name = _fallback_model()

    # Build a Gemini-style history (alternating roles, "model" instead of "assistant").
    history = []
    for m in messages[:-1]:
        role = "model" if m["role"] == "assistant" else "user"
        history.append({"role": role, "parts": [m["content"]]})

    kwargs: dict = {"system_instruction": system_prompt}
    if cache_key:
        kwargs["cached_content"] = cache_key

    model = genai.GenerativeModel(model_name, **kwargs)
    chat = model.start_chat(history=history)
    last = messages[-1]["content"] if messages else ""
    resp = await chat.send_message_async(last)

    usage = getattr(resp, "usage_metadata", None)
    _log_call(
        provider="gemini",
        model=model_name,
        intent=intent,
        prompt_tokens=getattr(usage, "prompt_token_count", None) if usage else None,
        completion_tokens=getattr(usage, "candidates_token_count", None) if usage else None,
    )
    return resp.text or ""





#this is just tokens being fired one by one
async def _chat_stream(system_prompt: str, messages: list[dict],
                       intent: str) -> AsyncIterator[str]:
    """
    Streaming variant. Tries Groq first; on rate-limit/5xx, restarts with
    Gemini. We don't try to mid-stream switch providers — that's a UX mess.
    """
    from groq import AsyncGroq

    try:
        client = AsyncGroq(api_key=_require_groq_key())
        model = _chat_model()
        stream = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system_prompt}, *messages],
            temperature=0.7,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
        _log_call(provider="groq", model=model, intent=intent,
                  prompt_tokens=None, completion_tokens=None)
        return
    except LLMError:
        pass  # Groq key missing — fall through to Gemini
    except Exception as exc:
        if not _is_rate_limit_or_5xx(exc):
            raise LLMError(f"Groq stream failed: {exc}") from exc

    # Gemini streaming fallback
    import google.generativeai as genai

    genai.configure(api_key=_require_gemini_key())
    model_name = _fallback_model()
    model = genai.GenerativeModel(model_name, system_instruction=system_prompt)

    history = []
    for m in messages[:-1]:
        role = "model" if m["role"] == "assistant" else "user"
        history.append({"role": role, "parts": [m["content"]]})

    chat = model.start_chat(history=history)
    last = messages[-1]["content"] if messages else ""
    resp = await chat.send_message_async(last, stream=True)
    async for chunk in resp:
        if chunk.text:
            yield chunk.text
    _log_call(provider="gemini", model=model_name, intent=intent,
              prompt_tokens=None, completion_tokens=None)
