from flask import Flask, render_template, request, jsonify, redirect, url_for
from pymongo import MongoClient
from bson import ObjectId
import json
import os
from datetime import datetime, timedelta, timezone
import asyncio
from threading import Thread
import logging
import schedule
import time
from apscheduler.schedulers.background import BackgroundScheduler

# Import Gemini and search components
from llama_index.llms.google_genai import GoogleGenAI
from google.genai import types
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MongoDB Configuration
MONGODB_URI = os.getenv('MONGODB_URI')
MONGODB_DB = os.getenv('MONGODB_DB', 'hackathon_db')

client = MongoClient(MONGODB_URI)
db = client[MONGODB_DB]
hackathons_collection = db.hackathons

# Initialize Gemini with search capabilities and retry logic
google_search_tool = types.Tool(
    google_search=types.GoogleSearch()
)

llm_with_search = GoogleGenAI(
    model="gemini-2.5-flash",
    generation_config=types.GenerateContentConfig(tools=[google_search_tool]),
    max_retries=5,  # Retry up to 5 times
    timeout=120  # Increase timeout to 120 seconds
)

class HackathonScraper:
    def __init__(self):
        self.llm = llm_with_search
        
    async def search_hackathons(self, query=None, limit=10):
        """Search for popular hackathons using Gemini with Google Search"""
        # Generate dynamic query based on current date
        current_date = datetime.now()
        current_year = current_date.year
        next_year = current_year + 1
        current_month = current_date.strftime("%B %Y")
        
        if query is None:
            query = f"latest hackathons {current_year} {next_year} October November December unstop devfolio hackerearth mlh devpost"
        
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                search_prompt = f"""
                TODAY'S DATE: {current_date.strftime('%Y-%m-%d')} ({current_month})
                
                Search for the top {limit} most POPULAR and CURRENTLY ACTIVE/UPCOMING hackathons happening from NOW ({current_month}) onwards.
                Focus on major platforms: Unstop.com, Devfolio.co, HackerEarth.com, MLH (Major League Hacking), Devpost.com
                
                SEARCH FOR: {query}
                
                MANDATORY REQUIREMENTS:
                1. Find hackathons with registration deadlines AFTER {current_date.strftime('%Y-%m-%d')}
                2. Include hackathons happening in {current_year} and {next_year}
                3. Get COMPLETE and VERIFIED registration URLs (must start with https://)
                4. Focus on popular hackathons with good prize pools
                5. Include both ongoing (registration open) and upcoming hackathons
                
                Return ONLY a valid JSON array with this EXACT format (MAXIMUM {limit} hackathons):
                [
                    {{
                        "title": "Full Official Hackathon Name",
                        "end_date": "YYYY-MM-DD",
                        "website_url": "https://complete-working-url.com/hackathon-page",
                        "platform": "unstop/devfolio/hackerearth/mlh/devpost/other",
                        "status": "open",
                        "description": "Comprehensive description including themes, tracks, and key details (2-3 sentences)",
                        "prize_pool": "$10,000 or ₹50,000 or TBD"
                    }}
                ]
                
                CRITICAL VALIDATION:
                - ALL end_date values MUST be AFTER {current_date.strftime('%Y-%m-%d')}
                - ALL website_url values MUST be complete URLs with https://
                - Focus on VERIFIED hackathons from official platforms
                - Include diverse hackathons (AI/ML, Web3, general tech, etc.)
                - NO expired or past hackathons
                
                Return ONLY the JSON array, absolutely no markdown, no explanations, no extra text.
                """
                
                response = await self.llm.acomplete(search_prompt)
                logger.info(f"Successfully fetched hackathons on attempt {attempt + 1}")
                logger.debug(f"Response preview: {response.text[:300]}")
                return response.text
                
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/{max_attempts} failed: {str(e)}")
                if attempt < max_attempts - 1:
                    wait_time = (attempt + 1) * 10  # Exponential backoff: 10s, 20s, 30s
                    logger.info(f"Waiting {wait_time} seconds before retry...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All attempts failed for search_hackathons: {str(e)}")
                    return "[]"
    
    def parse_hackathon_data(self, raw_data, limit=10):
        """Parse and clean the hackathon data"""
        try:
            # Try to extract JSON from the response
            if isinstance(raw_data, str):
                # Remove any markdown formatting
                clean_data = raw_data.strip()
                
                # Log the raw response for debugging
                logger.info(f"Parsing response data (length: {len(clean_data)} chars)")
                logger.debug(f"Raw API response (first 300 chars): {clean_data[:300]}")
                
                if not clean_data or clean_data == "[]":
                    logger.warning("Empty response from API")
                    return []
                
                # Method 1: Remove markdown code blocks
                if clean_data.startswith('```json'):
                    clean_data = clean_data.replace('```json', '').replace('```', '').strip()
                    logger.debug("Removed JSON markdown formatting")
                elif clean_data.startswith('```'):
                    clean_data = clean_data.replace('```', '').strip()
                    logger.debug("Removed markdown formatting")
                
                # Method 2: Try to find JSON array in the response
                if not clean_data.startswith('['):
                    # Look for JSON array start
                    start_idx = clean_data.find('[')
                    end_idx = clean_data.rfind(']')
                    if start_idx != -1 and end_idx != -1:
                        clean_data = clean_data[start_idx:end_idx+1]
                        logger.info("Extracted JSON array from response")
                    else:
                        logger.error(f"No JSON array found in response. Preview: {clean_data[:200]}")
                        return []
                
                # Method 3: Clean up common issues
                clean_data = clean_data.replace('\n', ' ').replace('\r', ' ')
                clean_data = ' '.join(clean_data.split())  # Normalize whitespace
                
                # Parse JSON
                try:
                    hackathons = json.loads(clean_data)
                    logger.info(f"Successfully parsed JSON with {len(hackathons)} items")
                except json.JSONDecodeError as je:
                    logger.error(f"JSON decode failed at position {je.pos}")
                    logger.error(f"Error: {je.msg}")
                    logger.error(f"Response excerpt (chars {max(0, je.pos-50)} to {je.pos+50}): {clean_data[max(0, je.pos-50):je.pos+50]}")
                    logger.debug(f"Full response: {clean_data[:1000]}")
                    return []
                
                # Validate it's a list
                if not isinstance(hackathons, list):
                    logger.error(f"Expected list, got {type(hackathons)}")
                    return []
                
                # Limit to specified number
                hackathons = hackathons[:limit]
                logger.info(f"Processing {len(hackathons)} hackathons (limited to {limit})")
                
                # Add metadata and clean data
                current_date = datetime.now(timezone.utc)
                valid_hackathons = []
                
                for idx, hackathon in enumerate(hackathons):
                    logger.debug(f"Processing hackathon {idx + 1}: {hackathon.get('title', 'NO TITLE')}")
                    
                    # Add metadata
                    hackathon['scraped_at'] = current_date
                    hackathon['source'] = 'gemini_search'
                    
                    # Validate and clean end_date
                    if 'end_date' in hackathon and hackathon['end_date'] != 'TBD':
                        try:
                            # Try to parse and validate the date
                            parsed_date = datetime.strptime(hackathon['end_date'][:10], '%Y-%m-%d')
                            # Include hackathons ending today or in the future
                            if parsed_date.date() >= current_date.date():
                                hackathon['end_date'] = parsed_date.strftime('%Y-%m-%d')
                                valid_hackathons.append(hackathon)
                                logger.debug(f"  ✓ Valid: ends on {hackathon['end_date']}")
                            else:
                                logger.debug(f"  ✗ Expired: ended on {hackathon['end_date']}")
                        except Exception as e:
                            # Log but include hackathons with parse issues if they look valid
                            logger.warning(f"Date parse issue for {hackathon.get('title')}: {str(e)}")
                            # Still include if the date string looks reasonable
                            if len(hackathon['end_date']) >= 10:
                                valid_hackathons.append(hackathon)
                                logger.debug(f"  ~ Included despite parse issue")
                    else:    
                        # Include hackathons with TBD dates
                        valid_hackathons.append(hackathon)
                        logger.debug(f"  ✓ Included (TBD date)")
                
                logger.info(f"Validated {len(valid_hackathons)} hackathons out of {len(hackathons)}")
                
                # Sort by end_date (latest first)
                try:
                    valid_hackathons.sort(key=lambda x: x.get('end_date', '9999-12-31'), reverse=True)
                except Exception as e:
                    logger.warning(f"Could not sort hackathons: {str(e)}")
                return valid_hackathons
            
            logger.warning("raw_data is not a string, returning empty list")
            return []
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {str(e)}")
            logger.error(f"Failed to parse response. First 500 chars: {raw_data[:500] if isinstance(raw_data, str) else 'N/A'}")
            return []
        except Exception as e:
            logger.error(f"Error parsing hackathon data: {str(e)}")
            logger.error(f"Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return []

# Initialize scraper
scraper = HackathonScraper()

# Initialize scheduler for automatic scraping
scheduler = BackgroundScheduler()

def automatic_scrape():
    """Automatically scrape hackathons every 6 hours and append new ones"""
    try:
        logger.info("=" * 60)
        logger.info("Starting automatic hackathon scraping...")
        logger.info(f"Current date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        def run_scraping():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # First, remove expired hackathons and duplicates
                logger.info("Cleaning up expired hackathons...")
                expired_count = remove_expired_hackathons()
                logger.info(f"Removed {expired_count} expired hackathons")
                
                logger.info("Removing duplicates...")
                dup_count = remove_duplicates()
                logger.info(f"Removed {dup_count} duplicate hackathons")
                
                # Fetch new hackathons
                logger.info("Fetching new hackathons from Gemini API...")
                raw_data = loop.run_until_complete(scraper.search_hackathons(limit=15))
                
                if not raw_data or raw_data == "[]":
                    logger.warning("Empty response from API - no data returned")
                    return
                
                logger.info(f"Raw data received: {len(raw_data)} characters")
                logger.debug(f"Raw data preview: {raw_data[:500]}")
                
                hackathons = scraper.parse_hackathon_data(raw_data, limit=15)
                logger.info(f"Parsed {len(hackathons)} hackathons from API response")
                
                if hackathons and len(hackathons) > 0:
                    # Filter out duplicates based on title and website_url
                    new_hackathons = []
                    skipped_duplicates = 0
                    
                    for hackathon in hackathons:
                        # Validate required fields
                        if not hackathon.get('title') or not hackathon.get('website_url'):
                            logger.warning(f"Skipping hackathon with missing title or URL: {hackathon}")
                            continue
                        
                        # Check for duplicates (case-insensitive title match or exact URL match)
                        existing = hackathons_collection.find_one({
                            "$or": [
                                {"title": {"$regex": f"^{hackathon['title']}$", "$options": "i"}},
                                {"website_url": hackathon.get("website_url")}
                            ]
                        })
                        
                        if not existing:
                            new_hackathons.append(hackathon)
                            logger.info(f"✓ New hackathon found: {hackathon['title']}")
                        else:
                            skipped_duplicates += 1
                            logger.debug(f"✗ Duplicate skipped: {hackathon['title']}")
                    
                    logger.info(f"Found {len(new_hackathons)} new hackathons, {skipped_duplicates} duplicates skipped")
                    
                    if new_hackathons:
                        # Append only new hackathons
                        result = hackathons_collection.insert_many(new_hackathons)
                        logger.info(f"✓ Successfully added {len(result.inserted_ids)} new hackathons to database")
                        
                        # Log the titles of added hackathons
                        for h in new_hackathons:
                            logger.info(f"  - {h['title']} ({h.get('platform', 'unknown')})")
                    else:
                        logger.info("No new hackathons found - all already exist in database")
                else:
                    logger.warning("No hackathons parsed from API response. Check API response format.")
                    logger.debug(f"Raw response for debugging: {raw_data[:1000]}")
                    
            except Exception as e:
                logger.error(f"ERROR in automatic scraping: {str(e)}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
            finally:
                loop.close()
                logger.info("Scraping cycle completed")
                logger.info("=" * 60)
        
        run_scraping()
        
    except Exception as e:
        logger.error(f"Error in automatic_scrape wrapper: {str(e)}")

def remove_expired_hackathons():
    """Remove hackathons that have already ended (registration deadline passed)"""
    try:
        current_date = datetime.now().strftime('%Y-%m-%d')
        current_datetime = datetime.now()
        
        # Remove hackathons where end_date is before current date
        result = hackathons_collection.delete_many({
            "end_date": {"$lt": current_date, "$ne": "TBD"}
        })
        
        deleted_count = result.deleted_count
        
        # Also check for hackathons with invalid or missing dates that are old
        # Remove hackathons scraped more than 60 days ago with TBD dates
        old_tbd_result = hackathons_collection.delete_many({
            "end_date": "TBD",
            "scraped_at": {"$lt": current_datetime - timedelta(days=60)}
        })
        
        deleted_count += old_tbd_result.deleted_count
        
        if deleted_count > 0:
            logger.info(f"Removed {deleted_count} expired/old hackathons (Date: {result.deleted_count}, Old TBD: {old_tbd_result.deleted_count})")
        
        return deleted_count
    except Exception as e:
        logger.error(f"Error removing expired hackathons: {str(e)}")
        return 0

def remove_duplicates():
    """Remove duplicate hackathons based on title, website_url, and similarity"""
    try:
        total_removed = 0
        
        # Method 1: Remove exact title duplicates (case-insensitive)
        all_hackathons = list(hackathons_collection.find())
        seen_titles = {}
        title_duplicates = []
        
        for hackathon in all_hackathons:
            title_lower = hackathon.get('title', '').lower().strip()
            if title_lower in seen_titles:
                # Keep the newer one (by scraped_at)
                existing = seen_titles[title_lower]
                existing_date = existing.get('scraped_at', datetime.min)
                current_date = hackathon.get('scraped_at', datetime.min)
                
                if current_date < existing_date:
                    title_duplicates.append(hackathon['_id'])
                else:
                    title_duplicates.append(existing['_id'])
                    seen_titles[title_lower] = hackathon
            else:
                seen_titles[title_lower] = hackathon
        
        if title_duplicates:
            result = hackathons_collection.delete_many({"_id": {"$in": title_duplicates}})
            total_removed += result.deleted_count
            logger.info(f"Removed {result.deleted_count} title duplicates")
        
        # Method 2: Remove URL duplicates
        all_hackathons = list(hackathons_collection.find())
        seen_urls = {}
        url_duplicates = []
        
        for hackathon in all_hackathons:
            url = hackathon.get('website_url', '').strip()
            if url and url not in ['', 'N/A', 'TBD']:
                if url in seen_urls:
                    existing = seen_urls[url]
                    existing_date = existing.get('scraped_at', datetime.min)
                    current_date = hackathon.get('scraped_at', datetime.min)
                    
                    if current_date < existing_date:
                        url_duplicates.append(hackathon['_id'])
                    else:
                        url_duplicates.append(existing['_id'])
                        seen_urls[url] = hackathon
                else:
                    seen_urls[url] = hackathon
        
        if url_duplicates:
            result = hackathons_collection.delete_many({"_id": {"$in": url_duplicates}})
            total_removed += result.deleted_count
            logger.info(f"Removed {result.deleted_count} URL duplicates")
        
        # Method 3: Remove similar titles (fuzzy matching)
        all_hackathons = list(hackathons_collection.find())
        similar_duplicates = []
        
        for i, h1 in enumerate(all_hackathons):
            for h2 in all_hackathons[i+1:]:
                title1 = h1.get('title', '').lower().strip()
                title2 = h2.get('title', '').lower().strip()
                
                # Check if titles are very similar (contain each other or differ by version numbers)
                if title1 and title2:
                    # Remove version numbers and special characters for comparison
                    clean_title1 = ''.join(c for c in title1 if c.isalnum() or c.isspace()).strip()
                    clean_title2 = ''.join(c for c in title2 if c.isalnum() or c.isspace()).strip()
                    
                    # If one title contains the other (90% or more similarity)
                    if clean_title1 in clean_title2 or clean_title2 in clean_title1:
                        # Keep the one with more information (longer description or newer)
                        h1_score = len(h1.get('description', '')) + (1000 if h1.get('scraped_at', datetime.min) > h2.get('scraped_at', datetime.min) else 0)
                        h2_score = len(h2.get('description', '')) + (1000 if h2.get('scraped_at', datetime.min) > h1.get('scraped_at', datetime.min) else 0)
                        
                        if h1_score < h2_score and h1['_id'] not in similar_duplicates:
                            similar_duplicates.append(h1['_id'])
                        elif h2['_id'] not in similar_duplicates:
                            similar_duplicates.append(h2['_id'])
        
        if similar_duplicates:
            result = hackathons_collection.delete_many({"_id": {"$in": similar_duplicates}})
            total_removed += result.deleted_count
            logger.info(f"Removed {result.deleted_count} similar title duplicates")
        
        if total_removed > 0:
            logger.info(f"TOTAL: Removed {total_removed} duplicate hackathons from database")
        
        return total_removed
    except Exception as e:
        logger.error(f"Error removing duplicates: {str(e)}")
        return 0

# Schedule automatic scraping every 6 hours
scheduler.add_job(
    func=automatic_scrape,
    trigger="interval",
    hours=6,
    id='hackathon_scraper',
    name='Automatic Hackathon Scraper',
    replace_existing=True
)

# Start the scheduler
scheduler.start()

# Run initial scrape on startup
def initial_scrape():
    """Run initial scrape when the app starts"""
    time.sleep(2)  # Wait for app to fully initialize
    automatic_scrape()

# Start initial scrape in background thread
initial_thread = Thread(target=initial_scrape)
initial_thread.daemon = True
initial_thread.start()

@app.route('/')
def index():
    """Home page showing all hackathons"""
    try:
        # Remove expired hackathons and duplicates first
        remove_expired_hackathons()
        remove_duplicates()
        
        # Get all hackathons
        hackathons = list(hackathons_collection.find())
        
        # Sort by priority: ongoing first, then upcoming, then by end_date
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        def sort_key(h):
            status = h.get('status', 'upcoming').lower()
            end_date = h.get('end_date', '9999-12-31')
            
            # Priority order: open > upcoming
            priority = 0 if status == 'open' else 1
            
            # Within each priority, sort by end_date (sooner first)
            return (priority, end_date if end_date != 'TBD' else '9999-12-31')
        
        hackathons.sort(key=sort_key)
        
        for hackathon in hackathons:
            hackathon['_id'] = str(hackathon['_id'])
            # Add days_until_deadline for color coding
            if hackathon.get('end_date') and hackathon['end_date'] != 'TBD':
                try:
                    end_date_obj = datetime.strptime(hackathon['end_date'], '%Y-%m-%d')
                    current_date_obj = datetime.strptime(current_date, '%Y-%m-%d')
                    days_until = (end_date_obj - current_date_obj).days
                    hackathon['days_until_deadline'] = days_until
                except:
                    hackathon['days_until_deadline'] = 999
            else:
                hackathon['days_until_deadline'] = 999
                
        return render_template('index.html', hackathons=hackathons)
    except Exception as e:
        logger.error(f"Error in index route: {str(e)}")
        return render_template('index.html', hackathons=[], error="Failed to load hackathons")

@app.route('/hackathon/<hackathon_id>')
def view_hackathon(hackathon_id):
    """View single hackathon details"""
    try:
        hackathon = hackathons_collection.find_one({'_id': ObjectId(hackathon_id)})
        if hackathon:
            hackathon['_id'] = str(hackathon['_id'])
            return render_template('hackathon_detail.html', hackathon=hackathon)
        else:
            return redirect(url_for('index'))
    except Exception as e:
        logger.error(f"Error viewing hackathon: {str(e)}")
        return redirect(url_for('index'))

@app.route('/edit/<hackathon_id>')
def edit_hackathon(hackathon_id):
    """Edit hackathon page"""
    try:
        hackathon = hackathons_collection.find_one({'_id': ObjectId(hackathon_id)})
        if hackathon:
            hackathon['_id'] = str(hackathon['_id'])
            return render_template('edit_hackathon.html', hackathon=hackathon)
        else:
            return redirect(url_for('index'))
    except Exception as e:
        logger.error(f"Error loading edit page: {str(e)}")
        return redirect(url_for('index'))

@app.route('/update/<hackathon_id>', methods=['POST'])
def update_hackathon(hackathon_id):
    """Update hackathon"""
    try:
        update_data = {
            'title': request.form.get('title'),
            'description': request.form.get('description'),
            'organizer': request.form.get('organizer'),
            'registration_deadline': request.form.get('registration_deadline'),
            'event_date': request.form.get('event_date'),
            'prize_pool': request.form.get('prize_pool'),
            'website_url': request.form.get('website_url'),
            'platform': request.form.get('platform'),
            'status': request.form.get('status'),
            'eligibility': request.form.get('eligibility'),
            'updated_at': datetime.utcnow()
        }
        
        # Handle tags
        tags = request.form.get('tags', '')
        if tags:
            update_data['tags'] = [tag.strip() for tag in tags.split(',')]
        
        hackathons_collection.update_one(
            {'_id': ObjectId(hackathon_id)},
            {'$set': update_data}
        )
        
        return redirect(url_for('view_hackathon', hackathon_id=hackathon_id))
    except Exception as e:
        logger.error(f"Error updating hackathon: {str(e)}")
        return redirect(url_for('edit_hackathon', hackathon_id=hackathon_id))

@app.route('/delete/<hackathon_id>', methods=['POST'])
def delete_hackathon(hackathon_id):
    """Delete hackathon"""
    try:
        hackathons_collection.delete_one({'_id': ObjectId(hackathon_id)})
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error deleting hackathon: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/search/<hackathon_id>')
def search_hackathon(hackathon_id):
    """Redirect to Google search with relevant keywords for the hackathon"""
    try:
        hackathon = hackathons_collection.find_one({'_id': ObjectId(hackathon_id)})
        if hackathon:
            # Generate relevant search keywords
            keywords = generate_search_keywords(hackathon)
            # Redirect to Google search
            google_search_url = f"https://www.google.com/search?q={keywords}"
            return redirect(google_search_url)
        else:
            return redirect(url_for('index'))
    except Exception as e:
        logger.error(f"Error in search redirect: {str(e)}")
        return redirect(url_for('index'))

def generate_search_keywords(hackathon):
    """Generate relevant search keywords for a hackathon"""
    import urllib.parse
    
    keywords = []
    
    # Add hackathon title (most important)
    if hackathon.get('title'):
        keywords.append(hackathon['title'])
    
    # Add platform for specificity
    if hackathon.get('platform'):
        keywords.append(hackathon['platform'])
    
    # Add year to get current results
    current_year = datetime.now().year
    keywords.append(str(current_year))
    
    # Add "hackathon" and "registration" for relevance
    keywords.extend(['hackathon', 'registration'])
    
    # Join keywords and URL encode
    search_query = ' '.join(keywords)
    return urllib.parse.quote_plus(search_query)

@app.route('/api/hackathons')
def api_hackathons():
    """API endpoint to get all active hackathons"""
    try:
        # Remove expired hackathons first
        remove_expired_hackathons()
        
        # Get all hackathons sorted by end_date (latest first)
        hackathons = list(hackathons_collection.find().sort("end_date", -1))
        for hackathon in hackathons:
            hackathon['_id'] = str(hackathon['_id'])
            # Convert datetime objects to strings
            if 'scraped_at' in hackathon:
                hackathon['scraped_at'] = hackathon['scraped_at'].isoformat()
            if 'updated_at' in hackathon:
                hackathon['updated_at'] = hackathon['updated_at'].isoformat()
        return jsonify(hackathons)
    except Exception as e:
        logger.error(f"Error in API endpoint: {str(e)}")
        return jsonify({'error': str(e)})

@app.route('/api/scrape-now', methods=['POST'])
def manual_scrape():
    """Manual trigger for scraping hackathons"""
    try:
        logger.info("Manual scrape triggered via API")
        
        # Run scraping in a separate thread to avoid blocking
        def run_manual_scrape():
            automatic_scrape()
        
        thread = Thread(target=run_manual_scrape)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Scraping started. Check logs for progress. Refresh page in 30 seconds.'
        })
    except Exception as e:
        logger.error(f"Error in manual scrape: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/stats')
def api_stats():
    """Get statistics about hackathons"""
    try:
        total = hackathons_collection.count_documents({})
        
        current_date = datetime.now().strftime('%Y-%m-%d')
        open_count = hackathons_collection.count_documents({'status': 'open'})
        
        # Count by platform
        platforms = hackathons_collection.aggregate([
            {'$group': {'_id': '$platform', 'count': {'$sum': 1}}}
        ])
        platform_stats = {p['_id']: p['count'] for p in platforms}
        
        return jsonify({
            'total': total,
            'open': open_count,
            'platforms': platform_stats,
            'last_updated': current_date
        })
    except Exception as e:
        logger.error(f"Error in stats endpoint: {str(e)}")
        return jsonify({'error': str(e)})

import atexit

def shutdown_scheduler():
    """Shutdown the scheduler gracefully"""
    if scheduler:
        scheduler.shutdown()

atexit.register(shutdown_scheduler)

if __name__ == '__main__':
    try:
        app.run(debug=False, port=5000)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        shutdown_scheduler()
