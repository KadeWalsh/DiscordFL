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
    def __init__(self, startup_data: json = TEST_JSON):
        self.setup_logic(startup_data['jobs'])
        print(startup_data['settings'])
        self.ADB = ADBdevice(startup_data['settings'])
        self.running = True
        self.is_first_lady = True
        self.time_offset = startup_data['time_offset']
        self.idle_timeout = startup_data.get('idle_timeout') or 10
        self.thread = None
        self.game_name = 'com.fun.lastwar.gp'
        self.click_thread = None
        self.current_job = None
        self.status = self.get_status()

        # Add flag to enable pause/resume functionality mid-event loop
        self.paused = False

    def check_relogin_window(self):
        # Check if the game is still running on the device
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

        close_relogin = Event(event_dict)

        if self.trigger_found(close_relogin.trigger):
            login_job = Job({"name": "Re-login window closed",
                            "description": "Close the re-login popup window",
                             "events": []})
            login_job.last_run += datetime.timedelta(days=1)
            self.insert_job(login_job)
            self.execute_action(close_relogin.action)

    def reload_jobs(self, filename: str = 'actual.json'):
        with open(filename, 'r') as f:
            json_file = json.load(f)
            self.setup_logic(json_file['settings']['clicker']['jobs'])

    def get_server_time(self):
        UTC = datetime.datetime.now(datetime.timezone.utc)
        server_time = UTC + datetime.timedelta(hours=self.time_offset)

        return server_time.replace(tzinfo=None)

    def check_new_day(self):
        if self.get_server_time().day != self.last_run_time.day:
            for job in self.jobs:
                job.run_count = 0
            self.last_run_time = self.get_server_time()

    def can_run(self, job: Job) -> bool:
        if job.skip is True:
            return False

        elif job.last_run is None:
            job.last_run = self.get_server_time()
            return True

        random_interval = job.run_interval + \
            (random.random() * job.run_interval)

        run_after = (job.last_run +
                     datetime.timedelta(hours=random_interval))

        if job.daily_limit is None:
            if job.run_interval is None or job.run_interval == 0:
                return True

            current_time = self.get_server_time()
            random_interval = job.run_interval + \
                (random.random() * job.run_interval)
            run_after = (job.last_run +
                         datetime.timedelta(hours=random_interval))

            return current_time > run_after

        else:
            conditions = [job.daily_limit > job.run_count,
                          self.get_server_time() > run_after]
            return all(conditions)

    def run_jobs(self, job_list=None):
        if job_list is None or job_list == [None]:
            job_list = self.jobs

        # Set job_executed to true to trigger screen reset on startup
        need_reset = True

        # Create bot loop
        while self.running is True:
            # Iterate through jobs
            for job in job_list:
                # Check if game is not running, start it if necessary
                if self.ADB.is_game_running() is False:
                    # Kill game if still in memory
                    self.ADB.stop_game()
                    random_sleep(10)
                    # Start game
                    self.ADB.start_game()
                    time.sleep(30)
                    # Exit for loop and restart job
                    break

                if (job.name == "FIRST LADY" and job.run_count > 5 and
                        (job.last_run <= self.get_server_time()
                         - datetime.timedelta(minutes=self.idle_timeout))):
                    job.run_count = 0
                    job.last_run = self.get_server_time()
                    self.restart_game()
                    need_reset = True
                    print(f"""FL Timeout triggered.  Restarting game at {
                          self.get_server_time()}.""")
                    break

                if self.running is False:
                    reset = job_list[0]
                    for event in reset.events:
                        self.execute_event(event)
                    break

                if job.name == "RESET" and need_reset is False:
                    continue

                # Check if server time has passed reset
                self.check_new_day()

                # Check if job eligible to be run
                if self.can_run(job) is True:
                    # Update current_job name
                    self.current_job = job.name

                    # Print current time and job name to console
                    # print(f"Starting {job.name} Job...")

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
                            # Break from for loop and start again
                            break

                # Update last job and server last_run_times
                self.last_run_time = self.get_server_time()

            # Wait a few seconds between job iterations
            random_sleep(5)

    def start(self, job_list: list[Job] = None):
        print("Starting ClickerBot...")
        self.running = True
        self.paused = False
        if job_list is None:
            job_list = self.jobs
        if self.click_thread is None or self.click_thread.is_alive() is False:
            self.click_thread = Thread(target=self.run_jobs, args=(job_list,))
            self.click_thread.start()

        startup = Job(
            {"name": "BOT STARTED",
             "description": "Bot startup marker",
             "events": []})
        startup.last_run = self.get_server_time()

        DB.insert_job(startup)

    def stop(self):
        self.running = False
        if self.click_thread is not None:
            if self.click_thread.is_alive is True:
                self.click_thread.join()
        print("Bot stopped.")

    def setup_logic(self, job_logic: json) -> Job:
        # Generate job objects from input JSON
        job_list = [job for job in job_logic]
        # RUNNING_JOBS = ["RESET", "FIRST LADY"]
        RUNNING_JOBS = None
        self.jobs = [Job(job) for job in job_list]
        for job in self.jobs:
            if RUNNING_JOBS is not None and job.name not in RUNNING_JOBS:
                job.skip = True

            else:
                job.skip = False

        # Set 'last_run_time' to yesterday to enable all jobs to run on init
        yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
        self.last_run_time = yesterday

        self.load_dismiss_buff_logic()

    def execute_event(self, event: Event) -> bool:
        if self.running is False:
            return False

        if (event.run_last is not None and
                event.run_last > self.get_server_time()
                - datetime.timedelta(hours=event.run_interval)):
            return False

        # Set event_executed to False as default
        event_executed = False

        # Check for 're-login' popup
        self.check_relogin_window()

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
                    else:
                        event_executed = True

                elif event.trigger_type == 'while':
                    while True:
                        trigger_hits = self.trigger_found(event.trigger)

                        if trigger_hits is None:
                            break
                        else:
                            event_executed = True

                        if event.action is not None:
                            for hit in trigger_hits:
                                self.execute_action(event.action, [hit])

                                if event.events is not None:
                                    for next_event in event.events:
                                        self.execute_event(next_event)

                else:
                    event_executed = True

            # If trigger is overridden generate generic trigger at [0, 0]
            else:
                # Set event_executed to True if trigger is overridden
                event_executed = True

                # Create generic trigger hits
                trigger_hits = [[0, 0]]

            if event.action is not None:
                for hit in trigger_hits:
                    self.execute_action(event.action, [hit])
                    if event.events is not None:
                        for next_event in event.events:
                            self.execute_event(next_event)
                    random_sleep(1)

            else:
                if event.events is not None:
                    for next_event in event.events:
                        self.execute_event(next_event)

            return event_executed

        elif event.action is not None:
            self.execute_action(event.action, None)
            event_executed = True

            if event.events is not None:
                for next_event in event.events:
                    self.execute_event(next_event)

        else:
            raise ValueError("Event must have a Trigger, an Action, or both.")

        return event_executed

    def send_adb(self, command):
        output = self.ADB.execute_shell_command(command)
        if output != ("", ""):
            print(f"Output: {output}")

    def send_click(self, action: Action) -> None:
        coords = action.coords

        variance = action.variation
        variation = random.randint(-variance, variance)

        for _ in range(action.repeat + variation):
            command = f"input tap {coords.x} {coords.y}"
            self.send_adb(command)
            time.sleep(action.click_delay)
            random_sleep(1)

    def send_drag(self, action: Action) -> None:
        start = action.coords[0]
        end = action.coords[1]
        variance = action.variation
        variation = random.randint(-variance, variance)

        for i in range(action.repeat + variation):
            command = f"""input touchscreen swipe {
                start.x} {start.y} {end.x} {end.y} {
                    100 + random.randint(0, 50)}"""
            self.send_adb(command)
            time.sleep(action.click_delay)
            random_sleep(1)

    def execute_action(self,
                       action: Action,
                       trigger_hits: Coords) -> None:
        while self.paused is True:
            time.sleep(1)
        # Check if current action is disabled in JSON
        if action.skip is True:
            return

        # Check for 're-login' popup
        self.check_relogin_window()

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
        keycode = action.__dict__.get('keycode') or "KEYCODE_BACK"
        command = f"input keyevent {keycode}"
        variance = action.variation
        variation = random.randint(-variance, variance)

        for _ in range(action.repeat + variation):
            self.send_adb(command)
            time.sleep(action.click_delay)
            random_sleep(0.2)

    def get_status(self):
        status_dict = {}
        status_dict['is first lady'] = all(
            [self.is_first_lady, self.ADB.is_game_running()])
        status_dict['game running'] = self.ADB.is_game_running()
        status_dict['bot running'] = self.running
        status_dict['currently running'] = self.current_job or "None"

        status = "\n".join([f"{key.upper()} : {str(value).upper()}" for key,
                            value in status_dict.items()])

        return status

    @ staticmethod
    def create_mask(search_area: np.ndarray, color: Color) -> np.ndarray:
        hsv_img = cv2.cvtColor(search_area, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv_img, color.lower, color.upper)

        if color.lower2 is not None and color.upper2 is not None:
            mask2 = cv2.inRange(hsv_img, color.lower2, color.upper2)
            mask = cv2.bitwise_or(mask, mask2)

        DEBUG = False

        if DEBUG is True:
            cv2.imshow("Search Area", search_area)
            cv2.imshow("Mask", mask)
            cv2.waitKey(0)
            cv2.destroyAllWindows()

        return mask

    @ staticmethod
    def crop_image(image: np.ndarray, area: Area) -> np.ndarray:
        return image[area.y:area.y2, area.x:area.x2]

    def trigger_found(self, trigger: Trigger) -> Coords:
        screenshot = self.ADB.capture_screenshot()
        search_area = self.crop_image(screenshot, trigger.area)
        mask = self.create_mask(search_area, trigger.color)
        all_contours, _ = cv2.findContours(mask,
                                           cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_SIMPLE)
        hit_list = [list(cv2.boundingRect(hit)) for hit
                    in all_contours
                    if cv2.contourArea(hit) > trigger.min_size]
        # Print size of all contours if needed to determine min_size values
        # print(*[cv2.boundingRect(hit) for hit in all_contours])
        if len(hit_list) < 1:
            return None

        for hit in hit_list:
            hit[0] += hit[2] // 2
            hit[1] += hit[3] // 2
            hit[0] += trigger.area.x
            hit[1] += trigger.area.y

        hits = [hit[:2] for hit in hit_list]

        return hits

    def capture_screenshot(self, filename: str = None) -> np.ndarray:
        return self.ADB.capture_screenshot(filename)

    def load_dismiss_buff_logic(self) -> None:
        buff_logic = 'buff_dismiss_logic.json'
        with open(buff_logic, 'r') as f:
            self.dismiss_buff_dict_list = json.load(f)['buffs']

            self.dismiss_buff_jobs = {buff['name']: Job(buff)
                                      for buff in self.dismiss_buff_dict_list}

    def dismiss_buff(self, buff_name: str) -> None:
        # Get buff logic from JSON file
        buff = self.dismiss_buff_jobs.get(buff_name)
        # Ensure buff exists in JSON file
        if buff is not None:
            # Convert buff to list to pass to job run function
            buff = [buff]
            # Check if thread is still running
            if self.thread is not None and self.thread.running is True:
                # set self.running to False
                self.running = False
                # Wait for current function to finish running
                self.thread.join()

            # Run dismiss buff job
            self.start(buff)

            # Wait for job to finish
            self.thread.join()

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
        while self.ADB.is_game_running(self.game_name) is False:
            self.ADB.start_game(self.game_name)
            time.sleep(10)

        print("Game started successfully")
        return True

    def restart_game(self):
        self.ADB.stop_game(self.game_name)
        time.sleep(2)
        self.ensure_game_running()
        time.sleep(10)
        self.start()

    def grab_screen_recording(self, duration=30):
        """
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
    with open(logic_file, 'r') as f:
        logic = json.load(f)

        return logic['settings']['clicker']


def random_sleep(max_time: int = 2) -> None:
    TIME_MULTIPLIER = random.random() + 1
    time.sleep(max_time * TIME_MULTIPLIER)


def main():
    logic = load_job_logic(TEST_JSON)
    bot = ClickerBot(logic)


if __name__ == "__main__":
    main()
