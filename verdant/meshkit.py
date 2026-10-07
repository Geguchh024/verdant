# SPDX-License-Identifier: GPL-3.0-or-later
"""Accumulate vertices, faces, UVs and per-vertex attributes, then build a mesh.

Generators append parts (tubes, leaves, blades) to a MeshBuilder and call
``build`` once, which is much faster than creating many small meshes.
Every builder writes two float attributes that the shaders read:

- ``vd_height``: 0 at the base of a blade, leaf or branch, 1 at its tip.
- ``vd_rand``: a random value per part (blade, leaf, needle), for colour variation.
"""

import math

import bpy
from mathutils import Matrix, Vector

UP = Vector((0.0, 0.0, 1.0))


class MeshBuilder:
    def __init__(self):
        self.verts = []
        self.faces = []
        self.uvs = []      # one (u, v) per face corner, in face order
        self.height = []   # per vertex
        self.rand = []     # per vertex
        self.mat = []      # per face material index

    def add_vert(self, co, height=0.0, rand=0.0):
        self.verts.append(tuple(co))
        self.height.append(height)
        self.rand.append(rand)
        return len(self.verts) - 1

    def add_face(self, idx, uvs, mat=0):
        self.faces.append(tuple(idx))
        self.uvs.extend(uvs)
        self.mat.append(mat)

    # -- shapes -----------------------------------------------------------
    def tube(self, points, radii, sides, mat=0, rand=0.0, uv_scale=1.0, cap=False, h0=0.0, h1=1.0):
        """A tapered tube along a polyline, using parallel-transport frames.

        UV u goes around the tube, v is the distance along it divided by
        the circumference (scaled by uv_scale) so bark is never stretched.
        """
        n = len(points)
        if n < 2:
            return
        tangents = []
        for i in range(n):
            a = points[max(i - 1, 0)]
            b = points[min(i + 1, n - 1)]
            t = (b - a)
            tangents.append(t.normalized() if t.length > 1e-9 else UP.copy())
        ref = UP if abs(tangents[0].dot(UP)) < 0.95 else Vector((1.0, 0.0, 0.0))
        normal = tangents[0].cross(ref).normalized()
        rings = []
        dist = 0.0
        circ = max(2.0 * math.pi * radii[0], 1e-4)
        vs = []
        for i in range(n):
            if i > 0:
                prev, cur = tangents[i - 1], tangents[i]
                axis = prev.cross(cur)
                if axis.length > 1e-9:
                    ang = prev.angle(cur)
                    normal = Matrix.Rotation(ang, 3, axis.normalized()) @ normal
                dist += (points[i] - points[i - 1]).length
            binormal = tangents[i].cross(normal)
            ring = []
            h = h0 + (h1 - h0) * i / (n - 1)
            for s in range(sides):
                a = 2.0 * math.pi * s / sides
                off = normal * math.cos(a) + binormal * math.sin(a)
                ring.append(self.add_vert(points[i] + off * radii[i], h, rand))
            rings.append(ring)
            vs.append(dist / circ * uv_scale)
        for i in range(n - 1):
            r0, r1 = rings[i], rings[i + 1]
            for s in range(sides):
                s1 = (s + 1) % sides
                u0, u1 = s / sides, (s + 1) / sides
                self.add_face((r0[s], r0[s1], r1[s1], r1[s]),
                              ((u0, vs[i]), (u1, vs[i]), (u1, vs[i + 1]), (u0, vs[i + 1])), mat)
        if cap:
            top = rings[-1]
            self.add_face(tuple(reversed(top)), [(0.5, 0.5)] * sides, mat)

    def strip(self, rows, mat=0, rand=0.0):
        """A ribbon from rows of vertices (each row is a list of positions, left to right).

        UV v runs along the rows, u across them. Used for blades and fronds.
        """
        n = len(rows)
        cols = len(rows[0])
        idx = []
        for i, row in enumerate(rows):
            h = i / (n - 1)
            idx.append([self.add_vert(co, h, rand) for co in row])
        for i in range(n - 1):
            v0, v1 = i / (n - 1), (i + 1) / (n - 1)
            for j in range(cols - 1):
                u0, u1 = j / (cols - 1), (j + 1) / (cols - 1)
                self.add_face((idx[i][j], idx[i][j + 1], idx[i + 1][j + 1], idx[i + 1][j]),
                              ((u0, v0), (u1, v0), (u1, v1), (u0, v1)), mat)
        return idx

    def blade(self, origin, direction, side, length, width, segments=5, bend=0.4, fold=0.3,
              taper=1.0, mat=0, rand=0.0, droop_axis=None, width_fn=None):
        """A folded, tapering grass blade or leaf strap.

        direction: initial growth direction; side: unit vector across the blade.
        bend: how far it arches under gravity (0 = straight, 1 = strong arch).
        fold: height of the centre crease relative to width (V cross-section).
        """
        direction = direction.normalized()
        side = side.normalized()
        up_face = direction.cross(side).normalized()
        rows = []
        pos = origin.copy()
        seg = length / segments
        d = direction.copy()
        for i in range(segments + 1):
            t = i / segments
            if width_fn:
                w = width * width_fn(t)
            else:
                w = width * (1.0 - t ** 1.5 * taper) if i < segments else 0.0
            w = max(w, 0.0)
            f = up_face * (fold * w)
            if i == segments and not width_fn:
                rows.append([pos, pos, pos])
            else:
                rows.append([pos - side * w * 0.5, pos + f, pos + side * w * 0.5])
            # bend toward the ground, more strongly further along
            d = (d - UP * (bend * 2.2 / segments) * (0.3 + t)).normalized()
            up_face = d.cross(side).normalized()
            pos = pos + d * seg
        return self.strip(rows, mat, rand)

    def leaf(self, base, direction, normal, length, width, outline, mat=0, rand=0.0,
             fold=0.12, curl=0.15, steps=6):
        """A leaf with a raised midrib, built from an outline function.

        outline(t) -> half width (0..1) at fraction t along the midrib.
        UV u spans the width (0.5 is the midrib), v runs base to tip.
        """
        direction = direction.normalized()
        side = direction.cross(normal).normalized()
        normal = side.cross(direction).normalized()
        left, mid, right = [], [], []
        for i in range(steps + 1):
            t = i / steps
            w = outline(t) * width * 0.5
            c = base + direction * (t * length) - normal * (curl * length * t * t)
            m = c + normal * (fold * width * 0.5 * (1.0 - t))
            h = t
            mid.append(self.add_vert(m, h, rand))
            left.append(self.add_vert(c - side * w, h, rand))
            right.append(self.add_vert(c + side * w, h, rand))
        for i in range(steps):
            v0, v1 = i / steps, (i + 1) / steps
            hw0 = outline(v0) * 0.5
            hw1 = outline(v1) * 0.5
            self.add_face((left[i], mid[i], mid[i + 1], left[i + 1]),
                          ((0.5 - hw0, v0), (0.5, v0), (0.5, v1), (0.5 - hw1, v1)), mat)
            self.add_face((mid[i], right[i], right[i + 1], mid[i + 1]),
                          ((0.5, v0), (0.5 + hw0, v0), (0.5 + hw1, v1), (0.5, v1)), mat)

    def needle(self, base, direction, side, length, width, mat=0, rand=0.0):
        """A single thin triangle, for conifer needles."""
        tip = base + direction * length
        a = self.add_vert(base - side * width, 0.0, rand)
        b = self.add_vert(base + side * width, 0.0, rand)
        c = self.add_vert(tip, 1.0, rand)
        self.add_face((a, b, c), ((0.0, 0.0), (1.0, 0.0), (0.5, 1.0)), mat)

    def spray(self, points, length, spacing, forward, planes, mat=0, rand=0.0, rng=None, start=0.0):
        """Needles along a shoot as crossed fringes, like a conifer sprig.

        Each sample along the polyline emits one needle per side per plane;
        a needle is a triangle from this sample to the next to its tip, so
        neighbouring needles share vertices and the shoot reads as a dense
        bottle brush. planes: angles (radians) of the fringe planes around
        the shoot, 0 = horizontal. forward: how far needles point toward
        the shoot tip (radians).
        """
        cum = [0.0]
        for i in range(len(points) - 1):
            cum.append(cum[-1] + (points[i + 1] - points[i]).length)
        total = cum[-1]
        if total < spacing * 2:
            return
        samples = []
        d = total * start
        seg = 0
        while d <= total:
            while seg < len(points) - 2 and cum[seg + 1] < d:
                seg += 1
            k = (d - cum[seg]) / max(cum[seg + 1] - cum[seg], 1e-9)
            p = points[seg].lerp(points[seg + 1], k)
            t = (points[seg + 1] - points[seg]).normalized()
            samples.append((p, t, d / total))
            d += spacing
        prev = None
        cf, sf = math.cos(forward), math.sin(forward)
        for p, t, u in samples:
            c = self.add_vert(p, 0.0, rand)
            side0 = t.cross(UP)
            side0 = side0.normalized() if side0.length > 1e-6 else any_perpendicular(t)
            # needles are shorter at the base and the very tip of the shoot
            scale = min(1.0, (1.0 - u) * 5.0 + 0.25) * min(1.0, u * 6.0 + 0.5)
            tips = []
            for a in planes:
                s = rotate(side0, t, a)
                for sign in (-1.0, 1.0):
                    jitter = rng.uniform(0.8, 1.15) if rng else 1.0
                    tip = p + (s * (sign * cf) + t * sf) * (length * scale * jitter)
                    tips.append(self.add_vert(tip, 1.0, rand))
            if prev is not None:
                pc, ptips = prev
                for tip in ptips:
                    self.add_face((pc, c, tip), ((0.0, 0.0), (1.0, 0.0), (0.5, 1.0)), mat)
            prev = (c, tips)

    # -- output -----------------------------------------------------------
    def build(self, name, materials=(), smooth=True):
        me = bpy.data.meshes.new(name)
        me.from_pydata(self.verts, [], self.faces)
        uv = me.uv_layers.new(name="UVMap")
        flat = [c for pair in self.uvs for c in pair]
        uv.data.foreach_set("uv", flat)
        for key, data in (("vd_height", self.height), ("vd_rand", self.rand)):
            attr = me.attributes.new(key, "FLOAT", "POINT")
            attr.data.foreach_set("value", data)
        for m in materials:
            me.materials.append(m)
        if self.mat:
            me.polygons.foreach_set("material_index", self.mat)
        me.polygons.foreach_set("use_smooth", [smooth] * len(self.faces))
        me.validate(clean_customdata=False)
        me.update()
        return me


def any_perpendicular(v):
    ref = UP if abs(v.normalized().dot(UP)) < 0.95 else Vector((1.0, 0.0, 0.0))
    return v.cross(ref).normalized()


def rotate(v, axis, angle):
    return Matrix.Rotation(angle, 3, axis) @ v
