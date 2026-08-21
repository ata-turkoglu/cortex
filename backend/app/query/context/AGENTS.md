# Conversation Context

Read parent `../AGENTS.md` and the Query V2 runtime contract. Own conversation-local references,
focus, assumptions, and bounded history. Never write conversation assumptions into canonical
workspace knowledge, and preserve ambiguity when a follow-up cannot be resolved safely. Persist
typed state through `store.py`; provider calls consume detached snapshots and occur outside the
persistence transaction.
