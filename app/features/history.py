"""
Contextual memory retrieval: search every past conversation with SQLite's built-in full-text
search (FTS5). It is fast, uses almost no memory, and ranks results by relevance (BM25).

Used two ways:
  * you ask:  "what did we talk about regarding flask?"
  * automatically: when you say "last time we..." relevant old messages are added to the AI's prompt
"""
import re

from app.agent.registry import Param, Tool, ToolContext, ToolError
from app.features.base import Feature, rule
from app.storage.database import DatabaseError

_STOP = {"the", "and", "for", "you", "your", "what", "who", "how", "are", "was", "has", "have", "with",
         "that", "this", "can", "tell", "about", "did", "does", "when", "where", "which", "then", "than",
         "talk", "talked", "discuss", "discussed", "said", "regarding", "conversation", "chat", "history"}
_RECALL = re.compile(
    r"\b(?:last time|earlier|previously|we (?:talked|spoke|discussed)|you (?:said|told|mentioned|suggested)|"
    r"i (?:told|asked|said|mentioned)|remember when|the other day)\b", re.IGNORECASE)


def _short(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 3].rstrip() + "..."


def _match_expression(text: str) -> str | None:
    tokens = [t for t in re.findall(r"[a-z0-9]{3,}", text.lower()) if t not in _STOP][:8]
    return " OR ".join(f'"{t}"*' for t in tokens) if tokens else None   # Quoted, so no FTS syntax errors


class HistoryIndex:
    def __init__(self, db, user_id: int):
        self.db, self.user_id = db, user_id
        self.available = False
        self._ensure()

    def _ensure(self):
        """Create the index (once) and keep it in sync with new and deleted messages."""
        try:
            existed = self.db.row("SELECT name FROM sqlite_master WHERE name = 'messages_fts'")
            self.db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5("
                            "content, content='messages', content_rowid='id')")
            self.db.execute("CREATE TRIGGER IF NOT EXISTS messages_fts_ai AFTER INSERT ON messages BEGIN "
                            "INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content); END")
            self.db.execute("CREATE TRIGGER IF NOT EXISTS messages_fts_ad AFTER DELETE ON messages BEGIN "
                            "INSERT INTO messages_fts(messages_fts, rowid, content) "
                            "VALUES ('delete', old.id, old.content); END")
            if not existed:   # First time: index the messages that already exist
                self.db.execute("INSERT INTO messages_fts(messages_fts) VALUES ('rebuild')")
            self.available = True
        except DatabaseError:
            self.available = False   # For example a Python build without FTS5

    def search(self, query: str, limit: int = 6, exclude_id: int | None = None) -> list[dict]:
        expression = _match_expression(query)
        if not self.available or not expression:
            return []
        sql = ("SELECT m.role, m.content, m.created_at, c.id AS cid, c.title FROM messages_fts "
               "JOIN messages m ON m.id = messages_fts.rowid "
               "JOIN conversations c ON c.id = m.conversation_id "
               "WHERE messages_fts MATCH ? AND c.user_id = ?")
        params: list = [expression, self.user_id]
        if exclude_id is not None:
            sql += " AND c.id != ?"
            params.append(exclude_id)
        sql += " ORDER BY bm25(messages_fts) LIMIT ?"
        params.append(limit)
        try:
            return self.db.rows(sql, params)
        except DatabaseError:
            return []

    def context_for(self, text: str, exclude_id: int | None = None, limit: int = 3) -> list[str]:
        """Snippets for the AI prompt, only when the message refers to the past."""
        if not _RECALL.search(text):
            return []
        return [f"- ({r['created_at'][:10]}, {'the user' if r['role'] == 'user' else 'you'}): {_short(r['content'])}"
                for r in self.search(text, limit, exclude_id)]


class HistoryFeature(Feature):
    name = "memory retrieval"

    def __init__(self, services):
        super().__init__(services)
        self.index = HistoryIndex(services.storage.db, services.storage.user_id)

    def register_tools(self):
        def search_history(ctx: ToolContext, query: str) -> str:
            if not self.index.available:
                raise ToolError("Searching old conversations is not available on this Python build.")
            rows = self.index.search(query, limit=6)
            if not rows:
                return f"I found nothing in earlier conversations about '{query}'."
            lines = [f"Found {len(rows)} earlier message{'s' if len(rows) != 1 else ''} about '{query}':"]
            for r in rows:
                who = "you" if r["role"] == "user" else "OPTIMUS"
                lines.append(f"- {r['created_at'][:10]}, {who}: {_short(r['content'])}  (chat: {r['title']})")
            return "\n".join(lines)

        self.add_tool(Tool("search_history", "Search earlier conversations for a topic.", search_history,
                           (Param("query", "string", "What to look for", max_length=200),),
                           status_text="Searching earlier conversations..."))

    def rules(self):
        return [
            rule(r"^(?:what|when)\s+did\s+(?:we|i)\s+(?:talk|speak|discuss|say|ask)\s+(?:about\s+)?(?P<q>.+)$", self._search),
            rule(r"^(?:please\s+)?(?:search|find)\s+(?:my\s+)?(?:chat\s+)?(?:history|conversations?|chats?)\s+"
                 r"(?:for|about)\s+(?P<q>.+)$", self._search),
            rule(r"^(?:please\s+)?(?:find|show)\s+(?:the\s+)?(?:conversation|chat)s?\s+(?:about|on)\s+(?P<q>.+)$", self._search),
        ]

    def _search(self, match, cb):
        result = self.call("search_history", {"query": match["q"]}, cb)
        return result.message if result.ok else f"Sorry, {result.message}"