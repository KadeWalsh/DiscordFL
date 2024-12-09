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
    """
        Contains all the functions related to the Discord Bot interface
    """

    def __init__(self,
                 settings: dict,
                 clickerBot: ClickerBot,
                 command_prefix: str = "!"):
        """
        Initializes the bot.
        :param token: The Discord bot token.
        :param command_prefix: The prefix for bot commands (default is "!").
        """
        # Save token and command prefix from JSON file
        self.token = settings['TOKEN']
        self.command_prefix = settings.get('command_prefix') or command_prefix

        # Initialize bot with specified prefix and intents
        self.intents = discord.Intents.default()
        self.intents.message_content = True  # Enable message content intent
        self.intents.messages = True  # Enable messages intent
        # Create instance of Discord.py Bot class using previous variables
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
            # Runs when bot first connects to the Discord server
            print(f"Bot is online and logged in as {self.bot.user}")

        @self.bot.command(name="start", help="Starts the FL Bot")
        async def start(ctx):
            # Sends message to Discord to confirm command was received
            await ctx.send(f"""FL Bot is starting, as requested by {
                ctx.author.mention}!""")
            # Runs the ClickerBot ensure_game_running() function
            self.clicker_bot.ensure_game_running()
            # Runs the ClickerBot start() function to start the bot
            self.clicker_bot.start()

        @self.bot.command(name="pause", help="Pauses the FL Bot")
        async def pause(ctx):
            # Sends message to Discord to confirm command was received
            await ctx.send(f"""FL Bot is paused, as requested by {
                ctx.author.mention}!""")
            # Sets ClickerBot.paused to True to pause clicking
            self.clicker_bot.paused = True

        @self.bot.command(name="restart", help="Restarts the FL Bot")
        async def restart(ctx):
            # Sends message to Discord to confirm command was received
            await ctx.send(f"""FL restarting, as requested by {
                ctx.author.mention}...""")
            # Set clicker.paused to True
            self.clicker_bot.paused = True
            # Stop the clicker bot
            self.clicker_bot.stop()
            # Wait for 5 seconds to allow the bot to stop
            time.sleep(5)
            # Start the clicker bot again
            self.clicker_bot.start()

        @self.bot.command(name="resume", help="Pauses the FL Bot")
        async def resume(ctx):
            # Sends message to Discord to confirm command was received
            await ctx.send(f"""FL Bot has resumed duties, as requested by {
                ctx.author.mention}!""")
            # Sets clicker.paused to False to resume clicking
            self.clicker_bot.paused = False

        @self.bot.command(name="stop", help="Stops the FL Bot")
        async def stop(ctx):
            # Sends message to Discord to confirm command was received
            await ctx.send(f"""FL Bot is stopping, as requested by {
                ctx.author.mention}!""")
            # Stops the clicker bot
            self.clicker_bot.stop()

        @self.bot.command(name="status", help="Check the status of the bot")
        async def status(ctx):
            # Sends message to Discord to confirm command was received
            await ctx.send("Getting current status")
            # Get status of various conditions from ClickerBot
            status = self.clicker_bot.get_status()
            # Send bot status do Discord channel
            await ctx.send(status)

            # Capture screenshot of current screen
            try:
                screenshot = self.clicker_bot.ADB.capture_screenshot()

                # Encode raw data from ADB device to .png format
                is_success, buffer = cv2.imencode(".png", screenshot)

                # Check for error in encoding
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

                # Send image to Discord
                await ctx.send("Current screen view:", file=discord_file)

            # Catch any errors and return them to Discord
            except Exception as e:
                await ctx.send(f"An error occurred: {e}")

        @self.bot.command(name="start_game",
                          help="Start the game if not already running")
        async def start_game(ctx):
            # Sends message to Discord to confirm command was received
            await ctx.send("Checking if game is already running...")
            # Check if game is already running
            if self.clicker_bot.ADB.is_game_running() is False:
                # If game is not running, start it
                await ctx.send("Game is not running.\nStarting game...")
                # Wait for game to start
                self.clicker_bot.ensure_game_running()
                # Send message to Discord once game is started
                await ctx.send("Game started successfully!")
                # Prompt user to send '!start' command to start the bot
                await ctx.send("Please use '!start' to start the bot!")
            else:
                # Game is already running
                await ctx.send("Game already running!")

        @self.bot.command(name='sync',
                          help='Sync all slash commands to the server')
        async def sync(ctx):
            # Ensures all commands are available to run on Discord
            print("sync command")
            await self.bot.tree.sync()
            await ctx.send('Command tree synced.')

        @self.bot.command(name='dismiss',
                          help='Sync all slash commands to the server')
        async def dismiss(ctx, buff_name=None):
            # TODO: Only partially implemented
            # Requires more testing to use safely
            # Check buff name
            if buff_name is not None:
                # Send message to Discord to confirm command received
                await ctx.send(f'''{buff_name} buff dismissal initiated by {
                    ctx.author.mention}''')
                # Run ClickerBot.dismiss_buff() with the buff name as parameter
                dismissal_status = self.clicker_bot.dismiss_buff(buff_name)
                # Send response from dismiss_buff function to Discord
                await ctx.send(dismissal_status)
            # Buff name was empty
            else:
                # Send error message to Discord if no buff name was specified
                await ctx.send("No buff name specified!  Usage: "
                               "'!dissmiss <buff name>'")

        @self.bot.command(name='reload_jobs',
                          help='Reload job logic from file as hot reload')
        async def reload_jobs(ctx):
            # Send message to Discord to confirm command received
            await ctx.send('Hot reloading job logic from file...')
            # Stop ClickerBot
            self.clicker_bot.stop()
            # Run reload_jobs() function
            self.clicker_bot.reload_jobs()
            # Restart the ClickerBot
            self.clicker_bot.start()
            # Send message to Discord to confirm reload is complete
            await ctx.send('Reload complete!')

        @self.bot.command(name="reboot",
                          help="Restart the game on the host device")
        async def reboot(ctx):
            # Send message to Discord to confirm command received
            await ctx.send("Attempting to kill game process...")
            # Run ClickerBot.restart_game() function to restart game
            self.clicker_bot.restart_game()
            # Send message to Discord to confirm game restart complete
            await ctx.send("Game restarted successfully!")

        @self.bot.command(name="screenshot",
                          help="Have me send a current screenshot")
        async def screenshot(ctx):
            # Capture a current screenshot of the ADB device and send
            # it via Discord message
            try:
                # Capture screenshot
                screenshot = self.clicker_bot.ADB.capture_screenshot()

                # Encode image
                is_success, buffer = cv2.imencode(".png", screenshot)

                # Check for error in encoding image
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

            # Catch any errors and return them to Discord
            except Exception as e:
                await ctx.send(f"An error occurred: {e}")

        @self.bot.command(name="stats",
                          help="Get stats for the last hour")
        async def stats(ctx):
            # Get stats from database using get_stats() function
            stats = self.get_stats()

            # Return formatted stats to Discord
            await ctx.send(f"Stats for the last hour: \n{stats}")

        @self.bot.event
        async def on_member_join(member: discord.Member):
            # TODO: This has not been tested yet
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
        Starts the DiscordBot
        """
        self.bot.run(self.token)

    def get_stats(self):
        # Get server time
        server_time = self.clicker_bot.get_server_time()
        # Set stat collection query
        query = """SELECT * FROM jobs WHERE last_run > ? AND job_ran = 1"""
        # Set minimum time threshold for valid stats
        time_cutoff = server_time - datetime.timedelta(hours=1)
        # Execute query
        res = DB.cur.execute(query, [time_cutoff,])
        # Fetch query results
        results = res.fetchall()
        # Create dictionary to store statistics
        job_stats = {}
        # Define list of jobs to be skipped when collecting stats
        SKIP_JOBS = ["RESET", "BOT STARTED"]

        # Iterate through rows returned from DB
        for job in results:
            # If job name should be skipped
            if job['name'] in SKIP_JOBS:
                # Continue to next row
                continue

            # Check if job name already in dicionary keys
            if job['name'] in job_stats:
                # Increment the count for the job
                job_stats[job['name']] += 1
            # Job name not in dictionary keys
            else:
                # Create new dictionary item and set value to 1
                job_stats[job['name']] = 1

        # Format statistics dictionary as string for transmission to Discord
        stat_string = "\n".join([f'{k} executed  {v} times'
                                 for k, v in job_stats.items()])

        # Return formatted statistics string
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
def main():
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


if __name__ == "__main__":
    main()
