import threading
import discord
from discord.ext import commands
import json
from clickerBot import ClickerBot
import cv2
from io import BytesIO


class DiscordBot:
    def __init__(self,
                 settings: dict,
                 clickerBot: ClickerBot,
                 command_prefix: str = "!"):
        """
        Initializes the bot.
        :param token: The Discord bot token.
        :param command_prefix: The prefix for bot commands (default is "!").
        """
        self.token = settings['TOKEN']
        self.command_prefix = settings.get('command_prefix') or command_prefix

        # Initialize bot with specified prefix and intents
        self.intents = discord.Intents.default()
        self.intents.message_content = True  # Enable message content intent
        self.intents.messages = True  # Enable messages intent
        self.bot = commands.Bot(
            command_prefix=self.command_prefix, intents=self.intents)

        # Set up the bot commands and events
        self.setup_bot()

        # Add reference to ADB connection instance
        self.clicker_bot = clickerBot

    def setup_bot(self):
        """
        Sets up commands and events for the bot.
        """
        @self.bot.event
        async def on_ready():
            print(f"Bot is online and logged in as {self.bot.user}")

        @self.bot.command(name="hello", help="Responds with a greeting")
        async def hello(ctx):
            print("Command '!hello' registered!")
            await ctx.send(f"Hello, {ctx.author.mention}!")

        @self.bot.command(name="start", help="Starts the FL Bot")
        async def start(ctx):
            await ctx.send(f"""FL Bot is starting, as requested by {
                ctx.author.mention}!""")
            self.clicker_bot.ensure_game_running()
            self.clicker_bot.start()

        @self.bot.command(name="stop", help="Stop the FL Bot")
        async def stop(ctx):
            await ctx.send(f"""FL Bot is stopping, as requested by {
                ctx.author.mention}!""")
            self.clicker_bot.stop()

        @self.bot.command(name="status", help="Check the status of the bot")
        async def status(ctx):
            await ctx.send("Getting current status")

            status = self.clicker_bot.get_status()

            await ctx.send(status)

        @self.bot.command(name="start_game",
                          help="Start the game if not already running.")
        async def start_game(ctx):
            await ctx.send("Checking if game is already running...")
            if self.clicker_bot.ADB.is_game_running() is False:
                await ctx.send("Game is not running.\nStarting game...")
                self.clicker_bot.ensure_game_running()
                await ctx.send("Game started successfully!")
                await ctx.send("Please use '/start' to start the bot!")
            else:
                await ctx.send("Game already running!")

        @self.bot.command()
        async def sync(ctx):
            print("sync command")
            await bot.tree.sync()
            await ctx.send('Command tree synced.')

        @discord.app_commands.choices(option=[
            discord.app_commands.Choice(name="No", value="n"),
            discord.app_commands.Choice(name="Yes", value="y"),
        ])
        @self.bot.command(name="restart",
                          help="Restart the game on the host device.")
        async def restart(ctx):
            await ctx.send("Attempting to kill game process...")
            self.clicker_bot.restart_game()
            await ctx.send("Game restarted successfully!")
            print(f"{ctx}")
            # if interaction.message == "y":
            #     self.clicker_bot.start()

        @self.bot.command(name="screenshot",
                          description="See a current screenshot.")
        async def screenshot(ctx):
            try:
                screenshot = self.clicker_bot.ADB.capture_screenshot()
                # rgb_screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGR2RGB)

                is_success, buffer = cv2.imencode(".png", screenshot)

                if not is_success:
                    await ctx.send("Failed to encode the image.")
                    return

                # Step 3: Store the encoded image in a BytesIO buffer
                image_buffer = BytesIO(buffer)
                # Reset the buffer pointer to the beginning
                image_buffer.seek(0)

                # Step 4: Send the image via Discord
                discord_file = discord.File(
                    fp=image_buffer, filename="image.png")
                await ctx.send("Here is your image:", file=discord_file)

            except Exception as e:
                await ctx.send(f"An error occurred: {e}")

    def run(self):
        """
        Starts the bot in the current thread.
        """
        self.bot.run(self.token)

    def run_in_thread(self):
        """
        Starts the bot in a separate thread.
        """
        bot_thread = threading.Thread(target=self.run, daemon=False)
        bot_thread.start()

        self.thread = bot_thread


# Main script to test the bot
if __name__ == "__main__":
    with open('working.json', 'r') as f:
        settings = json.load(f)['settings']

    discord_settings = settings['discord']
    clicker_settings = settings['clicker']

    clicker = ClickerBot(clicker_settings)
    # Instantiate the bot
    bot = DiscordBot(discord_settings, clicker)

    # Run the bot in the main thread
    try:
        bot.run()
    except KeyboardInterrupt:
        print("Bot is shutting down...")
    except Exception as e:
        print(f"An error occurred: {e}")