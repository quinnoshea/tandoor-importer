#!/usr/bin/env python3
"""
Tandoor Recipe Bulk Importer

A tool for bulk importing recipes into Tandoor Recipes.
Features error handling, retry logic, and logging capabilities.

Written with respect to established engineering principles and standards.
Strives to follow PEP-8, PEP-20 (Zen of Python), and PEP-484 (Type Hints).
"""

import sys
import argparse
import logging
from pathlib import Path

from config import load_config
from importer import BulkImporter
from file_processor import process_url_file
from exceptions import (
    ConfigurationError,
    NetworkError, 
    RecipeProcessingError,
    FileOperationError,
    TandoorImporterError
)


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
        importer = BulkImporter(tandoor_url, api_token, delay, output_file)
        
        importer.log_output("🔧 TANDOOR BULK RECIPE IMPORTER")
        importer.log_output("Using corrected two-step import process")
        importer.log_output("=" * 60)
        
        process_url_file(importer, args.url_file, args.start_from, args.max_imports)
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