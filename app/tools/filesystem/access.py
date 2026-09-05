"""FileAccessRegistry — enforces allowed filesystem roots.

All filesystem tools must resolve paths through this registry before
accessing the filesystem. Path traversal attacks are blocked here.
"""

from __future__ import annotations

from pathlib import Path


class PathNotAllowedError(Exception):
    """Raised when a path is outside all allowed roots."""


class FileAccessRegistry:
    """Maintains the set of allowed filesystem roots.

    Only paths that resolve to within a registered root are permitted.
    Symlinks are resolved before checking to prevent escape attacks.
    """

    def __init__(self) -> None:
        self._roots: dict[str, Path] = {}  # name -> resolved absolute path

    def add_root(self, name: str, path: Path, *, read_only: bool = True) -> None:
        resolved = path.resolve()
        self._roots[name] = resolved

    def remove_root(self, name: str) -> None:
        self._roots.pop(name, None)

    def roots(self) -> dict[str, Path]:
        return dict(self._roots)

    def validate(self, path: str | Path) -> Path:
        """Resolve path and verify it is inside an allowed root.

        Raises PathNotAllowedError if the path escapes all roots.
        Never follows symlinks outside permitted roots.
        """
        target = Path(path)

        # Resolve without following symlinks first to detect traversal attempts
        try:
            resolved = target.resolve()
        except (OSError, ValueError) as exc:
            raise PathNotAllowedError(f"Cannot resolve path: {path}") from exc

        for root in self._roots.values():
            try:
                resolved.relative_to(root)
                return resolved
            except ValueError:
                continue

        raise PathNotAllowedError(
            f"Access denied: '{path}' is outside all allowed roots. "
            f"Allowed roots: {[str(r) for r in self._roots.values()]}"
        )

    def is_allowed(self, path: str | Path) -> bool:
        try:
            self.validate(path)
            return True
        except PathNotAllowedError:
            return False
