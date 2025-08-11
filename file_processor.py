"""
File processing functionality for Tandoor Recipe Importer.

Handles reading URL files and managing the import workflow.
"""

from typing import Optional
from pathlib import Path

from exceptions import FileOperationError
from importer import BulkImporter


def process_url_file(
    importer: BulkImporter, 
    filename: str, 
    start_from: int = 0, 
    max_imports: Optional[int] = None
) -> None:
    """Import recipes from URL list file with comprehensive error handling."""
    importer.log_output(f"📂 Loading URLs from {filename}")

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
                        importer.log_output(f"⚠️ Skipping overly long URL on line {line_num}")
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
        if importer.is_valid_recipe_url(url):
            valid_urls.append(url)
        else:
            importer.stats['invalid_urls'] += 1
            importer.failed_urls['invalid_urls'].append(url)
            importer.log_output(f"🚫 Skipping invalid/non-recipe URL: {url[:60]}{'...' if len(url) > 60 else ''}")

    importer.log_output(f"📊 Found {len(valid_urls)} valid URLs ({importer.stats['invalid_urls']} invalid)")

    # Apply start/limit filters
    if start_from > 0:
        valid_urls = valid_urls[start_from:]
        importer.log_output(f"📊 Starting from index {start_from}, {len(valid_urls)} URLs remaining")

    if max_imports:
        valid_urls = valid_urls[:max_imports]
        importer.log_output(f"📊 Limited to {max_imports} imports")

    importer.stats['total'] = len(valid_urls)

    if not valid_urls:
        importer.log_output("❌ No valid URLs to import!")
        return

    # Get existing recipes to skip duplicates
    existing_urls = importer.get_existing_source_urls()
    new_urls = [url for url in valid_urls if url not in existing_urls]
    pre_existing_count = len(valid_urls) - len(new_urls)

    if pre_existing_count > 0:
        importer.log_output(f"⚠️ Skipping {pre_existing_count} URLs that already exist in database")
        importer.stats['duplicates'] += pre_existing_count

    if not new_urls:
        importer.log_output("✅ All URLs already imported!")
        return

    importer.log_output(f"🚀 Starting import of {len(new_urls)} new recipes...")
    estimated_minutes = (len(new_urls) * importer.delay) / 60
    importer.log_output(f"⏱️ Estimated time: {estimated_minutes:.1f} minutes")

    # Import each URL
    for i, url in enumerate(new_urls, 1):
        result = importer.import_single_recipe(url, i, len(new_urls))

        # Handle rate limiting
        if result == "rate_limited":
            importer.log_output("⏳ Hit rate limit, waiting for reset...")
            if importer.wait_for_rate_limit_reset():
                importer.log_output("🔄 Retrying current recipe...")
                result = importer.import_single_recipe(url, i, len(new_urls))
            else:
                importer.log_output("❌ Could not recover from rate limit, stopping import")
                break

        # Print progress
        success_rate = (importer.stats['successful'] / i) * 100 if i > 0 else 0
        progress_pct = i/len(new_urls)*100
        importer.log_output(
            f"📊 Progress: {i}/{len(new_urls)} ({progress_pct:.1f}%) | "
            f"Success rate: {success_rate:.1f}%"
        )
        enhanced_str = f"🎯{importer.stats.get('duplicates_enhanced', 0)} " if importer.stats.get('duplicates_enhanced', 0) > 0 else ""
        importer.log_output(f"📈 Stats: ✅{importer.stats['successful']} ⚠️{importer.stats['duplicates']} " + enhanced_str +
              f"🚫{importer.stats['non_recipe_urls']} 🌐{importer.stats['connection_errors']} "
              f"❌{importer.stats['failed_scrape']+importer.stats['failed_create']} ⏳{importer.stats['rate_limited']}")

        # Wait between requests (except on last one)
        if i < len(new_urls):
            importer.log_output(f"⏱️ Waiting {importer.delay}s before next import...")
            import time
            time.sleep(importer.delay)

    # Final report
    _print_final_report(importer, new_urls)


def _print_final_report(importer: BulkImporter, new_urls: list) -> None:
    """Print comprehensive final report of import results."""
    importer.log_output("\n🎉 BULK IMPORT COMPLETE!")
    importer.log_output("📊 Final Stats:")
    importer.log_output(f"   Total processed: {importer.stats['total']}")
    importer.log_output(f"   ✅ Successful imports: {importer.stats['successful']}")
    importer.log_output(f"   ⚠️ Duplicates skipped: {importer.stats['duplicates']}")
    if importer.stats.get('duplicates_enhanced', 0) > 0:
        importer.log_output(f"   🎯 Duplicates enhanced with images: {importer.stats['duplicates_enhanced']}")
    importer.log_output(f"   ❌ Failed scraping: {importer.stats['failed_scrape']}")
    importer.log_output(f"   ❌ Failed creation: {importer.stats['failed_create']}")
    importer.log_output(f"   🚫 Non-recipe URLs: {importer.stats['non_recipe_urls']}")
    importer.log_output(f"   🌐 Connection errors: {importer.stats['connection_errors']}")
    importer.log_output(f"   ⏳ Rate limited: {importer.stats['rate_limited']}")
    importer.log_output(f"   🚫 Invalid URLs: {importer.stats['invalid_urls']}")

    success_rate = (importer.stats['successful'] / max(1, len(new_urls))) * 100
    importer.log_output(f"   📈 Success rate: {success_rate:.1f}%")

    # Display failed URLs if any
    failure_types = ['failed_scrape', 'failed_create', 'non_recipe_urls', 
                    'connection_errors', 'invalid_urls']
    total_failures = sum(importer.stats[failure_type] for failure_type in failure_types)

    if total_failures > 0:
        importer.log_output(f"\n❌ FAILED URLS ({total_failures} total):")

        if importer.failed_urls['invalid_urls']:
            importer.log_output(f"\n🚫 Invalid URLs ({len(importer.failed_urls['invalid_urls'])}):")
            for url in importer.failed_urls['invalid_urls']:
                importer.log_output(f"   {url}")

        if importer.failed_urls['non_recipe_urls']:
            importer.log_output(f"\n🚫 Non-recipe URLs ({len(importer.failed_urls['non_recipe_urls'])}):")
            for url, reason in importer.failed_urls['non_recipe_urls']:
                importer.log_output(f"   {url} - {reason}")

        if importer.failed_urls['connection_errors']:
            importer.log_output(f"\n🌐 Connection errors ({len(importer.failed_urls['connection_errors'])}):")
            for url, reason in importer.failed_urls['connection_errors']:
                importer.log_output(f"   {url} - {reason}")

        if importer.failed_urls['failed_scrape']:
            importer.log_output(f"\n❌ Failed scraping ({len(importer.failed_urls['failed_scrape'])}):")
            for url, reason in importer.failed_urls['failed_scrape']:
                importer.log_output(f"   {url} - {reason}")

        if importer.failed_urls['failed_create']:
            importer.log_output(f"\n❌ Failed creation ({len(importer.failed_urls['failed_create'])}):")
            for url, reason in importer.failed_urls['failed_create']:
                importer.log_output(f"   {url} - {reason}")
    else:
        importer.log_output("\n✅ No failed URLs!")