#!/usr/bin/env python3
"""
Final corrected bulk import script using the proper two-step process
"""

import requests
import time
import sys
import configparser
import argparse
import logging
from typing import Optional, TextIO, Tuple
from pathlib import Path
from requests.exceptions import (
    RequestException, 
    Timeout, 
    ConnectionError, 
    HTTPError
)


class TandoorImporterError(Exception):
    """Base exception for Tandoor Importer."""
    pass


class ConfigurationError(TandoorImporterError):
    """Raised when configuration is invalid or missing."""
    pass


class NetworkError(TandoorImporterError):
    """Raised when network operations fail."""
    pass


class RecipeProcessingError(TandoorImporterError):
    """Raised when recipe processing fails."""
    pass


class FileOperationError(TandoorImporterError):
    """Raised when file operations fail."""
    pass

def load_config() -> Tuple[str, str, int]:
    """Load configuration from config.conf file with comprehensive error handling."""
    config = configparser.ConfigParser()
    config_path = Path(__file__).parent / 'config.conf'

    try:
        if not config_path.exists():
            raise ConfigurationError(
                f"Configuration file not found: {config_path}\n"
                "Please copy config.conf.example to config.conf and configure it."
            )

        if not config_path.is_file():
            raise ConfigurationError(f"Configuration path exists but is not a file: {config_path}")

        # Read configuration with error handling
        try:
            config.read(config_path, encoding='utf-8')
        except (UnicodeDecodeError, configparser.Error) as e:
            raise ConfigurationError(f"Failed to parse configuration file: {e}")

        # Validate required sections exist
        required_sections = {'tandoor', 'import'}
        missing_sections = required_sections - set(config.sections())
        if missing_sections:
            raise ConfigurationError(f"Missing required sections in config: {missing_sections}")

        # Extract and validate configuration values
        try:
            tandoor_url = config.get('tandoor', 'url', fallback='').strip().rstrip('/')
            api_token = config.get('tandoor', 'api_token', fallback='').strip()
            delay = config.getint('import', 'delay_between_requests', fallback=30)
        except (ValueError, configparser.NoOptionError) as e:
            raise ConfigurationError(f"Invalid configuration value: {e}")

        # Validate configuration values
        if not tandoor_url or tandoor_url == 'https://your-tandoor-instance.com':
            raise ConfigurationError(
                "Please configure your Tandoor URL in config.conf\n"
                "Set 'url' under [tandoor] section to your Tandoor instance URL."
            )

        if not api_token or api_token == 'your_api_token_here':  # nosec B105
            raise ConfigurationError(
                "Please configure your API token in config.conf\n"
                "Set 'api_token' under [tandoor] section to your Tandoor API token."
            )

        if delay < 1 or delay > 3600:
            raise ConfigurationError(f"Invalid delay value: {delay}. Must be between 1 and 3600 seconds.")

        # Validate URL format
        if not tandoor_url.startswith(('http://', 'https://')):
            raise ConfigurationError(f"Invalid Tandoor URL format: {tandoor_url}. Must start with http:// or https://")

        return tandoor_url, api_token, delay

    except ConfigurationError:
        raise
    except Exception as e:
        raise ConfigurationError(f"Unexpected error loading configuration: {e}") from e

class FinalBulkImporter:
    def __init__(self, tandoor_url: str, api_token: str, delay: int, output_file: Optional[TextIO] = None):
        self.tandoor_url = tandoor_url
        self.api_token = api_token
        self.delay = delay
        self.output_file = output_file

        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.api_token}'
        })
        self.stats = {
            'total': 0,
            'successful': 0,
            'duplicates': 0,
            'failed_scrape': 0,
            'failed_create': 0,
            'rate_limited': 0,
            'invalid_urls': 0,
            'non_recipe_urls': 0,
            'connection_errors': 0
        }

        # Track failed URLs with reasons
        self.failed_urls = {
            'failed_scrape': [],
            'failed_create': [],
            'non_recipe_urls': [],
            'connection_errors': [],
            'invalid_urls': []
        }

    def is_valid_recipe_url(self, url):
        """Validate if URL could potentially contain a recipe"""
        if not url or not isinstance(url, str):
            return False

        url = url.strip()

        # Basic URL structure check
        if not url.startswith(('http://', 'https://')):
            return False

        if len(url) < 15 or '.' not in url:
            return False

        # Skip obvious non-recipe URLs
        skip_patterns = [
            # Images
            '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp',
            # Videos
            '.mp4', '.mov', '.avi', '.wmv', '.flv', '.webm',
            # Documents
            '.pdf', '.doc', '.docx', '.txt', '.csv',
            # Archives
            '.zip', '.rar', '.tar', '.gz',
            # Social media direct links (not recipe pages)
            'facebook.com/photo', 'instagram.com/p/', 'twitter.com/status',
            # Youtube (handled separately by Tandoor)
            # 'youtube.com', 'youtu.be',  # Actually, let these through as Tandoor handles them
            # Reddit image/generic links
            'i.redd.it', 'v.redd.it', 'reddit.com/gallery',
            # Imgur direct images
            'i.imgur.com',
            # Generic file hosting
            'dropbox.com/s/', 'drive.google.com/file',
            # Forums/generic pages (these are harder to filter)
        ]

        url_lower = url.lower()
        for pattern in skip_patterns:
            if pattern in url_lower:
                return False

        # Check for obvious recipe-related domains/paths
        recipe_indicators = [
            'recipe', 'cook', 'kitchen', 'food', 'allrecipes', 'foodnetwork',
            'kingarthur', 'seriouseats', 'bonappetit', 'tasteofhome', 
            'simplyrecipes', 'delish', 'epicurious', 'martha', 'williams-sonoma'
        ]

        # If URL contains recipe indicators, it's likely valid
        for indicator in recipe_indicators:
            if indicator in url_lower:
                return True

        # For other URLs, be more permissive and let Tandoor try to scrape
        # Better to attempt and fail gracefully than to over-filter
        return True

    def get_existing_source_urls(self) -> set:
        """Get all existing recipe source URLs for duplicate detection with robust error handling."""
        existing_urls = set()
        page = 1
        max_retries = 3
        base_delay = 1

        self.log_output("🔍 Fetching existing recipes for duplicate detection...")

        while True:
            retry_count = 0
            while retry_count <= max_retries:
                try:
                    response = self.session.get(
                        f"{self.tandoor_url}/api/recipe/?page={page}&page_size=100", 
                        timeout=30
                    )

                    if response.status_code == 429:
                        retry_after = int(response.headers.get('Retry-After', 60))
                        self.log_output(f"⏳ Rate limited while fetching existing recipes, waiting {retry_after}s...")
                        time.sleep(retry_after)
                        continue

                    response.raise_for_status()
                    break

                except (Timeout, ConnectionError) as e:
                    retry_count += 1
                    if retry_count > max_retries:
                        raise NetworkError(f"Failed to connect to Tandoor after {max_retries} retries: {e}")
                    
                    wait_time = base_delay * (2 ** (retry_count - 1))  # Exponential backoff
                    self.log_output(f"🔄 Network error (retry {retry_count}/{max_retries}), waiting {wait_time}s: {e}")
                    time.sleep(wait_time)

                except HTTPError as e:
                    if e.response.status_code == 401:
                        raise NetworkError("Authentication failed. Check your API token.")
                    elif e.response.status_code == 403:
                        raise NetworkError("Access forbidden. Check your API permissions.")
                    elif e.response.status_code >= 500:
                        retry_count += 1
                        if retry_count > max_retries:
                            raise NetworkError(f"Server error after {max_retries} retries: {e}")
                        
                        wait_time = base_delay * (2 ** (retry_count - 1))
                        self.log_output(f"🔄 Server error (retry {retry_count}/{max_retries}), waiting {wait_time}s: {e}")
                        time.sleep(wait_time)
                    else:
                        raise NetworkError(f"HTTP error fetching existing recipes: {e}")

                except RequestException as e:
                    raise NetworkError(f"Request failed while fetching existing recipes: {e}")

            try:
                data = response.json()
                results = data.get('results', [])

                if not results:
                    break

                # Check each recipe for source_url
                for recipe in results:
                    if not isinstance(recipe, dict):
                        continue
                    source_url = recipe.get('source_url')
                    if source_url and isinstance(source_url, str):
                        existing_urls.add(source_url.strip())

                if not data.get('next'):
                    break

                page += 1
                time.sleep(1)  # Small delay between pagination requests

            except (ValueError, KeyError) as e:
                raise RecipeProcessingError(f"Invalid response format from Tandoor: {e}")

        self.log_output(f"📊 Found {len(existing_urls)} existing recipes with source URLs")
        return existing_urls

    def scrape_recipe(self, url):
        """Step 1: Scrape recipe data from URL"""
        scrape_url = f"{self.tandoor_url}/api/recipe-from-source/"
        headers = {'Content-Type': 'application/json'}
        data = {'url': url}

        try:
            response = self.session.post(scrape_url, json=data, headers=headers, timeout=30)

            if response.status_code == 429:
                return False, "rate_limited", None, None

            if response.status_code != 200:
                return False, f"http_{response.status_code}", None, None

            result = response.json()

            # Check for errors
            if result.get('error'):
                error_msg = result.get('msg', 'Unknown error')
                # Categorize different types of errors
                if 'no usable data' in error_msg.lower() or 'no recipe' in error_msg.lower():
                    return False, f"non_recipe: {error_msg}", None, None
                elif 'connection' in error_msg.lower() or 'refused' in error_msg.lower():
                    return False, f"connection: {error_msg}", None, None
                else:
                    return False, error_msg, None, None

            # Check for duplicates
            duplicates = result.get('duplicates', [])
            if duplicates:
                return False, f"duplicate: {duplicates[0]['name']}", None, None

            # Get recipe data
            recipe_data = result.get('recipe')
            if not recipe_data:
                return False, "no_recipe_data", None, None

            images = result.get('images', [])
            return True, recipe_data, images, None

        except Exception as e:
            return False, f"exception: {e}", None, None

    def create_recipe(self, recipe_data, images=None):
        """Step 2: Create recipe in database"""
        # Select first image if available
        if images:
            recipe_data['image_url'] = images[0]

        create_url = f"{self.tandoor_url}/api/recipe/"
        headers = {'Content-Type': 'application/json'}

        try:
            response = self.session.post(create_url, json=recipe_data, headers=headers, timeout=30)

            if response.status_code == 429:
                return False, "rate_limited", None

            if response.status_code == 201:  # Created successfully
                created_recipe = response.json()
                recipe_id = created_recipe.get('id')
                return True, created_recipe, recipe_id
            else:
                return False, f"http_{response.status_code}: {response.text[:100]}", None

        except Exception as e:
            return False, f"exception: {e}", None

    def import_single_recipe(self, url, index, total):
        """Complete import process for a single recipe"""
        self.log_output(f"\n📝 [{index}/{total}] Importing: {url}")

        # Step 1: Scrape
        scrape_success, scrape_result, images, _ = self.scrape_recipe(url)
        if not scrape_success:
            if "rate_limited" in scrape_result:
                self.stats['rate_limited'] += 1
                self.log_output("⏳ Rate limited during scrape")
                return "rate_limited"
            elif "duplicate" in scrape_result:
                self.stats['duplicates'] += 1
                self.log_output(f"⚠️ Duplicate: {scrape_result}")
                return "duplicate"
            elif "non_recipe:" in scrape_result:
                self.stats['non_recipe_urls'] += 1
                self.failed_urls['non_recipe_urls'].append((url, scrape_result))
                self.log_output(f"🚫 Non-recipe URL: {scrape_result}")
                return "non_recipe"
            elif "connection:" in scrape_result:
                self.stats['connection_errors'] += 1
                self.failed_urls['connection_errors'].append((url, scrape_result))
                self.log_output(f"🌐 Connection error: {scrape_result}")
                return "connection_error"
            else:
                self.stats['failed_scrape'] += 1
                self.failed_urls['failed_scrape'].append((url, scrape_result))
                self.log_output(f"❌ Scrape failed: {scrape_result}")
                return "failed_scrape"

        recipe_data = scrape_result
        recipe_name = recipe_data.get('name', 'Unknown') if isinstance(recipe_data, dict) else 'Unknown'

        # Step 2: Create
        create_success, create_result, recipe_id = self.create_recipe(recipe_data, images)
        if not create_success:
            if "rate_limited" in create_result:
                self.stats['rate_limited'] += 1
                self.log_output("⏳ Rate limited during creation")
                return "rate_limited"
            else:
                self.stats['failed_create'] += 1
                self.failed_urls['failed_create'].append((url, create_result))
                self.log_output(f"❌ Create failed: {create_result}")
                return "failed_create"

        self.stats['successful'] += 1
        self.log_output(f"✅ SUCCESS: '{recipe_name}' (ID: {recipe_id})")
        return "success"

    def wait_for_rate_limit_reset(self):
        """Wait for rate limit to reset"""
        self.log_output("⏳ Waiting for rate limit to reset...")

        # Try a simple GET request to check rate limit status
        for attempt in range(12):  # Try for up to 10 minutes
            try:
                response = self.session.get(f"{self.tandoor_url}/api/recipe/?page_size=1", timeout=10)

                if response.status_code != 429:
                    self.log_output("✅ Rate limit appears to be reset!")
                    return True

                self.log_output(f"⏳ Still rate limited... waiting 30s (attempt {attempt + 1}/12)")
                time.sleep(30)

            except Exception as e:
                self.log_output(f"⚠️ Error checking rate limit: {e}")
                time.sleep(30)

        self.log_output("❌ Rate limit did not reset after 10 minutes")
        return False

    def log_output(self, message: str) -> None:
        """Output message to both console and file if specified."""
        print(message)
        if self.output_file:
            self.output_file.write(f"{message}\n")
            self.output_file.flush()
    
    def import_from_file(self, filename: str, start_from: int = 0, max_imports: Optional[int] = None) -> None:
        """Import recipes from URL list file"""
        self.log_output(f"📂 Loading URLs from {filename}")

        try:
            file_path = Path(filename)
            
            if not file_path.exists():
                raise FileOperationError(f"URL file not found: {filename}")
            
            if not file_path.is_file():
                raise FileOperationError(f"Path is not a file: {filename}")
            
            if file_path.stat().st_size > 100 * 1024 * 1024:  # 100MB limit
                raise FileOperationError(f"File too large (>100MB): {filename}")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                urls = []
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if line and not line.startswith('#'):  # Skip empty lines and comments
                        if len(line) > 2048:  # Reasonable URL length limit
                            self.log_output(f"⚠️ Skipping overly long URL on line {line_num}")
                            continue
                        urls.append(line)
                        
        except UnicodeDecodeError as e:
            raise FileOperationError(f"File encoding error: {e}. Ensure file is UTF-8 encoded.")
        except PermissionError as e:
            raise FileOperationError(f"Permission denied reading file: {e}")
        except OSError as e:
            raise FileOperationError(f"OS error reading file: {e}")
        except Exception as e:
            raise FileOperationError(f"Unexpected error reading file: {e}") from e

        # Filter and validate URLs
        valid_urls = []
        for url in urls:
            if self.is_valid_recipe_url(url):
                valid_urls.append(url)
            else:
                self.stats['invalid_urls'] += 1
                self.failed_urls['invalid_urls'].append(url)
                self.log_output(f"🚫 Skipping invalid/non-recipe URL: {url[:60]}{'...' if len(url) > 60 else ''}")

        self.log_output(f"📊 Found {len(valid_urls)} valid URLs ({self.stats['invalid_urls']} invalid)")

        # Apply start/limit filters
        if start_from > 0:
            valid_urls = valid_urls[start_from:]
            self.log_output(f"📊 Starting from index {start_from}, {len(valid_urls)} URLs remaining")

        if max_imports:
            valid_urls = valid_urls[:max_imports]
            self.log_output(f"📊 Limited to {max_imports} imports")

        self.stats['total'] = len(valid_urls)

        if not valid_urls:
            self.log_output("❌ No valid URLs to import!")
            return

        # Get existing recipes to skip duplicates
        existing_urls = self.get_existing_source_urls()
        new_urls = [url for url in valid_urls if url not in existing_urls]
        pre_existing_count = len(valid_urls) - len(new_urls)

        if pre_existing_count > 0:
            self.log_output(f"⚠️ Skipping {pre_existing_count} URLs that already exist in database")
            self.stats['duplicates'] += pre_existing_count

        if not new_urls:
            self.log_output("✅ All URLs already imported!")
            return

        self.log_output(f"🚀 Starting import of {len(new_urls)} new recipes...")
        estimated_minutes = (len(new_urls) * self.delay) / 60
        self.log_output(f"⏱️ Estimated time: {estimated_minutes:.1f} minutes")

        # Import each URL
        for i, url in enumerate(new_urls, 1):
            result = self.import_single_recipe(url, i, len(new_urls))

            # Handle rate limiting
            if result == "rate_limited":
                self.log_output("⏳ Hit rate limit, waiting for reset...")
                if self.wait_for_rate_limit_reset():
                    self.log_output("🔄 Retrying current recipe...")
                    result = self.import_single_recipe(url, i, len(new_urls))
                else:
                    self.log_output("❌ Could not recover from rate limit, stopping import")
                    break

            # Print progress
            success_rate = (self.stats['successful'] / i) * 100 if i > 0 else 0
            self.log_output(f"📊 Progress: {i}/{len(new_urls)} ({i/len(new_urls)*100:.1f}%) | Success rate: {success_rate:.1f}%")
            self.log_output(f"📈 Stats: ✅{self.stats['successful']} ⚠️{self.stats['duplicates']} "
                  f"🚫{self.stats['non_recipe_urls']} 🌐{self.stats['connection_errors']} "
                  f"❌{self.stats['failed_scrape']+self.stats['failed_create']} ⏳{self.stats['rate_limited']}")

            # Wait between requests (except on last one)
            if i < len(new_urls):
                self.log_output(f"⏱️ Waiting {self.delay}s before next import...")
                time.sleep(self.delay)

        # Final report
        self.log_output("\n🎉 BULK IMPORT COMPLETE!")
        self.log_output("📊 Final Stats:")
        self.log_output(f"   Total processed: {self.stats['total']}")
        self.log_output(f"   ✅ Successful imports: {self.stats['successful']}")
        self.log_output(f"   ⚠️ Duplicates skipped: {self.stats['duplicates']}")
        self.log_output(f"   ❌ Failed scraping: {self.stats['failed_scrape']}")
        self.log_output(f"   ❌ Failed creation: {self.stats['failed_create']}")
        self.log_output(f"   🚫 Non-recipe URLs: {self.stats['non_recipe_urls']}")
        self.log_output(f"   🌐 Connection errors: {self.stats['connection_errors']}")
        self.log_output(f"   ⏳ Rate limited: {self.stats['rate_limited']}")
        self.log_output(f"   🚫 Invalid URLs: {self.stats['invalid_urls']}")

        success_rate = (self.stats['successful'] / max(1, len(new_urls))) * 100
        self.log_output(f"   📈 Success rate: {success_rate:.1f}%")

        # Display failed URLs if any
        total_failures = (self.stats['failed_scrape'] + self.stats['failed_create'] +
                         self.stats['non_recipe_urls'] + self.stats['connection_errors'] +
                         self.stats['invalid_urls'])

        if total_failures > 0:
            self.log_output(f"\n❌ FAILED URLS ({total_failures} total):")

            if self.failed_urls['invalid_urls']:
                self.log_output(f"\n🚫 Invalid URLs ({len(self.failed_urls['invalid_urls'])}):")
                for url in self.failed_urls['invalid_urls']:
                    self.log_output(f"   {url}")

            if self.failed_urls['non_recipe_urls']:
                self.log_output(f"\n🚫 Non-recipe URLs ({len(self.failed_urls['non_recipe_urls'])}):")
                for url, reason in self.failed_urls['non_recipe_urls']:
                    self.log_output(f"   {url} - {reason}")

            if self.failed_urls['connection_errors']:
                self.log_output(f"\n🌐 Connection errors ({len(self.failed_urls['connection_errors'])}):")
                for url, reason in self.failed_urls['connection_errors']:
                    self.log_output(f"   {url} - {reason}")

            if self.failed_urls['failed_scrape']:
                self.log_output(f"\n❌ Failed scraping ({len(self.failed_urls['failed_scrape'])}):")
                for url, reason in self.failed_urls['failed_scrape']:
                    self.log_output(f"   {url} - {reason}")

            if self.failed_urls['failed_create']:
                self.log_output(f"\n❌ Failed creation ({len(self.failed_urls['failed_create'])}):")
                for url, reason in self.failed_urls['failed_create']:
                    self.log_output(f"   {url} - {reason}")
        else:
            self.log_output("\n✅ No failed URLs!")


def main() -> None:
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Bulk import recipes from URLs into Tandoor Recipes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  %(prog)s url-list.txt
  %(prog)s url-list.txt --start-from 100
  %(prog)s url-list.txt --max-imports 50 --output results.log
  %(prog)s url-list.txt --start-from 100 --max-imports 25 -o import.log"""
    )
    
    parser.add_argument("url_file", help="Path to text file containing recipe URLs")
    parser.add_argument("--start-from", type=int, default=0, 
                       help="Line number to start from (default: 0)")
    parser.add_argument("--max-imports", type=int, 
                       help="Maximum number of recipes to import")
    parser.add_argument("-o", "--output", type=str,
                       help="Output results to file")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    logger = logging.getLogger(__name__)

    try:
        # Load configuration with comprehensive error handling
        tandoor_url, api_token, delay = load_config()
        logger.info("Configuration loaded successfully")
        
    except ConfigurationError as e:
        print(f"❌ Configuration Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected configuration error: {e}")
        logger.exception("Unexpected error during configuration loading")
        sys.exit(1)
    
    # Setup output file if specified
    output_file = None
    if args.output:
        try:
            output_path = Path(args.output)
            # Ensure parent directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_file = open(output_path, 'w', encoding='utf-8')
            logger.info(f"Output file opened: {output_path}")
        except (IOError, OSError) as e:
            print(f"❌ Error opening output file {args.output}: {e}")
            sys.exit(1)
    
    try:
        importer = FinalBulkImporter(tandoor_url, api_token, delay, output_file)
        
        importer.log_output("🔧 TANDOOR BULK RECIPE IMPORTER")
        importer.log_output("Using corrected two-step import process")
        importer.log_output("=" * 60)
        
        importer.import_from_file(args.url_file, args.start_from, args.max_imports)
        logger.info("Import process completed successfully")
        
    except FileOperationError as e:
        print(f"❌ File Error: {e}")
        sys.exit(1)
    except NetworkError as e:
        print(f"❌ Network Error: {e}")
        sys.exit(1)
    except RecipeProcessingError as e:
        print(f"❌ Recipe Processing Error: {e}")
        sys.exit(1)
    except TandoorImporterError as e:
        print(f"❌ Import Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n🛑 Import interrupted by user")
        logger.info("Import interrupted by user (Ctrl+C)")
        sys.exit(130)  # Standard exit code for SIGINT
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        logger.exception("Unexpected error during import process")
        sys.exit(1)
        
    finally:
        if output_file:
            try:
                output_file.close()
                logger.info("Output file closed successfully")
            except Exception as e:
                print(f"⚠️ Warning: Error closing output file: {e}")


if __name__ == "__main__":
    main()