"""DirectorMemoryGraph + InMemoryGraphStore (services/cinematic-
intelligence): the graph memory backbone - character/object/location/
event/style nodes, appears_in/uses/wears/located_at/moves_to/speaks_to
edges."""

from __future__ import annotations

from cinematic_intelligence.memory_graph import DirectorMemoryGraph, InMemoryGraphStore


def test_record_character_creates_node():
    graph = DirectorMemoryGraph()
    node = graph.record_character("proj_1", "char_alice", "Alice")
    assert node.type == "character"
    assert node.ref_id == "char_alice"
    fetched = graph.store.get_node("proj_1", node.node_id)
    assert fetched == node


def test_record_character_is_idempotent_by_node_id():
    graph = DirectorMemoryGraph()
    first = graph.record_character("proj_1", "char_alice", "Alice")
    second = graph.record_character("proj_1", "char_alice", "Alice (renamed)")
    assert first.node_id == second.node_id
    assert graph.store.get_node("proj_1", first.node_id).label == "Alice (renamed)"


def test_nodes_by_type():
    graph = DirectorMemoryGraph()
    graph.record_character("proj_1", "char_alice", "Alice")
    graph.record_character("proj_1", "char_bob", "Bob")
    graph.record_object("proj_1", "obj_car", "car")
    characters = graph.store.nodes_by_type("proj_1", "character")
    assert {n.ref_id for n in characters} == {"char_alice", "char_bob"}


def test_record_event_creates_appears_in_edge():
    graph = DirectorMemoryGraph()
    graph.record_character("proj_1", "char_alice", "Alice")
    graph.record_event("proj_1", "evt_1", "Alice enters", character_ids=["char_alice"])

    events = graph.events_for_character("proj_1", "char_alice")
    assert len(events) == 1
    assert events[0].label == "Alice enters"


def test_record_event_creates_uses_edge_between_character_and_object():
    graph = DirectorMemoryGraph()
    graph.record_character("proj_1", "char_alice", "Alice")
    graph.record_object("proj_1", "obj_phone", "phone")
    graph.record_event("proj_1", "evt_1", "Alice checks her phone", character_ids=["char_alice"], object_ids=["obj_phone"])

    neighbors = graph.store.neighbors("proj_1", "node_character_char_alice", edge_type="uses")
    assert [n.label for _, n in neighbors] == ["phone"]


def test_record_event_creates_located_at_edges():
    graph = DirectorMemoryGraph()
    graph.record_character("proj_1", "char_alice", "Alice")
    graph.record_location("proj_1", "env_room", "Living Room")
    event = graph.record_event("proj_1", "evt_1", "Alice enters", character_ids=["char_alice"], location_id="env_room")

    char_neighbors = graph.store.neighbors("proj_1", "node_character_char_alice", edge_type="located_at")
    assert [n.node_id for _, n in char_neighbors] == ["node_location_env_room"]

    event_neighbors = graph.store.neighbors("proj_1", event.node_id, edge_type="located_at")
    assert [n.node_id for _, n in event_neighbors] == ["node_location_env_room"]


def test_record_movement_creates_moves_to_edge():
    graph = DirectorMemoryGraph()
    graph.record_character("proj_1", "char_alice", "Alice")
    graph.record_location("proj_1", "env_kitchen", "Kitchen")
    graph.record_movement("proj_1", "char_alice", "env_kitchen")

    neighbors = graph.store.neighbors("proj_1", "node_character_char_alice", edge_type="moves_to")
    assert [n.label for _, n in neighbors] == ["Kitchen"]


def test_record_dialogue_creates_speaks_to_edge():
    graph = DirectorMemoryGraph()
    graph.record_character("proj_1", "char_alice", "Alice")
    graph.record_character("proj_1", "char_bob", "Bob")
    graph.record_dialogue("proj_1", "char_alice", "char_bob")

    neighbors = graph.store.neighbors("proj_1", "node_character_char_alice", edge_type="speaks_to")
    assert [n.label for _, n in neighbors] == ["Bob"]


def test_record_wearing_creates_wears_edge_and_adhoc_object_node():
    graph = DirectorMemoryGraph()
    graph.record_character("proj_1", "char_alice", "Alice")
    accessory_node = graph.record_wearing("proj_1", "char_alice", "a silver necklace")

    assert accessory_node.type == "object"
    neighbors = graph.store.neighbors("proj_1", "node_character_char_alice", edge_type="wears")
    assert [n.node_id for _, n in neighbors] == [accessory_node.node_id]


def test_record_style():
    graph = DirectorMemoryGraph()
    node = graph.record_style("proj_1", "style_1", "Cinematic Photorealistic")
    assert node.type == "style"


def test_neighbors_filtered_by_edge_type_only_returns_matching():
    graph = DirectorMemoryGraph()
    graph.record_character("proj_1", "char_alice", "Alice")
    graph.record_object("proj_1", "obj_phone", "phone")
    graph.record_event("proj_1", "evt_1", "Alice checks phone", character_ids=["char_alice"], object_ids=["obj_phone"])

    appears_in = graph.store.neighbors("proj_1", "node_character_char_alice", edge_type="appears_in")
    uses = graph.store.neighbors("proj_1", "node_character_char_alice", edge_type="uses")
    assert len(appears_in) == 1
    assert len(uses) == 1
    assert appears_in[0][0].type == "appears_in"
    assert uses[0][0].type == "uses"


def test_neighbors_scoped_by_project():
    graph = DirectorMemoryGraph()
    graph.record_character("proj_1", "char_alice", "Alice")
    graph.record_character("proj_2", "char_alice", "Alice (different project)")
    graph.record_object("proj_1", "obj_phone", "phone")
    graph.record_event("proj_1", "evt_1", "checks phone", character_ids=["char_alice"], object_ids=["obj_phone"])

    proj2_neighbors = graph.store.neighbors("proj_2", "node_character_char_alice", edge_type="uses")
    assert proj2_neighbors == []


def test_get_node_returns_none_for_wrong_project():
    graph = DirectorMemoryGraph()
    graph.record_character("proj_1", "char_alice", "Alice")
    assert graph.store.get_node("proj_2", "node_character_char_alice") is None


def test_get_node_returns_none_for_unknown_id():
    store = InMemoryGraphStore()
    assert store.get_node("proj_1", "node_unknown") is None


def test_custom_store_can_be_injected():
    store = InMemoryGraphStore()
    graph = DirectorMemoryGraph(store=store)
    graph.record_character("proj_1", "char_alice", "Alice")
    assert graph.store is store
