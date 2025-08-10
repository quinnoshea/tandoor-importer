#!/usr/bin/env python3
"""
Final corrected bulk import script using the proper two-step process
"""

import requests
import json
import time
import sys
import configparser
import os
from datetime import datetime

def load_config():
    """Load configuration from config.conf file"""
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), 'config.conf')
    
    if not os.path.exists(config_path):
        print(f"❌ Configuration file not found: {config_path}")
        print("Please copy and configure the config.conf file with your Tandoor settings.")
        sys.exit(1)
    
    config.read(config_path)
    
    try:
        tandoor_url = config.get('tandoor', 'url').rstrip('/')
        api_token = config.get('tandoor', 'api_token')
        delay = config.getint('import', 'delay_between_requests')
        
        if not tandoor_url or tandoor_url == 'https://your-tandoor-instance.com':
            print("❌ Please configure your Tandoor URL in config.conf")
            sys.exit(1)
        
        if not api_token or api_token == 'your_api_token_here':
            print("❌ Please configure your API token in config.conf")
            sys.exit(1)
        
        return tandoor_url, api_token, delay
        
    except (configparser.NoSectionError, configparser.NoOptionError) as e:
        print(f"❌ Configuration error: {e}")
        print("Please check your config.conf file format.")
        sys.exit(1)

class FinalBulkImporter:
    def __init__(self, tandoor_url, api_token, delay):
        self.tandoor_url = tandoor_url
        self.api_token = api_token
        self.delay = delay
        
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

    def get_existing_source_urls(self):
        """Get all existing recipe source URLs for duplicate detection"""
        existing_urls = set()
        page = 1
        
        print("🔍 Fetching existing recipes for duplicate detection...")
        
        while True:
            try:
                response = self.session.get(f"{self.tandoor_url}/api/recipe/?page={page}&page_size=100", timeout=15)
                
                if response.status_code == 429:
                    print("⏳ Rate limited while fetching existing recipes, waiting...")
                    time.sleep(60)
                    continue
                    
                if response.status_code != 200:
                    print(f"❌ Error fetching existing recipes: {response.status_code}")
                    break
                    
                data = response.json()
                results = data.get('results', [])
                
                if not results:
                    break
                
                # Check each recipe for source_url
                for recipe in results:
                    source_url = recipe.get('source_url')
                    if source_url:
                        existing_urls.add(source_url.strip())
                
                if not data.get('next'):
                    break
                    
                page += 1
                time.sleep(1)  # Small delay between pagination requests
                
            except Exception as e:
                print(f"❌ Error getting existing recipes: {e}")
                break
        
        print(f"📊 Found {len(existing_urls)} existing recipes with source URLs")
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
        print(f"\n📝 [{index}/{total}] Importing: {url}")
        
        # Step 1: Scrape
        scrape_success, scrape_result, images, _ = self.scrape_recipe(url)
        if not scrape_success:
            if "rate_limited" in scrape_result:
                self.stats['rate_limited'] += 1
                print(f"⏳ Rate limited during scrape")
                return "rate_limited"
            elif "duplicate" in scrape_result:
                self.stats['duplicates'] += 1
                print(f"⚠️ Duplicate: {scrape_result}")
                return "duplicate"
            elif "non_recipe:" in scrape_result:
                self.stats['non_recipe_urls'] += 1
                self.failed_urls['non_recipe_urls'].append((url, scrape_result))
                print(f"🚫 Non-recipe URL: {scrape_result}")
                return "non_recipe"
            elif "connection:" in scrape_result:
                self.stats['connection_errors'] += 1
                self.failed_urls['connection_errors'].append((url, scrape_result))
                print(f"🌐 Connection error: {scrape_result}")
                return "connection_error"
            else:
                self.stats['failed_scrape'] += 1
                self.failed_urls['failed_scrape'].append((url, scrape_result))
                print(f"❌ Scrape failed: {scrape_result}")
                return "failed_scrape"
        
        recipe_data = scrape_result
        recipe_name = recipe_data.get('name', 'Unknown')
        
        # Step 2: Create
        create_success, create_result, recipe_id = self.create_recipe(recipe_data, images)
        if not create_success:
            if "rate_limited" in create_result:
                self.stats['rate_limited'] += 1
                print(f"⏳ Rate limited during creation")
                return "rate_limited"
            else:
                self.stats['failed_create'] += 1
                self.failed_urls['failed_create'].append((url, create_result))
                print(f"❌ Create failed: {create_result}")
                return "failed_create"
        
        self.stats['successful'] += 1
        print(f"✅ SUCCESS: '{recipe_name}' (ID: {recipe_id})")
        return "success"
    
    def wait_for_rate_limit_reset(self):
        """Wait for rate limit to reset"""
        print("⏳ Waiting for rate limit to reset...")
        
        # Try a simple GET request to check rate limit status
        for attempt in range(12):  # Try for up to 10 minutes
            try:
                response = self.session.get(f"{self.tandoor_url}/api/recipe/?page_size=1", timeout=10)
                
                if response.status_code != 429:
                    print("✅ Rate limit appears to be reset!")
                    return True
                    
                print(f"⏳ Still rate limited... waiting 30s (attempt {attempt + 1}/12)")
                time.sleep(30)
                
            except Exception as e:
                print(f"⚠️ Error checking rate limit: {e}")
                time.sleep(30)
        
        print("❌ Rate limit did not reset after 10 minutes")
        return False
    
    def import_from_file(self, filename, start_from=0, max_imports=None):
        """Import recipes from URL list file"""
        print(f"📂 Loading URLs from {filename}")
        
        try:
            with open(filename, 'r') as f:
                urls = [line.strip() for line in f if line.strip()]
        except Exception as e:
            print(f"❌ Error reading file: {e}")
            return
        
        # Filter and validate URLs
        valid_urls = []
        for url in urls:
            if self.is_valid_recipe_url(url):
                valid_urls.append(url)
            else:
                self.stats['invalid_urls'] += 1
                self.failed_urls['invalid_urls'].append(url)
                print(f"🚫 Skipping invalid/non-recipe URL: {url[:60]}{'...' if len(url) > 60 else ''}")
        
        print(f"📊 Found {len(valid_urls)} valid URLs ({self.stats['invalid_urls']} invalid)")
        
        # Apply start/limit filters
        if start_from > 0:
            valid_urls = valid_urls[start_from:]
            print(f"📊 Starting from index {start_from}, {len(valid_urls)} URLs remaining")
        
        if max_imports:
            valid_urls = valid_urls[:max_imports]
            print(f"📊 Limited to {max_imports} imports")
        
        self.stats['total'] = len(valid_urls)
        
        if not valid_urls:
            print("❌ No valid URLs to import!")
            return
        
        # Get existing recipes to skip duplicates
        existing_urls = self.get_existing_source_urls()
        new_urls = [url for url in valid_urls if url not in existing_urls]
        pre_existing_count = len(valid_urls) - len(new_urls)
        
        if pre_existing_count > 0:
            print(f"⚠️ Skipping {pre_existing_count} URLs that already exist in database")
            self.stats['duplicates'] += pre_existing_count
        
        if not new_urls:
            print("✅ All URLs already imported!")
            return
        
        print(f"🚀 Starting import of {len(new_urls)} new recipes...")
        estimated_minutes = (len(new_urls) * self.delay) / 60
        print(f"⏱️ Estimated time: {estimated_minutes:.1f} minutes")
        
        # Import each URL
        for i, url in enumerate(new_urls, 1):
            result = self.import_single_recipe(url, i, len(new_urls))
            
            # Handle rate limiting
            if result == "rate_limited":
                print("⏳ Hit rate limit, waiting for reset...")
                if self.wait_for_rate_limit_reset():
                    print("🔄 Retrying current recipe...")
                    result = self.import_single_recipe(url, i, len(new_urls))
                else:
                    print("❌ Could not recover from rate limit, stopping import")
                    break
            
            # Print progress
            success_rate = (self.stats['successful'] / i) * 100 if i > 0 else 0
            print(f"📊 Progress: {i}/{len(new_urls)} ({i/len(new_urls)*100:.1f}%) | Success rate: {success_rate:.1f}%")
            print(f"📈 Stats: ✅{self.stats['successful']} ⚠️{self.stats['duplicates']} "
                  f"🚫{self.stats['non_recipe_urls']} 🌐{self.stats['connection_errors']} "
                  f"❌{self.stats['failed_scrape']+self.stats['failed_create']} ⏳{self.stats['rate_limited']}")
            
            # Wait between requests (except on last one)
            if i < len(new_urls):
                print(f"⏱️ Waiting {self.delay}s before next import...")
                time.sleep(self.delay)
        
        # Final report
        print(f"\n🎉 BULK IMPORT COMPLETE!")
        print(f"📊 Final Stats:")
        print(f"   Total processed: {self.stats['total']}")
        print(f"   ✅ Successful imports: {self.stats['successful']}")
        print(f"   ⚠️ Duplicates skipped: {self.stats['duplicates']}")
        print(f"   ❌ Failed scraping: {self.stats['failed_scrape']}")
        print(f"   ❌ Failed creation: {self.stats['failed_create']}")
        print(f"   🚫 Non-recipe URLs: {self.stats['non_recipe_urls']}")
        print(f"   🌐 Connection errors: {self.stats['connection_errors']}")
        print(f"   ⏳ Rate limited: {self.stats['rate_limited']}")
        print(f"   🚫 Invalid URLs: {self.stats['invalid_urls']}")
        
        success_rate = (self.stats['successful'] / max(1, len(new_urls))) * 100
        print(f"   📈 Success rate: {success_rate:.1f}%")
        
        # Display failed URLs if any
        total_failures = (self.stats['failed_scrape'] + self.stats['failed_create'] + 
                         self.stats['non_recipe_urls'] + self.stats['connection_errors'] +
                         self.stats['invalid_urls'])
        
        if total_failures > 0:
            print(f"\n❌ FAILED URLS ({total_failures} total):")
            
            if self.failed_urls['invalid_urls']:
                print(f"\n🚫 Invalid URLs ({len(self.failed_urls['invalid_urls'])}):")
                for url in self.failed_urls['invalid_urls']:
                    print(f"   {url}")
            
            if self.failed_urls['non_recipe_urls']:
                print(f"\n🚫 Non-recipe URLs ({len(self.failed_urls['non_recipe_urls'])}):")
                for url, reason in self.failed_urls['non_recipe_urls']:
                    print(f"   {url} - {reason}")
            
            if self.failed_urls['connection_errors']:
                print(f"\n🌐 Connection errors ({len(self.failed_urls['connection_errors'])}):")
                for url, reason in self.failed_urls['connection_errors']:
                    print(f"   {url} - {reason}")
            
            if self.failed_urls['failed_scrape']:
                print(f"\n❌ Failed scraping ({len(self.failed_urls['failed_scrape'])}):")
                for url, reason in self.failed_urls['failed_scrape']:
                    print(f"   {url} - {reason}")
            
            if self.failed_urls['failed_create']:
                print(f"\n❌ Failed creation ({len(self.failed_urls['failed_create'])}):")
                for url, reason in self.failed_urls['failed_create']:
                    print(f"   {url} - {reason}")
        else:
            print("\n✅ No failed URLs!")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 tandoor-importer.py <url_file> [start_index] [max_imports]")
        print("Example: python3 tandoor-importer.py url-list.txt 0 10")
        sys.exit(1)
    
    filename = sys.argv[1]
    start_from = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    max_imports = int(sys.argv[3]) if len(sys.argv) > 3 else None
    
    # Load configuration
    tandoor_url, api_token, delay = load_config()
    
    importer = FinalBulkImporter(tandoor_url, api_token, delay)
    
    print("🔧 TANDOOR BULK RECIPE IMPORTER")
    print("Using corrected two-step import process")
    print("=" * 60)
    
    importer.import_from_file(filename, start_from, max_imports)


if __name__ == "__main__":
    main()