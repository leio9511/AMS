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
