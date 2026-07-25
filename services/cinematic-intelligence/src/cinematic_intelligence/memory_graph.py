from __future__ import annotations

from cinematic_intelligence_sdk import GraphEdge, GraphNode, IGraphStore

from ._util import new_id


class InMemoryGraphStore(IGraphStore):
    """In-memory IGraphStore - enough for local dev and single-process
    testing. A graph database (Neo4j or similar) is a later IGraphStore
    implementation, swapped in without touching DirectorMemoryGraph or
    anything above it - see docs/adr/0013-cinematic-intelligence-layer.md."""

    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: list[GraphEdge] = []

    def add_node(self, node: GraphNode) -> None:
        self._nodes[node.node_id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        self._edges.append(edge)

    def get_node(self, project_id: str, node_id: str) -> GraphNode | None:
        node = self._nodes.get(node_id)
        return node if node is not None and node.project_id == project_id else None

    def nodes_by_type(self, project_id: str, type: str) -> list[GraphNode]:
        return [n for n in self._nodes.values() if n.project_id == project_id and n.type == type]

    def neighbors(
        self, project_id: str, node_id: str, edge_type: str | None = None
    ) -> list[tuple[GraphEdge, GraphNode]]:
        result: list[tuple[GraphEdge, GraphNode]] = []
        for edge in self._edges:
            if edge.project_id != project_id or edge.from_node_id != node_id:
                continue
            if edge_type is not None and edge.type != edge_type:
                continue
            target = self._nodes.get(edge.to_node_id)
            if target is not None:
                result.append((edge, target))
        return result


class DirectorMemoryGraphError(Exception):
    """Raised when a graph operation references a node that hasn't been
    recorded yet."""


class DirectorMemoryGraph:
    """Convenience facade over an IGraphStore, building the memory
    backbone a future AI Director iteration queries instead of re-reading
    raw project history: characters/objects/locations/events/styles as
    nodes, appears_in/uses/wears/located_at/moves_to/speaks_to as edges
    (graph_node.schema.json / graph_edge.schema.json). Node ids are
    deterministic (`node_<type>_<ref_id>`) so re-recording the same
    subject is idempotent rather than creating a duplicate node."""

    def __init__(self, store: IGraphStore | None = None) -> None:
        self._store = store or InMemoryGraphStore()

    @property
    def store(self) -> IGraphStore:
        return self._store

    def record_character(self, project_id: str, character_id: str, label: str) -> GraphNode:
        return self._record_node(project_id, "character", character_id, label)

    def record_object(self, project_id: str, object_id: str, label: str) -> GraphNode:
        return self._record_node(project_id, "object", object_id, label)

    def record_location(self, project_id: str, environment_id: str, label: str) -> GraphNode:
        return self._record_node(project_id, "location", environment_id, label)

    def record_style(self, project_id: str, style_lock_id: str, label: str) -> GraphNode:
        return self._record_node(project_id, "style", style_lock_id, label)

    def record_event(
        self,
        project_id: str,
        event_id: str,
        label: str,
        *,
        character_ids: list[str] | None = None,
        object_ids: list[str] | None = None,
        location_id: str | None = None,
    ) -> GraphNode:
        event_node = self._record_node(project_id, "event", event_id, label)
        for character_id in character_ids or []:
            self._add_edge(project_id, "appears_in", self._node_id("character", character_id), event_node.node_id)
            for object_id in object_ids or []:
                self._add_edge(project_id, "uses", self._node_id("character", character_id), self._node_id("object", object_id))
            if location_id:
                self._add_edge(project_id, "located_at", self._node_id("character", character_id), self._node_id("location", location_id))
        if location_id:
            self._add_edge(project_id, "located_at", event_node.node_id, self._node_id("location", location_id))
        return event_node

    def record_movement(self, project_id: str, character_id: str, location_id: str) -> None:
        self._add_edge(project_id, "moves_to", self._node_id("character", character_id), self._node_id("location", location_id))

    def record_dialogue(self, project_id: str, from_character_id: str, to_character_id: str) -> None:
        self._add_edge(project_id, "speaks_to", self._node_id("character", from_character_id), self._node_id("character", to_character_id))

    def record_wearing(self, project_id: str, character_id: str, accessory_label: str) -> GraphNode:
        accessory_node = GraphNode(
            node_id=new_id("node_accessory"),
            project_id=project_id,
            type="object",
            label=accessory_label,
        )
        self._store.add_node(accessory_node)
        self._add_edge(project_id, "wears", self._node_id("character", character_id), accessory_node.node_id)
        return accessory_node

    def events_for_character(self, project_id: str, character_id: str) -> list[GraphNode]:
        neighbors = self._store.neighbors(project_id, self._node_id("character", character_id), edge_type="appears_in")
        return [node for _, node in neighbors]

    def _record_node(self, project_id: str, type: str, ref_id: str, label: str) -> GraphNode:
        node = GraphNode(node_id=self._node_id(type, ref_id), project_id=project_id, type=type, label=label, ref_id=ref_id)
        self._store.add_node(node)
        return node

    def _add_edge(self, project_id: str, edge_type: str, from_node_id: str, to_node_id: str) -> None:
        self._store.add_edge(
            GraphEdge(edge_id=new_id("edge"), project_id=project_id, type=edge_type, from_node_id=from_node_id, to_node_id=to_node_id)
        )

    def _node_id(self, type: str, ref_id: str) -> str:
        return f"node_{type}_{ref_id}"
