#
# -+- coding: utf-8 -+-

import unittest

from aiorosapi.packet import RosApiSentenceEncoder, RosApiWordParser


class RosApiSentenceTest(unittest.TestCase):
    def test_length(self):
        t = RosApiSentenceEncoder()

        self.assertEqual(b'\x00', t._encode_length(0x00))
        self.assertEqual(b'\x55', t._encode_length(0x55))
        self.assertEqual(b'\x80\x80', t._encode_length(0x80))
        self.assertEqual(b'\xBF\xFF', t._encode_length(0x3FFF))
        self.assertEqual(b'\xC0\x40\x00', t._encode_length(0x4000))
        self.assertEqual(b'\xDF\xFF\xFF', t._encode_length(0x1FFFFF))
        self.assertEqual(b'\xE0\x20\x00\x00', t._encode_length(0x200000))
        self.assertEqual(b'\xEF\xFF\xFF\xFF', t._encode_length(0xFFFFFFF))
        self.assertEqual(b'\xF0\x10\x00\x00\x00', t._encode_length(0x10000000))
        self.assertEqual(b'\xF0\xFF\xFF\xFF\xFF', t._encode_length(0xFFFFFFFF))

    def test_encoder(self):
        t = RosApiSentenceEncoder()

        t.command("check1")
        self.assertEqual(b'\x06check1\x00', t.get_buffer())

        t.command('check2')
        t.add_attribute('attr1', 'value1')
        t.add_attribute('attr2', 'value2')
        self.assertEqual(b'\x06check2\x0d=attr1=value1\x0d=attr2=value2\x00', t.get_buffer())

        t.command('check3')
        t.add_attribute('attr1', 'value1')
        t.add_query('value=test')
        self.assertEqual(b'\x06check3\x0d=attr1=value1\x0b?value=test\x00', t.get_buffer())

    def test_word_parser(self):
        t = RosApiWordParser()
        out = t.feed(b'\x06check3\x0d=attr1=value1\x0b?value=test\x00')
        self.assertEqual([b'check3', b'=attr1=value1', b'?value=test', b''], out)

        out = t.feed(b'\x00')
        self.assertEqual([b''], out)
