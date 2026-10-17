"""Procedural mesh generation (pure NumPy — no rendering engine needed).

Every part is a parametric surface sampled on a (rings × segments) grid; vertex normals
come from area-weighted face normals, so shading is smooth everywhere including seams and
poles. Coordinates: X right, Y away from the viewer (the robot faces -Y), Z up.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from eve.character.character_config import CharacterConfig


@dataclass
class Mesh:
    vertices: np.ndarray  # (n, 3) float32
    normals: np.ndarray  # (n, 3) float32
    indices: np.ndarray  # (m,) uint32, triangles
    colors: np.ndarray | None = None  # (n, 4) float32 optional (alpha for halos)

    @property
    def triangle_count(self) -> int:
        return self.indices.shape[0] // 3


def _grid_indices(rows: int, cols: int, wrap: bool) -> np.ndarray:
    r = np.arange(rows - 1)[:, None]
    c = np.arange(cols if wrap else cols - 1)[None, :]
    c1 = (c + 1) % cols
    a = r * cols + c
    b = r * cols + c1
    d = (r + 1) * cols + c
    e = (r + 1) * cols + c1
    tris = np.stack([a, d, b, b, d, e], axis=-1).reshape(-1)
    return tris.astype(np.uint32)


def _vertex_normals(vertices: np.ndarray, indices: np.ndarray) -> np.ndarray:
    tri = indices.reshape(-1, 3)
    v0, v1, v2 = vertices[tri[:, 0]], vertices[tri[:, 1]], vertices[tri[:, 2]]
    face = np.cross(v1 - v0, v2 - v0)  # area-weighted
    normals = np.zeros_like(vertices)
    for k in range(3):
        np.add.at(normals, tri[:, k], face)
    length = np.linalg.norm(normals, axis=1, keepdims=True)
    return normals / np.maximum(length, 1e-12)


def grid_mesh(points: np.ndarray, wrap: bool, outward_hint: np.ndarray | None = None) -> Mesh:
    """Build a mesh from a (rows, cols, 3) grid of points."""
    rows, cols, _ = points.shape
    vertices = points.reshape(-1, 3).astype(np.float64)
    indices = _grid_indices(rows, cols, wrap)
    normals = _vertex_normals(vertices, indices)
    # Degenerate pole rows: give every vertex of the row the row's average normal.
    for row in (0, rows - 1):
        seg = vertices[row * cols : (row + 1) * cols]
        if np.ptp(seg, axis=0).max() < 1e-9:
            n = normals[row * cols : (row + 1) * cols].sum(axis=0)
            n /= max(np.linalg.norm(n), 1e-12)
            normals[row * cols : (row + 1) * cols] = n
    if outward_hint is not None and np.mean(np.sum(normals * outward_hint, axis=1)) < 0:
        normals = -normals
        indices = indices.reshape(-1, 3)[:, ::-1].reshape(-1).copy()
    return Mesh(vertices.astype(np.float32), normals.astype(np.float32), indices)


def _spow(x: np.ndarray, p: float) -> np.ndarray:
    return np.sign(x) * np.abs(x) ** p


# ---------------------------------------------------------------------------------------
# Parts
# ---------------------------------------------------------------------------------------
def body_mesh(cfg: CharacterConfig) -> Mesh:
    rings, segs = cfg.rings, cfg.segments
    s = np.linspace(0.0, 1.0, rings)[:, None]  # bottom -> top
    phi = np.linspace(0.0, 2 * math.pi, segs, endpoint=False)[None, :]
    zn = -np.cos(math.pi * s)  # -1 .. 1
    radius = cfg.body_radius * np.sin(math.pi * s) * (1.0 + cfg.body_taper * zn)
    # Slightly flatter dome on top, elongated tip below.
    z = np.where(zn > 0, zn * cfg.body_top, zn * cfg.body_bottom)
    x = radius * np.cos(phi)
    y = radius * np.sin(phi)
    points = np.stack(np.broadcast_arrays(x, y, z), axis=-1)
    mesh = grid_mesh(points, wrap=True)
    return _orient_outward(mesh, center=np.zeros(3))


def superellipsoid_points(
    radii: tuple[float, float, float],
    exponent: float,
    theta: np.ndarray,  # elevation, -pi/2 .. pi/2
    phi: np.ndarray,  # azimuth around Z, 0 = -Y (front)
    scale: float = 1.0,
) -> np.ndarray:
    e = 2.0 / exponent
    ct, st = np.cos(theta), np.sin(theta)
    cp, sp = np.cos(phi), np.sin(phi)
    x = radii[0] * scale * _spow(ct, e) * _spow(sp, e)
    y = -radii[1] * scale * _spow(ct, e) * _spow(cp, e)
    z = radii[2] * scale * _spow(st, e)
    return np.stack(np.broadcast_arrays(x, y, z), axis=-1)


def head_mesh(cfg: CharacterConfig) -> Mesh:
    theta = np.linspace(-math.pi / 2, math.pi / 2, cfg.rings)[:, None]
    phi = np.linspace(0.0, 2 * math.pi, cfg.segments, endpoint=False)[None, :]
    pts = superellipsoid_points(cfg.head_radii, cfg.head_exponent, theta, phi)
    pts[..., 2] = np.where(pts[..., 2] < 0, pts[..., 2] * 0.88, pts[..., 2])  # flatter chin
    return _orient_outward(grid_mesh(pts, wrap=True), center=np.zeros(3))


def _face_angles(
    cfg: CharacterConfig, u: np.ndarray, v: np.ndarray, roundness: float = 0.7
) -> tuple[np.ndarray, np.ndarray]:
    """Map a [-1,1]² grid onto a rounded-rectangle region of the face (radians)."""
    du = u * np.sqrt(np.maximum(0.0, 1 - v * v / 2))
    dv = v * np.sqrt(np.maximum(0.0, 1 - u * u / 2))
    uu = u + (du - u) * roundness
    vv = v + (dv - v) * roundness
    az = np.radians(cfg.face_half_width) * uu
    el = np.radians(cfg.face_center_elevation + cfg.face_half_height * vv)
    return el, az


def face_mesh(cfg: CharacterConfig, n: int = 40) -> Mesh:
    u = np.linspace(-1, 1, n)[None, :]
    v = np.linspace(-1, 1, n)[:, None]
    el, az = _face_angles(cfg, u, v)
    pts = superellipsoid_points(cfg.head_radii, cfg.head_exponent, el, az, scale=1.012)
    pts[..., 2] = np.where(pts[..., 2] < 0, pts[..., 2] * 0.88, pts[..., 2])
    return _orient_outward(grid_mesh(pts, wrap=False), center=np.zeros(3))


def head_surface_frame(
    cfg: CharacterConfig, elevation_deg: float, azimuth_deg: float, lift: float = 1.02
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Point on the head surface plus a local frame (right, up, outward normal)."""

    def point(el: float, az: float) -> np.ndarray:
        p = superellipsoid_points(
            cfg.head_radii, cfg.head_exponent, np.array(math.radians(el)), np.array(math.radians(az)), lift
        )
        if p[2] < 0:
            p = p.copy()
            p[2] *= 0.88
        return np.asarray(p, dtype=np.float64)

    center = point(elevation_deg, azimuth_deg)
    d = 0.5
    right = point(elevation_deg, azimuth_deg + d) - point(elevation_deg, azimuth_deg - d)
    up = point(elevation_deg + d, azimuth_deg) - point(elevation_deg - d, azimuth_deg)
    right /= np.linalg.norm(right)
    normal = np.cross(up, right)
    normal /= np.linalg.norm(normal)
    if np.dot(normal, center) < 0:
        normal = -normal
    up = np.cross(normal, right)  # right-handed frame: right × (-normal) == up
    up /= np.linalg.norm(up)
    return center, right, up, normal


def eye_mesh(width: float, height: float, curvature_radius: float, n: int = 28) -> Mesh:
    """Oval eye in local coordinates (x right, z up, -y toward the viewer), curved to
    follow the face. Built around the origin so it can be scaled for blinking."""
    r = np.linspace(0.0, 1.0, n // 2)[:, None]
    a = np.linspace(0.0, 2 * math.pi, n, endpoint=False)[None, :]
    # Superellipse-ish oval (slightly fuller than an ellipse).
    c, s = np.cos(a), np.sin(a)
    x = width * r * _spow(c, 0.85)
    z = height * r * _spow(s, 0.85)
    y = (x * x + z * z) / (2.0 * curvature_radius)  # bends away with the face
    pts = np.stack(np.broadcast_arrays(x, y, z), axis=-1)
    mesh = grid_mesh(pts, wrap=True)
    mesh.normals[:] = (0.0, -1.0, 0.0)
    return _orient_toward(mesh, np.array([0.0, -1.0, 0.0]))


def eye_arc_mesh(width: float, height: float, curvature_radius: float, thickness: float = 0.55, n: int = 24) -> Mesh:
    """'Happy' eye: an upward arc (like ^) with rounded ends, local coordinates."""
    a = np.linspace(math.radians(18), math.radians(162), n)[None, :]
    t = np.linspace(-1.0, 1.0, 5)[:, None]
    radius = 1.0 + 0.5 * thickness * t
    x = width * np.cos(a) * radius
    z = height * 1.15 * (np.sin(a) * radius - 0.55)
    y = (x * x + z * z) / (2.0 * curvature_radius)
    pts = np.stack(np.broadcast_arrays(x, y, z), axis=-1)
    mesh = grid_mesh(pts, wrap=False)
    mesh.normals[:] = (0.0, -1.0, 0.0)
    return _orient_toward(mesh, np.array([0.0, -1.0, 0.0]))


def disc_mesh(
    radius_x: float,
    radius_z: float,
    n: int = 40,
    rings: int = 10,
    alpha_profile: bool = False,
    curvature_radius: float = 0.0,
) -> Mesh:
    """Flat (optionally curved) disc facing -Y; with ``alpha_profile`` vertex alpha fades
    from the centre outward (soft glow halo)."""
    r = np.linspace(0.0, 1.0, rings)[:, None]
    a = np.linspace(0.0, 2 * math.pi, n, endpoint=False)[None, :]
    x = radius_x * r * np.cos(a)
    z = radius_z * r * np.sin(a)
    y = (x * x + z * z) / (2.0 * curvature_radius) if curvature_radius > 0 else np.zeros_like(x * z)
    pts = np.stack(np.broadcast_arrays(x, y, z), axis=-1)
    mesh = grid_mesh(pts, wrap=True)
    mesh.normals[:] = (0.0, -1.0, 0.0)
    mesh = _orient_toward(mesh, np.array([0.0, -1.0, 0.0]))
    if alpha_profile:
        rr = np.broadcast_to(r, (rings, n)).reshape(-1)
        alpha = (1.0 - rr) ** 2.2
        mesh.colors = np.stack([np.ones_like(alpha)] * 3 + [alpha], axis=1).astype(np.float32)
    return mesh


def halo_on_face(
    cfg: CharacterConfig,
    azimuth_deg: float,
    elevation_deg: float,
    radius_scale: float = 2.4,
    lift: float = 1.016,
    n: int = 40,
    rings: int = 12,
) -> Mesh:
    """Soft glow disc lying exactly on the head surface (between face and eye layers), in
    head coordinates, so it never sinks behind the curved visor."""
    r = np.linspace(0.0, 1.0, rings)[:, None]
    a = np.linspace(0.0, 2 * math.pi, n, endpoint=False)[None, :]
    az = np.radians(azimuth_deg + radius_scale * cfg.eye_width * r * np.cos(a))
    el = np.radians(elevation_deg + radius_scale * 1.15 * cfg.eye_height * r * np.sin(a))
    pts = superellipsoid_points(cfg.head_radii, cfg.head_exponent, el, az, scale=lift)
    pts[..., 2] = np.where(pts[..., 2] < 0, pts[..., 2] * 0.88, pts[..., 2])
    mesh = _orient_outward(grid_mesh(pts, wrap=True), center=np.zeros(3))
    alpha = (1.0 - np.broadcast_to(r, (rings, n)).reshape(-1)) ** 2.0
    mesh.colors = np.stack([np.ones_like(alpha)] * 3 + [alpha], axis=1).astype(np.float32)
    return mesh


def arm_mesh(cfg: CharacterConfig) -> Mesh:
    """Teardrop paddle hanging down from the shoulder pivot (origin)."""
    rings, segs = max(24, cfg.rings // 2), max(32, cfg.segments // 2)
    s = np.linspace(0.0, 1.0, rings)[:, None]  # top -> tip
    phi = np.linspace(0.0, 2 * math.pi, segs, endpoint=False)[None, :]
    # Profile: rounded top, widest at ~30%, long taper to a soft tip.
    radius = cfg.arm_radius * np.sin(math.pi * s) ** 0.75 * (1.15 - 0.55 * s)
    z = -cfg.arm_length * s
    x = radius * np.cos(phi)
    y = radius * cfg.arm_flatten * np.sin(phi)
    pts = np.stack(np.broadcast_arrays(x, y, z), axis=-1)
    mesh = grid_mesh(pts, wrap=True)
    return _orient_outward(mesh, center=np.array([0.0, 0.0, -cfg.arm_length * 0.5]), axis_only=True)


def _orient_outward(mesh: Mesh, center: np.ndarray, axis_only: bool = False) -> Mesh:
    rel = mesh.vertices - center
    if axis_only:
        rel[:, 2] = 0.0
    if np.mean(np.sum(mesh.normals * rel, axis=1)) < 0:
        mesh.normals = -mesh.normals
        mesh.indices = mesh.indices.reshape(-1, 3)[:, ::-1].reshape(-1).copy()
    return mesh


def _orient_toward(mesh: Mesh, direction: np.ndarray) -> Mesh:
    """Make triangle winding face ``direction`` (counter-clockwise when viewed from it)."""
    tri = mesh.indices.reshape(-1, 3)
    v = mesh.vertices
    face = np.cross(v[tri[:, 1]] - v[tri[:, 0]], v[tri[:, 2]] - v[tri[:, 0]])
    if np.mean(face @ direction) < 0:
        mesh.indices = tri[:, ::-1].reshape(-1).copy()
    return mesh


def eye_size(cfg: CharacterConfig) -> tuple[float, float]:
    """Eye half-width and half-height in character units."""
    return (
        math.radians(cfg.eye_width) * cfg.head_radii[0],
        math.radians(cfg.eye_height) * cfg.head_radii[2] * 1.1,
    )


def build_all(cfg: CharacterConfig) -> dict[str, Mesh]:
    """All meshes in their local frames (eyes/halos are centred on their own origin)."""
    w, h = eye_size(cfg)
    curvature = cfg.head_radii[0] * 1.02
    return {
        "body": body_mesh(cfg),
        "head": head_mesh(cfg),
        "face": face_mesh(cfg),
        "arm": arm_mesh(cfg),
        "eye": eye_mesh(w, h, curvature),
        "eye_arc": eye_arc_mesh(w, h, curvature),
        "halo_l": halo_on_face(cfg, -cfg.eye_spacing, cfg.eye_elevation),
        "halo_r": halo_on_face(cfg, cfg.eye_spacing, cfg.eye_elevation),
        "chest": disc_mesh(cfg.chest_light_radius, cfg.chest_light_radius, n=32, rings=6),
        "chest_halo": disc_mesh(
            cfg.chest_light_radius * 2.6, cfg.chest_light_radius * 2.6, n=32, rings=8, alpha_profile=True
        ),
        "shadow": disc_mesh(1.0, 1.0, n=48, rings=12, alpha_profile=True),
    }
