import database as DB
import random
from io import BytesIO
import json
import cv2
import numpy as np
import time
import copy
import datetime
from threading import Thread

from adbDevice import ADBdevice
from classes import Job, Event, Trigger, Area, Color, Coords, Action

TEST_JSON = 'working.json'
IObuffer = BytesIO()


class ClickerBot:
    """
        Contains all the functions, and variables, related to the
        operation of the actual click generation and interations
        with the game.
    """

    def __init__(self, clicker_settings: json = TEST_JSON):
        """
            Creates the starting state for the click bot by
            processing the JSON file and generating the various
            jobs that it is expected to execute.

            Args:
                clicker_settings (json): The JSON file containing the
                                         settings for the clicker bot.
                                         Defaults to 'working.json'.
        """
        # Sets the server time offset from GMT from the JSON file (GMT -2)
        self.time_offset = clicker_settings['time_offset']

        self.setup_logic(clicker_settings['jobs'])
        # Gets and stores instance of the ADBdevice class
        self.ADB = ADBdevice(clicker_settings['settings'])
        # Sets running variable to true on initialization
        self.running = True
        # Not currently implemented but used to store flag for VP duties on/off
        self.is_first_lady = True

        # Sets the timeout between VP sucessfully executing.
        # This helps prevent repeated failures by restarting the game
        self.idle_timeout = clicker_settings.get('idle_timeout') or 10

        # click_thread holds the reference to the Thread which runs the clicker
        self.click_thread = None

        # game_name is used to refer to the game within Android OS interactions
        self.game_name = 'com.fun.lastwar.gp'

        # current_job holds the name of the current 'Job' being executed
        self.current_job = None

        # Add flag to enable pause/resume functionality mid-event loop
        self.paused = False

        # Allows "status" to call the get_status() function via Discord command
        self.status = self.get_status()

    def check_relogin_window(self):
        """
            Currently hard-coded, should be moved to JSON file later.
            Checks for the presence of the ever-annoying "Please re-login"
            window on screen, and sends press of the "back button" to
            the device to clear this window
        """
        # Create pseudo JSON event for re-login popup window
        event_dict = {
            "description": "Check for re-login popup",
            "trigger": {
                "area": [
                    570,
                    965,
                    980,
                    1092],
                "color": [
                    [89, 222, 200],
                    [180, 255, 255]],
                "min_size": 35000,
            },
            "action": {
                "description": "Dismiss popup",
                "coords": [
                    0,
                    0
                ],
                "repeat": 2,
                "delay": 1,
                "action_type": "key",
                "click_delay": 0.2
            },
            "events": None,
        }

        # Convert JSON object to Event object
        close_relogin = Event(event_dict)

        # Execute event using standard functions for event handling
        # Check if Event.trigger is found (blue button in middle of screen)
        if self.trigger_found(close_relogin.trigger):
            # Exexcute action to close the popup
            self.execute_action(close_relogin.action)

    def reload_jobs(self, filename: str = 'JSON/clicker.json'):
        """
            Enables a "hot reload" of jobs from the JSON file if needed.
            Args:
                filename (str): The path to the JSON file containing the jobs.
                                Defaults to 'clicker.json'.
        """
        # Opens JSON file
        with open(filename, 'r') as f:
            # Loads the file into memory
            json_file = json.load(f)
            # Runs setup_logic() function with updated file
            self.setup_logic(json_file['jobs'])

    def get_server_time(self, delta_hours=0):
        """
            Returns the current server time
        """
        # Gets current time in UTC/GMT format
        UTC = datetime.datetime.now(datetime.timezone.utc)
        # Applied time shift to UTC to compensate for time difference
        server_time = UTC + datetime.timedelta(hours=self.time_offset)

        # Correct time for timedelta if provided
        server_time = server_time + datetime.timedelta(hours=delta_hours)

        # Returns corrected server time
        return server_time.replace(tzinfo=None)

    def check_new_day(self):
        """
            Checks if current day is different from previous day, such as
            before and after server reset.
            Uses ClickerBot.last_run_time to determine previous date and
            compares to current server time.  If current day is different
            resets all job counters and cooldown timers to allow for
            collection of things such as once daily items like VIP points,
            or multiple time items such as stamina points.
        """
        # Get current server time
        server_time = self.get_server_time()
        # Compare day of server time to day last run time
        if server_time.day != self.last_run_time.day:
            # If different iterate through jobs list
            for job in self.jobs:
                # Set job run_count to 0
                job.run_count = 0
                # Set job last_run to server time - run_interval
                job.last_run = server_time - \
                    datetime.timedelta(hours=job.run_interval)

            # Set last_run_time to new day
            self.last_run_time = server_time

    def can_run(self, job: Job) -> bool:
        """
            Checks if a job is valid to be run.  Returns True if job is
            valid to be run, and False otherwise.
        """
        # Check if job is currently being skipped
        if job.skip is True:
            # Return False to prevent job from running
            return False
        # Check if job has not run yet
        elif job.last_run is None:
            # Set job last_run time to current server time
            job.last_run = self.get_server_time()
            # Return True to run job
            return True
        # Create a random interval between job executions to prevent
        # repeating routine as regular intervals and possibly avoid
        # detection by devs.
        random_interval = job.run_interval + \
            (random.random() * job.run_interval)

        # Calculate new random time to use as job starting time threshold
        run_after = (job.last_run +
                     datetime.timedelta(hours=random_interval))
        # Check if job has daily limit (ie VIP/Gems)
        if job.daily_limit is None:
            # If no limit check if job has interval
            if job.run_interval is None or job.run_interval == 0:
                # If no limit and no interval (ie clicking help button)
                # return True to run job
                return True

            # If job has run interval get current server time
            current_time = self.get_server_time()

            # Return True if current time is after job's randomized
            # run_after time and False otherwise to prevent job from running
            return current_time > run_after

        # If Job DOES have a daily limit
        else:
            # Create conditions for job to be allowed to run and create a list
            # of conditions to check
            conditions = [job.daily_limit > job.run_count,
                          self.get_server_time() > run_after]

            # Return True if all conditions are met, otherwise False
            return all(conditions)

    def run_jobs(self, job_list=None):
        """
            Runs a specified list of jobs

            Args:
                job_list (list of Job): The list of jobs to be run.
                                        Defaults to ClickerBot.jobs
        """
        # Check if list is given in function call
        if job_list is None or job_list == [None]:
            # If no list is given, use ClickerBot.jobs
            job_list = self.jobs

        # Set job_executed to true to trigger screen reset on startup
        need_reset = True

        # Create bot loop
        while self.running is True:
            # Iterate through jobs
            for job in job_list:
                # Get current server time
                now = self.get_server_time()
                # Create restart timedelta to control restart interval
                restart_delay = datetime.timedelta(
                    minutes=self.idle_timeout + (5 * (random.random() + 1)))

                # Check is restart interval has been reached
                if self.last_run_time > now - restart_delay:
                    self.restart_game()
                    self.last_run_time = now
                    break

                # Update last_run_time
                self.last_run_time = self.get_server_time()

                # Check if game is not running, start it if necessary
                if self.ADB.is_game_running() is False:
                    # Kill game if still in memory
                    self.ADB.stop_game()
                    random_sleep(10)

                    # Start game
                    self.ADB.start_game()
                    # Wait for game to finish loading before continuing
                    time.sleep(30)

                    # Exit for loop and restart job
                    break

                # Check if "FIRST LADY" job is currently running
                if job.name == "FIRST_LADY":
                    # Get current server time
                    now = self.get_server_time()

                    # Calculate timeout for FL job execution
                    timeout = datetime.timedelta(minutes=self.idle_timeout)

                    # Get run_count for FL job
                    run_count = job.run_count

                    # Check for FL job not executing successfully by
                    # comparing job.last_run with given timeout
                    if run_count > 5 and job.last_run <= now - timeout:
                        # Set run_count to 0 before restarting game
                        job.run_count = 0

                        # Call restart_game function
                        self.restart_game()

                        # Set need_reset to True to always trigger 'RESET' job
                        need_reset = True

                        # Print message to console as visual feedback
                        print(
                            f"""FL Timeout triggered.  Restarting game at {
                                now}.""")

                        # Exit for loop to return to outer "while" loop and
                        # restart jobs list from beginning
                        break

                    # set FL job.last_run to current server time
                    job.last_run = self.get_server_time()

                # Check if bot is running
                if self.running is False:
                    # If running is false then create RESET event from job list
                    reset = job_list[0]
                    # Run reset event
                    for event in reset.events:
                        self.execute_event(event)

                    # Set need_reset to False after running reset event
                    need_reset = False

                    # Exit for loop and return to main while loop
                    break

                # Check if job is "RESET" and if need_reset is False
                if job.name == "RESET" and need_reset is False:
                    # Skip job if both conditions are true
                    continue

                # Check if server time has passed reset
                self.check_new_day()

                # Check if job eligible to be run
                if self.can_run(job) is True:
                    # Update current_job name
                    self.current_job = job

                    # Iterate through events in current job
                    for event in job.events:
                        if self.running is False:
                            break

                        # Execute event and check if job returns True
                        if self.execute_event(event) is True:
                            # set job_executed to true unless by RESET
                            if job.name != "RESET":
                                need_reset = True

                    # Add job to database
                    DB.insert_job(job, need_reset)

                    # Add a random delay between jobs
                    random_sleep(1)

                    # Increment run count for job
                    job.run_count += 1

                    # Check if a job actually ran successfully
                    if need_reset is True:
                        # Update 'last run' time for job
                        job.last_run = self.get_server_time()

                        # Check if 'RESET' is current job
                        if job.name == "RESET":
                            # Ensure 'RESET' does not exit jobs loop
                            need_reset = False
                            # Start next job immediately
                            continue

                        # A job completed successfully
                        else:
                            # Break from for loop and start loop again to
                            # prioritize higher priority jobs such as FL
                            break

            # Wait a few seconds between job iterations
            random_sleep(5)

    def start(self, job_list: list[Job] = None):
        """
            Starts the ClickerBot thread using the given job list
            Args:
                job_list (list of Job): The list of jobs to be run.
                                        Defaults to ClickerBot.jobs
        """
        # Set running to True
        self.running = True

        # Set paused to False
        self.paused = False

        # Set job list to be run
        if job_list is None:
            job_list = self.jobs

        # Check if thread is not running
        if self.click_thread is None or self.click_thread.is_alive() is False:
            # Create a new thread using appropriate job list
            self.click_thread = Thread(target=self.run_jobs, args=(job_list,))

            # Start the thread
            self.click_thread.start()

        # Create pseudo Job object for bot startup to be inserted into DB
        startup = Job(
            {"name": "BOT STARTED",
             "description": "Bot startup marker",
             "events": []})

        # Insert data into database for reference purposes
        DB.insert_job(startup, True)

    def stop(self):
        """
            Stops the ClickerBot thread
        """
        # Set running to False
        self.running = False

        # Makde sure click_thread exists
        if self.click_thread is not None:
            # Check if click_thread is running
            if self.click_thread.is_alive is True:
                # Join thread wait for it to stop
                self.click_thread.join()

        # Log text to console for visual feedback
        print("Bot stopped.")

    def setup_logic(self, job_logic: json) -> Job:
        """
            Converts JSON file into various variables for use within
            the ClickerBot.

            Args:
                job_logic (json): JSON file containing job logic
        """
        # Generate job objects from input JSON
        job_list = [job for job in job_logic]

        # Create list of job names to run, all others are skipped
        RUNNING_JOBS = ["RESET", "FIRST LADY"]

        # Set RUNNING_JOBS to None to disable the filtering if desired
        RUNNING_JOBS = None

        # Converts job_list to a list of Job objects and stores then in
        # ClickerBot.jobs to be accessed later
        self.jobs = [Job(job) for job in job_list]

        # Iterate through jobs in self.jobs
        for job in self.jobs:
            # Check if job should be skipped due to RUNNING_JOBS list filter
            if RUNNING_JOBS is not None and job.name not in RUNNING_JOBS:
                # Set job.skip to True
                job.skip = True
            # Job should be run
            else:
                # Set job.skip to False
                job.skip = False

        # Set 'last_run_time' to yesterday to enable all jobs to run on startup
        self.last_run_time = self.get_server_time(-1) - \
            datetime.timedelta(days=1)

        # Load hard-coded jobs to dismiss various buffs as desired
        # This needs to be refined, and has NOT been tested throroughly yet
        self.load_dismiss_buff_logic()

    def execute_event(self, event: Event) -> bool:
        """
            Executes a specific event using the given Event object

            Args:
                event (Event): The event to be executed
        """
        # Ensure bot is running
        if self.running is False:
            # Return False and exit if not running to prevent unwanted clicks
            return False

        # Check if event should be allowed to execute
        if (event.run_last is not None and
                event.run_last > self.get_server_time()
                - datetime.timedelta(hours=event.run_interval)):
            # If event is not allowed to run return False and exit
            return False

        # Set event_executed to False as default
        event_executed = False

        # Check for 're-login' popup
        # self.check_relogin_window()

        # Check if event has trigger
        if event.trigger is not None:
            # Check if trigger should be overridden or not
            if event.trigger.override is False:
                if event.trigger_type == 'if':
                    # If trigger not overridden check for trigger
                    trigger_hits = self.trigger_found(event.trigger)

                    # Check for no matches
                    if trigger_hits is None:
                        # Return flase for event_executed
                        return False
                    # Trigger was found
                    else:
                        # Set event_executed to True before next action
                        event_executed = True

                # TODO: Implement in JSON for events such as buff acceptance
                # Check if event.trigger_type is 'while'
                elif event.trigger_type == 'while':
                    # Run trigger check repeatedly
                    while True:
                        # Check for trigger
                        trigger_hits = self.trigger_found(event.trigger)

                        # Check for no matches
                        if trigger_hits is None:
                            # Break out of loop if no trigger found
                            break
                        # Trigger found
                        else:
                            # Set event_executed to True before next action
                            event_executed = True
                        # Check for event.action
                        if event.action is not None:
                            # For each hit found in current iteration
                            for hit in trigger_hits:
                                # Execute action for each hit
                                self.execute_action(event.action, [hit])
                                # Check for followup events
                                if event.events is not None:
                                    # Run followup events as needed
                                    for next_event in event.events:
                                        self.execute_event(next_event)

                # If trigger.type is not 'if' or 'while'
                else:
                    t_type = event.trigger_type
                    raise ValueError(
                        f"Trigger type {t_type} is not yet supported")

            # If trigger is overridden generate generic trigger at [0, 0]
            else:
                # Set event_executed to True if trigger is overridden
                event_executed = True

                # Create empty hit to pass into execute_action function
                trigger_hits = None

            # Check for event action
            if event.action is not None:
                # For each hit found (multiple hits can be found)
                for hit in trigger_hits:
                    # Execute action for each hit
                    self.execute_action(event.action, [hit])
                    # Check for followup events
                    if event.events is not None:
                        # Run followup events as needed
                        for next_event in event.events:
                            self.execute_event(next_event)

                    # Add random delay to disturb execution time cycle
                    random_sleep(1)
            # event.action is None
            else:
                # Run followup events as needed
                if event.events is not None:
                    for next_event in event.events:
                        self.execute_event(next_event)

            # Return status of event execution
            return event_executed

        # Check for action with no trigger
        elif event.action is not None:
            # Execute action with no trigger reference
            self.execute_action(event.action, None)

            # Set event_executed to True
            event_executed = True

            # Run followup actions as needed
            if event.events is not None:
                for next_event in event.events:
                    self.execute_event(next_event)

        # If Event has no Action or Trigger
        else:
            # Raise exception for invalid Event format
            raise ValueError("Event must have a Trigger, an Action, or both.")

        # Return status of event execution
        return event_executed

    def send_adb(self, command):
        """
            Sends specified command to ADB connected device, and returns
            the response from the device.
            Args:
                command (str): Command to be sent to ADB
        """
        # Sends command to ADB device
        output = self.ADB.execute_shell_command(command)
        # Checks output for empty (expected) response
        if output != ("", ""):
            # Logs output to console for debugging if needed
            print(f"Output: {output}")

    def send_click(self, action: Action) -> None:
        """
            Sends a click event to the ADB device using the given Action
            Args:
                action (Action): The Action containing the information about
                the click to be sent
        """
        # Creates local reference to action coordinates
        coords = action.coords

        # Creates random click count variation from action.variation value
        variance = action.variation
        variation = random.randint(-variance, variance)

        # Repeat the click the randomized number of times
        for _ in range(action.repeat + variation):
            # Dynamically generate ADB command
            command = f"input tap {coords.x} {coords.y}"

            # Send command via ADB connection
            self.send_adb(command)

            # Add a small wait between clicks
            time.sleep(action.click_delay)

            # Add random delay to disrupt patterns
            random_sleep(1)

    def send_drag(self, action: Action) -> None:
        """
            Sends a drag command to the device using the given
            variables

            Args:
                action (Action): The Action containing the information about
                the drag to be sent
        """
        # Get the start and end points for the drag
        start = action.coords[0]
        end = action.coords[1]

        # Generate random variation for repeat count is applicable
        variance = action.variation
        variation = random.randint(-variance, variance)

        # Repeat the drag the randomized number of times
        for i in range(action.repeat + variation):
            # Generate the command to send via ADB
            # including a minor variation to duration of the drag
            # to reduce the appearance of any patterns
            command = f"""input touchscreen swipe {
                start.x} {start.y} {end.x} {end.y} {
                    100 + random.randint(0, 50)}"""
            # Send the drag command via ADB
            self.send_adb(command)
            # Add a small wait between commands being sent
            time.sleep(action.click_delay)
            # Add a small random delay to further disrupt any pattern
            random_sleep(1)

    def execute_action(self,
                       action: Action,
                       trigger_hits: Coords) -> None:
        """
            Executes the Action instance events
            Args:
                action (Action): The Action instance to be executed
                trigger_hits (Coords): The coordinates of the trigger hits
                                       to use as reference for the actions
        """
        # Check for bot paused and start looping until paused is False
        while self.paused is True:
            time.sleep(1)

        # Check if current action is disabled in JSON
        if action.skip is True:
            return

        # Check for 're-login' popup
        self.check_relogin_window()

        # Check for mising trigger hits
        if trigger_hits is None:
            trigger_hits = [[0, 0]]
        # Iterate through trigger hits
        for hit in trigger_hits:
            # Copy action instance
            updated_action = copy.deepcopy(action)
            # Check if action is a click
            if action.action_type == "click":
                # Modify action coords to offset for trigger hit locations
                updated_action.coords.x += hit[0] + \
                    ((random.randint(0, 10) - 5) / 10) * 10
                updated_action.coords.y += hit[1] + \
                    ((random.randint(0, 10) - 5) / 10) * 10
                # send action to send_click function
                self.send_click(updated_action)

            # Check if action is a drag
            elif action.action_type == "drag":
                # send action to send_drag function
                self.send_drag(updated_action)
            # Check if action is a keypress
            elif action.action_type == "key":
                # Send key press to send_keypress function
                self.send_keypress(updated_action)

            # Wait for post-action delay as set in action
            time.sleep(action.delay)
            random_sleep(1)

    def send_keypress(self, action: Action) -> None:
        """
            Sends a specified keypress to the Android Device using ADB
            Args:
                action (Action): The Action containing the information about
                                 the keypress to be sent
        """
        # Get keycode from action or use "KEYCODE_BACK" as default
        keycode = action.__dict__.get('keycode') or "KEYCODE_BACK"

        # Dynamically generate ADB command
        command = f"input keyevent {keycode}"

        # Generate time variation value
        variance = action.variation
        variation = random.randint(-variance, variance)

        # Loop randomized number of times to disrupt any patterns
        for _ in range(action.repeat + variation):
            # Send key press via ADB
            self.send_adb(command)

            # Add a small wait between key presses
            time.sleep(action.click_delay)

            # Add a small random delay to further disrupt any pattern
            random_sleep(0.2)

    def get_status(self):
        """
            Creates a dictionary containing the relevant keys and values
            related to the status of the ClickerBot instance
        """
        # Create empty dictionary
        status_dict = {}
        # Get FL status
        status_dict['is first lady'] = all(
            [self.is_first_lady, self.ADB.is_game_running()])
        # Check if game running
        status_dict['game running'] = self.ADB.is_game_running()
        # Check if bot running
        status_dict['bot running'] = self.running
        # Check if bot paused
        status_dict['paused'] = self.paused
        # Check current job
        if self.current_job is not None:
            status_dict['currently running'] = self.current_job.name
        else:
            status_dict['currently running'] = None

        # Join elements of dictionary with newline between elements
        status = "\n".join([f"{key.upper()} : {str(value).upper()}" for key,
                            value in status_dict.items()])

        # Return formatted string representation of status dictionary
        return status

    @ staticmethod
    def create_mask(search_area: np.ndarray, color: Color) -> np.ndarray:
        """
            Creates a binary mask from the given input image, where any
            pixels which fall within the specified range are white, and
            all others are black

            Args:
                search_area (np.ndarray): Input image in BGR (CV2) format
                color (Color): HSV color range (lower, upper)

        """
        # Convert image to HSV color space for use with CV2 module
        hsv_img = cv2.cvtColor(search_area, cv2.COLOR_BGR2HSV)

        # Create a mask for the specified color range
        mask = cv2.inRange(hsv_img, color.lower, color.upper)

        # Check if there is a second mask to match with
        # This may be needed when matching certain shades of red
        if color.lower2 is not None and color.upper2 is not None:
            # Create a second mask using second color range
            mask2 = cv2.inRange(hsv_img, color.lower2, color.upper2)

            # Combine the two masks to get a single mask
            mask = cv2.bitwise_or(mask, mask2)

        # Set this to True to show the finished mask, and its
        # corresponding search area for debugging purposes
        DEBUG = False

        # Check if debug mode is enabled
        if DEBUG is True:
            # Display new window with "search area" input image
            cv2.imshow("Search Area", search_area)

            # Display new window with "mask" created from search area
            cv2.imshow("Mask", mask)

            # Pause and wait for key press before continuing
            cv2.waitKey(0)

            # Close all open CV2 windows
            cv2.destroyAllWindows()

        # Return the created mask
        return mask

    @ staticmethod
    def crop_image(image: np.ndarray, area: Area) -> np.ndarray:
        """
            Crops the input image to the selected area
            Args:
                image (np.ndarray): Input image in BGR (CV2) format
                area (Area): Area to crop
        """
        # Return slices np.ndarray version of input image
        return image[area.y:area.y2, area.x:area.x2]

    def trigger_found(self, trigger: Trigger) -> Coords:
        """
            Checks for presence of Trigger on screen
            Args:
                trigger (Trigger): Trigger to be checked for
        """
        # Capture current screenshot to work with
        screenshot = self.ADB.capture_screenshot()

        # Crop image to appropriate section to reduce processing time
        search_area = self.crop_image(screenshot, trigger.area)

        # Create mask from newly cropped area
        mask = self.create_mask(search_area, trigger.color)

        # Find contours in mask using CV2.findContours function
        all_contours, _ = cv2.findContours(mask,
                                           cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_SIMPLE)

        # Filter contours list using trigger.min_size to eliminate
        # trigger hits for random points with similar color values
        hit_list = [list(cv2.boundingRect(hit)) for hit
                    in all_contours
                    if cv2.contourArea(hit) > trigger.min_size]

        # Print size of all contours if needed to determine min_size values
        # print(*[cv2.boundingRect(hit) for hit in all_contours])

        # Check length of hit list
        if len(hit_list) < 1:
            # If no hits, return None
            return None

        # Adjust hit coordinates to be (x,y) relative to uncropped image
        for hit in hit_list:
            hit[0] += hit[2] // 2
            hit[1] += hit[3] // 2
            hit[0] += trigger.area.x
            hit[1] += trigger.area.y

        # Remove unnecessary elements from each hit in hit list
        hits = [hit[:2] for hit in hit_list]

        # Return list of (x,y) coordinates for each trigger hit
        return hits

    def capture_screenshot(self, filename: str = None) -> np.ndarray:
        """
            Captures the current screen and stores in memory
            Args:
                filename (str, optional): Name of the file to save screenshot.
                                         Defaults to None.
        """
        # Calls the ADBdevice.capture_screenshot() function and passes
        # the filename to the function if there is one, then returns the
        # screenshot as a np.ndarray object
        return self.ADB.capture_screenshot(filename)

    def load_dismiss_buff_logic(self) -> None:
        """
            Loads all the logic needed to dismiss each of the standard capitol
            buffs, as separate jobs, and stores them in a dictionary with the
            name of the buff as the key
        """
        # Store reference to the JSON file used to store the necessary logic
        buff_logic = 'JSON/buff_dismiss_logic.json'
        # Open the logic file
        with open(buff_logic, 'r') as f:
            # Load the JSON data
            dismiss_buff_dict_list = json.load(f)['buffs']

            # Create a dictionary using the JSON as input
            self.dismiss_buff_jobs = {buff['name'].upper(): Job(buff)
                                      for buff in dismiss_buff_dict_list}

    def dismiss_buff(self, buff_name: str) -> None:
        # Get buff logic from JSON file
        buff = self.dismiss_buff_jobs.get(buff_name.upper())
        # Ensure buff exists in JSON file
        if buff is not None:
            # Convert buff to list to pass to job run function
            buff = [buff]
            # Check if thread is still running
            if (self.click_thread is not None and
                    self.click_thread.running is True):
                # set self.running to False
                self.running = False
                # Wait for current function to finish running
                self.click_thread.join()

            # Run dismiss buff job
            self.start(buff)

            # Wait for job to finish
            self.click_thread.join()

            # Restart normal jobs
            self.start()

            return f"{buff_name.upper()} dismissed successfully!"

        # Check for empty buff name
        elif buff_name == '':
            # Exit function
            return "Missing buff name.  Usage: '!dismiss <buff name>'"

        # Buff not found in JSON
        else:
            # Log error to console for debugging purposes
            return f"{buff_name.upper()} not found"

    def ensure_game_running(self):
        """
            Check Android device list of running processes for game process
        """
        # Runs ADB.is_game_running() function until it finds the game process
        while self.ADB.is_game_running(self.game_name) is False:
            # Game is not running, so start the game process
            self.ADB.start_game(self.game_name)
            # Wait 10 seconds before checking game status again
            time.sleep(10)

        # Log game startup message to console for visual feedback
        print("Game started successfully")

        # Game should now be running so return True
        return True

    def restart_game(self):
        """
            Stops clicking then stops game via ADB command, waits 2 seconds,
            then runs the ensure_game_running() function, which starts the
            game if it is not already running and waits for it to load fully,
            then  waits 10 seconds before starting the ClickerBot be calling
            the start() function
        """
        # Stop the ClickerBot thread
        self.stop()

        # Set running flag to default of false
        running = False

        # Set time variables
        timeout_time = datetime.timedelta(minutes=2)

        # Start loop
        while True:
            # Set time for start of current iteration
            start_time = datetime.datetime.now()
            # Kills the game if running
            self.ADB.stop_game(self.game_name)

            # Short delay
            time.sleep(1)

            # Start checking if game is running
            while datetime.datetime.now() - timeout_time <= start_time:
                if self.ensure_game_running() is True:
                    running = True
                    break

                else:
                    # Wait 10 seconds before starting the ClickerBot
                    time.sleep(10)
            if running is True:
                break

        # Restart the ClickerBot
        self.start()

    # TODO: Implement realtime screen streaming to reduce time needed to
    # capture screenshots repeatedly
    def grab_screen_recording(self, duration=30):
        """
            ~~~  THIS DOES NOT CURRENTLY WORK  ~~~

        Records a 30-second video from an Android device using adb exec-out
        and saves it to a Python variable.

        Parameters:
            duration (int): Duration of the screen recording in seconds.

        Returns:
            bytes:  The binary content of the recorded video,
                    or None if an error occurs.
        """
        try:
            # Step 1: Construct the screenrecord command
            print("Starting screen recording via exec-out...")
            record_cmd = f"""screenrecord --time-limit {
                duration} --output-format=h264"""

            # Step 2: Execute the command and capture the video output
            video_data = self.ADB.device.exec_out(record_cmd)

            # Step 3: Error checking
            if not video_data:
                print("Error: No video data was returned.")
                return None

            # Check if the video starts with a valid H.264 NAL unit start code
            if not video_data.startswith(b"\x00\x00\x00\x01"):
                print("Error: Video does not appear to be valid H.264 stream.")
                return None

            # Step 4: Return the validated video data
            print("Video recorded and validated successfully.")
            return video_data

        except Exception as e:
            print(f"Error during video recording: {e}")
            return None


def load_job_logic(logic_file: str):
    """
        Loads job logic from a JSON file and returns it as a dictionary
    """
    # Open file
    with open(logic_file, 'r') as f:
        # Load JSON file
        logic = json.load(f)

        # Extract clicker settings and return as dictionary
        return logic['settings']['clicker']


def random_sleep(wait_time: int = 2) -> None:
    """
        Generates a random number between 1 and 2, and multiplies it times
        wait_time to generate a random time between 1x and 2x the original
        wait_time
    """
    # Generate random number betwen 1 and 2
    TIME_MULTIPLIER = random.random() + 1
    # Multiply times the original time and sleep that duration of seconds
    time.sleep(wait_time * TIME_MULTIPLIER)


def main():
    """
        Main entry point of script
    """
    # Load JSON
    logic = load_job_logic(TEST_JSON)
    # Uses logic to initialize ClickerBot instance
    ClickerBot(logic)


if __name__ == "__main__":
    main()
