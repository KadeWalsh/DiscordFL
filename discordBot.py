import threading
import discord
from discord.ext import commands
import json
from clickerBot import ClickerBot
import cv2
from io import BytesIO
import database as DB
import datetime
import time


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

        @self.bot.command(name="start", help="Starts the FL Bot")
        async def start(ctx):
            await ctx.send(f"""FL Bot is starting, as requested by {
                ctx.author.mention}!""")
            self.clicker_bot.ensure_game_running()
            self.clicker_bot.start()

        @self.bot.command(name="pause", help="Pauses the FL Bot")
        async def pause(ctx):
            await ctx.send(f"""FL Bot is paused, as requested by {
                ctx.author.mention}!""")
            self.clicker_bot.paused = True

        @self.bot.command(name="restart", help="Pauses the FL Bot")
        async def restart(ctx):
            await ctx.send(f"""FL restarting, as requested by {
                ctx.author.mention}...""")
            self.clicker_bot.paused = True
            self.clicker_bot.stop()
            time.sleep(5)
            self.clicker_bot.start()

        @self.bot.command(name="resume", help="Pauses the FL Bot")
        async def resume(ctx):
            await ctx.send(f"""FL Bot has resumed duties, as requested by {
                ctx.author.mention}!""")
            self.clicker_bot.paused = False

        @self.bot.command(name="stop", help="Stops the FL Bot")
        async def stop(ctx):
            await ctx.send(f"""FL Bot is stopping, as requested by {
                ctx.author.mention}!""")
            self.clicker_bot.stop()

        @self.bot.command(name="status", help="Check the status of the bot")
        async def status(ctx):
            await ctx.send("Getting current status")

            status = self.clicker_bot.get_status()

            await ctx.send(status)

            try:
                screenshot = self.clicker_bot.ADB.capture_screenshot()

                is_success, buffer = cv2.imencode(".png", screenshot)

                if not is_success:
                    await ctx.send("Failed to encode the image.")
                    return

                # Store image into BytesIO Buffer object in memory
                image_buffer = BytesIO(buffer)

                # Reset the buffer pointer to the beginning
                image_buffer.seek(0)

                # Send the image via Discord
                discord_file = discord.File(
                    fp=image_buffer, filename="image.png")
                await ctx.send("Current screen view:", file=discord_file)

            except Exception as e:
                await ctx.send(f"An error occurred: {e}")

        @self.bot.command(name="start_game",
                          help="Start the game if not already running")
        async def start_game(ctx):
            await ctx.send("Checking if game is already running...")
            if self.clicker_bot.ADB.is_game_running() is False:
                await ctx.send("Game is not running.\nStarting game...")
                self.clicker_bot.ensure_game_running()
                await ctx.send("Game started successfully!")
                await ctx.send("Please use '/start' to start the bot!")
            else:
                await ctx.send("Game already running!")

        @self.bot.command(name='sync',
                          help='Sync all slash commands to the server')
        async def sync(ctx):
            print("sync command")
            await self.bot.tree.sync()
            await ctx.send('Command tree synced.')

        @self.bot.command(name='dismiss',
                          help='Sync all slash commands to the server')
        async def dismiss(ctx, buff_name=None):
            if buff_name is not None:
                await ctx.send(f'''{buff_name} buff dismissal initiated by {
                    ctx.author.mention}''')
                dismissal_status = self.clicker_bot.dismiss_buff(buff_name)
                await ctx.send(dismissal_status)
            else:
                await ctx.send("No buff name specified!  Usage: "
                               "'!dissmiss <buff name>'")

        @self.bot.command(name='reload_jobs',
                          help='Reload job logic from file as hot reload')
        async def reload_jobs(ctx):
            print("Reloading jobs...")
            await ctx.send('Hot reloading job logic from file...')
            self.clicker_bot.stop()
            self.clicker_bot.reload_jobs()
            self.clicker_bot.start()
            await ctx.send('Reload complete!')

        @discord.app_commands.choices(option=[
            discord.app_commands.Choice(name="No", value="n"),
            discord.app_commands.Choice(name="Yes", value="y"),
        ])
        @self.bot.command(name="reboot",
                          help="Restart the game on the host device")
        async def reboot(ctx):
            await ctx.send("Attempting to kill game process...")
            self.clicker_bot.restart_game()
            await ctx.send("Game restarted successfully!")

        @self.bot.command(name="screenshot",
                          help="Have me send a current screenshot")
        async def screenshot(ctx):
            try:
                screenshot = self.clicker_bot.ADB.capture_screenshot()

                is_success, buffer = cv2.imencode(".png", screenshot)

                if not is_success:
                    await ctx.send("Failed to encode the image.")
                    return

                # Store image into BytesIO Buffer object in memory
                image_buffer = BytesIO(buffer)

                # Reset the buffer pointer to the beginning
                image_buffer.seek(0)

                # Send the image via Discord
                discord_file = discord.File(
                    fp=image_buffer, filename="image.png")
                await ctx.send("Here is your image:", file=discord_file)

            except Exception as e:
                await ctx.send(f"An error occurred: {e}")

        @self.bot.command(name="stats",
                          help="Get stats for the last hour")
        async def stats(ctx):
            stats = self.get_stats()

            await ctx.send(f"Stats for the last hour: \n{stats}")

        @self.bot.event
        async def on_member_join(member: discord.Member):
            # Get the first available text channel
            text_channels = member.guild.text_channels
            if text_channels:  # Ensure there are text channels in the server
                first_channel = text_channels[0]
                # Send a welcome message
                await first_channel.send(
                    f"Welcome {member.mention} 🎉!"
                )
                # Split message into 2 parts
                message = "If you are curious what I can currently do, " +\
                    "please use the '!help' command to see the full " +\
                    "list of options!"
                # Recombine parts and send to channel
                await first_channel.send(message)

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

    def get_stats(self):
        server_time = self.clicker_bot.get_server_time()
        query = """SELECT * FROM jobs WHERE last_run > ? AND job_ran = 1"""
        time_cutoff = server_time - datetime.timedelta(hours=1)
        res = DB.cur.execute(query, [time_cutoff,])
        results = res.fetchall()
        job_stats = {}
        SKIP_JOBS = ["RESET", "BOT STARTED"]

        for job in results:
            if job['name'] in SKIP_JOBS:
                continue

            if job['name'] in job_stats:
                job_stats[job['name']] += 1

            else:
                job_stats[job['name']] = 1

        stat_string = "\n".join([f'{k} executed  {v} times'
                                 for k, v in job_stats.items()])

        return stat_string


def query_database(query: str, variables: list[str | int]) -> dict:
    """
    Execute a query against the database and return the results.

    Args:
        query (str): SQL query to execute

    Returns:
        dict: Result of the query
    """
    DB.cur.execute(query, variables)
    results = DB.cur.fetchall()

    return results


# Main script to test the bot
if __name__ == "__main__":
    with open('actual.json', 'r') as f:
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
