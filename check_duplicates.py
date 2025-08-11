#!/usr/bin/env python3
"""
Script to check for actual duplicates in the Tandoor database
"""

import requests
from config import load_config

def check_for_duplicates():
    """Check if there are actual duplicate entries in Tandoor"""
    
    try:
        tandoor_url, api_token, _ = load_config()
        print(f"✅ Connected to: {tandoor_url}")
    except Exception as e:
        print(f"❌ Config error: {e}")
        return
    
    session = requests.Session()
    session.headers.update({'Authorization': f'Bearer {api_token}'})
    
    # Search for the specific recipe that might have duplicates
    search_terms = ["Sweet Habanero", "chilipeppermadness"]
    
    for term in search_terms:
        print(f"\n🔍 Searching for recipes containing: '{term}'")
        
        try:
            # Search recipes by name
            response = session.get(
                f"{tandoor_url}/api/recipe/",
                params={'search': term, 'page_size': 50},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                
                print(f"📊 Found {len(results)} recipes matching '{term}':")
                
                for recipe in results:
                    recipe_id = recipe.get('id')
                    recipe_name = recipe.get('name', 'Unknown')
                    
                    # Get detailed recipe to check source_url
                    try:
                        detail_response = session.get(
                            f"{tandoor_url}/api/recipe/{recipe_id}/",
                            timeout=10
                        )
                        if detail_response.status_code == 200:
                            detail = detail_response.json()
                            source_url = detail.get('source_url', 'No source URL')
                            print(f"   ID {recipe_id}: '{recipe_name}'")
                            print(f"   Source: {source_url}")
                            print()
                    except Exception as e:
                        print(f"   ID {recipe_id}: '{recipe_name}' (could not get details: {e})")
                        
            else:
                print(f"❌ Search failed with status {response.status_code}")
                
        except Exception as e:
            print(f"❌ Error searching for '{term}': {e}")

if __name__ == "__main__":
    check_for_duplicates()