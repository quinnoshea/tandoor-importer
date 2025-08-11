"""
Core import functionality for Tandoor Recipe Importer.

Contains the main importer class with recipe processing logic.
"""

import requests
import time
from typing import Optional, TextIO, Tuple, Union
from pathlib import Path

from exceptions import NetworkError, RecipeProcessingError, FileOperationError
from requests.exceptions import (
    RequestException, 
    Timeout, 
    ConnectionError, 
    HTTPError
)


class BulkImporter:
    """
    Main importer class for bulk importing recipes into Tandoor.
    
    Handles recipe scraping, creation, and comprehensive error handling.
    """
    
    def __init__(
        self, 
        tandoor_url: str, 
        api_token: str, 
        delay: int, 
        output_file: Optional[TextIO] = None
    ):
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
            'duplicates_enhanced': 0,
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

    def log_output(self, message: str) -> None:
        """Output message to both console and file if specified."""
        print(message)
        if self.output_file:
            self.output_file.write(f"{message}\n")
            self.output_file.flush()

    def is_valid_recipe_url(self, url) -> bool:
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
            response = None
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
                        self.log_output(
                            f"🔄 Server error (retry {retry_count}/{max_retries}), "
                            f"waiting {wait_time}s: {e}"
                        )
                        time.sleep(wait_time)
                    else:
                        raise NetworkError(f"HTTP error fetching existing recipes: {e}")

                except RequestException as e:
                    raise NetworkError(f"Request failed while fetching existing recipes: {e}")

            # Ensure we have a valid response before proceeding
            if response is None:
                raise NetworkError("Failed to get valid response after retries")

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

    def scrape_recipe(self, url: str) -> Tuple[bool, Union[str, dict], Optional[list], None]:
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

            # Check for duplicates and potentially enhance them with images
            duplicates = result.get('duplicates', [])
            if duplicates:
                duplicate_recipe = duplicates[0]
                duplicate_name = duplicate_recipe.get('name', 'Unknown')
                duplicate_id = duplicate_recipe.get('id')
                
                # Check if we can enhance the duplicate with an image
                enhancement_result = self._try_enhance_duplicate_recipe(duplicate_recipe, result, url)
                if enhancement_result:
                    return False, f"duplicate_enhanced: {duplicate_name}", None, None
                else:
                    return False, f"duplicate: {duplicate_name}", None, None

            # Get recipe data
            recipe_data = result.get('recipe')
            if not recipe_data:
                return False, "no_recipe_data", None, None

            # Validate and fix critical fields that cause HTTP 400 errors
            recipe_data = self._validate_and_fix_recipe_data(recipe_data, url)
            if not recipe_data:
                return False, "invalid_recipe_data", None, None

            images = result.get('images', [])
            return True, recipe_data, images, None

        except Exception as e:
            return False, f"exception: {e}", None, None

    def _validate_and_fix_recipe_data(self, recipe_data: dict, source_url: str) -> dict:
        """Validate and fix recipe data to prevent HTTP 400 errors"""
        try:
            # Fix empty/blank name field - critical for recipe creation
            name = recipe_data.get('name', '').strip()
            if not name:
                # Generate name from URL as fallback
                from urllib.parse import urlparse
                parsed_url = urlparse(source_url)
                path_parts = [p for p in parsed_url.path.split('/') if p and p != 'recipes']
                if path_parts:
                    # Use last meaningful part of URL path
                    name = path_parts[-1].replace('-', ' ').replace('_', ' ').title()
                    # Remove common suffixes
                    name = name.replace('.Html', '').replace('.Php', '').replace(' Recipe', '')
                else:
                    # Ultimate fallback
                    name = f"Recipe from {parsed_url.netloc}"
                
                recipe_data['name'] = name
                self.log_output(f"   ⚠️ Empty recipe name detected, using fallback: '{name}'")

            # Ensure name is not too long (Tandoor has field limits)
            if len(recipe_data['name']) > 128:
                recipe_data['name'] = recipe_data['name'][:125] + "..."
                self.log_output(f"   ⚠️ Recipe name truncated to 128 characters")

            # Fix empty description - not critical but good UX
            if not recipe_data.get('description', '').strip():
                recipe_data['description'] = f"Recipe imported from {source_url}"
                self.log_output(f"   ℹ️ Empty description, using URL fallback")

            # Ensure minimum required steps structure
            if not recipe_data.get('steps') or len(recipe_data.get('steps', [])) == 0:
                recipe_data['steps'] = [{'instruction': 'See original recipe for instructions', 'ingredients': []}]
                self.log_output(f"   ⚠️ No recipe steps found, added placeholder step")

            # Ensure servings is valid
            if not isinstance(recipe_data.get('servings'), int) or recipe_data.get('servings') <= 0:
                recipe_data['servings'] = 1
                self.log_output(f"   ℹ️ Invalid servings value, defaulting to 1")

            return recipe_data

        except Exception as e:
            self.log_output(f"   ❌ Error validating recipe data: {e}")
            return None

    def _try_enhance_duplicate_recipe(self, duplicate_recipe: dict, scrape_result: dict, source_url: str) -> bool:
        """Try to enhance existing duplicate recipe with image if it lacks one"""
        try:
            duplicate_id = duplicate_recipe.get('id')
            duplicate_name = duplicate_recipe.get('name', 'Unknown')
            
            # Check if duplicate has an image
            has_image = duplicate_recipe.get('image') and duplicate_recipe.get('image').strip()
            
            if has_image:
                self.log_output(f"   ℹ️ Duplicate recipe '{duplicate_name}' already has image, skipping enhancement")
                return False
            
            # Get potential image sources from scrape result
            images = scrape_result.get('images', [])
            recipe_image_url = scrape_result.get('recipe', {}).get('image_url')
            
            # Prioritize recipe image_url over images array
            primary_image_url = recipe_image_url if recipe_image_url and recipe_image_url.strip() else None
            if not primary_image_url and images:
                primary_image_url = images[0]
            
            if not primary_image_url:
                self.log_output(f"   ℹ️ No images available to enhance duplicate recipe '{duplicate_name}'")
                return False
            
            # Attempt to add image to existing recipe
            self.log_output(f"   🎯 Enhancing duplicate recipe '{duplicate_name}' (ID: {duplicate_id}) with image")
            self.log_output(f"   📸 Adding image: {primary_image_url[:60]}{'...' if len(primary_image_url) > 60 else ''}")
            
            success = self._upload_recipe_image(duplicate_id, primary_image_url)
            if success:
                self.log_output(f"   ✅ Successfully enhanced duplicate recipe with image!")
                self.stats['duplicates_enhanced'] = self.stats.get('duplicates_enhanced', 0) + 1
                return True
            else:
                self.log_output(f"   ⚠️ Failed to enhance duplicate recipe with image")
                return False
                
        except Exception as e:
            self.log_output(f"   ❌ Error enhancing duplicate recipe: {e}")
            return False

    def create_recipe(
        self, 
        recipe_data: dict, 
        images: Optional[list] = None
    ) -> Tuple[bool, Union[dict, str], Optional[int]]:
        """Step 2: Create recipe in database"""
        create_url = f"{self.tandoor_url}/api/recipe/"
        headers = {'Content-Type': 'application/json'}

        try:
            # The recipe_data should already contain image_url from Tandoor's scraper
            # Create recipe with the image_url already included
            response = self.session.post(create_url, json=recipe_data, headers=headers, timeout=30)

            if response.status_code == 429:
                return False, "rate_limited", None

            if response.status_code == 201:  # Created successfully
                created_recipe = response.json()
                recipe_id = created_recipe.get('id')
                
                # Upload primary image - prioritize image_url from recipe data, then images array
                primary_image_url = recipe_data.get('image_url')
                if not primary_image_url and images:
                    primary_image_url = images[0]
                
                if primary_image_url and recipe_id:
                    self.log_output(f"   📸 Uploading primary image: {primary_image_url[:60]}{'...' if len(primary_image_url) > 60 else ''}")
                    image_success = self._upload_recipe_image(recipe_id, primary_image_url)
                    if not image_success:
                        self.log_output(f"   ⚠️ Primary image upload failed")
                else:
                    self.log_output(f"   ℹ️ No image URL found for upload")
                
                return True, created_recipe, recipe_id
            else:
                return False, f"http_{response.status_code}: {response.text[:100]}", None

        except Exception as e:
            return False, f"exception: {e}", None

    def _upload_recipe_image(self, recipe_id: int, image_url: str) -> bool:
        """Upload image to recipe using Tandoor's image endpoint"""
        try:
            image_endpoint = f"{self.tandoor_url}/api/recipe/{recipe_id}/image/"
            
            # Use multipart/form-data format - Tandoor's image endpoint expects this
            # The format (None, url) tells requests to send it as a form field, not a file
            files_data = {'image_url': (None, image_url)}
            
            response = self.session.put(
                image_endpoint, 
                files=files_data,  # Use files parameter for multipart data
                timeout=30
            )
            
            if response.status_code == 200:
                self.log_output(f"   📸 Image uploaded successfully from {image_url[:60]}{'...' if len(image_url) > 60 else ''}")
                return True
            else:
                self.log_output(f"   ⚠️ Image upload failed ({response.status_code}): {image_url[:60]}{'...' if len(image_url) > 60 else ''}")
                return False
                
        except Exception as e:
            self.log_output(f"   ⚠️ Image upload error: {e}")
            return False

    def import_single_recipe(self, url: str, index: int, total: int) -> str:
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
                if "duplicate_enhanced" in scrape_result:
                    # Duplicate was enhanced with image - count as both duplicate and enhancement
                    self.stats['duplicates'] += 1
                    self.log_output(f"✅ Enhanced duplicate: {scrape_result}")
                    return "duplicate_enhanced"
                else:
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

        # At this point, scrape_success is True, so scrape_result must be a dict
        if not isinstance(scrape_result, dict):
            # This should never happen given our logic, but satisfies type checker
            self.stats['failed_scrape'] += 1
            self.log_output("❌ Unexpected non-dict result from successful scrape")
            return "failed_scrape"
            
        recipe_data = scrape_result
        recipe_name = recipe_data.get('name', 'Unknown')

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

    def wait_for_rate_limit_reset(self) -> bool:
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