import datetime


class CommonPrintFormat:
    def __repr__(self):
        return f'{self.__dict__.items()}'

    def __str__(self):
        return f'{[k for k in self.__dict__.items()]}'


class Area(CommonPrintFormat):
    def __init__(self, coords: list[int, int, int, int]):
        self.x, self.y, self.x2, self.y2 = coords
        self.w = self.x2 - self.x
        self.h = self.y2 - self.y


class Coords(CommonPrintFormat):
    def __init__(self, coords: list[int, int, int]):
        self.x, self.y = coords


class Color(CommonPrintFormat):
    def __init__(self, color_range: list[(int, int, int)]):
        if len(color_range) < 2:
            raise ValueError("Color range should contain at least 2 values.")
        if len(color_range) > 4:
            raise ValueError("Color range should contain at most 4 values.")
        self.lower = tuple(color_range[0])
        self.upper = tuple(color_range[1])
        self.lower2 = tuple(color_range[2]) if len(color_range) == 4 else None
        self.upper2 = tuple(color_range[3]) if len(color_range) == 4 else None


class Trigger(CommonPrintFormat):
    def __init__(self, trigger: dict):
        self.area = Area(trigger['area'])
        self.color = Color(trigger['color'])
        self.min_size = trigger['min_size']
        self.ref_image = trigger.get('ref_img') or None
        self.time_offset = (datetime.datetime.now()
                            - datetime.timedelta(
                                seconds=trigger.get('time_offset') or 0))
        self.override = trigger.get('override') or False


class Action(CommonPrintFormat):
    def __init__(self, action_data: dict):
        self.description = action_data['description']
        self.action_type = action_data['action_type']
        if action_data.get('action_type') == 'drag':
            self.coords = [Coords(action_data['coords'][:2]),
                           Coords(action_data['coords'][2:])]
        else:
            self.coords = Coords(action_data['coords'])

        self.repeat = action_data['repeat']
        self.delay = action_data['delay']
        self.action_type = action_data['action_type']
        self.click_delay = action_data['click_delay']


class Event(CommonPrintFormat):
    def __init__(self, event: dict):
        self.description = event['description']
        self.action = None
        self.trigger = None
        self.events = None
        if event.get('trigger') is not None:
            self.trigger = Trigger(event['trigger'])
        if event.get('action') is not None:
            self.action = Action(event['action'])
        if event.get('events') is not None:
            self.events = [Event(event) for event in event['events']]
        self.run_interval = event.get('run_interval') or None
        if self.run_interval is not None:
            self.run_last = datetime.datetime.now(
            ) - datetime.timedelta(event.get('run_last'))


class Job(CommonPrintFormat):
    def __init__(self, job_data: dict):
        self.name = job_data['name']
        self.description = job_data['description']
        if job_data['events'] is not None:
            self.events = [Event(event) for event in job_data['events']]
        else:
            self.events = None

        self.last_run = (datetime.datetime.now() -
                         datetime.timedelta(days=1))
        self.last_run.replace(tzinfo=None)
        self.daily_limit = job_data.get('daily_limit') or None
        self.run_count = 0
        self.run_interval = job_data.get('run_interval') or 0
        self.skip = job_data.get('skip') or False
