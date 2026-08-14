"""Minimal mathutils stub (row-of-rows Matrix, Blender semantics)."""

import math


class Matrix:
    def __init__(self, rows=None):
        if rows is None:
            rows = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]
        self.rows = [list(map(float, row)) for row in rows]

    @property
    def translation(self):
        return (self.rows[0][3], self.rows[1][3], self.rows[2][3])

    @translation.setter
    def translation(self, value):
        for i in range(3):
            self.rows[i][3] = float(value[i])

    @classmethod
    def Translation(cls, vec):
        m = cls()
        for i in range(3):
            m.rows[i][3] = float(vec[i])
        return m

    @classmethod
    def Rotation(cls, angle, size, axis):
        c, s = math.cos(angle), math.sin(angle)
        m = cls()
        if axis == "X":
            m.rows[1][1], m.rows[1][2] = c, -s
            m.rows[2][1], m.rows[2][2] = s, c
        elif axis == "Y":
            m.rows[0][0], m.rows[0][2] = c, s
            m.rows[2][0], m.rows[2][2] = -s, c
        else:
            m.rows[0][0], m.rows[0][1] = c, -s
            m.rows[1][0], m.rows[1][1] = s, c
        return m

    def __matmul__(self, other):
        out = [[sum(self.rows[i][k] * other.rows[k][j] for k in range(4)) for j in range(4)] for i in range(4)]
        return Matrix(out)

    def __getitem__(self, index):
        return self.rows[index]

    def __repr__(self):
        return f"Matrix({self.rows})"


class Vector(tuple):
    pass
