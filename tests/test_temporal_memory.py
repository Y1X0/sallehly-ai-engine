"""TemporalMemoryEngine (services/cinematic-intelligence): maintains one
ProjectMemory per project, updated after every generated shot."""

from __future__ import annotations

from cinematic_intelligence.temporal_memory import TemporalMemoryEngine


def test_get_or_create_starts_empty():
    engine = TemporalMemoryEngine()
    memory = engine.get_or_create("proj_1")
    assert memory["character_ids"] == []
    assert memory["events"] == []
    assert memory["timeline"] == []


def test_get_or_create_is_idempotent():
    engine = TemporalMemoryEngine()
    first = engine.get_or_create("proj_1")
    second = engine.get_or_create("proj_1")
    assert first["project_id"] == second["project_id"] == "proj_1"


def test_register_character_is_idempotent():
    engine = TemporalMemoryEngine()
    engine.register_character("proj_1", "char_alice")
    memory = engine.register_character("proj_1", "char_alice")
    assert memory["character_ids"] == ["char_alice"]


def test_register_object_and_environment():
    engine = TemporalMemoryEngine()
    engine.register_object("proj_1", "obj_car")
    memory = engine.register_environment("proj_1", "env_street")
    assert memory["object_ids"] == ["obj_car"]
    assert memory["environment_ids"] == ["env_street"]


def test_set_style_lock():
    engine = TemporalMemoryEngine()
    memory = engine.set_style_lock("proj_1", "style_1")
    assert memory["style_lock_id"] == "style_1"


def test_record_shot_appends_event_and_timeline():
    engine = TemporalMemoryEngine()
    memory = engine.record_shot(
        "proj_1",
        "shot_1",
        "scene_1",
        "Alice enters the room",
        character_ids=["char_alice"],
        object_ids=["obj_phone"],
        environment_id="env_room",
        order=0,
    )
    assert len(memory["events"]) == 1
    assert memory["events"][0]["summary"] == "Alice enters the room"
    assert memory["timeline"][0]["order"] == 0
    assert memory["character_ids"] == ["char_alice"]
    assert memory["object_ids"] == ["obj_phone"]
    assert memory["environment_ids"] == ["env_room"]


def test_record_shot_updates_last_camera_state():
    engine = TemporalMemoryEngine()
    camera = {"shot_type": "wide", "movement": {"type": "static"}}
    memory = engine.record_shot("proj_1", "shot_1", "scene_1", "Establishing shot", camera=camera)
    assert memory["last_camera_state"] == {"shot_id": "shot_1", "camera": camera}


def test_record_shot_does_not_duplicate_already_registered_ids():
    engine = TemporalMemoryEngine()
    engine.register_character("proj_1", "char_alice")
    memory = engine.record_shot("proj_1", "shot_1", "scene_1", "Alice again", character_ids=["char_alice"])
    assert memory["character_ids"] == ["char_alice"]


def test_multiple_shots_accumulate_timeline_order():
    engine = TemporalMemoryEngine()
    engine.record_shot("proj_1", "shot_1", "scene_1", "First shot")
    memory = engine.record_shot("proj_1", "shot_2", "scene_1", "Second shot")
    assert [t["shot_id"] for t in memory["timeline"]] == ["shot_1", "shot_2"]
    assert memory["timeline"][1]["order"] == 1


def test_memories_are_isolated_per_project():
    engine = TemporalMemoryEngine()
    engine.record_shot("proj_1", "shot_1", "scene_1", "Project 1 shot")
    engine.record_shot("proj_2", "shot_1", "scene_1", "Project 2 shot")
    assert len(engine.get_or_create("proj_1")["events"]) == 1
    assert len(engine.get_or_create("proj_2")["events"]) == 1


def test_updated_at_changes_on_mutation():
    engine = TemporalMemoryEngine()
    first = engine.get_or_create("proj_1")
    second = engine.register_character("proj_1", "char_alice")
    assert second["updated_at"] >= first["updated_at"]
