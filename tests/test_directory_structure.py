import os
import pytest

def test_directories_exist():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    
    assert os.path.isdir(os.path.join(base_dir, 'engine'))
    assert os.path.isdir(os.path.join(base_dir, 'strategies'))
    assert os.path.isdir(os.path.join(base_dir, 'data_adapters'))
    assert os.path.isdir(os.path.join(base_dir, 'legacy_scripts'))

def test_legacy_scripts_moved():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    
    legacy_dir = os.path.join(base_dir, 'legacy_scripts')
    scripts_dir = os.path.join(base_dir, 'scripts')
    
    files_to_check = ['etf_tracker.py', 'crystal_fly_swatter.py', 'pilot_stock_radar.py']
    
    for filename in files_to_check:
        assert os.path.isfile(os.path.join(legacy_dir, filename)), f"{filename} not found in legacy_scripts"
        assert not os.path.isfile(os.path.join(scripts_dir, filename)), f"{filename} should not be in scripts"
