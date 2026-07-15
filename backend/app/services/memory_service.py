"""
Memory Service — wraps mem0 for long-term user memory.
Provides semantic search over a user's stored preferences, patterns, and
corrections, and allows adding new memories when the system detects relevant
information (e.g., "I prefer mornings for deep work", duration patterns,
priority rules).
Graceful degradation: if mem0 is unavailable (API key missing, network error,
service down), the service logs a warning and returns empty results / silently
skips writes. The rest of the system continues without memory context.
Conversational feedback uses mem0 for personalization.
"""


#this is the memory servive where the entire model gets better
import logging
import os
from dataclasses import dataclass, field
from typing import Any



#logger - is for the logging
logger = logging.getLogger(__name__)#so the log meessage create the module name and show it in the logs 
#the module name would be memory service , so you immediately know from where the module log came 



# ============================================================================
# Public data model
# ============================================================================


@dataclass
class Memory:#this is the retrieval model to get the relevant memories from the mem0 
    """
    A single memory entry retrieved from mem0.

    Attributes:
        id: Unique identifier assigned by mem0.
        content: The natural-language content of the memory.
        metadata: Arbitrary metadata dict (e.g., {"type": "preference"}).
        score: Relevance score from semantic search (0.0–1.0). May be None
               if the provider doesn't return scores.
               #this is using embeddings of the keywords input 
            
    more reflection on metadata
    mem0.add(
        "User prefers morning tasks 
        user_id= "MN"
        metadata = {"type":preference}#this means this data has to be saved in the preference 
        column of the user 
 )


    mem0.add(
        "john usually works more on friday nights on his startups after his job"

        metadata = {"type":pattern}

        #the user has a pattern that he works on friday nights [2-3 occurence]
    )           
    """

    id: str#assigned by the mem0 
    content: str#this is the memory in the natural language
    metadata: dict[str, Any] = field(default_factory=dict)#see in the above instance
    score: float | None = None#relevance score from semantic search[uses embeddings] 



# ============================================================================
# Internal helpers
# ============================================================================


def _get_mem0_api_key() -> str | None:
    """
    Return the MEM0_API_KEY from environment, or None if not configured.

    A key starting with "your_" is treated as a placeholder (not configured).
    """
    key = os.getenv("MEM0_API_KEY")
    if not key or key.startswith("your_"):
        return None
    return key

def _get_client():#this is to get the memory client functionality of the mem0 
    """
    Lazily import and instantiate the mem0 MemoryClient.

    Returns None if the API key is missing or the import fails.
    This lazy approach keeps the module importable even when mem0ai
    is not installed or configured (useful for CI and local dev).
    """
    api_key = _get_mem0_api_key()
    if api_key is None:
        logger.debug("MEM0_API_KEY not configured; mem0 client unavailable")
        return None

    try:#memory client is mem0 memory function 
        from mem0 import MemoryClient  # type: ignore[import-untyped]

        return MemoryClient(api_key=api_key)
    except ImportError:
        logger.warning("mem0ai package not installed; memory features disabled")
        return None
    except Exception as exc:
        logger.warning("Failed to initialize mem0 client: %s", exc)
        return None


# ============================================================================
# Public API
# ============================================================================

#we are passing user_id - because this is gonna fetch the memory from the user_id
async def get_relevant_memories(user_id: str, query: str) -> list[Memory]:
    """
    Semantic search over the user's mem0 memory store.

    Returns a list of Memory objects ranked by relevance to the query.
    Returns an empty list if mem0 is unavailable or the search fails.

    Parameters
    ----------
    user_id : str
        The user whose memories to search.
    query : str
        Natural-language query for semantic matching.

    Returns
    -------
    list[Memory]
        Relevant memories sorted by score (highest first), or [] on failure.

    in a nutshell returns the user memory which are most relevant to the query - and is then 
    arranged in a list with the relevance of the memory from high-> low from begin->end




 The query parameter in get_relevant_memories(user_id, query) is typically the user's natural language input (their
  task description or chat message). The semantic search then returns memories most relevant to that specific task — things like:

  - "I prefer mornings for deep work" → influences scheduling time
  - "Gym sessions are usually 90 minutes" → infers duration
  - "I always prioritize work over personal tasks" → infers priority
  - "I'm a night owl" → influences energy window placement

  So when a user says "schedule a gym session tomorrow," the query "gym session" hits mem0 and pulls back stored patterns like
  duration history, preferred times, energy associations — all to make scheduling smarter and more personalized without the user
  repeating themselves every time.

  It feeds into Requirements 1 (duration/priority inference), 4 (energy preferences), and 7 (personalization context for LLM
  decisions).

    """
    client = _get_client()#get the memory client from the above function 
    if client is None:
        return []

    try:
        results = client.search(query=query, user_id=user_id)

        memories: list[Memory] = []#memory is the class we initialised on the to
        #so these memories would be a list of dict like ["id" , "memory" , "metadata" , "score"]
        # mem0 returns a list of dicts (or objects) with id, memory, metadata, score
        for item in results:
            # Handle both dict-style and object-style responses from mem0
            if isinstance(item, dict):#if the item we got is of the dict type
                memory_id = item.get("id", "")
                content = item.get("memory", "") or item.get("content", "")
                metadata = item.get("metadata") or {}
                score = item.get("score")
            else:
                memory_id = getattr(item, "id", "")
                content = getattr(item, "memory", "") or getattr(item, "content", "")
                metadata = getattr(item, "metadata", None) or {}
                score = getattr(item, "score", None)

            memories.append(Memory(
                id=str(memory_id),
                content=str(content),
                metadata=metadata if isinstance(metadata, dict) else {},
                score=float(score) if score is not None else None,
            ))

        return memories

    except Exception as exc: #this is error handling
        logger.warning(
            "mem0 search failed for user %s (query: %r): %s",
            user_id,
            query[:50],
            exc,
        )
        return []



#we are using the user id - so as to add the content on that user_id
async def add_memory(user_id: str, content: str, metadata: dict[str, Any] | None = None) -> None:
    """
    Store a new memory in the user's mem0 store.

    Used to persist:
    - Preference statements ("I prefer mornings for deep work")
    - Scheduling patterns ("I usually work out at 7am")
    - Explicit corrections to defaults
    - Learned priority rules ("User prioritizes work tasks highly")
    - Learned duration patterns ("Gym sessions are typically 90 minutes")

    Silently returns if mem0 is unavailable or the write fails.

    Parameters
    ----------
    user_id : str
        The user to associate the memory with.
    content : str
        Natural-language content of the memory.
    metadata : dict | None
        Optional metadata (e.g., {"type": "preference", "category": "energy"}).
    """
    if not content or not content.strip():
        logger.debug("Skipping empty memory content for user %s", user_id)
        return[]

    client = _get_client()
    if client is None:
        return[]

    try:
        messages = [{"role": "user", "content": content}]
        kwargs: dict[str, Any] = {"messages": messages, "user_id": user_id}
        if metadata:
            kwargs["metadata"] = metadata#metadata is optional
            #so if metadata is preset add the metadata as well 

        client.add(**kwargs)
        logger.info(
            "Stored memory for user %s: %s",
            user_id,
            content[:80],
        )
    except Exception as exc:
        logger.warning(
            "mem0 add failed for user %s (content: %r): %s",
            user_id,
            content[:50],
            exc,
        )





