import unittest
import logging
from hls_proxy import StreamingM3U8Processor, HLS_URI_PATTERN # Assuming hls_proxy.py is in the same directory or accessible

# Silence logging during tests unless specifically testing log output
# logging.disable(logging.CRITICAL)

class TestStreamingM3U8Processor(unittest.TestCase):

    def setUp(self):
        # Base URL for the M3U8 manifest segments and tags
        self.base_url = "http://example.com/live/"
        self.processor = StreamingM3U8Processor(self.base_url)
        # Reset line count for each test if necessary (though process_line is stateless regarding count for its output)
        self.processor.line_count = 0

    def test_rewrite_segment_url_relative(self):
        line = "segment1.ts"
        expected = "/proxy/http%3A//example.com/live/segment1.ts"
        self.assertEqual(self.processor.process_line(line), expected)

    def test_rewrite_segment_url_absolute(self):
        # Absolute segment URLs should also be proxied
        line = "http://othersite.com/segment2.ts"
        expected = "/proxy/http%3A//othersite.com/segment2.ts"
        self.assertEqual(self.processor.process_line(line), expected)

    def test_rewrite_ext_x_key_uri_relative(self):
        line = '#EXT-X-KEY:METHOD=AES-128,URI="key.bin"'
        expected = '#EXT-X-KEY:METHOD=AES-128,URI="/proxy/http%3A//example.com/live/key.bin"'
        self.assertEqual(self.processor.process_line(line), expected)

    def test_rewrite_ext_x_key_uri_absolute(self):
        line = '#EXT-X-KEY:METHOD=AES-128,URI="http://keys.example.com/key.bin"'
        expected = '#EXT-X-KEY:METHOD=AES-128,URI="/proxy/http%3A//keys.example.com/key.bin"'
        self.assertEqual(self.processor.process_line(line), expected)

    def test_rewrite_ext_x_map_uri_relative(self):
        line = '#EXT-X-MAP:URI="init.mp4"'
        expected = '#EXT-X-MAP:URI="/proxy/http%3A//example.com/live/init.mp4"'
        self.assertEqual(self.processor.process_line(line), expected)

    def test_rewrite_ext_x_map_uri_absolute(self):
        line = '#EXT-X-MAP:URI="https://maps.example.com/init.mp4"'
        expected = '#EXT-X-MAP:URI="/proxy/https%3A//maps.example.com/init.mp4"'
        self.assertEqual(self.processor.process_line(line), expected)

    def test_do_not_rewrite_extm3u(self):
        line = "#EXTM3U"
        self.assertEqual(self.processor.process_line(line), line)

    def test_do_not_rewrite_comment(self):
        line = "#This is a comment"
        self.assertEqual(self.processor.process_line(line), line)

    def test_do_not_rewrite_tag_without_uri(self):
        line = "#EXT-X-VERSION:3"
        self.assertEqual(self.processor.process_line(line), line)

    def test_do_not_rewrite_empty_line(self):
        line = ""
        self.assertEqual(self.processor.process_line(line), line)

    def test_rewrite_line_with_leading_trailing_spaces(self):
        line = "  segment3.ts  "
        # The current implementation's segment handling does line.strip()
        # before urljoin, so spaces around segment URLs are handled.
        # For tags, the regex handles spaces if they are part of the URI or other attributes.
        expected = "/proxy/http%3A//example.com/live/segment3.ts"
        self.assertEqual(self.processor.process_line(line), expected)

    def test_uri_with_query_parameters(self):
        line = '#EXT-X-KEY:METHOD=AES-128,URI="key.bin?id=123&token=abc"'
        expected = '#EXT-X-KEY:METHOD=AES-128,URI="/proxy/http%3A//example.com/live/key.bin%3Fid%3D123%26token%3Dabc"'
        self.assertEqual(self.processor.process_line(line), expected)

    def test_segment_url_with_query_parameters(self):
        line = "segment.ts?param1=val1&param2=val2"
        expected = "/proxy/http%3A//example.com/live/segment.ts%3Fparam1%3Dval1%26param2%3Dval2"
        self.assertEqual(self.processor.process_line(line), expected)

    def test_complex_ext_x_media_uri(self):
        line = '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aac",NAME="English",DEFAULT=YES,AUTOSELECT=YES,LANGUAGE="en",URI="audio/main.m3u8"'
        expected = '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aac",NAME="English",DEFAULT=YES,AUTOSELECT=YES,LANGUAGE="en",URI="/proxy/http%3A//example.com/live/audio/main.m3u8"'
        self.assertEqual(self.processor.process_line(line), expected)

    def test_line_is_just_uri(self):
        # This case implies a segment URL that might look like a full URL but is relative to nothing specific in the M3U8 context
        # but will be joined with base_url
        line = "another/segment4.ts"
        expected = "/proxy/http%3A//example.com/live/another/segment4.ts"
        self.assertEqual(self.processor.process_line(line), expected)

if __name__ == '__main__':
    unittest.main()
