"""
Twinkly Twinkly Little Star
https://github.com/jschlyter/ttls

Copyright (c) 2019 Jakob Schlyter. All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions
are met:
1. Redistributions of source code must retain the above copyright
   notice, this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright
   notice, this list of conditions and the following disclaimer in the
   documentation and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY
DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE
GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER
IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN
IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

import argparse
import base64
import json
import logging
import os
import socket
import time
from typing import List, Tuple

import requests

logger = logging.getLogger(__name__)

TWINKLY_MODES = ['rt', 'movie', 'off', 'demo', 'effect']
TWINKLY_FRAME = List[Tuple[int, int, int]]


class Twinkly(object):

    def __init__(self, host: str, login: bool = True):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.session = requests.Session()
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.host = host
        self.rt_port = 7777
        self.expires = None
        self._token = None
        self._length = None
        if login:
            self.ensure_token()

    @property
    def base(self) -> str:
        return f"http://{self.host}/xled/v1"

    def _post(self, endpoint, **kwargs):
        self.ensure_token()
        self.logger.info("POST endpoint %s", endpoint)
        if 'json' in kwargs:
            self.logger.info("POST payload %s", kwargs['json'])
        return self.session.post(f"{self.base}/{endpoint}", **kwargs)

    def _get(self, endpoint, **kwargs):
        self.ensure_token()
        self.logger.info("GET endpoint %s", endpoint)
        return self.session.get(f"{self.base}/{endpoint}", **kwargs)

    def ensure_token(self):
        if self.expires is None or self.expires <= time.time():
            self.logger.debug("Authentication token expired, will refresh")
            self.login()
            self.verify_login()
        else:
            self.logger.debug("Authentication token still valid")

    def login(self):
        challenge = base64.b64encode(os.urandom(32)).decode()
        payload = {"challenge": challenge}
        response = self.session.post(f"{self.base}/login", json=payload)
        response.raise_for_status()
        r = response.json()
        self._token = r['authentication_token']
        self.session.headers['X-Auth-Token'] = self._token
        self.expires = time.time() + r['authentication_token_expires_in']

    def logout(self):
        response = self._post('logout', json={})
        response.raise_for_status()
        self._token = None

    def verify_login(self):
        response = self._post('verify', json={})
        response.raise_for_status()

    @property
    def token(self) -> str:
        self.ensure_token()
        return self._token

    @property
    def length(self) -> int:
        if self._length is None:
            self._length = self.get_details()['number_of_led']
        return self._length

    @property
    def name(self) -> str:
        return self.get_name()['name']

    @name.setter
    def name(self, n: str) -> None:
        self.set_name({'name': n})

    @property
    def mode(self) -> str:
        return self.get_mode()['mode']

    @mode.setter
    def mode(self, m: str) -> None:
        self.set_mode({'mode': m})

    @property
    def version(self) -> str:
        return self.get_firmware_version()['version']

    def get_name(self):
        response = self._get('device_name')
        response.raise_for_status()
        return response.json()

    def set_name(self, data):
        response = self._post('device_name', json=data)
        response.raise_for_status()
        return response.json()

    def reset(self):
        response = self._get('reset')
        response.raise_for_status()
        return response.json()

    def get_network_status(self):
        response = self._get('network/status')
        response.raise_for_status()
        return response.json()

    def get_firmware_version(self):
        response = self._get('fw/version')
        response.raise_for_status()
        return response.json()

    def get_details(self):
        response = self._get('gestalt')
        response.raise_for_status()
        return response.json()

    def get_mode(self):
        response = self._get('led/mode')
        response.raise_for_status()
        return response.json()

    def set_mode(self, data):
        response = self._post('led/mode', json=data)
        response.raise_for_status()
        return response.json()

    def get_mqtt(self):
        response = self._get('mqtt/config')
        response.raise_for_status()
        return response.json()

    def set_mqtt(self, data):
        response = self._post('mqtt/config', json=data)
        response.raise_for_status()
        return response.json()

    def send_frame(self, frame: TWINKLY_FRAME):
        if len(frame) != self.length:
            raise ValueError("Invalid frame length")
        header = bytes([0x01]) + bytes(base64.b64decode(self.token)) + bytes([self.length])
        payload = []
        for x in frame:
            payload.extend(list(x))
        self.socket.sendto(header + bytes(payload), (self.host, self.rt_port))

    def get_movie_config(self):
        response = self._get('led/movie/config')
        response.raise_for_status()
        return response.json()

    def set_movie_config(self, data):
        response = self._post('led/movie/config', json=data)
        response.raise_for_status()
        return response.json()

    def upload_movie(self, movie: bytes):
        response = self._post('led/movie/full', data=movie,
                              headers={'Content-Type': 'application/octet-stream'})
        response.raise_for_status()
        return response.json()

    def realtime(self):
        self.mode = "rt"

    def movie(self):
        self.mode = "movie"

    def off(self):
        self.mode = "off"

    def demo(self):
        self.mode = "demo"


def main():
    """ Main function"""

    parser = argparse.ArgumentParser(description='Twinkly Twinkly Little Star')
    parser.add_argument('--host',
                        metavar='hostname',
                        required=True,
                        help='Device address')
    parser.add_argument('--debug',
                        action='store_true',
                        help="Enable debugging")
    parser.add_argument('--json',
                        action='store_true',
                        help="Output result as compact JSON")

    subparsers = parser.add_subparsers(dest='command')

    subparsers.add_parser('network', help="Get network status")
    subparsers.add_parser('firmware', help="Get firmware version")
    subparsers.add_parser('details', help="Get device details")
    subparsers.add_parser('token', help="Get authentication token")

    parser_name = subparsers.add_parser('name', help="Get or set device name")
    parser_name.add_argument('--name', metavar='name', type=str, required=False)

    parser_mode = subparsers.add_parser('mode', help="Get or set LED operation mode")
    parser_mode.add_argument('--mode', choices=TWINKLY_MODES, required=False)

    parser_mqtt = subparsers.add_parser('mqtt', help="Get or set MQTT configuration")
    parser_mqtt.add_argument('--json',
                             dest='mqtt_json',
                             metavar='mqtt',
                             type=str,
                             required=False,
                             help="MQTT config as JSON")

    parser_movie = subparsers.add_parser('movie', help="Movie configuration")
    parser_movie.add_argument('--delay',
                              dest='movie_delay',
                              metavar='milliseconds',
                              type=int,
                              default=100,
                              required=False,
                              help="Delay between frames")
    parser_movie.add_argument('--file',
                              dest='movie_file',
                              metavar='filename',
                              type=str,
                              required=True,
                              help="Movie file")

    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
        requests_log = logging.getLogger("requests.packages.urllib3")
        requests_log.setLevel(logging.DEBUG)
        requests_log.propagate = True

    t = Twinkly(host=args.host)

    if args.command == 'name':
        res = t.get_name() if args.name is None else t.set_name({'name': args.name})
    elif args.command == 'network':
        res = t.get_network_status()
    elif args.command == 'firmware':
        res = t.get_firmware_version()
    elif args.command == 'details':
        res = t.get_details()
    elif args.command == 'mode':
        res = t.get_mode() if args.mode is None else t.set_mode({'mode': args.mode})
    elif args.command == 'mqtt':
        if args.mqtt_json is None:
            res = t.get_mqtt()
        else:
            data = json.loads(args.mqtt_json)
            res if args.mode is None else t.set_mqtt(data)
    elif args.command == 'movie':
        if args.movie_file:
            with open(args.movie_file, 'rb') as f:
                movie = f.read()
            params = {
                'frame_delay': args.movie_delay,
                'leds_number': t.length,
                'frames_number': int(len(movie) / 3 / t.length)
            }
            t.mode = 'movie'
            t.set_movie_config(params)
            res = t.upload_movie(movie)
        else:
            res = t.get_movie_config()
    else:
        raise Exception("Unknown command")

    if args.json:
        print(json.dumps(res, indent=None, separators=(',', ':')))
    else:
        print(json.dumps(res, indent=4))


if __name__ == "__main__":
    main()
