import json
# import time
from clickerBot import ClickerBot
from discordBot import DiscordBot

DEFAULT_JSON = "actual.json"


class MainBot:
    def __init__(self, config_filename: str = "working.json"):

        # Load configuration
        startup_data = self.load_startup_data(config_filename)
        settings = startup_data['settings']

        # Initialize bots
        self.clicker = ClickerBot(settings['clicker'])
        self.discordBot = DiscordBot(
            settings['discord'], clickerBot=self.clicker)

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
    bot = MainBot(DEFAULT_JSON)
    bot.start_bots()


if __name__ == "__main__":
    main()
