"""Procedural meshes are valid (no NaNs, normals unit-length, outward-facing, indices in range)."""

from __future__ import annotations

import numpy as np
import pytest

from eve.character import character_geometry as geo
from eve.character.character_config import CharacterConfig
from eve.character.character_rig import Ch, neutral_pose
from eve.character.facial_expressions import eye_state

CFG = CharacterConfig()
MESHES = geo.build_all(CFG)


@pytest.mark.parametrize("name", sorted(MESHES))
def test_mesh_is_well_formed(name: str) -> None:
    mesh = MESHES[name]
    n = mesh.vertices.shape[0]
    assert mesh.vertices.dtype == np.float32 and mesh.normals.shape == (n, 3)
    assert np.isfinite(mesh.vertices).all() and np.isfinite(mesh.normals).all()
    assert mesh.indices.max() < n and mesh.indices.shape[0] % 3 == 0
    lengths = np.linalg.norm(mesh.normals, axis=1)
    assert np.allclose(lengths, 1.0, atol=1e-3)
    if mesh.colors is not None:
        assert mesh.colors.shape == (n, 4)


@pytest.mark.parametrize("name", ["body", "head"])
def test_closed_shapes_have_outward_normals(name: str) -> None:
    mesh = MESHES[name]
    outward = np.sum(mesh.normals * mesh.vertices, axis=1)
    assert np.mean(outward > 0) > 0.98


def test_body_proportions() -> None:
    v = MESHES["body"].vertices
    assert v[:, 2].max() == pytest.approx(CFG.body_top, abs=0.01)
    assert v[:, 2].min() == pytest.approx(-CFG.body_bottom, abs=0.01)
    top_half = np.abs(v[v[:, 2] > 0.1][:, 0]).max()
    bottom_half = np.abs(v[v[:, 2] < -0.3][:, 0]).max()
    assert top_half > bottom_half  # egg shape: wider at the top


def test_face_sits_on_front_of_head() -> None:
    face = MESHES["face"].vertices
    assert face[:, 1].max() < 0.0  # entirely on the -Y (front) side


def test_eye_frame_is_right_handed_and_outward() -> None:
    center, right, up, normal = geo.head_surface_frame(CFG, CFG.eye_elevation, CFG.eye_spacing)
    assert np.dot(np.cross(right, -normal), up) > 0.99
    assert normal[1] < -0.5  # faces the viewer


def test_eye_state_mapping() -> None:
    pose = neutral_pose()
    pose[Ch.EYE_OPEN] = 0.0
    assert eye_state(pose).open_l == 0.0
    pose[Ch.EYE_OPEN] = 1.0
    pose[Ch.EYE_HAPPY] = 1.0
    state = eye_state(pose)
    assert state.happy == 1.0 and state.open_l < 0.2
