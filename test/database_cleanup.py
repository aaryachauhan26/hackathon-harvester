"""
Database Cleanup Utility
Run this script to manually check and clean the database
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

def analyze_database():
    """Analyze the database for duplicates and expired entries"""
    print("\n" + "="*60)
    print("DATABASE ANALYSIS REPORT")
    print("="*60)
    
    # Total count
    total = hackathons_collection.count_documents({})
    print(f"\n📊 Total Hackathons: {total}")
    
    # Check for expired hackathons
    current_date = datetime.now().strftime('%Y-%m-%d')
    expired = hackathons_collection.count_documents({
        "end_date": {"$lt": current_date, "$ne": "TBD"}
    })
    print(f"❌ Expired Hackathons: {expired}")
    
    # Check for TBD dates
    tbd_count = hackathons_collection.count_documents({"end_date": "TBD"})
    print(f"❓ Hackathons with TBD dates: {tbd_count}")
    
    # Check for old TBD hackathons (>60 days old)
    old_tbd = hackathons_collection.count_documents({
        "end_date": "TBD",
        "scraped_at": {"$lt": datetime.now() - timedelta(days=60)}
    })
    print(f"🕐 Old TBD Hackathons (>60 days): {old_tbd}")
    
    # Check for duplicates by title
    all_hackathons = list(hackathons_collection.find())
    titles = {}
    duplicates = []
    
    for h in all_hackathons:
        title = h.get('title', '').lower().strip()
        if title in titles:
            duplicates.append(title)
        else:
            titles[title] = h
    
    unique_duplicates = len(set(duplicates))
    print(f"🔄 Duplicate Titles: {len(duplicates)} duplicates, {unique_duplicates} unique")
    
    # Check for URL duplicates
    urls = {}
    url_duplicates = []
    
    for h in all_hackathons:
        url = h.get('website_url', '').strip()
        if url and url not in ['', 'N/A', 'TBD']:
            if url in urls:
                url_duplicates.append(url)
            else:
                urls[url] = h
    
    unique_url_dups = len(set(url_duplicates))
    print(f"🔗 Duplicate URLs: {len(url_duplicates)} duplicates, {unique_url_dups} unique")
    
    # Status breakdown
    print("\n📈 Status Breakdown:")
    for status in ['open', 'upcoming', 'closed']:
        count = hackathons_collection.count_documents({"status": status})
        print(f"   • {status.title()}: {count}")
    
    # Platform breakdown
    print("\n🌐 Platform Breakdown:")
    platforms = hackathons_collection.distinct("platform")
    for platform in platforms:
        count = hackathons_collection.count_documents({"platform": platform})
        print(f"   • {platform.title() if platform else 'Unknown'}: {count}")
    
    # List some duplicate titles
    if unique_duplicates > 0:
        print("\n🔍 Sample Duplicate Titles:")
        shown = 0
        for title in set(duplicates)[:5]:
            matches = hackathons_collection.find({"title": {"$regex": title, "$options": "i"}})
            count = hackathons_collection.count_documents({"title": {"$regex": title, "$options": "i"}})
            print(f"   • '{title}' - {count} copies")
            shown += 1
            if shown >= 5:
                break
    
    # List some expired hackathons
    if expired > 0:
        print("\n⏰ Sample Expired Hackathons:")
        expired_list = list(hackathons_collection.find({
            "end_date": {"$lt": current_date, "$ne": "TBD"}
        }).limit(5))
        for h in expired_list:
            print(f"   • {h.get('title', 'Unknown')} - Deadline: {h.get('end_date', 'N/A')}")
    
    print("\n" + "="*60)
    return {
        'total': total,
        'expired': expired,
        'old_tbd': old_tbd,
        'title_duplicates': len(duplicates),
        'url_duplicates': len(url_duplicates)
    }

def clean_database():
    """Clean the database by removing expired and duplicate entries"""
    print("\n🧹 STARTING DATABASE CLEANUP...")
    print("="*60)
    
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
    
    # Step 3: Remove exact title duplicates
    print("\n3️⃣  Removing title duplicates...")
    all_hackathons = list(hackathons_collection.find())
    seen_titles = {}
    title_duplicates = []
    
    for hackathon in all_hackathons:
        title_lower = hackathon.get('title', '').lower().strip()
        if title_lower in seen_titles:
            # Keep the newer one
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
    
    if title_duplicates:
        title_result = hackathons_collection.delete_many({"_id": {"$in": title_duplicates}})
        print(f"   ✓ Removed {title_result.deleted_count} title duplicates")
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
    
    if url_duplicates:
        url_result = hackathons_collection.delete_many({"_id": {"$in": url_duplicates}})
        print(f"   ✓ Removed {url_result.deleted_count} URL duplicates")
    else:
        print(f"   ✓ No URL duplicates found")
    
    total_removed = (expired_result.deleted_count + old_tbd_result.deleted_count + 
                    len(title_duplicates) + len(url_duplicates))
    
    print("\n" + "="*60)
    print(f"✅ CLEANUP COMPLETE! Removed {total_removed} total entries")
    print("="*60 + "\n")
    
    return total_removed

def main():
    """Main function"""
    print("\n🎯 HACKATHON DATABASE UTILITY")
    print("="*60)
    
    while True:
        print("\nOptions:")
        print("1. Analyze Database")
        print("2. Clean Database")
        print("3. Both (Analyze then Clean)")
        print("4. Exit")
        
        choice = input("\nEnter your choice (1-4): ").strip()
        
        if choice == '1':
            analyze_database()
        elif choice == '2':
            stats = analyze_database()
            if stats['total'] == 0:
                print("\n⚠️  Database is empty. Nothing to clean.")
                continue
            
            confirm = input("\n⚠️  Are you sure you want to clean the database? (yes/no): ").strip().lower()
            if confirm == 'yes':
                clean_database()
                print("\n📊 Post-Cleanup Analysis:")
                analyze_database()
            else:
                print("❌ Cleanup cancelled.")
        elif choice == '3':
            analyze_database()
            stats = analyze_database()
            
            if stats['total'] == 0:
                print("\n⚠️  Database is empty. Nothing to clean.")
                continue
            
            confirm = input("\n⚠️  Proceed with cleanup? (yes/no): ").strip().lower()
            if confirm == 'yes':
                clean_database()
                print("\n📊 Post-Cleanup Analysis:")
                analyze_database()
            else:
                print("❌ Cleanup cancelled.")
        elif choice == '4':
            print("\n👋 Goodbye!\n")
            break
        else:
            print("❌ Invalid choice. Please enter 1-4.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted by user. Goodbye!\n")
    except Exception as e:
        print(f"\n❌ Error: {str(e)}\n")
