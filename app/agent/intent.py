"""
Intent recognition: what kind of request is this?

  WORKFLOW   - matches an approved workflow ("prepare my Python workspace")
  MULTI_STEP - several actions in one sentence ("open Notepad and then take a screenshot")
  ACTION     - a single computer action
  CHAT       - normal conversation (no tools are offered, so chat stays fast and safe)
"""
import re
from dataclasses import dataclass
from enum import Enum

from app.agent.workflows import WORKFLOWS


class IntentKind(str, Enum):
    CHAT = "chat"
    ACTION = "action"
    WORKFLOW = "workflow"
    MULTI_STEP = "multi_step"


@dataclass(frozen=True)
class Intent:
    kind: IntentKind
    workflow: str | None = None


_ACTION_WORDS = re.compile(
    r"\b(open|launch|start|run|close|quit|exit|kill|find|search|locate|look for|where is|show me|"
    r"screenshot|screen shot|capture|cpu|ram|memory|battery|charge|charging|lock|usage|performance|"
    r"disk|storage|folder|directory|file|document|app|apps|application|program|notepad|calculator|"
    r"calc|paint|chrome|edge|explorer|task manager|vs ?code|word|excel|powerpoint|settings|system)\b",
    re.IGNORECASE,
)
_VERBS = re.compile(r"\b(open|launch|start|close|quit|find|search|locate|take|check|lock|capture|show)\b",
                    re.IGNORECASE)
_SEQUENCE = re.compile(r"\b(and then|then|after that|afterwards|followed by|next|and)\b|,", re.IGNORECASE)


def looks_like_action(text: str) -> bool:
    return bool(_ACTION_WORDS.search(text))


def recognize_intent(text: str, follow_up: bool = False) -> Intent:
    """follow_up=True means the previous turn used tools ("open the second one" has no keyword)."""
    for workflow in WORKFLOWS.values():
        if workflow.matches(text):
            return Intent(IntentKind.WORKFLOW, workflow.name)
    verbs = {match.group(1).lower() for match in _VERBS.finditer(text)}
    if len(verbs) >= 2 and _SEQUENCE.search(text):
        return Intent(IntentKind.MULTI_STEP)
    if follow_up or looks_like_action(text):
        return Intent(IntentKind.ACTION)
    return Intent(IntentKind.CHAT)