#
# -+- coding: utf-8 -+-

import asyncio
from asyncio import QueueEmpty


from .packet import RosApiSentenceEncoder, RosApiWordParser
from .exceptions import RosApiConnectionLostException, RosApiCommunicationException, RosApiNoResultsException, \
    RosApiTooManyResultsException, RosApiTrapException, RosApiFatalException, RosApiLoginFailureException
from .utils import LoggingMixin


class RosApiProtocol(asyncio.Protocol, LoggingMixin):
    DONE_REPLY = b'!done'
    DATA_REPLY = b'!re'
    TRAP_REPLY = b'!trap'
    FATAL_REPLY = b'!fatal'

    def __init__(self, talk_encoding='utf-8', loop=None):
        self._talk_encoding = talk_encoding
        self._loop = loop or asyncio.get_event_loop()

        self._parser = RosApiWordParser()
        self._disconnected = self._loop.create_future()
        self._received_frames = asyncio.Queue()

    def connection_made(self, t):
        self.logging.debug("Connected to API {}".format(t))
        self._transport = t

    def connection_lost(self, e):
        self.logging.debug("Connection lost: {}".format(e))
        self._transport = None
        self._disconnected.set_result(True)
        self._received_frames.put(RosApiConnectionLostException)

    def data_received(self, data):
        for out in self._parser.feed(data):
            self._loop.create_task(self._received_frames.put(out))

    def eof_received(self):
        return False

    async def _receive_sentence(self):
        answer = []
        while True:
            r = await self._received_frames.get()
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

    async def _talk(self, sentence):
        self.logging.debug('API REQUEST {}'.format(sentence))

        self._transport.write(sentence)

        exception = None
        exception_info = []

        results = []

        while True:
            answer = await self._receive_sentence()
            if len(answer) == 0: raise RosApiCommunicationException("Zero length answer")

            self.logging.debug("API ANSWER {}".format(answer))

            ans = answer[0]
            if ans == self.DONE_REPLY:
                break

            elif ans == self.DATA_REPLY:
                result, skip = self._parse_kv(answer[1:])
                results.append(result)
                if len(skip): self.logging.debug("skipped words in answer: {}".format(skip))

            elif ans == self.TRAP_REPLY:
                exception = RosApiTrapException
                exception_info, skip = self._parse_kv(answer[1:])
                if len(skip): self.logging.debug("skipped words in answer: {}".format(skip))

            elif ans == self.FATAL_REPLY:
                exception = RosApiFatalException
                exception_info, skip = self._parse_kv(answer[1:])
                if len(skip): self.logging.debug("skipped words in answer: {}".format(skip))

        if exception is not None:
            raise exception(exception_info)

        return results

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

    async def talk_all(self, cmd, attrs=None, query=None):
        """
        Perform API request and return all sentences as list of dicts
        :param cmd: command to execute
        :param attrs: attributes
        :param query: query
        :return: all received sentences as a list of dicts
        """
        sentence = RosApiSentenceEncoder(cmd, attrs, query).get_buffer()
        return await self._talk(sentence)

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
        out = await self._talk(sentence)
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
        out = await self._talk(sentence)
        if not len(out): raise RosApiNoResultsException()
        if len(out) != 1: raise RosApiTooManyResultsException()
        return out[0]

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

