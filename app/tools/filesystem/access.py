"""FileAccessRegistry — enforces allowed filesystem roots.

All filesystem tools must resolve paths through this registry before
accessing the filesystem. Path traversal attacks are blocked here.
"""

from __future__ import annotations

from pathlib import Path


class PathNotAllowedError(Exception):
    """Raised when a path is outside all allowed roots."""


class PathReadOnlyError(Exception):
    """Raised when a write is attempted on a read-only root."""


class FileAccessRegistry:
    """Maintains the set of allowed filesystem roots.

    Only paths that resolve to within a registered root are permitted.
    Symlinks are resolved before checking to prevent escape attacks.
    Each root carries a read_only flag; write operations must call
    validate_write() which rejects read-only roots.
    """

    def __init__(self) -> None:
        # name -> (resolved_path, read_only)
        self._roots: dict[str, tuple[Path, bool]] = {}

    def add_root(self, name: str, path: Path, *, read_only: bool = True) -> None:
        self._roots[name] = (path.resolve(), read_only)

    def remove_root(self, name: str) -> None:
        self._roots.pop(name, None)

    def roots(self) -> dict[str, Path]:
        return {name: info[0] for name, info in self._roots.items()}

    def is_read_only(self, name: str) -> bool | None:
        """Return the read_only flag for a named root, or None if not found."""
        info = self._roots.get(name)
        return info[1] if info else None

    def validate(self, path: str | Path) -> Path:
        """Resolve path and verify it is inside an allowed root.

        Raises PathNotAllowedError if the path escapes all roots.
        Never follows symlinks outside permitted roots.
        """
        target = Path(path)
        try:
            resolved = target.resolve()
        except (OSError, ValueError) as exc:
            raise PathNotAllowedError(f"Cannot resolve path: {path}") from exc

        for root, _read_only in self._roots.values():
            try:
                resolved.relative_to(root)
                return resolved
            except ValueError:
                continue

        raise PathNotAllowedError(
            f"Access denied: '{path}' is outside all allowed roots. "
            f"Allowed roots: {[str(r) for r, _ in self._roots.values()]}"
        )

    def validate_write(self, path: str | Path) -> Path:
        """Resolve path, verify it is inside an allowed root, and that the
        root is not read-only.

        Raises PathNotAllowedError if outside all roots.
        Raises PathReadOnlyError if the matching root is read-only.
        """
        target = Path(path)
        try:
            resolved = target.resolve()
        except (OSError, ValueError) as exc:
            raise PathNotAllowedError(f"Cannot resolve path: {path}") from exc

        for root, read_only in self._roots.values():
            try:
                resolved.relative_to(root)
                if read_only:
                    raise PathReadOnlyError(
                        f"Write access denied: '{path}' is in a read-only root."
                    )
                return resolved
            except ValueError:
                continue

        raise PathNotAllowedError(
            f"Access denied: '{path}' is outside all allowed roots. "
            f"Allowed roots: {[str(r) for r, _ in self._roots.values()]}"
        )

    def is_allowed(self, path: str | Path) -> bool:
        try:
            self.validate(path)
            return True
        except PathNotAllowedError:
            return False
