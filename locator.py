import geopy
import sqlite3
import pprint
import pickle
import math
import logging

logger = logging.getLogger(__name__)


class Locate(object):
    """ Tools for determining location from lat/lon data including
        sqlite3 cache for reverse geocode lookups

    Thanks:
        https://stackoverflow.com/users/95810/alex-martelli
    """

    def __init__(self, fn='location_cache.db'):
        # Initilize Geolocator
        # g = geopy.geocoders.GoogleV3()
        self.g = geopy.geocoders.Nominatim(user_agent=__name__, timeout=20)
        self.conn = conn = sqlite3.connect(fn)
        cur = conn.cursor()
        cur.execute('CREATE TABLE IF NOT EXISTS '
                    'Geo ( '
                    'location STRING PRIMARY KEY, '
                    'address BLOB '
                    ')')
        conn.commit()

    def _address_cached(self, location):
        cur = self.conn.cursor()
        cur.execute('SELECT address FROM Geo WHERE location=?', (location,))
        res = cur.fetchone()
        if res is None:
            return False
        return pickle.loads(res[0])

    def _save_to_cache(self, location, address):
        cur = self.conn.cursor()
        cur.execute('INSERT INTO Geo(location, address) VALUES(?, ?)',
                    (location, sqlite3.Binary(pickle.dumps(address))))
        self.conn.commit()

    def _latlon_to_tile(self, location, zoom=18):
        """ Identify a the 'tile' a partciular latitude and longitude is in

        from: https://wiki.openstreetmap.org/wiki/
        Slippy_map_tilenames#Lon..2Flat._to_tile_numbers_2

        Args:
            location (list): [latitude, longitude]
        """
        lat_deg, lon_deg = location
        lat_rad = math.radians(lat_deg)
        n = 2.0 ** zoom
        xtile = int((lon_deg + 180.0) / 360.0 * n)
        ytile = int(
            (1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) /
             math.pi) / 2.0 * n)
        return str(xtile) + ',' + str(ytile)

    def _geolocate(self, location):
        """ Look up location data from lat/lon """
        tilehash = self._latlon_to_tile(location)
        logger.debug('Looking up location {} with {}'.format(location, self.g))
        address_record = self._address_cached(tilehash)
        if address_record is False:
            latitude, longitude = location
            lat_lon = str(latitude) + ',' + str(longitude)
            try:
                address_record = self.g.reverse(lat_lon)
            except geopy.exc.GeocoderTimedOut as e:
                return "Skipped"
            except Exception as e:
                logger.error('Exception: {}'.format(e))
                raise
            self._save_to_cache(tilehash, address_record)
        logger.debug('{} Address: {}'.format(
            location, address_record.address))
        return address_record

    def get_town(self, location):
        """ Return town from lat,lon

        Args:
            location (list): [latitude, longitude]

        Returns:
            string: Town/City the coordinates are in or:
                "Skipped": if there was an error retrieving data
                "NotInData: got data, but couldn't find a town/city
        """
        record = self._geolocate(location)
        if type(record) != geopy.location.Location:
            return record
        for key in ['hamlet', 'village', 'town', 'city']:
            if key in record.raw['address']:
                return record.raw['address'][key]
        return "NotInData"

    def get_address(self, location):
        """ Return town from lat,lon

        Args:
            location (list): [latitude, longitude]

        Returns:
            string: Town/City the coordinates are in or:
                "Skipped": if there was an error retrieving data
                "NotInData: got data, but couldn't find a town/city
        """
        record = self._geolocate(location)
        if type(record) != geopy.location.Location:
            return record
        return record.address
