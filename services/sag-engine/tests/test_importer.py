from argparse import Namespace
from pathlib import Path

from sag_video.importer import MaintenanceImporter
from sag_video.store import Store


def test_importer_plan_is_read_only_and_reports_normalized_rows(tmp_path: Path):
    database = tmp_path / "source.db"
    store = Store(database)
    store.create_project("Import me", "vertical_1080p", "workspace_import")
    store.close()
    for name in ("media", "proxies", "artifacts", "cache"):
        (tmp_path / name).mkdir()
    importer = MaintenanceImporter(Namespace(
        sqlite=str(database), media_root=str(tmp_path / "media"),
        proxy_root=str(tmp_path / "proxies"), artifact_root=str(tmp_path / "artifacts"),
        workspace_map=None, database_url="", bucket="", cache_dir=str(tmp_path / "cache"),
    ))
    report = importer.plan()
    assert report.status == "ready"
    assert report.rows["projects"] == 2
    assert report.files == 0
    assert report.missing_files == []
    assert importer.plan().status == "ready"
