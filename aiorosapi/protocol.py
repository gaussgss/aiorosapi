#
# -+- coding: utf-8 -+-

import asyncio
from asyncio import QueueEmpty
from collections import namedtuple

from .packet import RosApiSentenceEncoder, RosApiWordParser
from .exceptions import RosApiConnectionLostException, RosApiCommunicationException, RosApiNoResultsException, \
    RosApiTooManyResultsException, RosApiTrapException, RosApiFatalException, RosApiLoginFailureException, \
    RosApiCommunicationTimeoutException
from .utils import LoggingMixin


RosApiAnswer = namedtuple('RosApiAnswer', 'ret items')


class RosApiProtocol(asyncio.Protocol, LoggingMixin):
    DONE_REPLY = b'!done'
    DATA_REPLY = b'!re'
    TRAP_REPLY = b'!trap'
    FATAL_REPLY = b'!fatal'

    @property
    def logging_raw(self):
        return self.logging.getChild('raw')

    @property
    def logging_proto(self):
        return self.logging.getChild('protocol')

    def __init__(self, talk_encoding='utf-8', answer_timeout=30, loop=None):
        self._talk_encoding = talk_encoding
        self._loop = loop or asyncio.get_event_loop()

        self._parser = RosApiWordParser()
        self._disconnected = self._loop.create_future()
        self._received_frames = asyncio.Queue()

        self._answer_timeout = answer_timeout

    def connection_made(self, t):
        self.logging_raw.debug("Connected to API {}".format(t))
        self._transport = t

    def connection_lost(self, e):
        self.logging_raw.debug("Connection lost: {}".format(e))
        self._transport = None
        self._disconnected.set_result(True)
        self._received_frames.put_nowait(RosApiConnectionLostException)

    def data_received(self, data):
        self.logging_raw.debug('Received data: {}'.format(data))
        for out in self._parser.feed(data):
            self.logging_raw.debug('Received frame: {}'.format(out))
            self._received_frames.put_nowait(out)

    def eof_received(self):
        return False

    def is_connected(self):
        return self._transport is not None

    async def _receive_sentence(self):
        answer = []
        while True:
            if not self.is_connected(): raise RosApiConnectionLostException()
            r = await self._received_frames.get()
            if r is RosApiConnectionLostException: raise RosApiConnectionLostException()
            if r is b'': break
            answer.append(r)

        return answer

    def _parse_kv(self, answer, encoding=None):
        encoding = encoding or self._talk_encoding

        parsed = {}
        skipped = []

        for item in answer:
            if item.startswith(b'='):
                kv = item[1:].split(b'=', 1)
                if len(kv) == 2:
                    k = kv[0].decode(encoding, 'replace')
                    v = kv[1].decode(encoding, 'replace')
                    parsed[k] = v

                else:
                    skipped.append(item)
            else:
                skipped.append(item)

        return parsed, skipped

    def _parse_obj(self, obj_str):
        parsed = {}

        buf = ''
        cur_name = None
        cur_value = None
        for ch in obj_str:
            if ch == '=':
                if cur_name is not None: parsed[cur_name] = cur_value

                cur_name = buf
                cur_value = []
                buf = ''

            elif ch == ';':
                cur_value.append(buf)
                buf = ''

            else:
                buf += ch

        if cur_name is not None:
            cur_value.append(buf)
            parsed[cur_name] = cur_value

        return parsed

    async def _talk(self, sentence):
        self.logging_proto.debug('API REQUEST {}'.format(sentence))

        if self._transport is None: raise RosApiConnectionLostException()
        self._transport.write(sentence)

        exception = None
        exception_info = []

        results = []

        while True:
            try: answer = await asyncio.wait_for(self._receive_sentence(), self._answer_timeout)
            except asyncio.TimeoutError: raise RosApiCommunicationTimeoutException("No answer from device")

            if len(answer) == 0: raise RosApiCommunicationException("Zero length answer")

            self.logging_proto.debug("API ANSWER {}".format(answer))

            ans = answer[0]
            if ans == self.DONE_REPLY:
                ret, skip = self._parse_kv(answer[1:])
                if len(skip): self.logging_proto.debug('skipped words in !done answer: {}'.format(skip))
                break

            elif ans == self.DATA_REPLY:
                result, skip = self._parse_kv(answer[1:])
                results.append(result)
                if len(skip): self.logging_proto.debug("skipped words in !data answer: {}".format(skip))

            elif ans == self.TRAP_REPLY:
                exception = RosApiTrapException
                exception_info, skip = self._parse_kv(answer[1:])
                if len(skip): self.logging_proto.debug("skipped words in !trap answer: {}".format(skip))

            elif ans == self.FATAL_REPLY:
                exception = RosApiFatalException
                exception_info, skip = self._parse_kv(answer[1:])
                if len(skip): self.logging_proto.debug("skipped words in !fatal answer: {}".format(skip))

        if exception is not None:
            raise exception(exception_info)

        return RosApiAnswer(ret, results)

    # developer-side api

    async def disconnect(self):
        """
        Disconnect from API server
        :return:
        """
        self._transport.close()

    async def wait_disconnect(self):
        """
        Wait for server to disconnect, use after disconnect() call. Also useful for detecting sudden disconnections.
        :return: True on disconnect
        """
        return await self._disconnected

    async def flush(self):
        """
        Flush internal frame buffer
        :return: None
        """
        while True:
            try: self._received_frames.get_nowait()
            except QueueEmpty: break

    async def execute(self, cmd, attrs=None, query=None):
        """
        Execute command and return tuple of (ret, items)
        :param cmd: command to execute
        :param attrs: attributes
        :param query: query
        :return: RosApiAnswer tuple
        """
        sentence = RosApiSentenceEncoder(cmd, attrs, query).get_buffer()
        return await self._talk(sentence)

    async def execute_ret_obj(self, cmd, attrs=None, query=None):
        """
        Execute command and return tuple of (ret_kv, items)
        :param cmd: command to execute
        :param attrs: attributes
        :param query: query
        :return: RosApiAnswer tuple
        """
        sentence = RosApiSentenceEncoder(cmd, attrs, query).get_buffer()
        ret, items = await self._talk(sentence)
        ret = ret.get('ret', '')
        ret = self._parse_obj(ret)
        return ret, items


    async def talk_all(self, cmd, attrs=None, query=None):
        """
        Perform API request and return all sentences as list of dicts
        :param cmd: command to execute
        :param attrs: attributes
        :param query: query
        :return: all received sentences as a list of dicts
        """
        sentence = RosApiSentenceEncoder(cmd, attrs, query).get_buffer()
        return (await self._talk(sentence)).items

    async def talk_first(self, cmd, attrs=None, query=None):
        """
        Perform API request and return only first sentence as a dict
        :param cmd: command to execute
        :param attrs: attributes
        :param query: query
        :return: first sentence of answer as a dict
        :exception RosApiNoResultsException if empty result set is received
        """
        sentence = RosApiSentenceEncoder(cmd, attrs, query).get_buffer()
        ret, out = await self._talk(sentence)
        if not len(out): raise RosApiNoResultsException()
        return out[0]

    async def talk_one(self, cmd, attrs=None, query=None):
        """
        Perform API reequest and return first sentence as a dict,
        raise exception if more than one sentence received or no sentences received at all
        :param cmd: command to execute
        :param attrs: attributes
        :param query: query
        :return: first sentence of answer as a dict
        :exception RosApiNoResultsException if empty result set is received
        :exception RosApiTooManyResultsException if received more than one result sentence
        """
        sentence = RosApiSentenceEncoder(cmd, attrs, query).get_buffer()
        ret, out = await self._talk(sentence)
        if not len(out): raise RosApiNoResultsException()
        if len(out) != 1: raise RosApiTooManyResultsException()
        return out[0]

    async def find(self, cmd, match=lambda a: True):
        """
        Iterate over all values returned by cmd/print and return sentences that matched by 'match' function
        :param cmd: api command to search, /print will be appended automatically
        :param match: filter function returns True if record is matched
        :return: list of matched records
        """
        out = []
        if not cmd.endswith('/print'): cmd += '/print'
        rsp = await self.talk_all(cmd)
        for l in rsp:
            if match(l): out.append(l)

        return out

    async def find_attrs(self, cmd, attrs):
        """
        Search list and return records that matches all of attrs
        :param cmd: api command to search, /print will be appended automatically
        :param attrs: dict of attributes to match
        :return: list of matched records
        """
        return await self.find(
            cmd,
            lambda m: any(
                m.get(k) == v for k, v in attrs.items()
            )
        )

    async def set_values(self, cmd, search, values_to_set):
        """
        Set values to records matched by search
        :param cmd: command to work with
        :param search: dict with search request
        :param values_to_set: values to set into matched records
        :return: list of changed record id's
        """
        changed = []

        rsp_find = await self.talk_all(cmd + '/print')
        for line in rsp_find:
            for k, v in search.items():
                if line.get(k) != v: continue

                lid = line.get('.id')

                vts = {'.id': lid}
                vts.update(values_to_set)

                await self.talk_all(cmd + '/set', vts)
                changed.append(lid)

        return changed


    def _make_login_sentence(self, username, password):
        """
        Generate login sentence for currently set credentials
        :param username: username
        :param password: password
        :return: generated sentence as a bytestring
        """
        return RosApiSentenceEncoder(
            '/login', {
                'name': username,
                'password': password
            }).get_buffer()

    async def login(self, username, password):
        """
        Perform API login using username and password
        :param username: username
        :param password: password
        :return: None
        :exception RosApiLoginFailureException on unsuccessful login
        """
        try:
            await self._talk(self._make_login_sentence(username, password))

        except RosApiTrapException as e:
            raise RosApiLoginFailureException("Login failure: {}".format(e))


async def create_ros_connection(host, port, username, password):
    """
    Create new RouterOS API connection
    :param host: hostname
    :param port: tcp port to use
    :param username: user name
    :param password: password
    :return: connected RosApiProtocol instance
    :exception RosApiLoginFailureException on unsuccessful login
    """
    loop = asyncio.get_event_loop()

    t, p = await loop.create_connection(lambda: RosApiProtocol(), host, port)
    await p.login(username, password)

    return p

