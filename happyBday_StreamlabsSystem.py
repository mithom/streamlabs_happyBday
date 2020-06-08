# ---------------------------------------
#   Import Libraries
# ---------------------------------------
import os
import time
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "lib"))  # Point at lib folder for classes / references
import clr
clr.AddReference("IronPython.Modules.dll")

import happyBday
import bdaySettings

# ---------------------------------------
#   [Required]  Script Information
# ---------------------------------------
ScriptName = "happyBday"
Website = "https://www.twitch.tv/mi_thom"
Description = "tells you who has had his birthday since you last streamed"
Creator = "mi_thom / powerclan"
Version = "0.0.1"

# ---------------------------------------
#   Global Variables
# ---------------------------------------
m_settings_file = os.path.join(os.path.dirname(__file__), "Settings", "happyBday_settings.json")
ScriptSettings = None
happy_bday = None
next_tick = 0


# ---------------------------------------
#   main interface
# ---------------------------------------
# noinspection PyPep8Naming
def Init():
    global ScriptSettings, happy_bday
    # Insert Parent in submodules
    happyBday.Parent = Parent
    bdaySettings.Parent = Parent

    #   Create Settings and db Directory
    settings_directory = os.path.join(os.path.dirname(__file__), "Settings")
    if not os.path.exists(settings_directory):
        os.makedirs(settings_directory)

    db_directory = os.path.join(os.path.dirname(__file__), "db")
    if not os.path.exists(db_directory):
        os.makedirs(db_directory)

    #   Load settings
    ScriptSettings = bdaySettings.BdaySettings(m_settings_file, ScriptName)

    # Create game
    happy_bday = happyBday.HappyBDay(ScriptSettings, ScriptName, db_directory)


# noinspection PyPep8Naming
def ReloadSettings(jsondata):
    ScriptSettings.reload(jsondata)
    happy_bday.apply_settings()


# noinspection PyPep8Naming
def Unload():
    ScriptSettings.save()


# noinspection PyPep8Naming
def ScriptToggle(state):
    global next_tick
    # next_tick is time remaining in tick while script is toggled off.
    if state:
        next_tick -= time.time()
    else:
        next_tick += time.time()


# noinspection PyPep8Naming
def Tick():
    if time.time() >= next_tick:
        set_next_tick()
        happy_bday.tick()


# noinspection PyPep8Naming
def Execute(data):
    if data.IsChatMessage() or data.IsWhisper():
        p_count = data.GetParamCount()
        command_functions = happy_bday.commands()
        if p_count <= len(command_functions):
            param0 = data.GetParam(0)
            if param0 in command_functions[p_count-1]:
                command_functions[p_count-1][param0](data.User, data.UserName, *data.Message.split()[1:])


push_time = 0
push_count = 0


def ResetDatabase():
    global push_time, push_count
    if time.time() > push_time:
        push_count = 0
        push_time = time.time() + 5
    push_count += 1
    if push_count >= 5:
        happy_bday.reset_db()
        Init()


# ---------------------------------------
#   auxiliary functions
# ---------------------------------------
def set_next_tick():
    global next_tick
    next_tick = time.time() + 30
