
from libs.eth_async.utils.files import read_json
from libs.eth_async.classes import AutoRepr, Singleton
from data.config import SETTINGS_FILE 

class Settings(Singleton, AutoRepr):
    def __init__(self):
        json_data = read_json(path=SETTINGS_FILE)

