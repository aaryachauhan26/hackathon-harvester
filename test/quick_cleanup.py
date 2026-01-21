"""
Quick Database Cleanup - Automatically cleans without prompts
"""
from pymongo import MongoClient
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MongoDB Configuration
MONGODB_URI = os.getenv('MONGODB_URI')
MONGODB_DB = os.getenv('MONGODB_DB', 'hackathon_db')

client = MongoClient(MONGODB_URI)
db = client[MONGODB_DB]
hackathons_collection = db.hackathons

print("\n" + "="*60)
print("🧹 AUTOMATIC DATABASE CLEANUP")
print("="*60)

# Get initial count
total_before = hackathons_collection.count_documents({})
print(f"\n📊 Initial Count: {total_before} hackathons")

if total_before == 0:
    print("\n⚠️  Database is empty. Nothing to clean.")
    exit(0)

current_date = datetime.now().strftime('%Y-%m-%d')

# Step 1: Remove expired hackathons
print("\n1️⃣  Removing expired hackathons...")
expired_result = hackathons_collection.delete_many({
    "end_date": {"$lt": current_date, "$ne": "TBD"}
})
print(f"   ✓ Removed {expired_result.deleted_count} expired hackathons")

# Step 2: Remove old TBD hackathons
print("\n2️⃣  Removing old TBD hackathons (>60 days)...")
old_tbd_result = hackathons_collection.delete_many({
    "end_date": "TBD",
    "scraped_at": {"$lt": datetime.now() - timedelta(days=60)}
})
print(f"   ✓ Removed {old_tbd_result.deleted_count} old TBD hackathons")

# Step 3: Remove title duplicates
print("\n3️⃣  Removing title duplicates...")
all_hackathons = list(hackathons_collection.find())
seen_titles = {}
title_duplicates = []

for hackathon in all_hackathons:
    title_lower = hackathon.get('title', '').lower().strip()
    if title_lower in seen_titles:
        existing = seen_titles[title_lower]
        existing_date = existing.get('scraped_at', datetime.min)
        current_date_obj = hackathon.get('scraped_at', datetime.min)
        
        if current_date_obj < existing_date:
            title_duplicates.append(hackathon['_id'])
        else:
            title_duplicates.append(existing['_id'])
            seen_titles[title_lower] = hackathon
    else:
        seen_titles[title_lower] = hackathon

title_removed = 0
if title_duplicates:
    title_result = hackathons_collection.delete_many({"_id": {"$in": title_duplicates}})
    title_removed = title_result.deleted_count
    print(f"   ✓ Removed {title_removed} title duplicates")
else:
    print(f"   ✓ No title duplicates found")

# Step 4: Remove URL duplicates
print("\n4️⃣  Removing URL duplicates...")
all_hackathons = list(hackathons_collection.find())
seen_urls = {}
url_duplicates = []

for hackathon in all_hackathons:
    url = hackathon.get('website_url', '').strip()
    if url and url not in ['', 'N/A', 'TBD']:
        if url in seen_urls:
            existing = seen_urls[url]
            existing_date = existing.get('scraped_at', datetime.min)
            current_date_obj = hackathon.get('scraped_at', datetime.min)
            
            if current_date_obj < existing_date:
                url_duplicates.append(hackathon['_id'])
            else:
                url_duplicates.append(existing['_id'])
                seen_urls[url] = hackathon
        else:
            seen_urls[url] = hackathon

url_removed = 0
if url_duplicates:
    url_result = hackathons_collection.delete_many({"_id": {"$in": url_duplicates}})
    url_removed = url_result.deleted_count
    print(f"   ✓ Removed {url_removed} URL duplicates")
else:
    print(f"   ✓ No URL duplicates found")

# Final count
total_after = hackathons_collection.count_documents({})
total_removed = total_before - total_after

print("\n" + "="*60)
print(f"✅ CLEANUP COMPLETE!")
print(f"   Before: {total_before} hackathons")
print(f"   After: {total_after} hackathons")
print(f"   Removed: {total_removed} total entries")
print("="*60)

# Show breakdown by status
print("\n📈 Current Status Breakdown:")
for status in ['open', 'upcoming']:
    count = hackathons_collection.count_documents({"status": status})
    print(f"   • {status.title()}: {count}")

# Show breakdown by platform
print("\n🌐 Current Platform Breakdown:")
platforms = hackathons_collection.distinct("platform")
for platform in platforms[:5]:  # Show top 5
    count = hackathons_collection.count_documents({"platform": platform})
    print(f"   • {platform.title() if platform else 'Unknown'}: {count}")

print("\n✨ Database is now clean and optimized!\n")
