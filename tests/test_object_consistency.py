"""ObjectConsistencyEngine (services/cinematic-intelligence): tracks
persistent objects' materials/colors/damage state and location history
across scenes."""

from __future__ import annotations

import pytest
from cinematic_intelligence.object_consistency import ObjectConsistencyEngine, ObjectConsistencyEngineError


def test_establish_defaults_to_pristine():
    engine = ObjectConsistencyEngine()
    profile = engine.establish("proj_1", "car", object_id="obj_car")
    assert profile["attributes"]["damage_state"] == "pristine"


def test_establish_with_attributes():
    engine = ObjectConsistencyEngine()
    profile = engine.establish(
        "proj_1",
        "car",
        object_id="obj_car",
        attributes={"materials": ["metal", "glass"], "colors": ["red"], "damage_state": "pristine"},
    )
    assert profile["attributes"]["colors"] == ["red"]


def test_establish_with_reference_image_ids():
    engine = ObjectConsistencyEngine()
    profile = engine.establish("proj_1", "car", object_id="obj_car", reference_image_ids=["asset_1"])
    assert profile["reference_image_ids"] == ["asset_1"]


def test_establish_twice_raises():
    engine = ObjectConsistencyEngine()
    engine.establish("proj_1", "car", object_id="obj_car")
    with pytest.raises(ObjectConsistencyEngineError, match="already exists"):
        engine.establish("proj_1", "car", object_id="obj_car")


def test_get_unknown_raises():
    engine = ObjectConsistencyEngine()
    with pytest.raises(ObjectConsistencyEngineError, match="No ObjectProfile"):
        engine.get("obj_unknown")


def test_record_location_appends_history():
    engine = ObjectConsistencyEngine()
    engine.establish("proj_1", "car", object_id="obj_car")
    engine.record_location("obj_car", "scene_1", "shot_1", "driveway")
    profile = engine.record_location("obj_car", "scene_2", "shot_5", "garage")

    assert [h["location"] for h in profile["location_history"]] == ["driveway", "garage"]


def test_current_location_reflects_most_recent():
    engine = ObjectConsistencyEngine()
    engine.establish("proj_1", "car", object_id="obj_car")
    assert engine.current_location("obj_car") is None

    engine.record_location("obj_car", "scene_1", "shot_1", "driveway")
    engine.record_location("obj_car", "scene_2", "shot_5", "garage")
    assert engine.current_location("obj_car") == "garage"


def test_update_damage_state():
    engine = ObjectConsistencyEngine()
    engine.establish("proj_1", "car", object_id="obj_car")
    profile = engine.update_damage_state("obj_car", "scratched")
    assert profile["attributes"]["damage_state"] == "scratched"


def test_exists():
    engine = ObjectConsistencyEngine()
    assert engine.exists("obj_car") is False
    engine.establish("proj_1", "car", object_id="obj_car")
    assert engine.exists("obj_car") is True


def test_list_for_project():
    engine = ObjectConsistencyEngine()
    engine.establish("proj_1", "car", object_id="obj_car")
    engine.establish("proj_2", "hammer", object_id="obj_hammer")
    assert [p["object_id"] for p in engine.list_for_project("proj_1")] == ["obj_car"]


def test_auto_generated_object_id():
    engine = ObjectConsistencyEngine()
    profile = engine.establish("proj_1", "phone")
    assert profile["object_id"].startswith("obj_")
