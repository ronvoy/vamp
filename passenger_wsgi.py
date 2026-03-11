import os
import sys

# Add the app directory to the Python path so imports resolve correctly
app_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app")
sys.path.insert(0, app_dir)

from app import application
