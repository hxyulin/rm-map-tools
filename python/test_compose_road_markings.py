# SPDX-License-Identifier: LicenseRef-Proprietary
import copy
import unittest
from unittest.mock import patch

import numpy as np
from compose_road_markings import ROADS, WORDMARKS, remove_obsolete_wordmarks


class RoadMarkingsTest(unittest.TestCase):
    def fixture(self):
        names = (
            [n for group in WORDMARKS for n in group]
            + list(ROADS)
            + ["retained_wordmark"]
        )
        doc = {"nodes": [{"name": n, "mesh": i} for i, n in enumerate(names)]}
        parts = [
            (i, 0, np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 0.001]]), np.zeros((2, 3)), 0)
            for i in range(len(names))
        ]
        return doc, parts

    def test_both_complete_words_removed_and_other_geometry_retained(self):
        doc, parts = self.fixture()
        original = copy.deepcopy(doc)
        with patch("compose_road_markings.mesh_instances", return_value=parts):
            result, removed = remove_obsolete_wordmarks(doc, b"")
        self.assertEqual(doc, original)
        self.assertEqual(len(removed), 30)
        self.assertTrue(all("mesh" not in n for n in result["nodes"][:30]))
        self.assertEqual(result["nodes"][30:], original["nodes"][30:])

    def test_changed_source_selection_fails(self):
        doc, parts = self.fixture()
        for missing in [0, 30]:
            with (
                patch(
                    "compose_road_markings.mesh_instances",
                    return_value=[p for p in parts if p[0] != missing],
                ),
                self.assertRaises(ValueError),
            ):
                remove_obsolete_wordmarks(doc, b"")
        parts[0][2][1, 2] = 0.1
        with (
            patch("compose_road_markings.mesh_instances", return_value=parts),
            self.assertRaises(ValueError),
        ):
            remove_obsolete_wordmarks(doc, b"")

    def test_nonoverlapping_road_fails(self):
        doc, parts = self.fixture()
        parts[30][2][:, :2] += 5
        with (
            patch("compose_road_markings.mesh_instances", return_value=parts),
            self.assertRaises(ValueError),
        ):
            remove_obsolete_wordmarks(doc, b"")


if __name__ == "__main__":
    unittest.main()
