"""
Test Gemini API Response - Diagnostic Tool
Run this to see what the API is actually returning
"""
import asyncio
import json
from llama_index.llms.google_genai import GoogleGenAI
from google.genai import types
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

print("\n" + "="*60)
print("GEMINI API DIAGNOSTIC TEST")
print("="*60)

# Initialize with same config as app.py
google_search_tool = types.Tool(
    google_search=types.GoogleSearch()
)

llm_with_search = GoogleGenAI(
    model="gemini-2.5-flash",
    generation_config=types.GenerateContentConfig(tools=[google_search_tool]),
    max_retries=5,
    timeout=120
)

async def test_api():
    print("\n1️⃣  Testing API connection...")
    
    try:
        search_prompt = """
        Search for the top 3 most POPULAR and current hackathons from platforms like Unstop, Devfolio, HackerEarth.
        
        Please extract and return ONLY a valid JSON array with the following format:
        [
            {
                "title": "Exact Hackathon Name",
                "end_date": "YYYY-MM-DD",
                "website_url": "https://example.com",
                "platform": "unstop",
                "status": "open",
                "description": "Brief description",
                "prize_pool": "$10,000"
            }
        ]
        
        Return ONLY the JSON array, no additional text.
        """
        
        print("   Sending request to Gemini API...")
        response = await llm_with_search.acomplete(search_prompt)
        
        print("\n2️⃣  Response received!")
        print(f"   Response type: {type(response)}")
        print(f"   Response has text attribute: {hasattr(response, 'text')}")
        
        raw_text = response.text
        print(f"\n3️⃣  Raw Response (first 500 characters):")
        print("   " + "="*56)
        print(f"   {raw_text[:500]}")
        print("   " + "="*56)
        
        print(f"\n4️⃣  Response Details:")
        print(f"   Total length: {len(raw_text)} characters")
        print(f"   Starts with: '{raw_text[:20]}'")
        print(f"   Ends with: '{raw_text[-20:]}'")
        print(f"   Contains '[': {('[' in raw_text)}")
        print(f"   Contains ']': {(']' in raw_text)}")
        print(f"   Contains '```': {('```' in raw_text)}")
        
        # Try to parse it
        print(f"\n5️⃣  Attempting to parse JSON...")
        
        clean_data = raw_text.strip()
        
        # Remove markdown
        if clean_data.startswith('```json'):
            clean_data = clean_data.replace('```json', '').replace('```', '').strip()
            print("   ✓ Removed ```json markers")
        elif clean_data.startswith('```'):
            clean_data = clean_data.replace('```', '').strip()
            print("   ✓ Removed ``` markers")
        
        # Find JSON array
        if not clean_data.startswith('['):
            start_idx = clean_data.find('[')
            end_idx = clean_data.rfind(']')
            if start_idx != -1 and end_idx != -1:
                clean_data = clean_data[start_idx:end_idx+1]
                print(f"   ✓ Extracted JSON from position {start_idx} to {end_idx}")
        
        try:
            hackathons = json.loads(clean_data)
            print(f"\n✅ SUCCESS! Parsed {len(hackathons)} hackathons")
            
            print(f"\n6️⃣  Sample Hackathon Data:")
            if hackathons and len(hackathons) > 0:
                sample = hackathons[0]
                print(f"   Title: {sample.get('title', 'N/A')}")
                print(f"   Platform: {sample.get('platform', 'N/A')}")
                print(f"   Status: {sample.get('status', 'N/A')}")
                print(f"   End Date: {sample.get('end_date', 'N/A')}")
                print(f"   Prize Pool: {sample.get('prize_pool', 'N/A')}")
                print(f"   URL: {sample.get('website_url', 'N/A')}")
            
        except json.JSONDecodeError as je:
            print(f"\n❌ JSON PARSE FAILED!")
            print(f"   Error: {str(je)}")
            print(f"   Position: Line {je.lineno}, Column {je.colno}")
            print(f"\n   Cleaned data (first 300 chars):")
            print(f"   {clean_data[:300]}")
            
            # Try to identify the issue
            print(f"\n   Diagnosis:")
            if not clean_data:
                print("   → Response is empty")
            elif not clean_data.startswith('['):
                print(f"   → Doesn't start with '[', starts with: {clean_data[:50]}")
            elif not clean_data.endswith(']'):
                print(f"   → Doesn't end with ']', ends with: {clean_data[-50:]}")
            else:
                print("   → Malformed JSON structure")
                
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        print(f"   Error type: {type(e).__name__}")
        import traceback
        print(f"\n   Full traceback:")
        print(traceback.format_exc())

print("\n🔍 Starting test...\n")
asyncio.run(test_api())

print("\n" + "="*60)
print("TEST COMPLETE")
print("="*60)
print("\nℹ️  If you see JSON parse errors, the issue is with:")
print("   • API returning non-JSON text")
print("   • Markdown formatting not being cleaned")
print("   • API rate limits or errors")
print("\n💡 Solutions:")
print("   • Wait a few minutes and try again")
print("   • Check your API key and quota")
print("   • Review the raw response above for issues")
print("\n")
