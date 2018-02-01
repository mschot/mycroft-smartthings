from os.path import dirname, join

from adapt.intent import IntentBuilder
from mycroft.skills.core import MycroftSkill
from mycroft.util.log import getLogger

from os.path import dirname, join
from requests import get, post
from requests.exceptions import ConnectionError
from fuzzywuzzy import fuzz
import json

__author__ = 'robconnolly, btotharye, nielstron'
LOGGER = getLogger(__name__)


class SmartThingsClient(object):
    def __init__(self, host, password, portnum, ssl=False, verify=True):
        self.ssl = ssl
        self.verify = verify
        if portnum is None:
            portnum = 8123
        if self.ssl:
            self.url = "https://%s:%d" % (host, portnum)
        else:
            self.url = "http://%s:%d" % (host, portnum)
        self.headers = {
            'x-ha-access': password,
            'Content-Type': 'application/json'
        }

    def find_entity(self, entity, types):
        if self.ssl:
            req = get("%s/api/states" %
                      self.url, headers=self.headers, verify=self.verify)
        else:
            req = get("%s/api/states" % self.url, headers=self.headers)

        if req.status_code == 200:
            # require a score above 50%
            best_score = 50
            best_entity = None
            for state in req.json():
                try:
                    if state['entity_id'].split(".")[0] in types:
                        # something like temperature outside
                        # should score on "outside temperature sensor"
                        # and repetitions should not count on my behalf
                        score = fuzz.token_set_ratio(
                            entity,
                            state['attributes']['friendly_name'].lower())
                        if score > best_score:
                            best_score = score
                            best_entity = {
                                "id": state['entity_id'],
                                "dev_name": state['attributes']
                                ['friendly_name'],
                                "state": state['state']}
                        score = fuzz.token_set_ratio(
                            entity,
                            state['entity_id'].lower())
                        if score > best_score:
                            best_score = score
                            best_entity = {
                                "id": state['entity_id'],
                                "dev_name": state['attributes']
                                ['friendly_name'],
                                "state": state['state']}
                except KeyError:
                    pass
            return best_entity
    #
    # checking the entity attributes to be used in the response dialog.
    #

    def find_entity_attr(self, entity):
        if self.ssl:
            req = get("%s/api/states" %
                      self.url, headers=self.headers, verify=self.verify)
        else:
            req = get("%s/api/states" % self.url, headers=self.headers)

        if req.status_code == 200:
            for attr in req.json():
                if attr['entity_id'] == entity:
                    entity_attrs = attr['attributes']
                    if attr['entity_id'].startswith('light.'):
                        unit_measur = entity_attrs['brightness']
                        sensor_name = entity_attrs['friendly_name']
                        sensor_state = attr['state']
                        return unit_measur, sensor_name, sensor_state
                    else:
                        try:
                            unit_measur = entity_attrs['unit_of_measurement']
                            sensor_name = entity_attrs['friendly_name']
                            sensor_state = attr['state']
                            return unit_measur, sensor_name, sensor_state
                        except BaseException:
                            unit_measur = 'null'
                            sensor_name = entity_attrs['friendly_name']
                            sensor_state = attr['state']
                            return unit_measur, sensor_name, sensor_state
        return None

    def execute_service(self, domain, service, data):
        if self.ssl:
            post("%s/api/services/%s/%s" % (self.url, domain, service),
                 headers=self.headers, data=json.dumps(data),
                 verify=self.verify)
        else:
            post("%s/api/services/%s/%s" % (self.url, domain, service),
                 headers=self.headers, data=json.dumps(data))

# TODO - Localization


class SmartThingsSkill(MycroftSkill):
    def __init__(self):
        super(SmartThingsSkill, self).__init__(name="SmartThingsSkill")
        self.st = SmartThingsClient(
            self.config.get('host'),
            self.config.get('password'),
            self.config.get('portnum'),
            ssl=self.config.get('ssl', False),
            verify=self.config.get('verify', True)
            )

    def initialize(self):
        self.language = self.config_core.get('lang')
        self.load_vocab_files(join(dirname(__file__), 'vocab', self.lang))
        self.load_regex_files(join(dirname(__file__), 'regex', self.lang))
        self.__build_switch_intent()
        self.__build_light_set_intent()
        self.__build_light_adjust_intent()
        self.__build_automation_intent()
        self.__build_sensor_intent()
        self.__build_tracker_intent()

    def __build_switch_intent(self):
        intent = IntentBuilder("switchIntent").require("SwitchActionKeyword") \
            .require("Action").require("Entity").build()
        self.register_intent(intent, self.handle_switch_intent)

    def __build_light_set_intent(self):
        intent = IntentBuilder("LightSetBrightnessIntent") \
            .optionally("LightsKeyword").require("SetVerb") \
            .require("Entity").require("BrightnessValue").build()
        self.register_intent(intent, self.handle_light_set_intent)

    def __build_light_adjust_intent(self):
        intent = IntentBuilder("LightAdjBrightnessIntent") \
            .optionally("LightsKeyword") \
            .one_of("IncreaseVerb", "DecreaseVerb", "LightBrightenVerb",
                    "LightDimVerb") \
            .require("Entity").optionally("BrightnessValue").build()
        self.register_intent(intent, self.handle_light_adjust_intent)

    def __build_automation_intent(self):
        intent = IntentBuilder("AutomationIntent").require(
            "AutomationActionKeyword").require("Entity").build()
        self.register_intent(intent, self.handle_automation_intent)

    def __build_sensor_intent(self):
        intent = IntentBuilder("SensorIntent").require(
            "SensorStatusKeyword").require("Entity").build()
        # TODO - Sensors - Locks, Temperature, etc
        self.register_intent(intent, self.handle_sensor_intent)

    def __build_tracker_intent(self):
        intent = IntentBuilder("TrackerIntent").require(
            "DeviceTrackerKeyword").require("Entity").build()
        # TODO - Identity location, proximity
        self.register_intent(intent, self.handle_tracker_intent)

    def handle_switch_intent(self, message):
        LOGGER.debug("Starting Switch Intent")
        entity = message.data["Entity"]
        action = message.data["Action"]
        LOGGER.debug("Entity: %s" % entity)
        LOGGER.debug("Action: %s" % action)
        # TODO if entity is 'all', 'any' or 'every' turn on
        # every single entity not the whole group
        try:
            ha_entity = self.st.find_entity(
                entity, ['group', 'light', 'switch', 'scene', 'input_boolean'])
        except ConnectionError:
            self.speak_dialog('smartthings.error.offline')
            return
        if ha_entity is None:
            self.speak_dialog('smartthings.device.unknown', data={
                              "dev_name": entity})
            return
        LOGGER.debug("Entity State: %s" % ha_entity['state'])
        ha_data = {'entity_id': ha_entity['id']}

        # set context for 'turn it off' again or similar
        # self.set_context('Entity', ha_entity['dev_name'])

        if self.language == 'de':
            if action == 'ein':
                action = 'on'
            elif action == 'aus':
                action = 'off'
        if ha_entity['state'] == action:
            LOGGER.debug("Entity in requested state")
            self.speak_dialog('smartthings.device.already', data={
                "dev_name": ha_entity['dev_name'], 'action': action})
        elif action == "toggle":
            self.st.execute_service("smartthings", "toggle",
                                    ha_data)
            if(ha_entity['state'] == 'off'):
                action = 'on'
            else:
                action = 'off'
            self.speak_dialog('smartthings.device.%s' % action,
                              data=ha_entity)
        elif action in ["on", "off"]:
            self.speak_dialog('smartthings.device.%s' % action,
                              data=ha_entity)
            self.st.execute_service("smartthings", "turn_%s" % action,
                                    ha_data)
        else:
            self.speak_dialog('smartthings.error.sorry')
            return

    def handle_light_set_intent(self, message):
        entity = message.data["Entity"]
        try:
            brightness_req = float(message.data["BrightnessValue"])
            if brightness_req > 100 or brightness_req < 0:
                self.speak_dialog('smartthings.brightness.badreq')
        except KeyError:
            brightness_req = 10.0
        brightness_value = int(brightness_req / 100 * 255)
        brightness_percentage = int(brightness_req)
        LOGGER.debug("Entity: %s" % entity)
        LOGGER.debug("Brightness Value: %s" % brightness_value)
        LOGGER.debug("Brightness Percent: %s" % brightness_percentage)
        try:
            ha_entity = self.st.find_entity(
                entity, ['group', 'light'])
        except ConnectionError:
            self.speak_dialog('smartthings.error.offline')
            return
        if ha_entity is None:
            self.speak_dialog('smartthings.device.unknown', data={
                              "dev_name": entity})
            return
        ha_data = {'entity_id': ha_entity['id']}

        # set context for 'turn it off again' or similar
        # self.set_context('Entity', ha_entity['dev_name'])

        # TODO - Allow value set
        if "SetVerb" in message.data:
            ha_data['brightness'] = brightness_value
            self.st.execute_service("smartthings", "turn_on", ha_data)
            if self.language == 'de':
                # TODO - Fix translation
                self.speak("%s wurde gedimmt" % ha_entity['dev_name'])
            else:
                self.speak("Set the %s brightness to %s percent" %
                           (ha_entity['dev_name'], brightness_percentage))
        else:
            self.speak_dialog('smartthings.error.sorry')
            return

    def handle_light_adjust_intent(self, message):
        entity = message.data["Entity"]
        try:
            brightness_req = float(message.data["BrightnessValue"])
            if brightness_req > 100 or brightness_req < 0:
                self.speak_dialog('smartthings.brightness.badreq')
        except KeyError:
            brightness_req = 10.0
        brightness_value = int(brightness_req / 100 * 255)
        # brightness_percentage = int(brightness_req) # debating use
        LOGGER.debug("Entity: %s" % entity)
        LOGGER.debug("Brightness Value: %s" % brightness_value)
        try:
            ha_entity = self.st.find_entity(
                entity, ['group', 'light'])
        except ConnectionError:
            self.speak_dialog('smartthings.error.offline')
            return
        if ha_entity is None:
            self.speak_dialog('smartthings.device.unknown', data={
                              "dev_name": entity})
            return
        ha_data = {'entity_id': ha_entity['id']}
        # set context for 'turn it off again' or similar
        # self.set_context('Entity', ha_entity['dev_name'])

        # if self.language == 'de':
        #    if action == 'runter' or action == 'dunkler':
        #        action = 'dim'
        #    elif action == 'heller' or action == 'hell':
        #        action = 'brighten'
        if "DecreaseVerb" in message.data or \
                "LightDimVerb" in message.data:
            if ha_entity['state'] == "off":
                if self.language == 'de':
                    self.speak("Kann %s nicht dimmen. Es ist aus." %
                               ha_entity['dev_name'])
                else:
                    self.speak("Can not dim %s. It is off." %
                               ha_entity['dev_name'])
            else:
                light_attrs = self.st.find_entity_attr(ha_entity['id'])
                ha_data['brightness'] = light_attrs[0]
                if ha_data['brightness'] < brightness_value:
                    ha_data['brightness'] = 10
                else:
                    ha_data['brightness'] -= brightness_value
                self.st.execute_service("smartthings", "turn_on", ha_data)
                if self.language == 'de':
                    self.speak("%s wurde gedimmt" % ha_entity['dev_name'])
                else:
                    self.speak("Dimmed the %s" % ha_entity['dev_name'])
        elif "IncreaseVerb" in message.data or \
                "LightBrightenVerb" in message.data:
            if ha_entity['state'] == "off":
                if self.language == 'de':
                    self.speak("Kann %s nicht dimmen. Es ist aus." %
                               ha_entity['dev_name'])
                else:
                    self.speak("Can not dim %s. It is off." %
                               ha_entity['dev_name'])
            else:
                light_attrs = self.st.find_entity_attr(ha_entity['id'])
                ha_data['brightness'] = light_attrs[0]
                if ha_data['brightness'] > brightness_value:
                    ha_data['brightness'] = 255
                else:
                    ha_data['brightness'] += brightness_value
                self.st.execute_service("smartthings", "turn_on", ha_data)
                if self.language == 'de':
                    self.speak("Erhoehe helligkeit auf %s" %
                               ha_entity['dev_name'])
                else:
                    self.speak("Increased brightness of %s" %
                               ha_entity['dev_name'])
        else:
            self.speak_dialog('smartthings.error.sorry')
            return

    def handle_automation_intent(self, message):
        entity = message.data["Entity"]
        LOGGER.debug("Entity: %s" % entity)
        # also handle scene and script requests
        try:
            ha_entity = self.st.find_entity(
                entity, ['automation', 'scene', 'script'])
        except ConnectionError:
            self.speak_dialog('smartthings.error.offline')
            return
        ha_data = {'entity_id': ha_entity['id']}
        if ha_entity is None:
            self.speak_dialog('smartthings.device.unknown', data={
                              "dev_name": entity})
            return

        # set context for 'turn it off again' or similar
        # self.set_context('Entity', ha_entity['dev_name'])

        LOGGER.debug("Triggered automation/scene/script: {}".format(ha_data))
        if "automation" in ha_entity['id']:
            self.st.execute_service('automation', 'trigger', ha_data)
            self.speak_dialog('smartthings.automation.trigger',
                              data={"dev_name": ha_entity['dev_name']})
        elif "script" in ha_entity['id']:
            self.speak_dialog('smartthings.automation.trigger',
                              data={"dev_name": ha_entity['dev_name']})
            self.st.execute_service("smartthings", "turn_on",
                                    data=ha_data)
        elif "scene" in ha_entity['id']:
            self.speak_dialog('smartthings.device.on',
                              data=ha_entity)
            self.st.execute_service("smartthings", "turn_on",
                                    data=ha_data)

    #
    # In progress, still testing.
    #
    def handle_sensor_intent(self, message):
        entity = message.data["Entity"]
        LOGGER.debug("Entity: %s" % entity)
        try:
            ha_entity = self.st.find_entity(entity, ['sensor'])
        except ConnectionError:
            self.speak_dialog('smartthings.error.offline')
            return
        if ha_entity is None:
            self.speak_dialog('smartthings.device.unknown', data={
                              "dev_name": ha_entity['dev_name']})
            return
        ha_data = ha_entity
        entity = ha_entity['id']

        # set context for 'read it out again' or similar
        # self.set_context('Entity', ha_entity['dev_name'])

        unit_measurement = self.st.find_entity_attr(entity)
        if unit_measurement[0] != 'null':
            sensor_unit = unit_measurement[0]
            sensor_name = unit_measurement[1]
            sensor_state = unit_measurement[2]
            if self.language == 'de':
                self.speak(('{} ist {} {}'.format(
                    sensor_name, sensor_state, sensor_unit)))
            else:
                # extract unit for correct pronounciation
                # this is fully optional
                try:
                    from quantulum import parser
                    quantulumImport = True
                except ImportError:
                    quantulumImport = False

                if quantulumImport:
                    quantity = parser.parse((u'{} is {} {}'.format(
                                      sensor_name, sensor_state, sensor_unit)))
                    if len(quantity) > 0:
                        quantity = quantity[0]
                        if (quantity.unit.name != "dimensionless" and
                           quantity.uncertainty <= 0.5):
                            sensor_unit = quantity.unit.name
                            sensor_state = quantity.value

                self.speak_dialog('smartthings.sensor', data={
                              "dev_name": sensor_name,
                              "value": sensor_state,
                              "unit": sensor_unit})
            # Add some context if the person wants to look the unit up
            # Maybe also change to name
            # if one wants to look up "outside temperature"
            # self.set_context("SubjectOfInterest", sensor_unit)
        else:
            sensor_name = unit_measurement[1]
            sensor_state = unit_measurement[2]
            if self.language == 'de':
                self.speak('{} ist {}'.format(sensor_name, sensor_state))
            else:
                self.speak_dialog('smartthings.sensor', data={
                              "dev_name": sensor_name,
                              "value": sensor_state,
                              "unit": ''})

    # In progress, still testing.
    # Device location works.
    # Proximity might be an issue
    # - overlapping command for directions modules
    # - (e.g. "How far is x from y?")
    def handle_tracker_intent(self, message):
        entity = message.data["Entity"]
        LOGGER.debug("Entity: %s" % entity)
        try:
            ha_entity = self.st.find_entity(entity, ['device_tracker'])
        except ConnectionError:
            self.speak_dialog('smartthings.error.offline')
            return
        if ha_entity is None:
            self.speak_dialog('smartthings.device.unknown', data={
                              "dev_name": entity})
            return
        ha_data = ha_entity

        # set context for 'locate it off again' or similar
        # self.set_context('Entity', ha_entity['dev_name'])

        entity = ha_entity['id']
        dev_name = ha_entity['dev_name']
        dev_location = ha_entity['state']
        if self.language == 'de':
            self.speak('{} ist {}'.format(dev_name, dev_location))
        else:
            self.speak_dialog('smartthings.tracker.found',
                              data={'dev_name': dev_name,
                                    'location': dev_location})

    def stop(self):
        pass


def create_skill():
    return SmartThingsSkill()
