#!/usr/bin/env python3
"""
Utility to find existing duplicate recipes in Tandoor database
"""

import requests
from typing import Dict, List
from collections import defaultdict
from config import load_config

def find_existing_duplicates():
    """Find recipes that are likely duplicates based on name similarity"""
    
    try:
        tandoor_url, api_token, _ = load_config()
        print(f"✅ Connected to: {tandoor_url}")
    except Exception as e:
        print(f"❌ Config error: {e}")
        return
    
    session = requests.Session()
    session.headers.update({'Authorization': f'Bearer {api_token}'})
    
    print("🔍 Fetching all recipes to analyze duplicates...")
    
    all_recipes = []
    page = 1
    
    try:
        while True:
            response = session.get(
                f"{tandoor_url}/api/recipe/?page={page}&page_size=100",
                timeout=30
            )
            
            if response.status_code != 200:
                print(f"❌ Failed to fetch recipes: {response.status_code}")
                return
                
            data = response.json()
            results = data.get('results', [])
            
            if not results:
                break
                
            all_recipes.extend(results)
            print(f"   Fetched {len(all_recipes)} recipes so far...")
            
            if not data.get('next'):
                break
                
            page += 1
            
    except Exception as e:
        print(f"❌ Error fetching recipes: {e}")
        return
    
    print(f"📊 Total recipes in database: {len(all_recipes)}")
    
    # Group recipes by normalized name
    name_groups: Dict[str, List] = defaultdict(list)
    
    for recipe in all_recipes:
        name = recipe.get('name', '').strip()
        if name:
            # Normalize name for comparison
            normalized_name = name.lower().strip()
            # Remove common variations
            normalized_name = normalized_name.replace('recipe', '').strip()
            normalized_name = normalized_name.replace('  ', ' ')
            
            name_groups[normalized_name].append(recipe)
    
    # Find potential duplicates
    duplicates_found = 0
    print(f"\n🔍 Analyzing for duplicate recipe names...")
    
    for normalized_name, recipes in name_groups.items():
        if len(recipes) > 1:
            duplicates_found += 1
            print(f"\n🚨 Potential duplicates for: '{recipes[0]['name']}'")
            for recipe in recipes:
                print(f"   ID {recipe['id']}: '{recipe['name']}'")
            
            # If we have many duplicates of the same recipe, suggest cleanup
            if len(recipes) > 2:
                print(f"   ⚠️ {len(recipes)} copies found - manual cleanup recommended")
    
    print(f"\n📊 Summary:")
    print(f"   Total recipe groups: {len(name_groups)}")
    print(f"   Duplicate groups found: {duplicates_found}")
    print(f"   Unique recipes: {len(name_groups) - duplicates_found}")

if __name__ == "__main__":
    find_existing_duplicates()