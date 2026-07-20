import tempfile
import unittest
from pathlib import Path

from editor import storage
from editor.models import Project, RoadFeature
from editor.storage import InvalidProjectNameError


class StorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_dir = storage.PROJECTS_DIR
        storage.PROJECTS_DIR = Path(self._tmp.name)

    def tearDown(self) -> None:
        storage.PROJECTS_DIR = self._orig_dir
        self._tmp.cleanup()

    def test_round_trip(self) -> None:
        project = Project(
            roads=[
                RoadFeature(
                    id="r1", road_type="local", max_speed_kmh=50, oneway=False,
                    coordinates=[(47.9, 56.6), (47.91, 56.61)],
                )
            ]
        )
        storage.save_project("mytest", project)
        loaded = storage.load_project("mytest")
        self.assertEqual(loaded.roads[0].id, "r1")
        self.assertEqual(loaded.roads[0].coordinates, [(47.9, 56.6), (47.91, 56.61)])

    def test_missing_project_returns_empty(self) -> None:
        loaded = storage.load_project("doesnotexist")
        self.assertEqual(loaded.roads, [])

    def test_rejects_path_traversal_name(self) -> None:
        with self.assertRaises(InvalidProjectNameError):
            storage.load_project("../../etc/passwd")

    def test_lists_saved_projects(self) -> None:
        storage.save_project("a", Project())
        storage.save_project("b", Project())
        self.assertEqual(storage.list_projects(), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
