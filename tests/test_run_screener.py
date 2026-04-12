import json
import os
import pytest
from unittest import mock
import sys

# Add scripts directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from run_screener import run_screener

@mock.patch('run_screener.CACHE_FILE', 'dummy_cache.json')
def test_run_screener_missing_data():
    if os.path.exists('dummy_cache.json'):
        os.remove('dummy_cache.json')
    result = run_screener("Crystal Fly")
    assert "error" in result
    assert result["error"] == "Local cache missing or corrupted"

@mock.patch('run_screener.CACHE_FILE', 'test_cache.json')
def test_run_screener_pe_filter():
    test_data = [
        {"ticker": "000001.SZ", "name": "Ping An Bank", "pe": 10},
        {"ticker": "000002.SZ", "name": "Vanke", "pe": 20},
        {"ticker": "000003.SZ", "name": "Test", "pe": 5}
    ]
    with open('test_cache.json', 'w') as f:
        json.dump(test_data, f)
        
    try:
        result = run_screener("Crystal Fly", max_pe=15.0)
        assert "error" not in result
        assert result["strategy"] == "Crystal Fly"
        assert len(result["results"]) == 2
        tickers = [r["ticker"] for r in result["results"]]
        assert "000001.SZ" in tickers
        assert "000003.SZ" in tickers
        assert "000002.SZ" not in tickers
    finally:
        if os.path.exists('test_cache.json'):
            os.remove('test_cache.json')
