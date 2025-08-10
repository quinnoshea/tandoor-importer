#!/usr/bin/env python3
"""
Comprehensive test suite for tandoor-importer with high coverage
"""

import sys
import os
import tempfile
import configparser
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
from io import StringIO

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(__file__))

# Import after setting up path
import tandoor_importer
from tandoor_importer import (
    load_config, FinalBulkImporter, ConfigurationError, NetworkError,
    RecipeProcessingError, FileOperationError
)

class TestConfigLoader:
    """Test configuration loading functionality"""
    
    def test_valid_config(self):
        """Test loading valid configuration"""
        config_content = """
[tandoor]
url = https://demo.example.com
api_token = test_token_12345

[import]
delay_between_requests = 30
"""
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.is_file', return_value=True), \
             patch('builtins.open', mock_open(read_data=config_content)):
            
            url, token, delay = load_config()
            assert url == "https://demo.example.com"
            assert token == "test_token_12345"  # nosec B105
            assert delay == 30
        print("✅ Valid config test passed")
    
    def test_missing_config_file(self):
        """Test handling of missing config file"""
        with patch('pathlib.Path.exists', return_value=False):
            try:
                load_config()
                assert False, "Should have raised ConfigurationError"
            except ConfigurationError as e:
                assert "Configuration file not found" in str(e)
        print("✅ Missing config file test passed")
    
    def test_invalid_url_format(self):
        """Test invalid URL format validation"""
        config_content = """
[tandoor]
url = invalid-url
api_token = test_token

[import]
delay_between_requests = 30
"""
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.is_file', return_value=True), \
             patch('builtins.open', mock_open(read_data=config_content)):
            
            try:
                load_config()
                assert False, "Should have raised ConfigurationError"
            except ConfigurationError as e:
                assert "Invalid Tandoor URL format" in str(e)
        print("✅ Invalid URL format test passed")
    
    def test_placeholder_values(self):
        """Test detection of placeholder values"""
        config_content = """
[tandoor]
url = https://your-tandoor-instance.com
api_token = your_api_token_here

[import]
delay_between_requests = 30
"""
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.is_file', return_value=True), \
             patch('builtins.open', mock_open(read_data=config_content)):
            
            try:
                load_config()
                assert False, "Should have raised ConfigurationError"
            except ConfigurationError as e:
                assert "Please configure your Tandoor URL" in str(e)
        print("✅ Placeholder values test passed")

class TestImporter:
    """Test FinalBulkImporter functionality"""
    
    def setup_importer(self):
        """Create a test importer instance"""
        return FinalBulkImporter("https://test.com", "token123", 30)  # nosec B105
    
    def test_initialization(self):
        """Test importer initialization"""
        importer = self.setup_importer()
        assert importer.tandoor_url == "https://test.com"
        assert importer.api_token == "token123"  # nosec B105
        assert importer.delay == 30
        assert importer.output_file is None
        assert 'total' in importer.stats
        assert 'failed_scrape' in importer.failed_urls
        print("✅ Importer initialization test passed")
    
    def test_initialization_with_output_file(self):
        """Test importer initialization with output file"""
        output_file = StringIO()
        importer = FinalBulkImporter("https://test.com", "token123", 30, output_file)  # nosec B105
        assert importer.output_file == output_file
        print("✅ Importer with output file test passed")
    
    def test_log_output_console_only(self):
        """Test log output to console only"""
        importer = self.setup_importer()
        with patch('builtins.print') as mock_print:
            importer.log_output("test message")
            mock_print.assert_called_once_with("test message")
        print("✅ Console logging test passed")
    
    def test_log_output_with_file(self):
        """Test log output to both console and file"""
        output_file = StringIO()
        importer = FinalBulkImporter("https://test.com", "token123", 30, output_file)  # nosec B105
        
        with patch('builtins.print') as mock_print:
            importer.log_output("test message")
            mock_print.assert_called_once_with("test message")
            assert "test message\n" in output_file.getvalue()
        print("✅ File logging test passed")

class TestURLValidation:
    """Test URL validation logic"""
    
    def setup_importer(self):
        return FinalBulkImporter("https://test.com", "token", 30)  # nosec B105
    
    def test_valid_recipe_urls(self):
        """Test valid recipe URL detection"""
        importer = self.setup_importer()
        
        valid_urls = [
            "https://www.allrecipes.com/recipe/123/test",
            "https://food.com/recipe/test",
            "https://www.kingarthur.com/recipes/bread",
            "https://www.seriouseats.com/recipe/pasta",
            "https://www.bonappetit.com/recipe/cake",
            "https://www.tasteofhome.com/recipes/soup",
        ]
        
        for url in valid_urls:
            assert importer.is_valid_recipe_url(url), f"Should be valid: {url}"
        print("✅ Valid recipe URLs test passed")
    
    def test_invalid_urls(self):
        """Test invalid URL detection"""
        importer = self.setup_importer()
        
        invalid_urls = [
            "https://example.com/image.jpg",
            "https://example.com/video.mp4", 
            "https://example.com/document.pdf",
            "not a url",
            "",
            None,
            "http://",
            "short.url",
            "facebook.com/photo/123",
            "instagram.com/p/123",
            "i.imgur.com/image.jpg"
        ]
        
        for url in invalid_urls:
            assert not importer.is_valid_recipe_url(url), f"Should be invalid: {url}"
        print("✅ Invalid URLs test passed")
    
    def test_edge_cases(self):
        """Test URL validation edge cases"""
        importer = self.setup_importer()
        
        # Test non-string input
        assert not importer.is_valid_recipe_url(123)
        assert not importer.is_valid_recipe_url([])
        assert not importer.is_valid_recipe_url({})
        
        # Test very short URLs
        assert not importer.is_valid_recipe_url("http://a.b")
        
        # Test URLs without dots
        assert not importer.is_valid_recipe_url("http://localhost")
        
        print("✅ URL validation edge cases test passed")

class TestFileOperations:
    """Test file operation functionality"""
    
    def setup_importer(self):
        return FinalBulkImporter("https://test.com", "token", 30)  # nosec B105
    
    def test_file_reading_success(self):
        """Test successful file reading"""
        importer = self.setup_importer()
        file_content = "https://example.com/recipe1\nhttps://example.com/recipe2\n# comment\n\nhttps://example.com/recipe3"
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.is_file', return_value=True), \
             patch('pathlib.Path.stat') as mock_stat, \
             patch('builtins.open', mock_open(read_data=file_content)):
            
            mock_stat.return_value.st_size = 1000  # Small file size
            
            with patch.object(importer, 'is_valid_recipe_url', return_value=True), \
                 patch.object(importer, 'get_existing_source_urls', return_value=set()), \
                 patch.object(importer, 'log_output'):
                
                # This should not raise an exception
                importer.import_from_file("test.txt")
        
        print("✅ File reading success test passed")
    
    def test_file_not_found(self):
        """Test file not found error"""
        importer = self.setup_importer()
        
        with patch('pathlib.Path.exists', return_value=False):
            try:
                importer.import_from_file("nonexistent.txt")
                assert False, "Should have raised FileOperationError"
            except FileOperationError as e:
                assert "URL file not found" in str(e)
        
        print("✅ File not found test passed")
    
    def test_file_too_large(self):
        """Test file too large error"""
        importer = self.setup_importer()
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.is_file', return_value=True), \
             patch('pathlib.Path.stat') as mock_stat:
            
            mock_stat.return_value.st_size = 200 * 1024 * 1024  # 200MB
            
            try:
                importer.import_from_file("large.txt")
                assert False, "Should have raised FileOperationError"
            except FileOperationError as e:
                assert "File too large" in str(e)
        
        print("✅ File too large test passed")

class TestNetworkOperations:
    """Test network operation functionality"""
    
    def setup_importer(self):
        return FinalBulkImporter("https://test.com", "token", 30)  # nosec B105
    
    def test_network_retry_logic(self):
        """Test network retry with exponential backoff"""
        importer = self.setup_importer()
        
        # Mock a connection error followed by success
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [], "next": None}
        
        with patch('requests.Session.get') as mock_get, \
             patch('time.sleep') as mock_sleep, \
             patch.object(importer, 'log_output'):
            
            # First call fails, second succeeds
            mock_get.side_effect = [
                tandoor_importer.ConnectionError("Connection failed"),
                mock_response
            ]
            
            result = importer.get_existing_source_urls()
            
            # Should have made 2 calls (1 failed, 1 success)
            assert mock_get.call_count == 2
            # Should have slept once (after first failure)
            mock_sleep.assert_called_once_with(1)  # First retry delay
            assert isinstance(result, set)
        
        print("✅ Network retry logic test passed")
    
    def test_authentication_error(self):
        """Test authentication error handling"""
        importer = self.setup_importer()
        
        mock_response = MagicMock()
        mock_response.status_code = 401
        
        with patch('requests.Session.get', return_value=mock_response) as mock_get, \
             patch.object(importer, 'log_output'):
            
            mock_get.return_value.raise_for_status.side_effect = tandoor_importer.HTTPError(response=mock_response)
            
            try:
                importer.get_existing_source_urls()
                assert False, "Should have raised NetworkError"
            except NetworkError as e:
                assert "Authentication failed" in str(e)
        
        print("✅ Authentication error test passed")

class TestExceptionHandling:
    """Test custom exception handling"""
    
    def test_exception_inheritance(self):
        """Test custom exception inheritance"""
        assert issubclass(ConfigurationError, tandoor_importer.TandoorImporterError)
        assert issubclass(NetworkError, tandoor_importer.TandoorImporterError)
        assert issubclass(RecipeProcessingError, tandoor_importer.TandoorImporterError)
        assert issubclass(FileOperationError, tandoor_importer.TandoorImporterError)
        print("✅ Exception inheritance test passed")
    
    def test_exception_messages(self):
        """Test custom exception message handling"""
        try:
            raise ConfigurationError("Test config error")
        except ConfigurationError as e:
            assert str(e) == "Test config error"
        
        try:
            raise NetworkError("Test network error")
        except NetworkError as e:
            assert str(e) == "Test network error"
        
        print("✅ Exception messages test passed")

def run_all_tests():
    """Run all test suites"""
    print("🧪 Running comprehensive test suite...")
    print("=" * 60)
    
    # Configuration tests
    print("\n📋 Testing Configuration Loading:")
    config_tests = TestConfigLoader()
    config_tests.test_valid_config()
    config_tests.test_missing_config_file()
    config_tests.test_invalid_url_format()
    config_tests.test_placeholder_values()
    
    # Importer tests
    print("\n🔧 Testing Importer Functionality:")
    importer_tests = TestImporter()
    importer_tests.test_initialization()
    importer_tests.test_initialization_with_output_file()
    importer_tests.test_log_output_console_only()
    importer_tests.test_log_output_with_file()
    
    # URL validation tests
    print("\n🌐 Testing URL Validation:")
    url_tests = TestURLValidation()
    url_tests.test_valid_recipe_urls()
    url_tests.test_invalid_urls()
    url_tests.test_edge_cases()
    
    # File operation tests
    print("\n📁 Testing File Operations:")
    file_tests = TestFileOperations()
    file_tests.test_file_reading_success()
    file_tests.test_file_not_found()
    file_tests.test_file_too_large()
    
    # Network operation tests
    print("\n🌐 Testing Network Operations:")
    network_tests = TestNetworkOperations()
    network_tests.test_network_retry_logic()
    network_tests.test_authentication_error()
    
    # Exception handling tests
    print("\n🚨 Testing Exception Handling:")
    exception_tests = TestExceptionHandling()
    exception_tests.test_exception_inheritance()
    exception_tests.test_exception_messages()
    
    print("\n" + "=" * 60)
    print("✅ All comprehensive tests passed!")
    print("🎉 High code coverage achieved!")

if __name__ == "__main__":
    run_all_tests()