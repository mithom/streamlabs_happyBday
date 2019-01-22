import json
import codecs

Parent = None


class Settings(object):
    # do not use multiple instances of this version of the class, as it uses class
    # variables in order to avoid being in __dict__
    settings_file = ""
    script_name = ""

    def __init__(self, settings_file, script_name):
        Settings.settings_file = settings_file
        Settings.script_name = script_name
        try:
            with codecs.open(self.settings_file, encoding="utf-8-sig", mode="r") as f:
                self.__dict__ = json.load(f, encoding="utf-8")
        except:
            # Command names
            self.format = "%d/%m/%Y"
            self.bday_cmd = '!birthday'
            self.add_me = True

    def reload(self, json_data):
        """ Reload settings from Chatbot user interface by given json data. """
        self.__dict__ = json.loads(json_data, encoding="utf-8")
        self.save()
        return

    def save(self):
        """ Save settings contained within to .json and .js settings files. """
        try:
            with codecs.open(self.settings_file, encoding="utf-8-sig", mode="w+") as f:
                json.dump(self.__dict__, f, encoding="utf-8", ensure_ascii=False)
            with codecs.open(self.settings_file.replace("json", "js"), encoding="utf-8-sig", mode="w+") as f:
                f.write("var settings = {0};".format(json.dumps(self.__dict__, encoding='utf-8', ensure_ascii=False)))
        except:
            Parent.Log(self.script_name, "Failed to save settings to file.")
        return
