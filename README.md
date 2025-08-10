[![License](https://img.shields.io/badge/license-MIT-9B59B6.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.9%2B-3498DB)
[![Codacy Badge](https://app.codacy.com/project/badge/Grade/0a51a6fa4d2f44d5aaa178054b2d30b9)](https://app.codacy.com/gh/quinnoshea/tandoor-importer/dashboard?utm_source=gh&utm_medium=referral&utm_content=&utm_campaign=Badge_grade)
[![Codacy Badge](https://app.codacy.com/project/badge/Coverage/0a51a6fa4d2f44d5aaa178054b2d30b9)](https://app.codacy.com/gh/quinnoshea/tandoor-importer/dashboard?utm_source=gh&utm_medium=referral&utm_content=&utm_campaign=Badge_coverage)
![Status](https://img.shields.io/badge/status-active-success)
[![CI](https://github.com/quinnoshea/tandoor-importer/actions/workflows/ci-workflow.yml/badge.svg)](https://github.com/quinnoshea/tandoor-importer/actions/workflows/ci-workflow.yml)

# Tandoor Recipe Bulk Importer

A Python script to bulk import recipes from a list of URLs into your [Tandoor Recipes](https://github.com/TandoorRecipes/recipes) instance.

## Features

- Bulk import recipes from text file containing URLs
- Duplicate detection to avoid importing existing recipes
- Rate limiting handling with automatic retry
- URL validation to skip non-recipe links
- Detailed progress reporting and statistics
- Configurable delay between imports
- Two-step import process (scrape then create) for reliability

## Requirements

- Python 3.6+
- `requests` library
- A running Tandoor Recipes instance
- Valid Tandoor API token

## Installation

1. Clone or download this repository
2. Install required dependencies:

   **Option 1: Using your system package manager (recommended)**
   ```bash
   # Ubuntu/Debian
   sudo apt install python3-requests
   
   # Fedora/RHEL
   sudo dnf install python3-requests
   
   # Arch Linux
   sudo pacman -S python-requests
   ```

   **Option 2: Using pip in a virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install requests
   ```

   **Option 3: Using pip globally (not recommended on modern systems)**
   ```bash
   pip install requests
   ```

## Configuration

1. Copy the example configuration file and update it with your settings:
   ```bash
   cp config.conf.example config.conf
   ```

2. Edit `config.conf` with your settings:
   ```ini
   [tandoor]
   # Your Tandoor server URL (without trailing slash)
   url = https://your-tandoor-instance.com
   
   # Your Tandoor API token (found in Tandoor settings)
   api_token = your_api_token_here
   
   [import]
   # Delay between recipe imports (in seconds)
   delay_between_requests = 30
   ```

3. To get your API token:

   - Log into your Tandoor instance
   - Go to Settings → API
   - Generate or copy your existing API token

## Usage

### Prepare your URL list

Create a text file (e.g., `url-list.txt`) with one recipe URL per line:

```
https://www.allrecipes.com/recipe/123/example-recipe/
https://www.foodnetwork.com/recipes/another-recipe
https://www.kingarthurbaking.com/recipes/bread-recipe
```

### Run the importer

Basic usage:
```bash
python3 tandoor-importer.py url-list.txt
```

Advanced usage with options:
```bash
# Start from a specific line (0-indexed)
python3 tandoor-importer.py url-list.txt 100

# Limit number of imports
python3 tandoor-importer.py url-list.txt 0 50

# Start from line 100 and import max 25 recipes
python3 tandoor-importer.py url-list.txt 100 25
```

### Arguments

- `url_file` - Path to text file containing recipe URLs (required)
- `start_index` - Line number to start from (optional, default: 0)
- `max_imports` - Maximum number of recipes to import (optional, default: all)

## Features & Behavior

### URL Validation

The script automatically filters out:

- Image files (.jpg, .png, etc.)
- Video files (.mp4, .mov, etc.)
- Document files (.pdf, .doc, etc.)
- Social media direct links
- Other non-recipe content

### Duplicate Detection

- Fetches existing recipes from your Tandoor instance
- Compares source URLs to avoid importing duplicates
- Shows count of skipped duplicates in progress report

### Rate Limiting

- Respects Tandoor's rate limits
- Automatically waits and retries when rate limited
- Configurable delay between requests (default: 30 seconds)

### Error Handling

The script handles various error scenarios:

- Connection timeouts
- Invalid URLs
- Non-recipe pages
- Server errors
- Rate limiting

### Progress Reporting

Real-time statistics showing:

- Import progress (current/total)
- Success rate percentage
- Breakdown of results (successful, duplicates, errors, etc.)

## Output

The script provides detailed console output including:

- Configuration validation
- URL filtering results
- Real-time import progress
- Detailed error messages
- Final statistics summary

## Troubleshooting

### Common Issues

1. **"Configuration file not found"**
   - Ensure `config.conf` exists in the same directory as the script
   - Check file permissions

2. **"Please configure your API token"**
   - Update `config.conf` with your actual Tandoor API token
   - Verify the token is valid in your Tandoor instance

3. **Rate limiting errors**
   - Increase `delay_between_requests` in config.conf
   - The script handles rate limiting automatically, but longer delays reduce likelihood

4. **Connection errors**
   - Verify your Tandoor URL is correct and accessible
   - Check network connectivity
   - Ensure Tandoor instance is running

### Getting Help

- Check Tandoor's API documentation
- Verify your Tandoor instance is up to date
- Test API token with a simple curl request:
  ```bash
  curl -H "Authorization: Bearer YOUR_TOKEN" https://your-tandoor-instance.com/api/recipe/?page_size=1
  ```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.