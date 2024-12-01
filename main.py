import json
# import time
from clickerBot import ClickerBot
from discordBot import DiscordBot
from database import create_tables
import database as DB
DEFAULT_JSON = "actual.json"


class MainBot:
    def __init__(self, config_filename: str = "working.json"):

        # Load configuration
        startup_data = self.load_startup_data(config_filename)
        settings = startup_data['settings']

        # Delete all old database data
        DB.clear_old_data()

        # Initialize bots
        self.clicker = ClickerBot(settings['clicker'])
        self.discordBot = DiscordBot(
            settings['discord'], clickerBot=self.clicker)
        self.start_bots()

    def load_startup_data(self, filename):
        with open(filename, "r") as file:
            return json.load(file)

    def start_bots(self):
        self.clicker.start()
        self.discordBot.run()

    def run_discord_bot(self):
        """Run the Discord bot and handle any errors"""
        if self.discordBot is not None:
            self.discordBot.run()

    def stop(self):
        """Gracefully stop all bots"""
        self.clicker.stop()
        if self.discordBot is not None:
            self.discordBot.stop()


def main(*args, **kwargs):
    create_tables()
    bot = MainBot(DEFAULT_JSON)


if __name__ == "__main__":
    main()
