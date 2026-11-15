"""
Shared error type for everything voice related.
Like AIEngineError, it carries a short 'kind' code and a friendly 'message'.
"""


class VoiceError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message