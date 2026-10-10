from collections.abc import Iterator
from contextlib import contextmanager

from mcp.server.mcpserver.exceptions import ResourceError, ResourceNotFoundError, ToolError

from anki_addons_mcp.domain.errors import AddonNotFound, DomainError, SnapshotNotFound


@contextmanager
def tool_errors() -> Iterator[None]:
    try:
        yield
    except DomainError as e:
        raise ToolError(str(e)) from e


@contextmanager
def resource_errors() -> Iterator[None]:
    try:
        yield
    except (AddonNotFound, SnapshotNotFound) as e:
        raise ResourceNotFoundError(str(e)) from e
    except DomainError as e:
        raise ResourceError(str(e)) from e


def parse_addon_id(value: str) -> int:
    try:
        return int(value)
    except ValueError as e:
        raise ResourceNotFoundError(f"Addon id must be an integer, got '{value}'") from e
