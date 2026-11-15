"""
A cheap pre-filter: only offer the tools to the AI when the message looks like a
computer action. This keeps normal chat fast and stops a small model from
calling tools during casual conversation.
"""
import re

_ACTION_WORDS = re.compile(
    r"\b(open|launch|start|run|close|quit|exit|kill|find|search|locate|look for|where is|show me|"
    r"screenshot|screen shot|capture|cpu|ram|memory|battery|charge|charging|lock|usage|performance|"
    r"disk|storage|folder|directory|file|document|app|apps|application|program|notepad|calculator|"
    r"calc|paint|chrome|edge|explorer|task manager|vs ?code|word|excel|powerpoint|settings|system)\b",
    re.IGNORECASE,
)


def looks_like_action(text: str) -> bool:
    return bool(_ACTION_WORDS.search(text))