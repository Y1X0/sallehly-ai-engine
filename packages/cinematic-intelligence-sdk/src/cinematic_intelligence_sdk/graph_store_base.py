from __future__ import annotations

from abc import ABC, abstractmethod

from .types import GraphEdge, GraphNode


class IGraphStore(ABC):
    """The Director Memory Graph's storage abstraction. An in-memory
    implementation (services/cinematic-intelligence's InMemoryGraphStore)
    is enough for local dev and single-process testing; a graph database
    (Neo4j or similar) is a later IGraphStore implementation, added
    without touching DirectorMemoryGraph or anything above it - same
    swap-point pattern as IProjectStore (packages/persistence) and
    IDirectorMemoryStore (packages/director-memory)."""

    @abstractmethod
    def add_node(self, node: GraphNode) -> None: ...

    @abstractmethod
    def add_edge(self, edge: GraphEdge) -> None: ...

    @abstractmethod
    def get_node(self, project_id: str, node_id: str) -> GraphNode | None: ...

    @abstractmethod
    def nodes_by_type(self, project_id: str, type: str) -> list[GraphNode]: ...

    @abstractmethod
    def neighbors(
        self, project_id: str, node_id: str, edge_type: str | None = None
    ) -> list[tuple[GraphEdge, GraphNode]]:
        """Outgoing edges from node_id, optionally filtered by edge type,
        each paired with the node it points to."""
        ...
