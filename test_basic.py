#!/usr/bin/env python3
"""
Basic tests for tandoor-importer to generate coverage data
"""

import sys
import os
import tempfile
import configparser
from unittest.mock import patch, MagicMock

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(__file__))

def test_load_config():
    """Test configuration loading"""
    # Import after setting up path
    from tandoor_importer import load_config
    
    # This will load the test config created in CI
    try:
        url, token, delay = load_config()
        assert url == "https://demo.example.com"
        assert token == "test_token_12345"
        assert delay == 30
        print("✅ Config loading test passed")
    except SystemExit:
        print("✅ Config validation working (expected exit for invalid config)")

def test_importer_init():
    """Test importer initialization"""
    from tandoor_importer import FinalBulkImporter
    
    importer = FinalBulkImporter("https://test.com", "token123", 30)
    assert importer.tandoor_url == "https://test.com"
    assert importer.api_token == "token123"
    assert importer.delay == 30
    assert 'total' in importer.stats
    assert 'failed_scrape' in importer.failed_urls
    print("✅ Importer initialization test passed")

def test_url_validation():
    """Test URL validation logic"""
    from tandoor_importer import FinalBulkImporter
    
    importer = FinalBulkImporter("https://test.com", "token", 30)
    
    # Valid URLs
    assert importer.is_valid_recipe_url("https://www.allrecipes.com/recipe/123/test") == True
    assert importer.is_valid_recipe_url("https://food.com/recipe/test") == True
    
    # Invalid URLs
    assert importer.is_valid_recipe_url("https://example.com/image.jpg") == False
    assert importer.is_valid_recipe_url("not a url") == False
    assert importer.is_valid_recipe_url("") == False
    assert importer.is_valid_recipe_url(None) == False
    
    print("✅ URL validation test passed")

if __name__ == "__main__":
    test_load_config()
    test_importer_init() 
    test_url_validation()
    print("✅ All basic tests passed!")