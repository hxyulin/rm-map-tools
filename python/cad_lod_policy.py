# SPDX-License-Identifier: MIT OR Apache-2.0
# Copyright (c) 2026 hxyulin <hxyulin@proton.me>
"""Pure planning for hierarchical CAD LOD; does not mesh or alter source geometry.

Policies use reviewed semantic node IDs, never fuzzy names or CAD layers. All
lengths are millimetres. Generated plans are requests, not validation evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math


@dataclass(frozen=True)
class Quality:
    """End-to-end deviation ceiling and its disjoint error allowances, in mm."""
    total_mm: float
    fit_mm: float = 0.0
    mesh_mm: float = 0.0
    quantization_mm: float = 0.0

    def __post_init__(self):
        values = (self.total_mm, self.fit_mm, self.mesh_mm, self.quantization_mm)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or
               not math.isfinite(v) or v < 0 for v in values) or self.total_mm <= 0:
            raise ValueError('quality allowances must be finite nonnegative numbers; total > 0')
        if self.fit_mm + self.mesh_mm + self.quantization_mm > self.total_mm + 1e-12:
            raise ValueError('fit, mesh and quantization allowances exceed total')


@dataclass(frozen=True)
class Node:
    """Reviewed ownership/culling node, separate from shared geometry definitions.

    max_world_scale is the accumulated world-transform singular-value bound,
    not a parent-relative scale. Protection applies to the complete subtree
    and cannot be removed by a child.
    Crossing boundaries remain source-owned; their sample contract is resolved
    separately by shared_boundary_limits before meshing.
    """
    id: str
    parent: str | None
    prototype: str | None = None
    max_world_scale: float = 1.0
    protected: bool = False


@dataclass(frozen=True)
class Request:
    """One definition's requested local meshing quality in an ownership context."""
    node: str
    prototype: str
    channel: str
    level: str
    quality: Quality
    protected: bool
    max_world_scale: float


def _tree(nodes):
    by_id = {n.id: n for n in nodes}
    if len(by_id) != len(nodes) or any(not n.id for n in nodes):
        raise ValueError('node IDs must be nonempty and unique')
    for node in nodes:
        if node.parent is not None and node.parent not in by_id:
            raise ValueError('missing parent')
        if isinstance(node.max_world_scale, bool) or not math.isfinite(node.max_world_scale) or node.max_world_scale <= 0:
            raise ValueError('max_world_scale must be a finite positive singular-value bound')
        visited = set()
        current = node
        while current is not None:
            if current.id in visited:
                raise ValueError('hierarchy cycle')
            visited.add(current.id)
            current = by_id.get(current.parent)
    return by_id


def plan(nodes, defaults, overrides=None):
    """Resolve ancestor overrides and conservative local errors for each mesh use.

    defaults is {(channel, level): Quality}; collision has exactly one level.
    overrides is {node_id: {(channel, level): Quality}}. Protected subtrees allow
    source-preserving retessellation but disable fit/quantization allowances.
    Input policies and hierarchy remain unchanged. No requested LOD is certified.
    """
    nodes = tuple(nodes)
    by_id = _tree(nodes)
    overrides = overrides or {}
    if set(overrides) - set(by_id):
        raise ValueError('unknown override node')
    if not defaults or any(not isinstance(k, tuple) or len(k) != 2 or
                           k[0] not in ('visual', 'collision') or not k[1]
                           for k in defaults):
        raise ValueError('expected (visual|collision, level) policy keys')
    if sum(k[0] == 'collision' for k in defaults) != 1:
        raise ValueError('collision must have one camera-independent level')
    for settings in (defaults, *overrides.values()):
        if set(settings) - set(defaults) or any(not isinstance(v, Quality) for v in settings.values()):
            raise ValueError('unknown quality slot or invalid Quality')
    requests = []
    for node in nodes:
        if node.prototype is None:
            continue
        chain = []
        current = node
        while current is not None:
            chain.append(current)
            current = by_id.get(current.parent)
        protected = any(n.protected for n in chain)
        settings = dict(defaults)
        for ancestor in reversed(chain):
            settings.update(overrides.get(ancestor.id, {}))
        for (channel, level), quality in sorted(settings.items()):
            if protected and (quality.fit_mm or quality.quantization_mm):
                raise ValueError(f'{node.id}: protected subtree requests fit or quantization')
            scale = node.max_world_scale
            local = Quality(**{key: value / scale for key, value in asdict(quality).items()})
            requests.append(Request(node.id, node.prototype, channel, level, local, protected, scale))
    return tuple(requests)


def shared_boundary_limits(requests, boundaries):
    """Resolve strictest world-mm mesh allowances for touching source boundaries.

    boundaries maps stable edge/interface IDs to node IDs. Visual interfaces use
    the finest allowance across *all* levels so any mixed-level pair can meet.
    Collision is resolved separately. Convert these world-space limits into the
    shared interface frame before sampling. Mesher must reuse the actual network;
    a common numeric tolerance alone cannot guarantee matching vertices.
    """
    requests = tuple(requests)
    known = {r.node for r in requests}
    result = {}
    for edge, owners in sorted(boundaries.items()):
        owners = set(owners)
        if not owners or owners - known:
            raise ValueError('boundary needs known mesh owners')
        result[edge] = {channel: min(r.quality.mesh_mm * r.max_world_scale for r in requests
                                   if r.node in owners and r.channel == channel)
                        for channel in ('visual', 'collision')
                        if any(r.node in owners and r.channel == channel for r in requests)}
    return result


def mesh_key(request, *, source_sha256, geometry_sha256, boundary_sha256,
             attributes_sha256, mesher_version):
    """Content key allowing identical effective LODs to alias one mesh payload.

    Caller hashes the complete trim/topology geometry, boundary sample network
    and attribute seam contract. Names, placements and LOD labels are excluded;
    source IDs/appearance/ownership remain separate use bindings. Different scale
    uses share only when their resolved local quality is identical.
    """
    digests = (source_sha256, geometry_sha256, boundary_sha256, attributes_sha256)
    if any(len(v) != 64 or any(c not in '0123456789abcdef' for c in v) for v in digests):
        raise ValueError('expected lowercase SHA-256 digests')
    if not mesher_version:
        raise ValueError('mesher version required')
    payload = dict(source=source_sha256, geometry=geometry_sha256,
                   boundary=boundary_sha256, attributes=attributes_sha256,
                   mesher=mesher_version, quality=asdict(request.quality))
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def projected_error_px(error_mm, depth_mm, viewport_height_px, vertical_fov_rad):
    """Approximate perspective error at conservative nearest positive view depth.

    Selection uses measured achieved error, not a requested budget. Near-plane
    crossings select finest LOD externally; hysteresis is a runtime concern.
    """
    values = (error_mm, depth_mm, viewport_height_px, vertical_fov_rad)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise ValueError('finite numeric projection inputs required')
    if error_mm < 0 or depth_mm <= 0 or viewport_height_px <= 0 or not 0 < vertical_fov_rad < math.pi:
        raise ValueError('invalid perspective projection inputs')
    return error_mm * viewport_height_px / (2 * depth_mm * math.tan(vertical_fov_rad / 2))
