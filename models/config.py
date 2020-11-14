import configparser
import os


class Config:

    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config.read(os.path.join("/config/settings.ini"))
        self.config.sections()

    def get(self, key):
        return self.config['DEFAULT'][key]

    def set(self, key, value):
        self.config["DEFAULT"][key] = value

    def save(self):
        with open("settings.ini", "w") as configfile:
            self.config.write(configfile)

    def load(self):
        self.config.read("settings.ini")
