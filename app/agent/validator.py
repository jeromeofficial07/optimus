"""
Argument validation. The AI's tool requests are treated as untrusted input:
every argument is checked against the tool's Param rules before anything runs.
Unknown extra arguments are simply dropped, never used.
"""
import json
import re

from app.agent.path_guard import PathGuard
from app.agent.registry import Param, Tool, ValidationError

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def validate_arguments(tool: Tool, raw_args, guard: PathGuard) -> dict:
    """Return a clean dict of arguments for the tool, or raise ValidationError."""
    if raw_args is None or raw_args == "":
        raw_args = {}
    if isinstance(raw_args, str):
        try:
            raw_args = json.loads(raw_args)
        except json.JSONDecodeError as exc:
            raise ValidationError("The arguments were not valid JSON.") from exc
    try:
        raw_args = dict(raw_args)
    except (TypeError, ValueError) as exc:
        raise ValidationError("The arguments must be a set of named values.") from exc

    clean = {}
    for param in tool.params:
        value = raw_args.get(param.name)
        if value is None or (isinstance(value, str) and not value.strip()):
            if param.required:
                raise ValidationError(f"Missing the required argument '{param.name}'.")
            continue
        clean[param.name] = _validate_value(param, value, guard)
    return clean


def _validate_value(param: Param, value, guard: PathGuard):
    if param.type == "integer":
        if isinstance(value, bool):
            raise ValidationError(f"'{param.name}' must be a whole number.")
        try:
            number = int(float(str(value).strip()))  # Accepts 2, "2" and 2.0
        except ValueError as exc:
            raise ValidationError(f"'{param.name}' must be a whole number.") from exc
        if param.minimum is not None and number < param.minimum:
            raise ValidationError(f"'{param.name}' must be at least {param.minimum}.")
        if param.maximum is not None and number > param.maximum:
            raise ValidationError(f"'{param.name}' must be at most {param.maximum}.")
        return number

    text = str(value).strip()
    if len(text) > param.max_length:
        raise ValidationError(f"'{param.name}' is too long.")
    if _CONTROL_CHARS.search(text):
        raise ValidationError(f"'{param.name}' contains invalid characters.")
    if param.enum:
        for allowed in param.enum:
            if text.lower() == allowed.lower():
                return allowed
        raise ValidationError(f"'{param.name}' must be one of: {', '.join(param.enum)}.")
    if param.path:
        return guard.resolve(text)  # Returns a safe pathlib.Path
    return text