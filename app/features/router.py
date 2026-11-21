"""
FeatureRouter - checks a message against every feature's rules.
handle() returns a string, an iterator of strings (a streamed answer), or None if no rule applies.
"""
from app.agent.events import ToolCallbacks


class FeatureRouter:
    def __init__(self, features: list):
        self.features = features
        self._rules = [(r, f) for f in features for r in f.rules()]

    def handle(self, text: str, callbacks: ToolCallbacks):
        original = text.strip()
        plain = original.rstrip(".!?, ").strip()
        is_question = original.endswith("?")
        for rule, feature in self._rules:
            if rule.statement_only and is_question:
                continue
            if rule.guard is not None and not rule.guard(plain):
                continue
            match = rule.pattern.match(plain)
            if match:
                try:
                    return rule.handler(match, callbacks)
                except Exception as exc:  # A feature problem must never crash the chat
                    return f"The {feature.name} feature ran into a problem: {exc}"
        return None