"""Repository interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


class Repository[T](ABC):
    """Repository interface."""

    @abstractmethod
    def get(self, key: str) -> T:
        """Get an item by its id."""
        ...

    @abstractmethod
    def query(self, **kwargs: object) -> Sequence[T]:
        """Get all sortables."""
        ...

    @abstractmethod
    def add(self, item: T) -> None:
        """Add a sortable."""
        ...

    @abstractmethod
    def remove(self, item: T) -> None:
        """Remove a sortable by its id."""
        ...

    @abstractmethod
    def update(self, item: T) -> None:
        """Update a sortable."""
        ...
