"""
Test script to verify the hackathon scraper is working correctly
"""
import sys
import os
import asyncio
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import scraper, logger

async def test_scraper():
    """Test the hackathon scraper functionality"""
    print("=" * 70)
    print("TESTING HACKATHON SCRAPER")
    print("=" * 70)
    print(f"Current Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    try:
        # Test 1: Search for hackathons
        print("Test 1: Searching for hackathons...")
        print("-" * 70)
        raw_data = await scraper.search_hackathons(limit=5)
        
        print(f"✓ Raw data received: {len(raw_data)} characters")
        print(f"Preview (first 500 chars):\n{raw_data[:500]}")
        print()
        
        # Test 2: Parse the data
        print("Test 2: Parsing hackathon data...")
        print("-" * 70)
        hackathons = scraper.parse_hackathon_data(raw_data, limit=5)
        
        print(f"✓ Parsed {len(hackathons)} hackathons")
        print()
        
        # Test 3: Display results
        if hackathons:
            print("Test 3: Hackathon Details")
            print("-" * 70)
            for idx, h in enumerate(hackathons, 1):
                print(f"\n{idx}. {h.get('title', 'NO TITLE')}")
                print(f"   Platform: {h.get('platform', 'N/A')}")
                print(f"   Status: {h.get('status', 'N/A')}")
                print(f"   End Date: {h.get('end_date', 'N/A')}")
                print(f"   Prize: {h.get('prize_pool', 'N/A')}")
                print(f"   URL: {h.get('website_url', 'N/A')[:80]}...")
                print(f"   Description: {h.get('description', 'N/A')[:100]}...")
            
            print("\n" + "=" * 70)
            print(f"✓ SUCCESS: Found {len(hackathons)} valid hackathons")
            print("=" * 70)
            
            # Save to file for inspection
            output_file = "test/scraper_test_output.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                # Convert datetime objects to strings for JSON serialization
                hackathons_json = []
                for h in hackathons:
                    h_copy = h.copy()
                    if 'scraped_at' in h_copy:
                        h_copy['scraped_at'] = h_copy['scraped_at'].isoformat()
                    hackathons_json.append(h_copy)
                json.dump(hackathons_json, f, indent=2, ensure_ascii=False)
            
            print(f"✓ Results saved to: {output_file}")
            
        else:
            print("✗ FAILED: No hackathons parsed")
            print("Check the logs above for errors")
            
    except Exception as e:
        print(f"\n✗ ERROR: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return False
    
    return len(hackathons) > 0

if __name__ == "__main__":
    # Run the async test
    result = asyncio.run(test_scraper())
    
    if result:
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print("\n✗ Tests failed!")
        sys.exit(1)
