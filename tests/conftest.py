import pytest
from unittest.mock import patch
import tempfile
import os

@pytest.fixture(autouse=True)
def mock_dataset_semantic_validator():
    with patch("ams.validators.cb_data_validator.DatasetSemanticValidator") as mock_validator:
        mock_validator.return_value.validate_dataframe.return_value = True
        yield mock_validator

@pytest.fixture(autouse=True)
def mock_dataset_paths():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_path = os.path.join(tmpdir, "cb_history_factors.csv")
        metrics_path = os.path.join(tmpdir, "cb_history_factors.metrics.json")
        with patch("etl.jqdata_sync_cb.DATA_PATH", data_path), \
             patch("etl.jqdata_sync_cb.METRICS_PATH", metrics_path):
            yield

@pytest.fixture
def isolated_paths(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    mock_data_path = str(data_dir / "cb_history_factors.csv")
    mock_metrics_path = str(data_dir / "cb_history_factors.metrics.json")
    mock_reports_dir = str(reports_dir)

    import os
    original_os_path_join = os.path.join
    original_makedirs = os.makedirs

    def mock_join(d, *args):
        if isinstance(d, str) and d == "/root/projects/AMS/reports":
            return original_os_path_join(mock_reports_dir, *args)
        return original_os_path_join(d, *args)

    def mock_makedirs(path, *args, **kwargs):
        if path == "/root/projects/AMS/reports":
            return original_makedirs(mock_reports_dir, *args, **kwargs)
        return original_makedirs(path, *args, **kwargs)

    with patch("etl.jqdata_sync_cb.DATA_PATH", mock_data_path), \
         patch("etl.jqdata_sync_cb.METRICS_PATH", mock_metrics_path), \
         patch("etl.cb_etl_runner.os.path.join", side_effect=mock_join), \
         patch("etl.cb_etl_runner.os.makedirs", side_effect=mock_makedirs):
             yield {
                 "data": mock_data_path,
                 "metrics": mock_metrics_path,
                 "reports": mock_reports_dir
             }
