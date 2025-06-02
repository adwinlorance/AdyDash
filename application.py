import sys
import os

# Add the app directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app import app

# This is the file that Oryx looks for by default
application = app

if __name__ == '__main__':
    app.run() 