import json
# import time
from clickerBot import ClickerBot
from discordBot import DiscordBot
from database import create_tables
import database as DB

# Prevents bot startup when only getting current screenshot during development
# while needing specific screenshots to build JSON files
SCREENSHOT_ONLY = False


class MainBot:
    """
        Contains references to both the Discord and Clicker bots, and starts
        them both when initializing a MainBot instance.
        Args:
            discordConfig (str): Path to the Discord bot's config file.
            clickerConnection (str): Path to the ADB connection config file.
            clickerConfig (str): Path to the JSON file containing clicker data.
    """

    def __init__(self,
                 discordConfig: str = "JSON/discord.json",
                 clickerConnection: str = "JSON/connection.json",
                 clickerConfig: str = "JSON/clicker.json"):

        # Load configuration
        discordSettings = self.parseJson(discordConfig)
        clickerSettings = self.parseJson(clickerConfig)
        clickerSettings['settings'] = self.parseJson(clickerConnection)
        # Used to delete any previous database data if desired.
        CLEAR_OLD_DATA = False
        # Checks for flag, and clears older data if desired.
        if CLEAR_OLD_DATA is True:
            # Delete all old database data
            DB.clear_old_data()

        # Initialize bots
        self.clicker = ClickerBot(clickerSettings)
        self.discordBot = DiscordBot(
            discordSettings, clickerBot=self.clicker)
        # Checks for SCREENSHOT_ONLY flag as defined previously
        if SCREENSHOT_ONLY is True:
            # Captures screenshot without starting bots
            self.clicker.capture_screenshot('profile_name.png')
        # If SCREENSHOT_ONLY is not 'True'
        else:
            # Calls the "start_bots()" function to start both
            self.start_bots()

    def parseJson(self, filename):
        """
            Loads the given JSON file from disk and returns
            its contents as a dictionary.

            Args:
                filename (str): Path to the JSON file
        """
        with open(filename, "r") as file:
            return json.load(file)

    def start_bots(self):
        """
            Runs the .start() and .run() methods on the
            ClickerBot and DiscordBot instances respectively,
            which starts their operation.
        """
        self.clicker.start()
        self.discordBot.run()

    def stop(self):
        """
            Stops both the DiscordBot and ClickerBot instances
        """
        self.clicker.stop()
        if self.discordBot is not None:
            self.discordBot.stop()


def main(*args, **kwargs):
    """
        Main function which runs when 'main.py' is run.

        Creates required database files as needed, and then
        creates an instance of MainBot which handles all other
        operations as needed.
    """
    create_tables()
    MainBot(clickerConnection="JSON/connection.json")


if __name__ == "__main__":
    main()
