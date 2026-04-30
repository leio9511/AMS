import json
import os

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "ams_provider_config.json")

def load_provider_config():
    if os.path.exists(DEFAULT_CONFIG_PATH):
        try:
            with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
            
    return {
        "default_provider": "jqdata",
        "providers": {
            "jqdata": {
                "dataset_path": "/root/projects/AMS/data/cb_history_factors_jqdata.csv",
                "metrics_path": "/root/projects/AMS/data/cb_history_factors_jqdata.metrics.json"
            },
            "tushare": {
                "dataset_path": "/root/projects/AMS/data/cb_history_factors_tushare.csv",
                "metrics_path": "/root/projects/AMS/data/cb_history_factors_tushare.metrics.json"
            }
        }
    }
