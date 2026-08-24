"""Conversation-local context boundary for Query V2."""

from .schemas import (
    ContextAssumption,
    ContextCanonicalResultSet,
    ContextConstraint,
    ContextEntityReference,
    ContextTemporalFocus,
    ConversationContext,
    ConversationContextState,
    ConversationTurn,
)
from .store import ContextRevisionConflict, load_conversation_context, save_conversation_context

__all__ = [
    "ContextAssumption",
    "ContextCanonicalResultSet",
    "ContextConstraint",
    "ContextEntityReference",
    "ContextRevisionConflict",
    "ContextTemporalFocus",
    "ConversationContext",
    "ConversationContextState",
    "ConversationTurn",
    "load_conversation_context",
    "save_conversation_context",
]
