from os.path import dirname, join

from adapt.intent import IntentBuilder
from mycroft.skills.core import MycroftSkill
from mycroft.util.log import getLogger

from os.path import dirname, join
from requests import get, post
from fuzzywuzzy import fuzz
import json

__author__ = 'robconnolly, btotharye'
LOGGER = getLogger(__name__)


class HomeAssistantClient(object):
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
            best_score = 0
            best_entity = None
            for state in req.json():
                try:
                    if state['entity_id'].split(".")[0] in types:
                        LOGGER.debug("Entity Data: %s" % state)
                        score = fuzz.ratio(
                            entity,
                            state['attributes']['friendly_name'].lower())
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
                    try:
                        unit_measur = attr['attributes']['unit_of_measurement']
                        sensor_name = attr['attributes']['friendly_name']
                        sensor_state = attr['state']
                        return unit_measure, sensor_name, sensor_state
                    except BaseException:
                        unit_measur = 'null'
                        sensor_name = attr['attributes']['friendly_name']
                        sensor_state = attr['state']
                        return unit_measure, sensor_name, sensor_state

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


class HomeAssistantSkill(MycroftSkill):
    def __init__(self):
        super(HomeAssistantSkill, self).__init__(name="HomeAssistantSkill")
        self.ha = HomeAssistantClient(
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
        self.__build_lighting_intent()
        self.__build_automation_intent()
        self.__build_sensor_intent()
        self.__build_tracker_intent()

    def __build_lighting_intent(self):
        intent = IntentBuilder("LightingIntent").require(
            "LightActionKeyword").require("Action").require("Entity").build()
        # TODO - Locks, Temperature, Identity location
        self.register_intent(intent, self.handle_lighting_intent)

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

    def handle_lighting_intent(self, message):
        entity = message.data["Entity"]
        action = message.data["Action"]
        LOGGER.debug("Entity: %s" % entity)
        LOGGER.debug("Action: %s" % action)
        ha_entity = self.ha.find_entity(
            entity, ['group', 'light', 'switch', 'scene', 'input_boolean'])
        if ha_entity is None:
            self.speak_dialog('homeassistant.device.unknown', data={
                              "dev_name": ha_entity['dev_name']})
            return
        ha_data = {'entity_id': ha_entity['id']}

        if self.language == 'de':
            if action == 'ein':
                action = 'on'
            elif action == 'aus':
                action = 'off'
            elif action == 'runter'or action == 'dunkler':
                action = 'dim'
            elif action == 'heller' or action == 'hell':
                action = 'brighten'
        if action == "on":
            if ha_entity['state'] == action:
                self.speak_dialog(
                    'homeassistant.device.already', data={
                        "dev_name": ha_entity['dev_name'], 'action': action})
            else:
                self.speak_dialog('homeassistant.device.on', data=ha_entity)
                self.ha.execute_service("homeassistant", "turn_on", ha_data)
        elif action == "off":
            if ha_entity['state'] == action:
                self.speak_dialog(
                    'homeassistant.device.already', data={
                        "dev_name": ha_entity['dev_name'], 'action': action})
            else:
                self.speak_dialog('homeassistant.device.off', data=ha_entity)
                self.ha.execute_service("homeassistant", "turn_off", ha_data)
        # TODO - Allow Dimming
        elif action == "dim":
            if ha_entity['state'] == "off":
                self.speak_dialog('homeassistant.device.off', data={
                                  "dev_name": ha_entity['dev_name']})
                if self.language == 'de':
                    self.speak("Kann %s nicht dimmen. Es ist aus." %
                               ha_entity['dev_name'])
                else:
                    self.speak("Can not dim %s. It is off." %
                               ha_entity['dev_name'])
            else:
                if ha_entity['attributes']['brightness'] < 25:
                    ha_data['brightness'] = 10
                else:
                    ha_data['brightness'] -= 25
                self.ha.execute_service("homeassistant", "turn_on", ha_data)
                if self.language == 'de':
                    self.speak("%s wurde gedimmt" % ha_entity['dev_name'])
                else:
                    self.speak("Dimmed the %s" % ha_entity['dev_name'])
        # TODO - Allow Brightening
        elif action == "brighten":
            if ha_entity['state'] == "off":
                self.speak_dialog('homeassistant.device.off', data={
                                  "dev_name": ha_entity['dev_name']})
                if self.language == 'de':
                    self.speak("Kann %s nicht dimmen. Es ist aus." %
                               ha_entity['dev_name'])
                else:
                    self.speak("Can not dim %s. It is off." %
                               ha_entity['dev_name'])
            else:
                if ha_entity['attributes']['brightness'] > 230:
                    ha_data['brightness'] = 255
                else:
                    ha_data['brightness'] += 25
                self.ha.execute_service("homeassistant", "turn_on", ha_data)
                if self.language == 'de':
                    self.speak("Erhoehe helligkeit auf %s" %
                               ha_entity['dev_name'])
                else:
                    self.speak("Increased brightness of %s" %
                               ha_entity['dev_name'])
        else:
            self.speak_dialog('homeassistant.error.sorry')

    def handle_automation_intent(self, message):
        entity = message.data["Entity"]
        LOGGER.debug("Entity: %s" % entity)
        ha_entity = self.ha.find_entity(entity, ['automation'])
        ha_data = {'entity_id': ha_entity['id']}
        if ha_entity is None:
            self.speak_dialog('homeassistant.device.unknown', data={
                              "dev_name": ha_entity['dev_name']})
            return
        LOGGER.debug("Triggered automation on: {}".format(ha_data))
        self.ha.execute_service('automation', 'trigger', ha_data)
        self.speak_dialog('homeassistant.automation.trigger',
                          data={"dev_name": ha_entity['dev_name']})

    #
    # In progress, still testing.
    #
    def handle_sensor_intent(self, message):
        entity = message.data["Entity"]
        LOGGER.debug("Entity: %s" % entity)
        ha_entity = self.ha.find_entity(entity, ['sensor'])
        if ha_entity is None:
            self.speak_dialog('homeassistant.device.unknown', data={
                              "dev_name": ha_entity['dev_name']})
            return
        ha_data = ha_entity
        entity = ha_entity['id']
        unit_measurement = self.ha.find_entity_attr(entity)
        if unit_measurement[0] != 'null':
            sensor_unit = unit_measurement[0]
            sensor_name = unit_measurement[1]
            sensor_state = unit_measurement[2]
            if self.language == 'de':
                self.speak(('{} ist {} {}'.format(
                    sensor_name, sensor_state, sensor_unit)))
            else:
                self.speak(('Currently {} is {} {}'.format(
                    sensor_name, sensor_state, sensor_unit)))
        else:
            sensor_name = unit_measurement[1]
            sensor_state = unit_measurement[2]
            if self.language == 'de':
                self.speak('{} ist {}'.format(sensor_name, sensor_state))
            else:
                self.speak('Currently {} is {}'.format(
                    sensor_name, sensor_state))

    # In progress, still testing.
    # Device location works.
    # Proximity might be an issue
    # - overlapping command for directions modules
    # - (e.g. "How far is x from y?")
    def handle_tracker_intent(self, message):
        entity = message.data["Entity"]
        LOGGER.debug("Entity: %s" % entity)
        ha_entity = self.ha.find_entity(entity, ['device_tracker'])
        if ha_entity is None:
            self.speak_dialog('homeassistant.device.unknown', data={
                              "dev_name": ha_entity['dev_name']})
            return
        ha_data = ha_entity
        entity = ha_entity['id']
        dev_name = ha_entity['dev_name']
        dev_location = ha_entity['state']
        if self.language == 'de':
            self.speak('{} ist {}'.format(dev_name, dev_location))
        else:
            self.speak_dialog('homeassistant.tracker.found',
                              data={'dev_name': dev_name,
                                    'location': dev_location})

    def stop(self):
        pass


def create_skill():
    return HomeAssistantSkill()
