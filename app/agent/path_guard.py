"""
PathGuard - decides which file system locations OPTIMUS may touch.

Every path is turned into its real absolute form first (so '..' tricks and
shortcuts/symlinks cannot escape), and only then is it compared with the
allowed folders.
"""
from pathlib import Path

from app.agent.registry import ValidationError


class PathGuard:
    BLOCKED_PARTS = {".ssh", ".aws", ".gnupg", "appdata"}  # Never allowed, even inside a root

    def __init__(self, roots):
        self.roots: list[Path] = []
        for root in roots:
            try:
                self.roots.append(Path(root).expanduser().resolve())
            except OSError:
                continue

    def _inside(self, path: Path) -> bool:
        return any(path == root or path.is_relative_to(root) for root in self.roots)

    def _find_relative(self, relative: Path) -> Path:
        """A relative path is only accepted if it exists inside one of the allowed folders."""
        for root in self.roots:
            option = (root / relative).resolve(strict=False)
            if option.exists() and self._inside(option):
                return option
        raise ValidationError("I need the full path of that item. Try searching for it first.")

    def resolve(self, raw: str) -> Path:
        """Return a safe absolute Path, or raise ValidationError."""
        text = raw.strip().strip("\"'")
        if not text:
            raise ValidationError("The path is empty.")
        if text.startswith(("\\\\", "//")):
            raise ValidationError("Network and device paths are not allowed.")
        try:
            candidate = Path(text).expanduser()
            if not candidate.is_absolute():
                candidate = self._find_relative(candidate)
            resolved = candidate.resolve(strict=False)  # Collapses '..' and follows shortcuts
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValidationError(f"That is not a valid path ({exc}).") from exc

        if not self._inside(resolved):
            raise ValidationError("That location is outside the folders OPTIMUS is allowed to use.")
        if any(part.lower() in self.BLOCKED_PARTS for part in resolved.parts):
            raise ValidationError("That location is protected.")
        return resolved