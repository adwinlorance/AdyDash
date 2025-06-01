from flask import Flask, render_template, jsonify
from datetime import datetime, timedelta
import requests
import os
import time
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
import logging
from googleapiclient.discovery import build
from calendar_setup import get_calendar_credentials
from config_manager import ConfigManager
from middleware import rate_limit, security_headers, cache_control, validate_request, performance_monitor
from flask_compress import Compress
import json
import os.path
import sys

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

try:
    app = Flask(__name__)
    Compress(app)  # Enable compression
    config_manager = ConfigManager()

    # Apply security headers to all responses
    @app.after_request
    def after_request(response):
        return security_headers(response)

    # Load environment variables and verify
    logger.info("Loading environment variables...")
    load_dotenv()
    weather_api_key = os.getenv('WEATHER_API_KEY')
    finnhub_api_key = os.getenv('FINNHUB_API_KEY')
    news_api_key = "44ccd6d6e2ae4918af34dafc854e4c0b"
    city = os.getenv('CITY', 'London')
    
    # Log configuration status
    logger.info(f"Environment loaded - Weather API Key present: {'Yes' if weather_api_key else 'No'}")
    logger.info(f"Environment loaded - Finnhub API Key present: {'Yes' if finnhub_api_key else 'No'}")
    logger.info(f"Environment loaded - News API Key present: {'Yes' if news_api_key else 'No'}")
    logger.info(f"City configured as: {city}")

    # Cache for storing data
    cache = {
        'weather': {'loading': True},
        'calendar': {'loading': True},
        'stocks': {'loading': True},
        'news': {'loading': True},
        'last_update': None
    }

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

            # Get the start and end of today in local time
            now = datetime.now()
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = start_of_day + timedelta(days=1)

            # Convert to UTC for API
            start_of_day_utc = start_of_day.isoformat() + 'Z'
            end_of_day_utc = end_of_day.isoformat() + 'Z'

            logger.info(f"Fetching calendar events between {start_of_day} and {end_of_day}")
            logger.info(f"TimeMin: {start_of_day_utc}")
            logger.info(f"TimeMax: {end_of_day_utc}")

            events_result = service.events().list(
                calendarId='primary',
                timeMin=start_of_day_utc,
                timeMax=end_of_day_utc,
                maxResults=20,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            # Log the full API response
            logger.info("Full Calendar API Response:")
            logger.info(str(events_result))

            events = events_result.get('items', [])
            
            if not events:
                logger.info('No upcoming events found for today.')
                return []

            formatted_events = []
            for event in events:
                logger.info(f"\nProcessing event details:")
                logger.info(f"Event raw data: {str(event)}")
                logger.info(f"Summary: {event.get('summary', 'No title')}")
                logger.info(f"Start: {event['start']}")
                logger.info(f"End: {event['end']}")
                
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                
                # Convert to datetime object
                if 'T' in start:  # This is a datetime
                    start_time = datetime.fromisoformat(start.replace('Z', '+00:00'))
                    # Convert to local time
                    start_time = start_time.astimezone()
                    # Format time as HH:MM
                    time_str = start_time.strftime('%H:%M')
                    logger.info(f"Converted time: {time_str}")
                else:  # This is a date
                    time_str = 'All day'
                    logger.info("All day event")

                formatted_events.append({
                    'time': time_str,
                    'summary': event['summary'],
                    'start': start,
                    'end': end
                })
                logger.info(f"Added event: {time_str} - {event['summary']}")

            logger.info(f"Found {len(formatted_events)} events for today")
            return formatted_events

        except Exception as e:
            logger.error(f"Error fetching calendar events: {str(e)}")
            logger.exception("Full error details:")
            return None

    def update_calendar():
        """Update calendar data"""
        try:
            events = get_calendar_events()
            if events is not None:
                cache['calendar'] = events
                logger.info("Calendar data updated successfully")
            else:
                cache['calendar'] = {'error': True}
        except Exception as e:
            logger.error(f"Error updating calendar: {str(e)}")
            cache['calendar'] = {'error': True}

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
            weather_data = get_weather_data()
            if weather_data:
                cache['weather'] = weather_data
                logger.info("Weather data updated successfully")
            else:
                cache['weather'] = {'error': True}
        except Exception as e:
            logger.error(f"Error updating weather: {str(e)}")
            cache['weather'] = {'error': True}
        cache['last_update'] = datetime.now()

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

    @app.route('/')
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

    @app.route('/health')
    @rate_limit
    @performance_monitor
    @cache_control(max_age=60)  # Cache for 1 minute
    def health_check():
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'services': {
                'weather_api': 'unknown',
                'finnhub_api': 'unknown',
                'google_calendar': 'unknown',
                'azure_config': 'unknown'
            },
            'environment': {
                'weather_api_key': 'present' if os.getenv('WEATHER_API_KEY') else 'missing',
                'finnhub_api_key': 'present' if os.getenv('FINNHUB_API_KEY') else 'missing',
                'azure_app_config': 'present' if os.getenv('AZURE_APP_CONFIG_CONNECTION_STRING') else 'missing'
            }
        }

        # Check Weather API
        try:
            if weather_api_key:
                weather_url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={weather_api_key}&units=metric"
                response = requests.get(weather_url)
                health_status['services']['weather_api'] = 'healthy' if response.status_code == 200 else f'error: {response.status_code}'
            else:
                health_status['services']['weather_api'] = 'error: no API key'
        except Exception as e:
            health_status['services']['weather_api'] = f'error: {str(e)}'

        # Check Finnhub API
        try:
            if finnhub_api_key:
                headers = {'X-Finnhub-Token': finnhub_api_key}
                response = requests.get('https://finnhub.io/api/v1/quote?symbol=AAPL', headers=headers)
                health_status['services']['finnhub_api'] = 'healthy' if response.status_code == 200 else f'error: {response.status_code}'
            else:
                health_status['services']['finnhub_api'] = 'error: no API key'
        except Exception as e:
            health_status['services']['finnhub_api'] = f'error: {str(e)}'

        # Check Google Calendar
        try:
            creds = get_calendar_credentials()
            if creds:
                health_status['services']['google_calendar'] = 'healthy'
            else:
                health_status['services']['google_calendar'] = 'error: no credentials'
        except Exception as e:
            health_status['services']['google_calendar'] = f'error: {str(e)}'

        # Check Azure App Configuration
        try:
            config = config_manager.get_stock_config()
            if config and 'stocks' in config:
                health_status['services']['azure_config'] = 'healthy'
            else:
                health_status['services']['azure_config'] = 'error: no configuration'
        except Exception as e:
            health_status['services']['azure_config'] = f'error: {str(e)}'

        # Overall status
        if any('error' in status for status in health_status['services'].values()):
            health_status['status'] = 'unhealthy'

        return jsonify(health_status)

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