"""Tests for filename sanitisation, generation ids, and storage boundaries."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from backend.app.services import storage

FIXED_DATE = datetime(2026, 8, 9)


class SanitizeFilenameTests(unittest.TestCase):
    def test_removes_illegal_characters(self):
        self.assertEqual(
            storage.sanitize_filename_component("Acme/Corp: Inc!"),
            "AcmeCorp Inc",
        )

    def test_keeps_spaces_underscores_and_hyphens(self):
        self.assertEqual(
            storage.sanitize_filename_component("Senior_Dev-Ops Lead"),
            "Senior_Dev-Ops Lead",
        )

    def test_truncates_to_max_length(self):
        value = "a" * 50
        self.assertEqual(len(storage.sanitize_filename_component(value)), 30)
        self.assertEqual(
            storage.sanitize_filename_component(value, max_length=5), "aaaaa"
        )

    def test_truncation_then_strip(self):
        self.assertEqual(
            storage.sanitize_filename_component("abcde   ghij", max_length=8),
            "abcde",
        )

    def test_empty_and_none_like_values(self):
        self.assertEqual(storage.sanitize_filename_component(""), "")
        self.assertEqual(storage.sanitize_filename_component(None), "")


class GenerationIdTests(unittest.TestCase):
    def test_build_generation_id_matches_legacy_shape(self):
        generation_id = storage.build_generation_id(
            "Stripe", "Technical Program Manager", when=FIXED_DATE
        )
        self.assertEqual(
            generation_id,
            "GopalKumar_Stripe_Technical Program Manager_20260809",
        )

    def test_build_generation_id_sanitizes_components(self):
        generation_id = storage.build_generation_id(
            "Acme/Inc", "Sr. PM!!", when=FIXED_DATE
        )
        self.assertEqual(generation_id, "GopalKumar_AcmeInc_Sr PM_20260809")

    def test_build_artifact_filename(self):
        self.assertEqual(
            storage.build_artifact_filename("GopalKumar_Stripe_TPM_20260809"),
            "GopalKumar_Stripe_TPM_20260809.pdf",
        )

    def test_build_artifact_filename_sanitizes_traversal(self):
        filename = storage.build_artifact_filename("../../etc/passwd")
        self.assertEqual(filename, "etcpasswd.pdf")
        self.assertNotIn("/", filename)
        self.assertNotIn("..", filename)

    def test_build_artifact_filename_falls_back_when_empty(self):
        self.assertEqual(storage.build_artifact_filename(""), "resume.pdf")


class BoundaryTests(unittest.TestCase):
    def test_build_artifact_path_stays_inside_output_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "Output"
            path = storage.build_artifact_path(
                output_dir, "GopalKumar_Stripe_TPM_20260809"
            )
            self.assertEqual(path.parent, output_dir.resolve())
            self.assertEqual(path.name, "GopalKumar_Stripe_TPM_20260809.pdf")

    def test_ensure_within_directory_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "Output"
            output_dir.mkdir()
            with self.assertRaises(storage.StorageBoundaryError):
                storage.ensure_within_directory(
                    output_dir / ".." / "escape.pdf", output_dir
                )

    def test_ensure_within_directory_accepts_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "Output"
            child = output_dir / "nested" / "file.pdf"
            resolved = storage.ensure_within_directory(child, output_dir)
            self.assertEqual(resolved, child.resolve())

    def test_store_artifact_uses_safe_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "compiled.pdf"
            source.write_bytes(b"%PDF-1.4")
            dest = storage.store_artifact(
                source, root / "Output", "../../evil name"
            )
            self.assertEqual(dest.parent, (root / "Output").resolve())
            self.assertEqual(dest.name, "evil name.pdf")
            self.assertTrue(dest.exists())


if __name__ == "__main__":
    unittest.main()
