import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET
import numpy as np

if __package__:
    from .surface_export import build_bone_coverage, export_coverage_surfaces
else:
    from surface_export import build_bone_coverage, export_coverage_surfaces


def mesh(v, f):
    return SimpleNamespace(vertices_sub=np.asarray(v, dtype=float).reshape(-1, 3),
                           faces=np.asarray(f, dtype=np.int64).reshape(-1, 3))


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.bone = mesh([[1,1,1], [2,1,1], [1,2,1], [2,2,1], [3,2,1]],
                         [[0,1,2], [1,3,2], [1,4,3]])
        # Reordered vertices AND reversed face winding still map exactly.
        self.scb = mesh(self.bone.vertices_sub[[3,2,1,0]], [[3,1,2], [2,1,0]])
        self.vox = np.array([2.,3.,4.])

    def test_mapping_area_and_nonmutation(self):
        before = self.bone.vertices_sub.copy()
        out = build_bone_coverage(self.bone, [("FC", self.scb, [True, False])], self.vox)
        np.testing.assert_array_equal(out["coverage_class"], [1,2,0])
        self.assertEqual(out["audit"]["union_cAB_mm2"], 3.)
        self.assertEqual(out["audit"]["union_dAB_mm2"], 3.)
        np.testing.assert_array_equal(before, self.bone.vertices_sub)

    def test_unmatched_face_rejected(self):
        invalid = mesh([[1,1,2], [2,1,2], [1,2,2]], [[0,1,2]])
        with self.assertRaisesRegex(ValueError, "exact subset"):
            build_bone_coverage(self.bone, [("FC", invalid, [True])], self.vox)

    def test_conflicting_overlap_rejected(self):
        with self.assertRaisesRegex(ValueError, "conflicting"):
            build_bone_coverage(self.bone, [("mTC", self.scb, [True,False]),
                                          ("lTC", self.scb, [False,False])], self.vox)

    def test_consistent_overlap_counted_once(self):
        out = build_bone_coverage(self.bone, [("mTC", self.scb, [True,False]),
                                            ("lTC", self.scb, [True,False])], self.vox)
        self.assertEqual(out["audit"]["union_tAB_mm2"], 6.)

    def test_empty_domain_is_gray(self):
        out = build_bone_coverage(self.bone, [("FC", mesh([], []), [])], self.vox)
        np.testing.assert_array_equal(out["coverage_class"], [0,0,0])
        self.assertIsNone(out["audit"]["regions"][0]["FCL_percent"])

    def test_vtp_affine_combined_connectivity_and_rgb(self):
        out = build_bone_coverage(self.bone, [("FC", self.scb, [True,False])], self.vox)
        # Rotation + anisotropic spacing + translation.
        affine = np.array([[0,-3,0,10], [2,0,0,20], [0,0,4,30], [0,0,0,1]], float)
        with tempfile.TemporaryDirectory() as directory:
            manifest = export_coverage_surfaces(directory, {"femur":out,"tibia":out}, affine, self.vox)
            tree = ET.parse(Path(directory) / "bone_coverage.vtp")
            piece = tree.find(".//Piece")
            self.assertEqual(int(piece.attrib["NumberOfPoints"]), 10)
            self.assertEqual(int(piece.attrib["NumberOfPolys"]), 6)
            points = np.fromstring(piece.find("Points/DataArray").text, sep=" ").reshape(-1,3)
            np.testing.assert_allclose(points[:2], [[10,20,30], [10,22,30]])
            arrays = {x.attrib["Name"]:np.fromstring(x.text or "",sep=" ") for x in piece.findall("CellData/DataArray")}
            np.testing.assert_array_equal(arrays["coverage_class"], [1,2,0,1,2,0])
            np.testing.assert_array_equal(arrays["bone_label"], [1,1,1,3,3,3])
            np.testing.assert_array_equal(arrays["coverage_rgb"][:6], [45,190,80,230,50,50])
            indices = np.fromstring(piece.find("Polys/DataArray[@Name='connectivity']").text,sep=" ").reshape(-1,3)
            np.testing.assert_array_equal(indices[3:], self.bone.faces + 5)
            self.assertEqual(json.loads((Path(directory)/"coverage_manifest.json").read_text()), manifest)

    def test_shear_is_rejected(self):
        out = build_bone_coverage(self.bone, [], self.vox)
        a = np.diag([2.,3.,4.,1.]); a[0,1] = .5
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,"shear"):
                export_coverage_surfaces(directory, {"femur":out,"tibia":out}, a, self.vox)


if __name__ == "__main__":
    unittest.main()
