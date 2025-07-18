from flask import Flask, render_template, jsonify
from datetime import datetime, timedelta
import requests
import os
import time
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
import logging
from googleapiclient.discovery import build
from calendar_setup import get_calendar_credentials, refresh_credentials
from config_manager import ConfigManager
from middleware import rate_limit, security_headers, cache_control, validate_request, performance_monitor, https_redirect
from flask_compress import Compress
import json
import os.path
import sys
import pytz

# Set up logging to both file and console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Log startup information
logger.info("Starting application...")
logger.info(f"Python version: {sys.version}")
logger.info(f"Working directory: {os.getcwd()}")
logger.info(f"Directory contents: {os.listdir('.')}")

# Initialize global variables
weather_api_key = None
finnhub_api_key = None
news_api_key = None
city = None

def load_environment():
    """Load environment variables into global scope"""
    global weather_api_key, finnhub_api_key, news_api_key, city
    
    # Load environment variables
    load_dotenv()
    
    # Set global variables
    weather_api_key = os.getenv('WEATHER_API_KEY')
    finnhub_api_key = os.getenv('FINNHUB_API_KEY')
    news_api_key = os.getenv('NEWS_API_KEY', "44ccd6d6e2ae4918af34dafc854e4c0b")
    city = os.getenv('CITY', 'Mooresville')
    
    # Log configuration status
    logger.info(f"Environment loaded - Weather API Key present: {'Yes' if weather_api_key else 'No'}")
    logger.info(f"Environment loaded - Finnhub API Key present: {'Yes' if finnhub_api_key else 'No'}")
    logger.info(f"Environment loaded - News API Key present: {'Yes' if news_api_key else 'No'}")
    logger.info(f"City configured as: {city}")

# Load environment variables first
logger.info("Loading environment variables...")
load_environment()

try:
    app = Flask(__name__)
    Compress(app)  # Enable compression
    config_manager = ConfigManager()
    scheduler = None  # Global scheduler instance

    # Cache for storing data
    cache = {
        'weather': {'loading': True},
        'calendar': {'loading': True},
        'stocks': {'loading': True},
        'news': {'loading': True},
        'last_update': None
    }

    def get_weather_data():
        """Get weather data from OpenWeatherMap API"""
        try:
            if not weather_api_key:
                logger.error("Weather API key not found in .env file")
                return None

            logger.info(f"Updating weather data for {city}")
            weather_url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={weather_api_key}&units=metric"
            weather_response = requests.get(weather_url)
            logger.info(f"Weather API response status: {weather_response.status_code}")
            
            if weather_response.status_code == 200:
                weather_data = weather_response.json()
                temp_c = round(weather_data['main']['temp'])
                temp_f = round((temp_c * 9/5) + 32)
                return {
                    'city': weather_data['name'],
                    'temperature_c': temp_c,
                    'temperature_f': temp_f,
                    'description': weather_data['weather'][0]['description'],
                    'humidity': weather_data['main']['humidity'],
                    'wind_speed': weather_data['wind']['speed']
                }
            else:
                logger.error(f"Weather API error: {weather_response.status_code}")
                logger.error(f"Response content: {weather_response.text}")
                return None
        except Exception as e:
            logger.error(f"Error fetching weather data: {str(e)}")
            return None

    def update_weather():
        """Update weather data"""
        try:
            logger.info("Starting weather update...")
            logger.info(f"Current cache state before update: {cache['weather']}")
            
            weather_data = get_weather_data()
            logger.info(f"Received weather data: {weather_data}")
            
            if weather_data:
                cache['weather'] = weather_data
                logger.info(f"Weather data updated successfully. New cache state: {cache['weather']}")
            else:
                cache['weather'] = {'error': True}
                logger.error("Weather data update failed - got None response")
            cache['last_update'] = datetime.now()
        except Exception as e:
            logger.error(f"Error updating weather: {str(e)}")
            cache['weather'] = {'error': True}

    def load_stock_config():
        """Load stock configuration from Azure App Configuration"""
        try:
            config = config_manager.get_stock_config()
            # Flatten the dictionary of categories into a list of symbols
            symbols = []
            for category, stocks in config['stocks'].items():
                symbols.extend(stocks)
            return config['stocks'], symbols
        except Exception as e:
            logger.error(f"Error loading stock configuration: {str(e)}")
            return {}, []

    # Load stock configuration
    STOCK_CATEGORIES, STOCK_SYMBOLS = load_stock_config()

    def get_stock_data():
        """Get real-time stock data from Finnhub API"""
        try:
            logger.info("Updating stock data...")
            stock_data = {}
            
            if not finnhub_api_key:
                logger.error("Finnhub API key not found in .env file")
                return None

            headers = {
                'X-Finnhub-Token': finnhub_api_key
            }

            for symbol in STOCK_SYMBOLS:
                try:
                    logger.info(f"Fetching data for {symbol}")
                    
                    # Get real-time quote data
                    url = f"https://finnhub.io/api/v1/quote?symbol={symbol}"
                    response = requests.get(url, headers=headers)
                    
                    if response.status_code == 200:
                        data = response.json()
                        logger.info(f"Raw API response for {symbol}: {data}")
                        
                        if data.get('c') is not None:  # Current price
                            current_price = data['c']
                            previous_close = data['pc']
                            
                            # Calculate percentage change
                            if previous_close > 0:
                                change_percent = ((current_price - previous_close) / previous_close) * 100
                            else:
                                change_percent = 0
                            
                            # Find the category for this symbol
                            category = next((cat for cat, symbols in STOCK_CATEGORIES.items() 
                                          if symbol in symbols), "Other")
                            
                            stock_data[symbol] = {
                                'price': round(current_price, 2),
                                'change': round(change_percent, 2),
                                'category': category
                            }
                            logger.info(f"Successfully fetched {symbol}: ${current_price} ({change_percent}%)")
                        else:
                            logger.error(f"No quote data found for {symbol}")
                            stock_data[symbol] = {'price': 'N/A', 'change': 'N/A', 'category': 'Other'}
                    else:
                        logger.error(f"Error fetching {symbol}: HTTP {response.status_code}")
                        stock_data[symbol] = {'price': 'N/A', 'change': 'N/A', 'category': 'Other'}
                    
                except Exception as e:
                    logger.error(f"Error fetching {symbol}: {str(e)}")
                    stock_data[symbol] = {'price': 'N/A', 'change': 'N/A', 'category': 'Other'}
                
                # Add a small delay between requests
                time.sleep(0.5)
            
            return {'categories': STOCK_CATEGORIES, 'data': stock_data}
        except Exception as e:
            logger.error(f"Error in get_stock_data: {str(e)}")
            return None

    def update_stocks():
        """Update stock data"""
        try:
            stock_data = get_stock_data()
            if stock_data:
                cache['stocks'] = stock_data
                logger.info("Stock data updated successfully")
            else:
                cache['stocks'] = {'error': True}
        except Exception as e:
            logger.error(f"Error updating stocks: {str(e)}")
            cache['stocks'] = {'error': True}

    def get_calendar_events():
        """Get today's calendar events"""
        try:
            creds = get_calendar_credentials()
            if not creds:
                logger.error("Failed to get calendar credentials")
                return None

            service = build('calendar', 'v3', credentials=creds)

            # Get the start and end of today in EST
            est = pytz.timezone('America/New_York')
            now = datetime.now(est)
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = start_of_day + timedelta(days=1)

            # Convert to UTC for API
            start_of_day_utc = start_of_day.astimezone(pytz.UTC).isoformat()
            end_of_day_utc = end_of_day.astimezone(pytz.UTC).isoformat()

            logger.info(f"Fetching calendar events between {start_of_day} and {end_of_day} EST")
            logger.info(f"UTC TimeMin: {start_of_day_utc}")
            logger.info(f"UTC TimeMax: {end_of_day_utc}")

            events_result = service.events().list(
                calendarId='primary',
                timeMin=start_of_day_utc,
                timeMax=end_of_day_utc,
                maxResults=20,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])
            
            if not events:
                logger.info('No upcoming events found for today.')
                return []

            formatted_events = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                
                # Convert to datetime object in EST
                if 'T' in start:  # This is a datetime
                    start_time = datetime.fromisoformat(start.replace('Z', '+00:00'))
                    # Convert to EST
                    start_time = start_time.astimezone(est)
                    # Format time as HH:MM
                    time_str = start_time.strftime('%H:%M')
                else:  # This is a date
                    time_str = 'All day'

                formatted_events.append({
                    'time': time_str,
                    'summary': event['summary'],
                    'start': start,
                    'end': end
                })
                logger.info(f"Added event: {time_str} EST - {event['summary']}")

            logger.info(f"Found {len(formatted_events)} events for today")
            return formatted_events

        except Exception as e:
            logger.error(f"Error fetching calendar events: {str(e)}")
            logger.exception("Full error details:")
            return None

    def update_calendar():
        """Update calendar data"""
        try:
            # Set loading state
            cache['calendar'] = {'loading': True}
            
            events = get_calendar_events()
            if events is not None:
                if isinstance(events, list):
                    cache['calendar'] = events
                    logger.info(f"Calendar data updated successfully with {len(events)} events")
                else:
                    logger.error("Calendar events returned invalid format")
                    cache['calendar'] = {'error': True, 'message': 'Invalid calendar data format'}
            else:
                logger.error("Failed to fetch calendar events")
                cache['calendar'] = {'error': True, 'message': 'Unable to fetch calendar events'}
        except Exception as e:
            logger.error(f"Error updating calendar: {str(e)}")
            cache['calendar'] = {'error': True, 'message': str(e)}

    def get_news_data():
        """Get news data from NewsAPI"""
        try:
            logger.info("Fetching news data...")
            news_data = {
                'business': [],
                'politics': []
            }

            # Fetch business news
            business_url = f"https://newsapi.org/v2/top-headlines?country=us&category=business&apiKey={news_api_key}"
            business_response = requests.get(business_url)
            
            # Fetch political news
            politics_url = f"https://newsapi.org/v2/top-headlines?country=us&category=politics&apiKey={news_api_key}"
            politics_response = requests.get(politics_url)
            
            if business_response.status_code == 200:
                data = business_response.json()
                if data.get('status') == 'ok':
                    # Get the first 5 articles
                    articles = data.get('articles', [])[:5]
                    for article in articles:
                        news_data['business'].append({
                            'title': article.get('title', ''),
                            'description': article.get('description', ''),
                            'url': article.get('url', ''),
                            'source': article.get('source', {}).get('name', ''),
                            'published_at': datetime.strptime(article.get('publishedAt', ''), '%Y-%m-%dT%H:%M:%SZ').strftime('%H:%M %d/%m') if article.get('publishedAt') else ''
                        })
                    logger.info(f"Successfully fetched {len(news_data['business'])} business news articles")
            else:
                logger.error(f"Business News API HTTP error: {business_response.status_code}")

            # Add a small delay between requests to avoid rate limiting
            time.sleep(1)

            if politics_response.status_code == 200:
                data = politics_response.json()
                if data.get('status') == 'ok':
                    # Get the first 5 articles
                    articles = data.get('articles', [])[:5]
                    for article in articles:
                        news_data['politics'].append({
                            'title': article.get('title', ''),
                            'description': article.get('description', ''),
                            'url': article.get('url', ''),
                            'source': article.get('source', {}).get('name', ''),
                            'published_at': datetime.strptime(article.get('publishedAt', ''), '%Y-%m-%dT%H:%M:%SZ').strftime('%H:%M %d/%m') if article.get('publishedAt') else ''
                        })
                    logger.info(f"Successfully fetched {len(news_data['politics'])} political news articles")
                else:
                    logger.error(f"Politics News API HTTP error: {politics_response.status_code}")

            return news_data if (news_data['business'] or news_data['politics']) else None
            
        except Exception as e:
            logger.error(f"Error fetching news data: {str(e)}")
            return None

    def update_news():
        """Update news data"""
        try:
            news_data = get_news_data()
            if news_data:
                cache['news'] = news_data
                logger.info("News data updated successfully")
            else:
                cache['news'] = {'error': True}
        except Exception as e:
            logger.error(f"Error updating news: {str(e)}")
            cache['news'] = {'error': True}

    def update_all():
        """Initial update of all data"""
        logger.info("Starting initial data update...")
        update_weather()
        update_calendar()
        update_stocks()
        update_news()
        logger.info("Initial data update completed")

    def init_scheduler():
        """Initialize the background scheduler"""
        global scheduler
        if scheduler is None:
            try:
                logger.info("Initializing background scheduler...")
                scheduler = BackgroundScheduler()
                
                # Only add jobs if their API keys are present
                if weather_api_key:
                    scheduler.add_job(func=update_weather, trigger="interval", minutes=5)
                else:
                    logger.warning("Weather API key missing - weather updates disabled")
                    
                scheduler.add_job(func=update_calendar, trigger="interval", minutes=15)
                
                if finnhub_api_key:
                    scheduler.add_job(func=update_stocks, trigger="interval", hours=1)
                else:
                    logger.warning("Finnhub API key missing - stock updates disabled")
                
                if news_api_key:
                    scheduler.add_job(func=update_news, trigger="interval", minutes=30)
                else:
                    logger.warning("News API key missing - news updates disabled")
                
                scheduler.start()
                logger.info("Background scheduler started successfully")
                
                # Perform initial data load
                logger.info("Starting initial data load...")
                update_all()
                logger.info("Initial data load completed")
                return True
            except Exception as e:
                logger.error(f"Failed to initialize scheduler: {str(e)}", exc_info=True)
                return False
        return True

    # Initialize scheduler when the app starts
    if not init_scheduler():
        logger.error("Failed to initialize the application scheduler")

    @app.route('/status')
    def scheduler_status():
        """Endpoint to check scheduler status"""
        return jsonify({
            'scheduler_running': bool(scheduler and scheduler.running),
            'cache_status': {
                'weather': not isinstance(cache['weather'], dict) or not cache['weather'].get('loading', False),
                'stocks': not isinstance(cache['stocks'], dict) or not cache['stocks'].get('loading', False),
                'news': not isinstance(cache['news'], dict) or not cache['news'].get('loading', False),
                'calendar': not isinstance(cache['calendar'], dict) or not cache['calendar'].get('loading', False)
            },
            'last_update': str(cache['last_update']) if cache['last_update'] else None
        })

    @app.route('/trigger-update')
    def trigger_update():
        """Endpoint to manually trigger data updates"""
        try:
            update_all()
            return jsonify({'status': 'success', 'message': 'Data update triggered successfully'})
        except Exception as e:
            logger.error(f"Error triggering update: {str(e)}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/refresh-token')
    @https_redirect
    def refresh_token():
        """Endpoint to refresh Google Calendar token"""
        try:
            success = refresh_credentials()
            if success:
                update_calendar()  # Refresh calendar data after token refresh
                return jsonify({'status': 'success', 'message': 'Token refreshed successfully'})
            return jsonify({'status': 'error', 'message': 'Failed to refresh token'}), 400
        except Exception as e:
            logger.error(f"Error refreshing token: {str(e)}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

    # Apply security headers to all responses
    @app.after_request
    def after_request(response):
        return security_headers(response)

    @app.route('/')
    @https_redirect
    @rate_limit
    @performance_monitor
    @cache_control(max_age=300)  # Cache for 5 minutes
    def index():
        try:
            current_time = datetime.now()
            return render_template('index.html',
                                time=current_time,
                                weather=cache['weather'],
                                calendar=cache['calendar'],
                                stocks=cache['stocks'],
                                news=cache['news'],
                                last_update=cache['last_update'])
        except Exception as e:
            logger.error(f"Error in index route: {str(e)}", exc_info=True)
            return f"An error occurred: {str(e)}", 500

    # Basic health check endpoint that doesn't depend on external services
    @app.route('/health')
    @https_redirect
    def health_check():
        try:
            health_status = {
                'status': 'healthy',
                'timestamp': datetime.now().isoformat(),
                'version': '1.0'
            }
            return jsonify(health_status), 200
        except Exception as e:
            logger.error(f"Health check error: {str(e)}")
            return jsonify({'status': 'unhealthy', 'error': str(e)}), 503

    # Full health check endpoint for detailed monitoring
    @app.route('/health/full')
    @https_redirect
    @rate_limit
    @performance_monitor
    @cache_control(max_age=300)
    def full_health_check():
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'version': '1.0',
            'instance': os.environ.get('WEBSITE_INSTANCE_ID', 'unknown'),
            'services': {
                'weather_api': 'unknown',
                'finnhub_api': 'unknown',
                'google_calendar': 'unknown',
                'azure_config': 'unknown'
            },
            'environment': {
                'weather_api_key': 'present' if os.getenv('WEATHER_API_KEY') else 'missing',
                'finnhub_api_key': 'present' if os.getenv('FINNHUB_API_KEY') else 'missing',
                'azure_app_config': 'present' if os.getenv('AZURE_APP_CONFIG_CONNECTION_STRING') else 'missing',
                'google_token': 'present' if os.getenv('GOOGLE_TOKEN_PICKLE') else 'missing',
                'google_creds': 'present' if os.getenv('GOOGLE_CREDENTIALS_JSON') else 'missing'
            },
            'cache_status': {
                'weather': cache.get('weather', {}),
                'stocks': cache.get('stocks', {}),
                'calendar': cache.get('calendar', {}),
                'news': cache.get('news', {})
            },
            'scheduler_status': {
                'running': bool(scheduler and scheduler.running),
                'jobs': [job.name for job in scheduler.get_jobs()] if scheduler else []
            }
        }

        # Check Weather API
        try:
            if weather_api_key:
                weather_url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={weather_api_key}&units=metric"
                response = requests.get(weather_url, timeout=10)
                health_status['services']['weather_api'] = {
                    'status': 'healthy' if response.status_code == 200 else 'error',
                    'code': response.status_code,
                    'response': response.json() if response.status_code == 200 else response.text
                }
            else:
                health_status['services']['weather_api'] = {'status': 'error', 'reason': 'no API key'}
        except Exception as e:
            logger.error(f"Health check - Weather API error: {str(e)}")
            health_status['services']['weather_api'] = {'status': 'error', 'error': str(e)}

        # Check Finnhub API
        try:
            if finnhub_api_key:
                headers = {'X-Finnhub-Token': finnhub_api_key}
                response = requests.get('https://finnhub.io/api/v1/quote?symbol=AAPL', headers=headers, timeout=10)
                health_status['services']['finnhub_api'] = {
                    'status': 'healthy' if response.status_code == 200 else 'error',
                    'code': response.status_code,
                    'response': response.json() if response.status_code == 200 else response.text
                }
            else:
                health_status['services']['finnhub_api'] = {'status': 'error', 'reason': 'no API key'}
        except Exception as e:
            logger.error(f"Health check - Finnhub API error: {str(e)}")
            health_status['services']['finnhub_api'] = {'status': 'error', 'error': str(e)}

        # Check Google Calendar
        try:
            creds = get_calendar_credentials()
            if creds:
                service = build('calendar', 'v3', credentials=creds)
                # Try to list calendars as a test
                calendar_list = service.calendarList().list().execute()
                health_status['services']['google_calendar'] = {
                    'status': 'healthy',
                    'calendars_found': len(calendar_list.get('items', []))
                }
            else:
                health_status['services']['google_calendar'] = {'status': 'error', 'reason': 'no credentials'}
        except Exception as e:
            logger.error(f"Health check - Google Calendar error: {str(e)}")
            health_status['services']['google_calendar'] = {'status': 'error', 'error': str(e)}

        # Check Azure App Configuration
        try:
            config = config_manager.get_stock_config()
            if config and 'stocks' in config:
                health_status['services']['azure_config'] = {
                    'status': 'healthy',
                    'config_found': True,
                    'stocks_configured': len(config['stocks'])
                }
            else:
                health_status['services']['azure_config'] = {'status': 'error', 'reason': 'no configuration'}
        except Exception as e:
            logger.error(f"Health check - Azure Config error: {str(e)}")
            health_status['services']['azure_config'] = {'status': 'error', 'error': str(e)}

        # Check critical services
        critical_services = ['weather_api', 'finnhub_api']
        critical_services_status = [
            health_status['services'][service].get('status') == 'healthy'
            for service in critical_services
        ]
        
        is_healthy = any(critical_services_status)

        if not is_healthy:
            health_status['status'] = 'unhealthy'
            logger.warning("Health check failed - all critical services are down", extra=health_status)
            return jsonify(health_status), 503

        if not all(critical_services_status):
            health_status['status'] = 'degraded'
            logger.warning("Health check warning - some services are down", extra=health_status)
            return jsonify(health_status), 200

        logger.info("Health check passed", extra=health_status)
        return jsonify(health_status), 200

    # Add error handlers
    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal Server Error: {error}", exc_info=True)
        return "Internal Server Error", 500

    @app.errorhandler(404)
    def not_found_error(error):
        logger.error(f"Page Not Found: {error}")
        return "Page Not Found", 404

    if __name__ == '__main__':
        try:
            logger.info("Starting scheduler...")
            scheduler = BackgroundScheduler()
            scheduler.add_job(func=update_weather, trigger="interval", minutes=5)
            scheduler.add_job(func=update_calendar, trigger="interval", minutes=15)
            scheduler.add_job(func=update_stocks, trigger="interval", hours=1)
            scheduler.add_job(func=update_news, trigger="interval", minutes=30)
            scheduler.start()
            
            # Start update_all in a separate thread
            import threading
            threading.Thread(target=update_all, daemon=True).start()
            
            # Get port from environment variable for Azure or use default
            port = int(os.environ.get('PORT', 8080))
            logger.info(f"Starting web server on port {port}...")
            app.run(host='0.0.0.0', port=port)
        except Exception as e:
            logger.error(f"Error starting application: {str(e)}", exc_info=True)
            raise
except Exception as e:
    logger.error(f"Critical error during application startup: {str(e)}", exc_info=True)
    raise

# ... rest of your existing code ... 