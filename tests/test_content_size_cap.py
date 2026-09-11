# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""H-12: media download has no size cap and buffers everything in memory.

get_content() ran requests.get(...) without stream=True, so a customer
sending a huge video is read fully into memory before any size check can
happen, inside the synchronous webhook request. These tests drive the public
seam (line.api.service.get_content) with a fake streaming response and
assert the download is refused before the cap is exceeded.
"""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

MOCK_GET = 'odoo.addons.woow_line_base.models.line_api_service.http_requests.get'
MB = 1024 * 1024


class FakeStreamResponse:
    """Stand-in for requests.Response(stream=True). Counts pulled bytes."""

    def __init__(self, chunks, status_code=200, content_type='image/jpeg',
                 content_length=None):
        self.status_code = status_code
        self.headers = {'Content-Type': content_type}
        if content_length is not None:
            self.headers['Content-Length'] = str(content_length)
        self._chunks = chunks
        self.pulled = 0
        self.closed = False

    def iter_content(self, chunk_size=65536):
        for chunk in self._chunks:
            self.pulled += len(chunk)
            yield chunk

    def close(self):
        self.closed = True


@tagged('post_install', '-at_install', 'line_ci')
class TestContentSizeCap(TransactionCase):

    def setUp(self):
        super().setUp()
        self.api = self.env['line.api.service']
        self.ICP = self.env['ir.config_parameter'].sudo()

    def test_declared_length_over_cap_is_refused_without_reading_body(self):
        """Content-Length says 60 MB → refused, almost nothing pulled."""
        fake = FakeStreamResponse(
            chunks=[b'x' * MB for _ in range(60)],
            content_length=60 * MB,
        )
        with patch(MOCK_GET, return_value=fake):
            content, content_type = self.api.get_content('msg1', access_token='fake')

        self.assertEqual((content, content_type), (None, None))
        self.assertLessEqual(fake.pulled, MB, 'declared size must be checked before streaming')
        self.assertTrue(fake.closed)

    def test_lying_or_missing_content_length_is_capped_by_the_stream_itself(self):
        """No (or a lying) Content-Length, but the stream itself exceeds the
        cap → still refused, and we never pulled much past the cap."""
        cap_mb = 50
        fake = FakeStreamResponse(
            chunks=[b'y' * MB for _ in range(cap_mb + 10)],
            content_length=None,
        )
        with patch(MOCK_GET, return_value=fake):
            content, content_type = self.api.get_content('msg2', access_token='fake')

        self.assertEqual((content, content_type), (None, None))
        self.assertLessEqual(fake.pulled, (cap_mb * MB) + MB,
                              "must stop reading once the stream itself exceeds the cap")
        self.assertTrue(fake.closed)

    def test_small_file_within_cap_returns_exact_bytes(self):
        body = b'small-file-bytes'
        fake = FakeStreamResponse(
            chunks=[body],
            content_type='application/pdf',
            content_length=len(body),
        )
        with patch(MOCK_GET, return_value=fake):
            content, content_type = self.api.get_content('msg3', access_token='fake')

        self.assertEqual(content, body)
        self.assertEqual(content_type, 'application/pdf')
        self.assertTrue(fake.closed)

    def test_cap_is_configurable_via_ir_config_parameter(self):
        self.ICP.set_param('woow_line_base.content_max_mb', '1')
        fake = FakeStreamResponse(
            chunks=[b'z' * MB for _ in range(2)],
            content_length=2 * MB,
        )
        with patch(MOCK_GET, return_value=fake):
            content, content_type = self.api.get_content('msg4', access_token='fake')

        self.assertEqual((content, content_type), (None, None))
