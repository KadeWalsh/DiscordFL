import sqlite3
from classes import Job
import datetime

DB_FILE = 'FL_BOT.db'
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cur = conn.cursor()

# Create tables


def create_tables():
    cur.execute('''CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    last_run DATETIME
                    )''')

    conn.commit()


def insert_job(job: Job, conn=conn):
    current_time = datetime.datetime.now(
        datetime.timezone.utc) + datetime.timedelta(hours=-2)
    current_time.replace(tzinfo=None)
    cur.execute('''INSERT INTO jobs (name, description, last_run)
                    VALUES (?,?,?)''', (job.name,
                                        job.description,
                                        current_time))

    conn.commit()


create_tables()
