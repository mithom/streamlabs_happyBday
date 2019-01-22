from functools import wraps
from threading import Lock
from datetime import datetime, timedelta, date
import json
import os
import clr

clr.AddReference("IronPython.SQLite.dll")
import sqlite3

Parent = None


def send_stream_message(f):
    @wraps(f)
    def sender(*args, **kwargs):
        value = f(*args, **kwargs)
        if value is not None:
            Parent.SendStreamMessage(args[0].format_message(*value))

    return sender


def connect(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            with args[0].get_connection() as conn:
                # not using the constraints right now, would only slow things down
                # conn.execute("""PRAGMA foreign_keys = ON""")
                return f(*args, conn=conn, **kwargs)
        finally:
            if 'conn' in locals():
                # noinspection PyUnboundLocalVariable
                conn.close()
            args[0].db_lock.release()

    return wrapper


# noinspection PyUnboundLocalVariable
class HappyBDay(object):
    db_lock = Lock()

    # ---------------------------------------
    #   init functions
    # ---------------------------------------
    def __init__(self, script_settings, script_name, db_directory):
        self.scriptSettings = script_settings
        self.script_name = script_name
        self.db_directory = db_directory
        self.session = None

        self.prepare_db()

    @connect
    def prepare_db(self, conn):
        Session.create_table_if_not_exists(conn)
        BDay.create_table_if_not_exists(conn)

        if Parent.IsLive():
            self.session = self.get_session(conn)

    def get_session(self, conn):
        session = Session.find_last_session(conn)
        if session is None or \
                (session.session_end is not None and session.session_end + timedelta(minutes=45) < datetime.now()):
            session = Session.create(conn)
            self.send_birthdays(session, conn)
            return session
        return session

    def send_birthdays(self, session, conn):
        bdays = BDay.find_since_past_stream(session, conn)
        names = map(lambda x: x.user_name, bdays)
        Parent.SendStreamWhisper(Parent.GetChannelName(), "birthday since last stream " + ", ".join(names))

    # ---------------------------------------
    #   interface functions
    # ---------------------------------------
    @connect
    def tick(self, conn):
        if Parent.IsLive:
            if self.session is None:
                self.session = self.get_session(conn)
            else:
                now = datetime.now()
                self.session.session_end = now
                self.session.save(conn)
        elif self.session is not None:
            self.session = None

    def commands(self):
        return [{},  # no 0 arg commands
                {
                    self.scriptSettings.bday_cmd: self.set_bday,
                }, {
                    self.scriptSettings.bday_cmd: self.mod_set_bday,
                }]

    def reset_db(self):
        self.db_lock.acquire()
        os.remove(os.path.join(self.db_directory, "database.db"))
        self.db_lock.release()
        Parent.Log(self.script_name, 'reset successful')

    # ---------------------------------------
    #   command functions
    # ---------------------------------------
    @send_stream_message
    @connect
    def set_bday(self, user_id, username, date_str, conn):
        if self.is_follower(username):
            try:
                bday = datetime.strptime(date_str, self.scriptSettings.format).date()
                if BDay.find(user_id, conn) is None:
                    BDay.create(user_id, username, bday, conn)
                    return "successfully saved your birthday, @{0}", username
                else:
                    return "@{0} , please ask a mod to update your birthday if you made a mistake", username
            except:
                return
        return "@{0} , please follow before saving your birthday", username

    def mod_set_bday(self, user_id, username, target_name, date_str):
        Parent.SendStreamMessage(self.format_message(
            "when you need to send multiple message, or don't want to wait until end of function to send message"
        ))

    # ---------------------------------------
    #   auxiliary functions
    # ---------------------------------------
    def format_message(self, msg, *args, **kwargs):
        if self.scriptSettings.add_me and not kwargs.get('whisper', False):
            msg = "/me " + msg
        return msg.format(*args, **kwargs)

    # because follower isn't a default permission in chatbot, thanks to @ocgineer for better version of decapi
    @staticmethod
    def is_follower(username):
        json_data = json.loads(Parent.GetRequest(
            "https://api.ocgineer.com/twitch/followage/{0}/{1}".format(Parent.GetChannelName(), username), {}))
        if json_data["status"] == 200:
            return True
        return False

    def get_connection(self):
        if self.db_lock.acquire():
            return sqlite3.connect(os.path.join(self.db_directory, "database.db"), detect_types=sqlite3.PARSE_DECLTYPES)
        else:
            Parent.Log(self.script_name, 'could not acquire db lock in time (5s)')


class BDay(object):
    def __init__(self, user_id, user_name, birthday, conn):
        self.conn = conn

        self.birthday = birthday
        self.user_id = user_id
        self.user_name = user_name

    def save(self):
        self.conn.execute("""UPDATE birthdays SET birthday = ? WHERE user_id = ?""", (self.birthday, self.user_id))

    @classmethod
    def find(cls, user_id, conn):
        cursor = conn.execute("""SELECT user_id, username, birthday FROM birthdays WHERE user_id = ?""", (user_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return cls(*row, conn=conn)

    @classmethod
    def find_by_today(cls, conn):
        cursor = conn.execute("""SELECT user_id, username, birthday FROM birthdays
                                        WHERE birthday = ?""", (date.today(),))
        return map(lambda row: cls(*row, conn=conn), cursor)

    @classmethod
    def find_since_past_stream(cls, current, conn):
        prev_session = Session.find_prev_session(current, conn)
        if prev_session is None:
            prev_end = date.today() - timedelta(days=1)
        else:
            prev_end = prev_session.session_start
        cursor = conn.execute(
            """SELECT user_id, username, birthday FROM
                (SELECT date(birthday, '+'||(date('NOW','START OF YEAR') - date(birthday, 'START OF YEAR'))||' years') 
                as bd, user_id, username, birthday FROM birthdays)
            WHERE bd > ? and bd <= ?""", (prev_end, date.today(),))
        return map(lambda row: cls(*row, conn=conn), cursor)

    @classmethod
    def create(cls, user_id, user_name, bday, conn):
        conn.execute("""INSERT INTO birthdays (user_id, username, birthday) VALUES (?, ?, ?)""",
                     (user_id, user_name, bday,))
        return cls(user_id, user_name, bday, conn)

    @staticmethod
    def create_table_if_not_exists(conn):
        conn.execute("""CREATE TABLE IF NOT EXISTS birthdays
             (user_id    TEXT   PRIMARY KEY NOT NULL,
             username    TEXT   NOT NULL,
             birthday    DATE   NOT NULL);""")


class Session(object):
    def __init__(self, id_, session_start, session_end, conn):
        self.id_ = id_
        self.session_start = session_start
        self.session_end = session_end

        self.conn = conn

    def save(self, conn=None):
        if conn is not None:
            self.conn = conn
        self.conn.execute("""UPDATE sessions SET session_end = ? WHERE id = ?""", (self.session_end, self.id_))

    @classmethod
    def create(cls, conn):
        now = datetime.now()
        cursor = conn.execute("""INSERT INTO sessions (session_start) VALUES (?)""", (now,))
        return cls(cursor.lastrowid, now, None, conn)

    @classmethod
    def find_last_session(cls, conn):
        cursor = conn.execute("""SELECT * FROM sessions ORDER BY session_start DESC LIMIT 1""")
        row = cursor.fetchone()
        if row is None:
            return None
        return cls(*row, conn=conn)

    @classmethod
    def find_prev_session(cls, current, conn):
        if type(cls) is not int:
            current = current.id_
        cursor = conn.execute("""SELECT * FROM sessions WHERE id != ? ORDER BY session_start DESC LIMIT 1""",
                              (current,))
        row = cursor.fetchone()
        if row is None:
            return None
        return cls(*row, conn=conn)

    @staticmethod
    def create_table_if_not_exists(conn):
        conn.execute("""CREATE TABLE IF NOT EXISTS sessions
         (id            INTEGER     PRIMARY KEY NOT NULL,
         session_start  TIMESTAMP   NOT NULL,
         session_end    TIMESTAMP);""")
