"""
Context Builder for the Autonomous Scheduler.

Builds intent-scoped LLM context per the Memory & Context Architecture design.
Instead of sending the full chat history to the LLM, we assemble a focused context
from layered sources:

    <THE CONTEXT WHICH IS BEING SENT TO THE LLM>
    1. System prompt (static, always included)- this is the prompt like [you are a parser.....]
    2. Session summary (rolling ~300-word paragraph, included for conversational intents)[the sumarry of n messages out of n+k messages - when k = 20 - then n is revaluated to sumarry of n+=20 and so then k = 0]
    3. mem0 memories (long-lived user facts, included for personalization-dependent intents)[mem0 memories for personalised decision makigns]
    4. Recent messages (last N raw messages for pronoun/referent resolution)[some k message to know what is being happening what has been moved and why]
    5. Current user message (always included)[this is the user prompt ]

Per-intent inclusion rules (from design doc):

why even use sumarry , when mem0 is being used?-this is because the simple sumarry handles the 
conversational flow  - about devcisions were taken and why where as the mem0 is used for the user
preferences , how does user prefer his day and every repetitive about user - so mem0 is to know
who you are and sumarry is to know why is the stuff which is happening happening?

this is something to see -
  - Summary = session-scoped, ephemeral — "what happened in this conversation and why." It dies when the session ends. It answers:
  "why did the gym move to evening?" "what did we already decide about Thursday?"
  - mem0 = user-scoped, persistent — "who is this person." It survives across all sessions forever. It answers: "is this person a
  morning worker?" "how long does their gym usually take?"

  One handles recency (decisions, movements, reasoning from 20 minutes ago), the other handles identity (patterns, preferences,
  corrections learned over weeks).

  Without the summary, the LLM would re-suggest things you already rejected 15 messages ago. Without mem0, it would ask you the same
  questions every new session.



i tell "move the gym to tomorrow evening instead of morrning i have dentist appointment in the tomorrow morning
i am tired today so might miss the evening"  -the coed would reschedule the timeline calendar and then 
store that user was tired ; thurs gym moved-> thurs evenign m thurs - momrnign appointsment 
wednesday tasks moved - so the app wont suggest absurd things again knowing the convo which 
the user had - so mem0 is who u are , and the sumarry is what you were doing some time ago



so the context needed to act upon each intent
energy priority inference should not be dependent on any of the last messages but on the user memories
entirely and so we need the mem0 context for the enery priority 

    | Intent                              | System | mem0 | Summary | Recent N | Current |
    |-------------------------------------|--------|------|---------|----------|---------|
    | Task extraction (NLParser)          | ✓      | ✗    | ✗       | last 2   | ✓       |
    | Intent classification               | ✓      | ✗    | ✗       | last 2   | ✓       |
    | Energy/priority/duration inference   | ✓      | ✓    | ✗       | ✗      | ✓       |
    | Conversational reply / rationale     | ✓      | ✓    | ✓       | last N   | ✓       |
    | Summarization pass                  | ✓      | ✗    | existing | new K    | ✗       |

task extraction - is filling in the schema
intent_classification is trying to know what the user wants to do , [task_update ,task_delete , move_task , create_task?]
energy/priority/duration inference - based on prior user activity trying to figure out how much time & energy & priority would user give on this task
conversational replies - to know how to reply , what to reply for [the summary of what is being happening is needed for good replies-apt replies]
sumarrization pass - pass it to the sumarriser , so we would have a rolling sumarry of n messages ; and k messages stored as it is - one k= 20 send it to 
sumarriser and sumarriser would sumarrise it to new last n message, k=0 resets to 0 again

Requirements: 7.5, 7.6, 7.8, 10.4
"""

import logging#this to get the logging for analysing the cost and optimizing for it
from enum import Enum
from typing import Optional

from pydantic import BaseModel#this is for the Schema 

from app.models.models import ChatMessage

logger = logging.getLogger(__name__)#this is to know for the logging


# ============================================================================
# Intent enum — determines which context layers are included
# ============================================================================




class Intent(str, Enum):#so these could be the user intents 
    TASK_EXTRACTION = "task_extraction"#extract the task
    INTENT_CLASSIFICATION = "intent_classification"#try to figure out the intent of the user
    ENERGY_INFERENCE = "energy_inference"#try to figure out the energy required for that task
    PRIORITY_INFERENCE = "priority_inference"#try to figure out the priority for that task
    DURATION_INFERENCE = "duration_inference"#figure out the duration of the task
    CONVERSATIONAL = "conversational"#the conversational replies using the past context
    RATIONALE = "rationale"#the reason for which the tasks were shifted or not shifted
    SUMMARIZATION = "summarization"#sumarrize the entire thing and give it for sumarrization

_MINIMAL_INTENTS = {
    Intent.TASK_EXTRACTION,#fill in the schema for the task
    Intent.INTENT_CLASSIFICATION,#try to figure out what the user wants to do 
}#so these task require minimal context [only last 2 message+current prompt]

_INFERENCE_INTENTS = {
    Intent.ENERGY_INFERENCE,#trying to figure out how much energy the task needs to be done
    Intent.PRIORITY_INFERENCE,#trying to figure out the priority of the task
    Intent.DURATION_INFERENCE,#trying to figure out the duration of the task 
}#these intents are inference based trying to get the inference of the tasks[energy , priority , duration]
#so these task do not need the past messages or a rolling sumarry of the n words but only need the mem0 memories - to make it personalised




#these are intents which need full context[mem0 memories+n messages + k messages + user prompt]
_FULL_CONTEXT_INTENTS = {
    Intent.CONVERSATIONAL,#this is the natural reply the LLM gives
    Intent.RATIONALE,#this is the explanation of the app that why it did something which it did
    #like it explains its decisions and for this reasoning it might need user preferences
    #the past message for the conversational flow that what was happening and the user's want 
    #in the form of user_prompt
}

# ============================================================================
# LLMContext model — the assembled context passed to LLM calls
# ============================================================================





class Memory(BaseModel):#these are the relevant memories from mem0 
    """A single mem0 memory entry."""
    id: str = ""#this is the memory id
    content: str#this is the content of the relevant memory
    metadata: dict = {}#this is the metadata like which type of memory [task related , preferences , patterns]
'''
  It does fetch from mem0 first-hand — it calls memory_service.get_relevant_memories() which hits mem0's semantic search. The raw
  results from mem0 do have a score. But when context_builder converts them into its own Memory model, it deliberately drops the
  score.

  Why? Because by this point the score has already done its job — mem0 already ranked and filtered by relevance during the search.
  What context_builder cares about is just the content to stuff into the LLM prompt. The LLM doesn't need to know "this memory had
  0.87 relevance" — it just needs the text.

  So: memories come from mem0 (via memory_service.py), score is used for ranking during retrieval, then discarded when packaging for
  the LLM context.
the whole pipeline to this 

  1. User types prompt → hits chat.py router
  2. Chat router calls intent classification (cheap LLM call with minimal context) → returns e.g. task_update
  3. Chat router maps to context_builder Intent (e.g. task_update needs conversational reply → Intent.CONVERSATIONAL)
  4. Chat router calls build_context(user_id, session_id, message, intent)
  5. build_context sees intent is in _FULL_CONTEXT_INTENTS → fetches summary + memories + recent N messages
  6. _fetch_memories(user_id, query) calls memory_service.get_relevant_memories() → mem0 semantic search → returns ranked results
  with scores
  7. Context_builder strips the score, keeps id/content/metadata, packages into LLMContext
  8. LLMContext.to_messages() flattens everything into the [system, ...recent, user] message list
  9. Chat router passes that to the LLM → gets the apt response

  So context_builder is a builder, not a decision-maker. The chat router is the orchestrator that says "I need conversational
  context" and context_builder assembles the right layers for that intent.


'''


class LLMContext(BaseModel):
    """
    Assembled LLM context for a single request.

    Fields:
        system_prompt: Static instruction text (tool descriptions, response format rules).
                       Provider-side cached when supported.
        session_summary: Rolling ~300-word paragraph of session context. None if not
                         applicable for this intent or if no summary exists yet.
        memories: List of relevant mem0 memories scoped to the current query.
                  Empty list for intents that don't need personalization.
        recent_messages: The most recent N raw messages (oldest-first) for pronoun
                         resolution. Length varies by intent (2 for extraction, N for chat).
        current_message: The new user input being processed.
        cache_hints: Dict of field names that should be provider-side cached.
                     Callers can use this to enable caching on supported providers.
    """
    system_prompt: str#this is the prompt which would be passed to the AI  
    session_summary: Optional[str] = None#the 300 word summary else none - if not there
    memories: list[Memory] = []#the list of memories if requited else  empty list  
    recent_messages: list[dict] = []  # [{"role": "user"|"assistant", "content": str}][convo history]
    current_message: str#the user prompt 
    cache_hints: dict = {}  # e.g. {"system_prompt": True, "session_summary": True} 
    #the cache hints is for the cost optimization  - by saving on the token costs for recurring tasks

    

    def to_messages(self) -> list[dict]:#this is the formatter
        """
        Flatten context into a messages list suitable for LLM API calls.

        Returns a list of role/content dicts in the order:
            [system, ...recent_messages, user(current_message)]

        The system prompt includes session_summary and memories inline when present,
        so the LLM sees them as stable prefix content (better for caching).
        """
        # system_parts is the thing which would be passed to the LLM
        system_parts = [self.system_prompt]
        #this it the part 1 of the system_prompt


        if self.session_summary:
            system_parts.append(
                f"\n\n## Session Context\n{self.session_summary}"
            )

        if self.memories:
            memory_text = "\n".join(f"- {m.content}" for m in self.memories)
            system_parts.append(
                f"\n\n## User Memories\n{memory_text}"
            )
            '''
            user goes to gym in morning
            user loves to work on his startup the first thing in mornign 
            user loves to go on walks on sundays to areas like professor lake - so dont schedule anything on sunday afternoons
            '''

        messages = [{"role": "system", "content": "\n".join(system_parts)}]#this is a list of dictionaries

        # Add recent messages (oldest-first conversation flow)
        for msg in self.recent_messages:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Add the current user message
        messages.append({"role": "user", "content": self.current_message})

        return messages#all of it goes to the LLM 
        #the messages is the everything which goes to the LLM , the sumarry , the memories and the messages
        '''
          so the messages is the system_prompt which goes to the LLM and it contains system_prompt[you are a parser.....] ; the memories of
  the user , the sumarry of the conversation of the last n message  , something about k messages in the recent_messages and the
  last_message[the user prompt] - and this all goes to the LLM okk

  Yes. Exactly. One correction on terminology: messages is the full payload to the LLM, not just the system prompt. It contains
  multiple messages with different roles:

  1. "role": "system" — the instructions + summary + memories (one block)
  2. "role": "user" / "role": "assistant" — the k recent messages (as separate turns)
  3. "role": "user" — the current message (last item)

  All of it = one API call to the LLM. That's the complete context the LLM has to work with.
        '''
# ============================================================================
# Context builder — the main public function
# ============================================================================
#this function is the brain of the entire file
async def build_context(
    user_id: str,
    session_id: str,
    current_message: str,#this is the current user_message
    intent: Intent,
    recent_n: int = 10,#so how much msgs needed based on the intent - this could be overwritten
    system_prompt: str = "",
) -> LLMContext:
    """
    Build intent-scoped LLM context.

    Assembles the convo based on the intent type:
    - Minimal intents (extraction, classification): system + last 2 + current
    - Inference intents (energy, priority, duration): system + memories + current
    - Full intents (conversational, rationale): system + summary + memories + recent N + current
    - Summarization: handled separately by SessionSummarizer (not through this path)

    Args[arguements or the attributes]:
        user_id: The authenticated user's ID.
        session_id: The current chat session ID.
        current_message: The new user input being processed.
        intent: The classified intent determining context scope.[full context , minimal , inference]
        recent_n: Max number of recent messages for full-context intents (default 10).
        system_prompt: The static system prompt text.

    Returns:
        LLMContext with all applicable layers populated.

    Notes:
        - Provider-side prompt caching is enabled via cache_hints for system_prompt
          and session_summary. Callers should check cache_hints and apply caching
          if their LLM SDK supports it (e.g., OpenAI, Anthropic). If not supported,
          the hints are simply ignored — no failure.
        - mem0 failures degrade gracefully (empty memories list, warning logged).
        - Missing ChatSession (no summary yet) is normal — session_summary stays None.
    """
    session_summary:Optional[str] =  None
    memories: list[Memory] = []
    recent_messages: list[dict] = []
    cache_hints: dict = {}

    # System prompt is always cached when possible - this is for the cost optimization 
    if system_prompt:
        cache_hints["system_prompt"] = True

    # --- Determine which layers to include based on intent ---

    if intent in _MINIMAL_INTENTS:
        # Task extraction / intent classification: only last 2 messages for follow-ups no memory required
        recent_messages = await _fetch_recent_messages(
            user_id, session_id, limit=2
        )#the other attributes would be empty leading to no errors

    elif intent in _INFERENCE_INTENTS:#this only reuires memory and not the conversation flow
        # Energy/priority/duration inference: memories for personalization, no history
        memories = await _fetch_memories(user_id, current_message)

    elif intent in _FULL_CONTEXT_INTENTS:
        # Conversational / rationale: full context
        session_summary = await _fetch_session_summary(user_id, session_id)
        memories = await _fetch_memories(user_id, current_message)
        recent_messages = await _fetch_recent_messages(
            user_id, session_id, limit=recent_n
        )
        # Session summary is stable content — cache it- stable content means the content which does not change much
        if session_summary:
            cache_hints["session_summary"] = True

    elif intent == Intent.SUMMARIZATION:
        # Summarization is handled by SessionSummarizer directly.
        # If called here, just include the existing summary for reference.
        session_summary = await _fetch_session_summary(user_id, session_id)

    return LLMContext(
        system_prompt=system_prompt,
        session_summary=session_summary,
        memories=memories,
        recent_messages=recent_messages,
        current_message=current_message,
        cache_hints=cache_hints,
    )#this would just give the final prompt


# ============================================================================
# Private helpers — fetch each context layer
# ============================================================================



#fetch the limit number of msg like the last n [10 , 2 , 0 ]msgs
async def _fetch_recent_messages(
    user_id: str,
    session_id: str,
    limit: int,
) -> list[dict]:
    """
    Fetch the most recent `limit` messages for the session, oldest-first.

    Returns a list of {"role": str, "content": str} dicts ready for LLM consumption.
    Degrades gracefully if the DB is unavailable. - the program does not stop
    """
    try:
        from app.db import get_session
        from app.crud.chat_crud import list_session_messages

        db_session = get_session()
        try:
            messages: list[ChatMessage] = list_session_messages(
                db_session, session_id, user_id, limit=limit
            )
            return [
                {"role": msg.role, "content": msg.content}
                for msg in messages
            ]
        finally:
            db_session.close()
    except Exception as exc:
        logger.warning(
            "Failed to fetch recent messages for context: %s", exc
        )
        return []



#this sumarry is in the LLM context from the chat session as the context
async def _fetch_session_summary(
    user_id: str,
    session_id: str,
) -> Optional[str]:
    """
    Fetch the rolling session summary from the ChatSession table.

    Returns None if no session exists yet or if the summary hasn't been generated.
    Degrades gracefully if ChatSession model/table doesn't exist yet.
    """
    try:
        from app.db import get_session

        db_session = get_session()
        try:
            # Try to import and query ChatSession
            # This will gracefully handle the case where the model doesn't exist yet
            from sqlmodel import select

            try:
                from app.models.models import ChatSession  # type: ignore[attr-defined]
                statement = select(ChatSession).where(
                    ChatSession.id == session_id,#for that user_id , select the chat_id
                    ChatSession.user_id == user_id,
                )
                result = db_session.exec(statement).first()
                if result and result.summary:
                    return result.summary#so a chat session has sumarry returns a rolling sumarry of 300 words
            except (ImportError, AttributeError):
                # ChatSession model not yet defined — that's fine
                pass

            return None
        finally:
            db_session.close()
    except Exception as exc:
        logger.warning(
            "Failed to fetch session summary for context: %s", exc
        )
        return None





#_fetch_memories() - is an important function to review
#this is used to fetch the memories about the user as the context for the Agent
async def _fetch_memories(
    user_id: str,
    query: str,
) -> list[Memory]:
    """
    Fetch relevant mem0 memories scoped to the user and current query.

    Degrades gracefully if memory_service is unavailable or mem0 is not configured.
    Memories are omitted for extraction/classification intents
    (handled by the caller), so this is only called for inference and conversational intents.
    """
    try:
        from app.services.memory_service import get_relevant_memories#this uses semantic search

        raw_memories = await get_relevant_memories(user_id, query)
        # Normalize to our Memory model
        return [
            Memory(
                id=getattr(m, "id", ""),
                content=getattr(m, "content", str(m)) if hasattr(m, "content") else str(m),
                metadata=getattr(m, "metadata", {}),
            )
            for m in raw_memories
        ]
    except ImportError:
        # memory_service not yet implemented — degrade silently
        logger.debug("memory_service not available, proceeding without memories")
        return []
    except Exception as exc:
        # mem0 unavailable or errored — degrade gracefully per design
        logger.warning(
            "Failed to fetch memories for context (proceeding without): %s", exc
        )
        return[]







