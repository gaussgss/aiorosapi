#
# -+- coding: utf-8 -+-

from .exceptions import RosApiSentenceOrderException


class RosApiWordParser(object):
    """
    Parse words sent from RouterOS API
    """

    def __init__(self):
        self._next_state = None
        self._state_fun = None

        self.flush()

    def flush(self):
        """
        Reset internal state and start from scratch
        :return: None
        """
        self._switch_state(self._sm_init_length_start)

    def feed(self, data):
        """
        Feed parser with new data
        :param data: bytestring to process
        :return: list of parsed words if any; empty list if data is incomplete
        """
        out = []

        for ch in data:
            while self._next_state is not None:
                cbfun, cbargs, cbkwargs = self._next_state
                self._next_state = None

                cbfun(*cbargs, **cbkwargs)

            r = self._state_fun(ch)
            if r is not None:
                out.append(r)

        return out

    # state machine implementation

    def _switch_state(self, fun, *args, **kwargs):
        """
        Prepare transition between internal states
        :param fun: function to call before feed
        :param args: positional arguments
        :param kwargs: keyword arguments
        :return: None
        """
        self._next_state = (fun, args, kwargs)

    def _sm_init_length_start(self):
        self._state_fun = self._sm_feed_length_start

    def _sm_feed_length_start(self, c):
        if c == 0x00: # zero bytes
            self._switch_state(self._sm_init_length_start)
            return b''

        if (c & 0x80) == 0x00: # one-byte
            self._switch_state(self._sm_init_length_more, 0, c)

        elif (c & 0xC0) == 0x80: # two-byte
            c &= ~0xC0
            self._switch_state(self._sm_init_length_more, 1, c)

        elif (c & 0xE0) == 0xC0: # three bytes
            c &= ~0xE0
            self._switch_state(self._sm_init_length_more, 2, c)

        elif (c & 0xF0) == 0xE0: # four bytes
            c &= ~0xF0
            self._switch_state(self._sm_init_length_more, 3, c)

        elif (c & 0xF8) == 0xF0: # five bytes
            c = 0x00
            self._switch_state(self._sm_init_length_more, 4, c)


    def _sm_init_length_more(self, count, value):
        if not count:
            self._switch_state(self._sm_init_word, value)
            return

        self._state_fun = self._sm_feed_length_more
        self._tmp_value = value
        self._tmp_counter = count

    def _sm_feed_length_more(self, c):
        if not self._tmp_counter:
            self._switch_state(self._sm_init_word, self._tmp_value)
            return

        self._tmp_value = ((self._tmp_value << 8) | c)
        self._tmp_counter -= 1


    def _sm_init_word(self, wordlen):
        self._state_fun = self._sm_feed_word
        self._tmp_counter = wordlen
        self._tmp_value = b''

    def _sm_feed_word(self, c):
        self._tmp_value += c.to_bytes(1, 'big')
        self._tmp_counter -= 1

        if not self._tmp_counter:
            out = self._tmp_value
            self._switch_state(self._sm_init_length_start)
            return out


class RosApiSentenceEncoder(object):
    """
    Sentence encoder for RouterOS API
    """
    def __init__(self, command=None, attrs=None, query=None, encoding='utf-8'):
        """
        Create new encoder instance
        :param command: command to insert
        :param attrs: dict of attributes
        :param query: list of query parameters (example: ["key=value", "-key", ...]
        :param encoding: which encoding to use while converting python strings to bytes
        """
        self._encoding = encoding
        self._buffer = b''
        self._started = False

        if command is not None:
            self.command(command)
            if attrs is not None:
                for k, v in attrs.items():
                    self.add_attribute(k, v)
            if query is not None:
                for q in query:
                    self.add_query(q)

    def _encode_length(self, len):
        if len == 0x00: return len.to_bytes(1, 'big')
        if len < 0x7f: return len.to_bytes(1, 'big')
        elif len <= 0x3FFF: return (len | 0x8000).to_bytes(2, 'big')
        elif len <= 0x1fffff: return (len | 0xC00000).to_bytes(3, 'big')
        elif len <= 0xFFFFFFF: return (len | 0xE0000000).to_bytes(4, 'big')
        else: return b'\xF0' + (len.to_bytes(4, 'big'))

    def _encode_word(self, w):
        if not isinstance(w, bytes): w = w.encode(self._encoding)
        return self._encode_length(len(w)) + w

    def _encode_attribute(self, name, value):
        return self._encode_word('=' + name + '=' + value)

    def _encode_query(self, query):
        return self._encode_word('?' + query)

    def command(self, cmd):
        """
        Clear internal buffer, encode and add command there.
        Must be first thing to call if `command` parameter not passed in __init__
        :param cmd: command string
        :return: None
        """
        self._buffer = self._encode_word(cmd)
        self._started = True

    def add_attribute(self, name, value):
        """
        Encode and add attribute to current buffer
        :param name: attribute name, string
        :param value: attribute value, string
        :return: None
        """
        if not self._started: raise RosApiSentenceOrderException()
        self._buffer += self._encode_attribute(name, value)

    def add_query(self, q):
        """
        Encode and add query line to current buffer
        :param q: query string
        :return: None
        """
        if not self._started: raise RosApiSentenceOrderException()
        self._buffer += self._encode_query(q)

    def get_buffer(self):
        """
        Return current buffer
        :return: buffer contents as bytestring
        """
        return self._buffer + self._encode_word('')
