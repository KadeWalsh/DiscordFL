import json
# import time
from clickerBot import ClickerBot
from discordBot import DiscordBot
from database import create_tables
import database as DB

SCREENSHOT_ONLY = False


class MainBot:
    def __init__(self,
                 discordConfig: str = "JSON/discord.json",
                 clickerConfig: str = "JSON/clicker.json"):

        # Load configuration
        discordSettings = self.parseJson(discordConfig)
        clickerSettings = self.parseJson(clickerConfig)

        CLEAR_OLD_DATA = False

        if CLEAR_OLD_DATA is True:
            # Delete all old database data
            DB.clear_old_data()

        # Initialize bots
        self.clicker = ClickerBot(clickerSettings)
        self.discordBot = DiscordBot(
            discordSettings, clickerBot=self.clicker)
        if SCREENSHOT_ONLY is True:
            self.clicker.capture_screenshot('profile_name.png')
        else:
            self.start_bots()

    def parseJson(self, filename):
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
    bot = MainBot("JSON/actual_discord.json")


if __name__ == "__main__":
    main()
