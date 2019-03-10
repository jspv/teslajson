######################################################################
#
# Parse the tesla json records
#

import json
import copy
from datetime import datetime, timedelta
import pytz
import sys
import logging
from locator import Locate

logger = logging.getLogger(__name__)


class TeslaRecord(object):
    """ Information about a specific record retrieved from a tesla """

    def __init__(self, line=None, tdata=None, want_offline=False):
        """Create object from json text data from tesla_poller"""
        if self.jline:
            # Parse the line and update the object with the current state
            self.timets = self.jline["retrevial_time"]
            self.vehicle_id = self.jline["vehicle_id"]
            self.state = self.jline["state"]
            self.car_locked = self._jget(["vehicle_state", "locked"])
            self.odometer = self._jget(["vehicle_state", "odometer"])
            self.is_user_present = self._jget(
                ["vehicle_state", "is_user_present"])
            self.valet_mode = self._jget(["vehicle_state", "valet_mode"])
            self.charging_state = self._jget(
                ["charge_state",  "charging_state"])
            self.usable_battery_level = self._jget(
                ["charge_state",  "usable_battery_level"])
            self.charge_miles_added = self._jget(
                ["charge_state",  "charge_miles_added_rated"])
            self.charge_energy_added = self._jget(
                ["charge_state",  "charge_energy_added"])
            self.charge_current_request = self._jget(
                ["charge_state",  "charge_current_request"])
            self.charge_time_to_full = self._jget(
                ["charge_state", "time_to_full_charge"])
            self.charger_power = self._jget(["charge_state",  "charger_power"])
            self.charge_port_open = self._jget(
                ["charge_state", "charge_port_door_open"])
            self.charge_port_latch = self._jget(
                ["charge_state", "charge_port_latch"])
            if (self.charge_port_open is True
                    and self.charge_port_latch == "Engaged"):
                self.plugged_in = True
            else:
                self.plugged_in = False
            self.charge_rate = self._jget(["charge_state",  "charge_rate"])
            self.charger_voltage = self._jget(
                ["charge_state",  "charger_voltage"])
            self.battery_range = self._jget(["charge_state",  "battery_range"])
            self.est_battery_range = self._jget(
                ["charge_state",  "est_battery_range"])
            self.shift_state = self._jget(["drive_state",   "shift_state"])
            self.speed = self._jget(["drive_state",   "speed"])
            self.latitude = self._jget(["drive_state",   "latitude"])
            self.longitude = self._jget(["drive_state",   "longitude"])
            if (self.latitude is not None
                    and self.longitude is not None):
                self.location = [self.latitude, self.longitude]
            else:
                self.location = None
            self.heading = self._jget(["drive_state",   "heading"])
            self.gps_as_of = self._jget(["drive_state",   "gps_as_of"])
            self.climate_on = self._jget(["climate_state", "is_climate_on"])
            self.preconditioning = self._jget(
                ["climate_state", "is_preconditioning"])
            self.inside_temp = self._jget(["climate_state", "inside_temp"])
            self.outside_temp = self._jget(["climate_state", "outside_temp"])
            self.battery_heater = self._jget(
                ["climate_state", "battery_heater"])
            self.vin = self.jline["vin"]
            self.display_name = self.jline["display_name"]
            self.car_type = self._jget(["vehicle_config", "car_type"])
            self.car_special_type = self._jget(
                ["vehicle_config", "car_special_type"])
            self.perf_config = self._jget(["vehicle_config", "perf_config"])
            self.has_ludicrous_mode = self._jget(
                ["vehicle_config", "has_ludicrous_mode"])
            self.wheel_type = self._jget(["vehicle_config", "wheel_type"])
            self.has_air_suspension = self._jget(
                ["vehicle_config", "has_air_suspension"])
            self.exterior_color = self._jget(
                ["vehicle_config", "exterior_color"])
            self.option_codes = self.jline["option_codes"]
            self.car_version = self._jget(["vehicle_state", "car_version"])
            self.distance_unit = self._jget(["gui_settings",
                                             "gui_distance_units"])
            self.temp_unit = self._jget(["gui_settings",
                                         "gui_temperature_units"])

        if tdata:
            for k in ('timets', 'vehicle_id', 'state', 'car_locked',
                      'odometer', 'is_user_present', 'valet_mode',
                      'charging_state', 'usable_battery_level',
                      'charge_miles_added', 'charge_energy_added',
                      'charge_current_request', 'charger_power', 'charge_rate',
                      'charger_voltage', 'battery_range', 'est_battery_range',
                      'shift_state', 'speed', 'latitude', 'longitude',
                      'heading', 'gps_as_of', 'climate_on', 'inside_temp',
                      'outside_temp', 'battery_heater', 'vin', 'display_name',
                      'car_type', 'car_special_type', 'perf_config',
                      'has_ludicrous_mode', 'wheel_type', 'has_air_suspension',
                      'exterior_color', 'option_codes', 'car_version'):
                if k in tdata and tdata[k] is not None:
                    if k in ('timets', 'gps_as_of'):
                        setattr(self, k, float(tdata[k].strftime('%s')))
                    else:
                        setattr(self, k, tdata[k])
                else:
                    setattr(self, k, None)

        # Determine state of vehicle and define the session_type
        # mode is the 'internal' mode we use for tracking the different
        # states and messages, session_type is the type of session the
        # vehicle is now in.  Mostly 1:1 except for "Polling" where the
        # vehicle is likely asleep and therefore parked.
        if self.charger_power and self.charge_time_to_full > 0:
            self.mode = "Charging"
        elif self.shift_state and self.shift_state != "P":
            self.mode = "Driving"
        elif self.preconditioning:
            self.mode = "Conditioning"
        elif self.charger_power is not None or self.odometer is not None:
            self.mode = "Standby"
        else:
            self.mode = "Polling"

        if self.mode in ['Standby', 'Polling']:
            self.session_type = "Parked"
        else:
            self.session_type = self.mode

    def __new__(cls, line=None, tdata=None, want_offline=False):
        """Evaluate the line and see if it meets initial criteria

        Ignore comments and attempt to JSON load the line.  Verify the JSON
        has the right criteria and if so return an object, otherwise return
        None
        """
        if line is not None and (line.startswith("#") or len(line) < 10):
            return None

        instance = super(TeslaRecord, cls).__new__(cls)

        if line is None:
            instance.jline = None
            return instance

        try:
            instance.jline = json.loads(line)
        except Exception as e:
            print("JSON parsing failed. Ignoring:{}".format(line),
                  file=sys.stderr)
            return None

        if "retrevial_time" not in instance.jline:
            print("retreval_time missing. Ignoring :{}".format(line),
                  file=sys.stderr)
            return None

        if instance.jline["state"] != "online" and not want_offline:
            return None

        return instance

    def __add__(self, b):
        """ Combine two objects

        For two objects a,b; create new object will have all the
        attributes of a and of b, b's attributes will overwrite a's
        """

        result = copy.copy(self)
        for attr in b.__dict__:
            v = getattr(b, attr)
            if v:
                setattr(result, attr, v)
        return result

    def _jget(self, tree, notfound=None):
        """ search self.jline for a subkey, return the value """
        info = self.jline
        for key in tree:
            if key not in info:
                return notfound
            info = info[key]
        return info

    def sql_vehicle_insert_dict(self):
        """Construct a dictionary with keys and values to insert

        To be used in a psycopg2. Vehicle_id and vin need to exist so we
        just add them
        """

        result = {}

        for memid in ("vehicle_id", "vin", "display_name", "car_type",
                      "car_special_type", "perf_config", "has_ludicrous_mode",
                      "wheel_type", "has_air_suspension", "exterior_color",
                      "option_codes", "car_version"):
            if getattr(self, memid) is not None:
                result[memid] = getattr(self, memid)

        return result

    def sql_vehicle_update_dict(self, current):
        """Construct a dictionary with keys and values to change.

           To be used in a psycopg2 update execute command. We assume vin
           never changes, so we don't check it
        """

        result = {}

        for memid in ("display_name", "car_type", "car_special_type",
                      "perf_config", "has_ludicrous_mode", "wheel_type",
                      "has_air_suspension", "exterior_color", "option_codes",
                      "car_version"):
            if current.get(memid, None) != getattr(self, memid):
                result[memid] = getattr(self, memid)
        return result

    def sql_vehicle_status_insert_dict(self):
        """Construct a dictionary to insert data into vehicle_status"""

        result = {}

        for memid in ("vehicle_id", "state", "car_locked", "odometer",
                      "is_user_present", "shift_state", "speed", "latitude",
                      "longitude", "heading", "charging_state",
                      "usable_battery_level", "battery_range",
                      "est_battery_range", "charge_rate", "charge_miles_added",
                      "charge_energy_added", "charge_current_request",
                      "charger_power", "charger_voltage", "inside_temp",
                      "outside_temp", "climate_on", "battery_heater",
                      "valet_mode"):
            if getattr(self, memid) is not None:
                result[memid] = getattr(self, memid)

        result["timets"] = datetime.fromtimestamp(
            float(self.timets), pytz.timezone("UTC")).isoformat()

        if self.gps_as_of is not None:
            result["gps_as_of"] = datetime.fromtimestamp(
                float(self.gps_as_of), pytz.timezone("UTC")).isoformat()
        return result


class TeslaSession(object):
    """ Class to store Tesla session information """

    # Timzone to use accross sessions, will get set on first __init__
    tz = None

    # odometer value to carry across sessions
    odo = None

    # Initialize numbers
    session_no = 0

    # tracker for the timestamp of the previous record received, used to
    # identify big gaps in records.  We will update this for each new
    # session or when update().  I don't do this on close() as the record
    # used for close() is the record that starts the next session
    #  with __init__
    _last_record_ts = None

    # note if a session is currently active, used to ensure only one at
    # a time
    _isactive = False

    # Tracker for the last location, as new Drives session locations will
    # have the first GPS coords during the drive, not the start, use this
    # to ensure proper start location
    _last_park_location = None
    _last_park_odo = None

    def __init__(self, record, tzone=None):
        if TeslaSession._isactive is True:
            raise Exception(
                'Attempted to create a session when one is already active')
        TeslaSession._isactive = True
        # Determine the time since we last saw a record
        if TeslaSession._last_record_ts is not None:
            self.since_last = record.timets - TeslaSession._last_record_ts
        else:
            self.since_last = 0
        TeslaSession._last_record_ts = record.timets
        TeslaSession.session_no += 1
        self.session_no = TeslaSession.session_no
        self.start_ts = record.timets
        self.end_ts = None
        self.type = None
        self.closed = False
        self.start_battery_level = record.usable_battery_level
        self.start_battery_range = record.battery_range
        self.start_json = record.jline
        self.temp_unit = record.temp_unit
        # Drive sessions will overwrite lat & lon with last parked location
        self.start_location = record.location
        # If we have a odo reading, use it, otherwise use the last known
        if record.odometer:
            self.start_odo = record.odometer
            TeslaSession.odo = record.odometer
        else:
            self.start_odo = TeslaSession.odo
        # Determine if we have start data to do delta's if not
        # set flags to indicat partial data and deal with this elsewhere
        if (not self.start_battery_level or not self.start_odo):
            self.has_start_data = False
            self.partialmark = '(x)'
        else:
            self.has_start_data = True
            self.partialmark = ""

        if record.distance_unit == "mi/hr":
            self.distance_unit = "mph"
        else:
            self.distance_unit = "kph"

        # Note: timezone may already exist in the tz class variable
        if tzone is not None:
            TeslaSession.tz = tzone
        elif TeslaSession.tz is None:
            # Get the local timezone and set it as the default
            TeslaSession.tz = datetime.now().astimezone().tzinfo

        # Create locator object
        self.locator = Locate()

    def __close__(self, record):
        TeslaSession._isactive = False
        self.closed = True
        if record.odometer:
            self.end_odo = record.odometer
            TeslaSession.odo = record.odometer
        else:
            self.end_odo = TeslaSession.odo
        self.end_battery_level = record.usable_battery_level
        self.end_battery_range = record.battery_range
        self.end_location = record.location
        self.end_ts = record.timets
        self.end_json = record.jline

    def __update__(self, record):
        """ Add data to session mid-session """
        self.since_last = record.timets - TeslaSession._last_record_ts
        TeslaSession._last_record_ts = record.timets
        self.end_ts = record.timets
        self.end_json = record.jline
        if record.odometer:
            TeslaSession.odo = record.odometer

        # If we have a session missing start data and the missing data
        # is here, add it.
        if not self.has_start_data:
            if not self.start_battery_level and record.usable_battery_level:
                self.start_battery_level = record.usable_battery_level

    def __pprint__(self):
        """ Print generic output if there isn't good start data """
        if not self.has_start_data:
            fmt = '{:<4}{} +{:<16} {} Incomplete Data, no starting information'
            print(fmt.format(self.session_no, self._fmt_starttime(),
                             str(self.durationtime()),
                             self.ppstate))

    def _fmt_ts(self, timeint):
        """ Return string of formatted and localized timestamp """
        time = datetime.fromtimestamp(timeint, TeslaSession.tz)
        return time.strftime('%Y-%m-%d %H:%M:%S')

    def _fmt_time(self, time):
        """ Return string of formatted and localized datetime """
        time_local = time.astimezone(TeslaSession.tz)
        return time_local.strftime('%Y-%m-%d %H:%M:%S')

    def duration(self):
        """ Return the current duration of the session in seconds """
        return self.end_ts - self.start_ts

    def durationtime(self):
        """ Return the current duration of the session as timedelta """
        return self.ts_diff(self.start_ts, self.end_ts)

    def starttime(self):
        """ Return datetime of current session's starttime """
        if self.start_ts is not None:
            return datetime.fromtimestamp(self.start_ts)
        return None

    def fmt_starttime(self):
        """ return starttime string formattted and localized """
        return self._fmt_ts(self.start_ts)

    def endtime(self):
        """ Return datetime of current session's endtime """
        if self.end_ts is not None:
            return datetime.fromtimestamp(self.end_ts)
        return None

    def fmt_endtime(self):
        """ return current endtime string formattted and localized """
        return self._fmt_ts(self.end_ts)

    @staticmethod
    def ts_diff(start_ts, end_ts):
        """ Return a timedelta object of difference between two timestamps """
        starttime = datetime.fromtimestamp(start_ts)
        endtime = datetime.fromtimestamp(end_ts)
        return endtime - starttime

    def _temp_cvt(self, celcius):
        if self.temp_unit == "F":
            return 9.0 / 5.0 * celcius + 32
        else:
            return celcius

    @staticmethod
    def _running_average(cur_dur, cur_avg, last_ts, new_ts, new_val):
        """ Keep a running average over a time series

        Update a continuous running avearge of a value over time.  For each
        value and duration, recalcuate the average adding the value an
        duration to the entire series

        Args:
            cur_dur (timedelta): time duration for the running average
            cur_avg (float): current running _running_average
            last_ts (datetime): timestamp for end of current running average
            new_val (float): new value to add to running average
            new_ts (datetime): timestamp of new value

        Returns:
            float: the updated current average
            timedelta: the update current duration
        """
        new_dur = new_ts - last_ts
        sum_cur_values = (cur_avg * cur_dur.total_seconds() +
                          new_val * new_dur.total_seconds())
        updated_dur = cur_dur + new_dur
        updated_val = sum_cur_values / updated_dur.total_seconds()
        return (updated_dur, updated_val)

    @classmethod
    def create(cls, record, tzone=None):
        """ Factory to create right subclass """
        SESSION_TYPE_TO_CLASS_MAP = {
            'Driving': DriveSession,
            'Conditioning': ConditionSession,
            'Charging': ChargeSession,
            'Parked': ParkSession,
        }
        if record.session_type not in SESSION_TYPE_TO_CLASS_MAP:
            raise ValueError('Bad session type {}'.format(record.session_type))

        # If a timezone is passed, set the class variable
        if tzone is not None:
            cls.tz = tzone
        return SESSION_TYPE_TO_CLASS_MAP[record.session_type](record)

    def update(self, record):
        """ Update the session record (overload this) """
        self.__update__(record)

    def pprint(self):
        """ Pretty print details about the session (overload this) """
        pass


class DriveSession(TeslaSession):
    def __init__(self, record):
        super().__init__(record)
        self.type = 'Driving'
        self.ppstate = 'Drove'
        self._outside_temps = []
        self._inside_temps = []
        self._add_data(record)
        # If we have a last location, use it, it's where we really started
        if TeslaSession._last_park_location is not None:
            # TODO check to see if _last_park_location is reasonably
            # close to the current location
            self.start_location = TeslaSession._last_park_location
        if TeslaSession._last_park_odo is not None:
            self.start_odo = TeslaSession._last_park_odo

    def update(self, record):
        super().update(record)
        self._add_data(record)
        if record.speed is None:
            super().update(record)
            return

    def _calc_whmi(self):
        spec_range = 310
        spec_battery = 75000
        return ((self.start_battery_range - self.end_battery_range)
                / spec_range * spec_battery / self.distance)

    def _add_data(self, record):
        if record.outside_temp is not None:
            self._outside_temps.append(record.outside_temp)
        if record.inside_temp is not None:
            self._inside_temps.append(record.inside_temp)

    def _avg(self, array):
        return sum(array) / len(array)

    def close(self, record):
        super().__close__(record)
        self._add_data(record)
        self.distance = self.end_odo - self.start_odo
        self.outside_temp = self._avg(self._outside_temps)
        self.inside_temp = self._avg(self._inside_temps)

    def pprint(self):
        super().__pprint__()
        if not self.has_start_data:
            return

        fmt = ('{:<4}{} +{:<16} {:>3}{:>11} {:3d}% ({:3d}% ->{:3d}%) '
               '{:>5.1f}mi {:>4.1f}{:3s} {:>6.1f}wh/m o:{:.1f}° i:{:.1f}° '
               '[{} -> {}]')
        print(fmt.format(self.session_no, self.fmt_starttime(),
                         str(self.durationtime()),
                         self.partialmark,
                         self.ppstate,
                         self.end_battery_level - self.start_battery_level,
                         self.start_battery_level,
                         self.end_battery_level,
                         self.distance,
                         self.distance / (self.duration() / 3600),
                         self.distance_unit,
                         self._calc_whmi(),
                         self._temp_cvt(self.outside_temp),
                         self._temp_cvt(self.inside_temp),
                         self.locator.get_town(self.start_location),
                         self.locator.get_town(self.end_location)),
              flush=True)


class ConditionSession(TeslaSession):
    def __init__(self, record):
        super().__init__(record)
        self.type = 'Conditioning'
        self.ppstate = "Conditioned"
        if record.plugged_in is True:
            self.plugstate = '(+)'
        else:
            self.plugstate = ''
        self.preconditioning = record.preconditioning
        logger.debug('Conditioning Session Start ({}) at {}'.format(
            TeslaSession.session_no, self.fmt_starttime()))
        logger.debug('Conditioning start: {}'.format(self.start_json))

    def close(self, record):
        super().__close__(record)
        logger.debug('Conditioning Session End ({}) at {}'.format(
            TeslaSession.session_no, self.fmt_endtime()))
        logger.debug('Conditioning close: {}'.format(self.end_json))

    def update(self, record):
        super().__update__(record)
        logger.debug('Conditioning Session Update ({}) at {}'.format(
            TeslaSession.session_no, self.fmt_endtime()))
        logger.debug('Parking Conditioning:{}'.format(self.end_json))

    def pprint(self):
        fmt = '{:<4}{} +{:<13} {:>3}{:>3}{:>11} {:3d}% ({:3d}% ->{:3d}%)'
        print(fmt.format(self.session_no, self.fmt_starttime(),
                         str(self.durationtime()),
                         self.partialmark,
                         self.plugstate,
                         self.ppstate,
                         self.end_battery_level - self.start_battery_level,
                         self.start_battery_level,
                         self.end_battery_level), flush=True)


class ChargeSession(TeslaSession):
    def __init__(self, record):
        super().__init__(record)
        self.type = 'Charging'
        self.start_battery_range = record.battery_range
        self.ppstate = "Charged"
        self.usable_battery_level = record.usable_battery_level
        self.charge_energy_added = record.charge_energy_added
        logger.debug('Started Charging Session({}): Energy Added = {}'.format(
            TeslaSession.session_no, record.charge_energy_added))
        # print('start:', self.start_json)

    def update(self, record):
        super().__update__(record)
        if record.charge_energy_added is not None:
            logger.debug(
                'Mid-State Charging Session ({}): Energy Added = {} '
                'ts:{}'.format(self.session_no, record.charge_energy_added,
                               record.timets))

            # If charge drops during charging, something is really wrong
            if (float(record.charge_energy_added) <
                    float(self.charge_energy_added)):
                logger.warning(
                    'Bad charging value ({}) in session {} ts:{}'
                    .format(self.session_no,
                            record.charge_energy_added,
                            record.timets))
            else:
                self.charge_energy_added = record.charge_energy_added

    def close(self, record):
        super().__close__(record)
        # If charge drops during charging, something is really wrong
        if (float(record.charge_energy_added) <
                float(self.charge_energy_added)):
            logger.warning(
                'Bad charging value ({}) in session {} ts:{}'
                .format(self.session_no,
                        record.charge_energy_added,
                        record.timets))
        else:
            self.charge_energy_added = record.charge_energy_added
        logger.debug(
            'Ended Charging Session({}): Energy Added = {} '
            'ts:{}'.format(self.session_no, record.charge_energy_added,
                           record.timets))

    def pprint(self):
        fmt = ('{:<4}{} +{:<16} {:>3}{:>11} {:3d}% ({:3d}% ->{:3d}%) '
               '{:>6.2f}kWh')
        print(fmt.format(self.session_no, self.fmt_starttime(),
                         str(self.durationtime()),
                         self.partialmark,
                         self.ppstate,
                         self.end_battery_level - self.start_battery_level,
                         self.start_battery_level,
                         self.end_battery_level,
                         self.charge_energy_added), flush=True)


class ParkSession(TeslaSession):
    def __init__(self, record):
        super().__init__(record)
        self.type = 'Parked'
        self.ppstate = 'Parked'
        # Save the current parked location
        if record.location is not None:
            TeslaSession._last_park_location = record.location
            self.location = record.location
        else:
            self.location = TeslaSession._last_park_location
        if record.odometer is not None:
            TeslaSession._last_park_odo = record.odometer

        logger.debug('Parking Session Start ({}) at {}'.format(
            TeslaSession.session_no, self.fmt_starttime()))
        logger.debug('Parking start: {}'.format(self.start_json))

    def close(self, record):
        super().__close__(record)
        logger.debug('Parking Session End ({}) at {}'.format(
            TeslaSession.session_no, self.fmt_endtime()))
        logger.debug('Parking close: {}'.format(self.end_json))

    def update(self, record):
        super().__update__(record)
        # Save the current parked location
        # TODO - Check for gaps/changes in parking location
        if record.location is not None:
            TeslaSession._last_park_location = record.location
            self.location = record.location
        logger.debug('Parking Session Update ({}) at {}'.format(
            TeslaSession.session_no, self.fmt_endtime()))
        logger.debug('Parking update:{}'.format(self.end_json))

    def pprint(self):
        fmt = '{:<4}{} +{:<16} {:>3}{:>11} {:3d}% ({:3d}% ->{:3d}%) {}'
        print(fmt.format(self.session_no, self.fmt_starttime(),
                         str(self.durationtime()),
                         self.partialmark,
                         self.ppstate,
                         self.end_battery_level - self.start_battery_level,
                         self.start_battery_level,
                         self.end_battery_level,
                         self.locator.get_address(self.location)), flush=True)
