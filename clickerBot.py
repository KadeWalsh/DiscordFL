import random
from io import BytesIO
import json
import cv2
import numpy as np
import time
import copy
import datetime
from threading import Thread
import ffmpeg

from adbDevice import ADBdevice
from classes import Job, Event, Trigger, Area, Color, Coords, Action

TEST_JSON = 'working.json'
IObuffer = BytesIO()


class ClickerBot:
    def __init__(self, startup_data: json = TEST_JSON):
        self.setup_logic(startup_data['jobs'])
        self.ADB = ADBdevice(startup_data['settings'])
        self.running = True
        self.is_first_lady = True
        self.time_offset = startup_data['time_offset']
        self.thread = None
        self.status = self.get_status()
        self.game_name = 'com.fun.lastwar.gp'
        self.click_thread = None
        self.start()

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

        if job.daily_limit is None:
            if job.run_interval is None or job.run_interval == 0:
                return True

            current_time = self.get_server_time()
            run_after = (job.last_run +
                         datetime.timedelta(hours=job.run_interval))

            return current_time > run_after

        else:
            return job.daily_limit > job.run_count

    def run_jobs(self, job_list=None):
        if job_list is None or job_list == [None]:
            job_list = self.jobs

        # Set job_executed to true to trigger screen reset on startup
        job_executed = True

        # Create bot loop
        while self.running is True:

            # Get current server time
            server_time = self.get_server_time()
            formatted_time = server_time.strftime("%d/%m %H:%M:%S")
            job_executed = False
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

                # Check if server time has passed reset
                self.check_new_day()

                # Check if job eligible to be run
                if self.can_run(job) is True:
                    # Print current time and job name to console
                    print(f"{formatted_time}: Running {job.name}.")

                    # Update 'last run' time for job
                    job.last_run = server_time

                    # Iterate through events in current job
                    for event in job.events:

                        # Execute event and check if job returns True
                        if self.execute_event(event) is True:
                            # set job_executed to true unless by RESET
                            if job.name != "RESET":
                                job_executed = True

                        random_sleep(2)

                    # Update last_run time for job
                    job.last_run = server_time

                    # Increment run count for job
                    job.run_count += 1

                    RESTART_CYCLE_NAME = "FIRST LADY"
                    # If FL jobs executed
                    if job.name == RESTART_CYCLE_NAME and job_executed is True:
                        print("FL Executed successfully!")
                        # Return to start of loop to improve FL performance
                        break
                    elif job.name == "RESET":
                        job_executed = False

                # Update last job and server last_run_times
                self.last_run_time = server_time

            # Wait 2 seconds between job iterations if no job was executed
            if job_executed is True:
                random_sleep(20)

    def start(self, job_list: list[Job] = [None]):
        print("Starting ClickerBot...")
        self.running = True
        if self.click_thread is None or self.click_thread.is_alive() is False:
            self.click_thread = Thread(target=self.run_jobs, args=(job_list,))
            self.click_thread.start()

        print("ClickerBot started.")

    def stop(self):
        self.running = False
        if self.click_thread is not None:
            if self.click_thread.is_alive is True:
                self.click_thread.join()
        print("Bot stopped.")

    def setup_logic(self, job_logic: json) -> Job:
        # Generate job objects from input JSON
        job_list = [job for job in job_logic]
        self.jobs = [Job(job) for job in job_list]

        # Set 'last_run_time' to yesterday to enable all jobs to run on init
        yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
        self.last_run_time = yesterday
        self.load_dismiss_buff_logic()

    def execute_event(self, event: Event) -> bool:
        if (event.run_last is not None and
                event.run_last > self.get_server_time()
                - datetime.timedelta(hours=event.run_interval)):
            return False

        event_executed = False

        # Check if event has trigger
        if event.trigger is not None:
            # Check if trigger should be overridden or not
            if event.trigger.override is False:
                # If trigger not overridden check for trigger
                trigger_hits = self.trigger_found(event.trigger)
                # Check for no matches
                if trigger_hits is None:
                    # Return flase for event_executed
                    return False

                else:
                    event_executed = True

            # If trigger is overridden generate generic trigger at [0, 0]
            else:
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
        for _ in range(action.repeat):
            command = f"input tap {coords.x} {coords.y}"
            self.send_adb(command)
            time.sleep(action.click_delay)
            random_sleep(1)

    def send_drag(self, action: Action) -> None:
        start = action.coords[0]
        end = action.coords[1]
        for i in range(action.repeat):
            command = f"input touchscreen swipe {
                start.x} {start.y} {end.x} {end.y} {100 + random.randint(0, 50)}"
            self.send_adb(command)
            time.sleep(action.click_delay)
            random_sleep(1)

    def execute_action(self,
                       action: Action,
                       trigger_hits: Coords) -> None:
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
        for _ in range(action.repeat):
            self.send_adb(command)
            time.sleep(action.click_delay)
            random_sleep(0.2)

    def get_status(self):
        status_dict = {}
        status_dict['is first lady'] = all(
            [self.is_first_lady, self.ADB.is_game_running()])
        status_dict['game running'] = self.ADB.is_game_running()

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

        # Check for empty buff name
        elif buff_name == '':
            # Exit function
            return

        # Buff not found in JSON
        else:
            # Log error to console for debugging purposes
            print(f"{buff_name.upper()} not found...")

    def ensure_game_running(self):
        while self.ADB.is_game_running(self.game_name) is False:
            self.ADB.start_game(self.game_name)
            time.sleep(10)

        print("Game started successfully")
        return True

    def restart_game(self):
        self.ADB.stop_game(self.game_name)
        time.sleep(5)
        self.ensure_game_running()

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
            record_cmd = f"screenrecord --time-limit {
                duration} --output-format=h264"

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
    time.sleep(random.random() * max_time)


def main():
    logic = load_job_logic(TEST_JSON)
    bot = ClickerBot(logic)

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
