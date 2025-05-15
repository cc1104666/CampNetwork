import os
import sys
from pathlib import Path
from loguru import logger
from dotenv import load_dotenv
load_dotenv() 

if getattr(sys, 'frozen', False):
    ROOT_DIR = Path(sys.executable).parent.absolute()
else:
    ROOT_DIR = Path(__file__).parent.parent.absolute()

FILES_DIR = os.path.join(ROOT_DIR, 'files')

SOLVIUM_API = os.getenv('SOLVIUM_API')
TWOCAPTCHA_API_KEY = os.getenv('TWOCAPTCHA_API')
CAPMONSTER_API_KEY = os.getenv('CAPMONSTER_API_KEY')

PROXY_FILE = os.path.join(FILES_DIR, 'proxy.txt')
PRIVATE_FILE = os.path.join(FILES_DIR, 'private.txt')
TWITTER_FILE = os.path.join(FILES_DIR, 'twitter.txt')

SETTINGS_FILE = os.path.join(FILES_DIR, 'settings.json')

LOG_FILE = os.path.join(FILES_DIR, 'log.log')
ERRORS_FILE = os.path.join(FILES_DIR, 'errors.log')

logger.add(ERRORS_FILE, level='ERROR')
logger.add(LOG_FILE, level='INFO')

