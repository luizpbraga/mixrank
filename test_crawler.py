import unittest
from unittest.mock import MagicMock, AsyncMock
from crawler import Crawler


# TODO: Add test for lazy-loaded images (data-src attribute)
# TODO: Add test for fallback to meta og:image tag
# TODO: Add test for favicon detection via link rel=icon
class TestCrawlerParsing(unittest.TestCase):
    """Basic tests for HTML parsing logic."""

    def setUp(self):
        self.crawler = Crawler()

    def test_parse_direct_logo_img_src(self):
        """Test finding logo via img src attribute."""
        html = '<html><body><img src="/images/logo.png" alt="Site Logo"></body></html>'
        url = "https://example.com"

        logo_url, favicon_url = self.crawler.parse(url, html)

        self.assertEqual(logo_url, "https://example.com/images/logo.png")
        self.assertEqual(favicon_url, "")

    def test_parse_logo_via_class_attribute(self):
        """Test finding logo via CSS class containing 'logo'."""
        html = '<html><body><img src="/header.png" class="site-logo"></body></html>'
        url = "https://example.com"

        logo_url, favicon_url = self.crawler.parse(url, html)

        self.assertEqual(logo_url, "https://example.com/header.png")

    def test_parse_no_logo_found(self):
        """Test when no logo can be found in HTML."""
        html = "<html><body><p>Just some text content</p></body></html>"
        url = "https://example.com"

        logo_url, favicon_url = self.crawler.parse(url, html)

        self.assertEqual(logo_url, "")
        self.assertEqual(favicon_url, "")

    def test_parse_relative_url_conversion(self):
        """Test that relative URLs are converted to absolute URLs."""
        html = '<html><body><img src="logo.png" alt="logo"></body></html>'
        url = "https://example.com/subdir/"

        logo_url, favicon_url = self.crawler.parse(url, html)

        self.assertEqual(logo_url, "https://example.com/subdir/logo.png")


# TODO: Add test for print_summary method output
# TODO: Add test for success rate calculations
class TestCrawlerMetrics(unittest.TestCase):
    """Basic tests for metrics functionality."""

    def setUp(self):
        self.metrics = Crawler.Metrics()

    def test_metrics_initialization(self):
        """Test metrics are properly initialized."""
        self.assertEqual(self.metrics.stats["total_processed"], 0)
        self.assertEqual(self.metrics.stats["logos_found"], 0)

    def test_record_success_with_logo(self):
        """Test recording successful logo extraction."""
        self.metrics.record_success(has_logo=True)

        self.assertEqual(self.metrics.stats["total_processed"], 1)
        self.assertEqual(self.metrics.stats["logos_found"], 1)

    def test_record_error(self):
        """Test recording different types of errors."""
        self.metrics.record_error("network_error")
        self.metrics.record_error("network_error")  # Increment existing

        self.assertEqual(self.metrics.stats["network_error"], 2)

# TODO: Add test for timeout handling
# TODO: Add test for HTTP error responses (404, 500, etc)
# TODO: Add test for network errors
# TODO: Add integration test for fetch_and_parse pipeline
class TestCrawlerAsync(unittest.IsolatedAsyncioTestCase):
    """Basic async tests - these are tricky to get right."""

    async def test_fetch_success(self):
        """Test successful HTTP fetch."""
        crawler = Crawler()

        # Mock the HTTP client
        mock_response = MagicMock()
        mock_response.text = "<html><body>Test content</body></html>"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        crawler.client = mock_client

        result = await crawler.fetch("https://example.com")

        self.assertEqual(result, "<html><body>Test content</body></html>")

# TODO: Add test for malformed HTML
# TODO: Add test for img tags without src attribute
# TODO: Add test for very large HTML documents
# TODO: Add test for non-UTF8 encoding issues
class TestEdgeCases(unittest.TestCase):
    """Edge cases that could break things."""

    def setUp(self):
        self.crawler = Crawler()

    def test_parse_empty_html(self):
        """Test parsing empty HTML doesn't crash."""
        html = ""
        url = "https://example.com"

        # Should not raise exception
        logo_url, favicon_url = self.crawler.parse(url, html)

        self.assertEqual(logo_url, "")
        self.assertEqual(favicon_url, "")


# TODO: Add tests for main() function
# TODO: Add tests for command line argument handling
# TODO: Add performance/load tests for concurrent processing
# TODO: Add tests for CSV output format validation
if __name__ == "__main__":
    # Run the basic tests we have
    unittest.main(verbosity=2)
