from functools import wraps
from flask import request, Response, make_response
import time
from datetime import datetime, timedelta
import threading
import logging

logger = logging.getLogger(__name__)

# Rate limiting
class RateLimiter:
    def __init__(self, requests_per_minute=60):
        self.requests_per_minute = requests_per_minute
        self.requests = {}
        self.lock = threading.Lock()

    def is_allowed(self, ip):
        now = datetime.now()
        with self.lock:
            # Clean old entries
            self.requests = {k: v for k, v in self.requests.items() 
                           if v[-1] > now - timedelta(minutes=1)}
            
            # Check current IP
            if ip not in self.requests:
                self.requests[ip] = []
            
            # Remove old requests for this IP
            self.requests[ip] = [t for t in self.requests[ip] 
                               if t > now - timedelta(minutes=1)]
            
            # Check rate limit
            if len(self.requests[ip]) >= self.requests_per_minute:
                return False
            
            # Add new request
            self.requests[ip].append(now)
            return True

rate_limiter = RateLimiter()

def rate_limit(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not rate_limiter.is_allowed(request.remote_addr):
            return make_response('Rate limit exceeded', 429)
        return f(*args, **kwargs)
    return decorated_function

# Security headers
def security_headers(response):
    """Add security headers to response"""
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:"
    return response

# Cache control
def cache_control(max_age=300):
    """Add cache control headers"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            response = f(*args, **kwargs)
            if not isinstance(response, Response):
                response = make_response(response)
            response.headers['Cache-Control'] = f'public, max-age={max_age}'
            return response
        return decorated_function
    return decorator

# Request validation
def validate_request(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check content type for POST requests
        if request.method == 'POST' and not request.is_json:
            return make_response('Content-Type must be application/json', 400)
        
        # Check request size
        content_length = request.content_length
        if content_length and content_length > 10 * 1024 * 1024:  # 10MB limit
            return make_response('Request too large', 413)
        
        return f(*args, **kwargs)
    return decorated_function

# Performance monitoring
def performance_monitor(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        start_time = time.time()
        response = f(*args, **kwargs)
        duration = time.time() - start_time
        
        # Log request duration
        logger.info(f"Request to {request.path} took {duration:.2f} seconds")
        
        # Add timing header
        if not isinstance(response, Response):
            response = make_response(response)
        response.headers['X-Response-Time'] = f"{duration:.2f}s"
        return response
    return decorated_function 