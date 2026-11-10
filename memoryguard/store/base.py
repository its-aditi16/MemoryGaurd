"""MemoryStore interface shared by the local and Hindsight backends."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Memory:
    id: str
    content: str
    metadata: dict = field(default_factory=dict)  # provenance envelope fields
    score: float = 0.0  # similarity score when returned from recall()

    @property
    def status(self) -> str:
        return self.metadata.get("status", "live")

    @property
    def trust(self) -> float:
        return float(self.metadata.get("trust", 0.0))

    def to_dict(self) -> dict:
        return {"id": self.id, "content": self.content, "score": round(self.score, 4), **self.metadata}


class MemoryStore(ABC):
    name: str = "base"

    @abstractmethod
    def retain(self, content: str, metadata: dict) -> str:
        """Store a memory; return its id."""

    def retain_many(self, items: list[tuple[str, dict]]) -> list[str]:
        """Store several memories; backends with a batch API override this."""
        return [self.retain(content, metadata) for content, metadata in items]

    @abstractmethod
    def recall(self, query: str, k: int = 5) -> list[Memory]:
        """Return up to k memories most relevant to query, best first."""

    @abstractmethod
    def get(self, memory_id: str) -> Memory | None: ...

    @abstractmethod
    def update_metadata(self, memory_id: str, **fields) -> None:
        """Merge fields into a memory's metadata (e.g. status='flagged')."""

    @abstractmethod
    def delete(self, memory_id: str) -> None: ...

    @abstractmethod
    def list_all(self) -> list[Memory]: ...

    @abstractmethod
    def clear(self) -> None:
        """Remove every memory (used by demo reset)."""

    def set_namespace(self, name: str) -> None:
        """Select the memory bank for an agent (Hindsight: one bank per agent). Local store: no-op."""
