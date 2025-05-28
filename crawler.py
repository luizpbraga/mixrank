import asyncio
import csv
import logging
import sys
import time
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup


class Crawler:
    """
    Asynchronous web crawler for logo and favicon extraction.

    Features:
    - Concurrency to prevent overwhelming target servers
    - Multiple logo detection strategies with fallbacks
    - Built-in metrics collection for monitoring
    - Logging for debugging
    """

    class Metrics:
        """
        (Super) Simple metrics collection for monitoring crawler performance.

        KPIs:
        - Processing rate (requests per second)
        - Success rate (logos found vs total processed)
        - Error categorization for debugging

        Improvements:
        - Export to monitoring systems (Prometheus, DataDog)
        - Add precision/recall measurements via sampling
        - Track response time percentiles
        - Monitor memory and CPU usage
        - Alert on quality degradation
        """

        def __init__(self) -> None:
            self.stats = {
                "total_processed": 0,
                "logos_found": 0,
            }
            self.start_time = time.time()

        def record_success(self, has_logo=False):
            """
            Record successful processing of a domain whether a logo was successfully extracted
            """
            self.stats["total_processed"] += 1
            if has_logo:
                self.stats["logos_found"] += 1

        def record_error(self, error_type):
            """
            Record processing errors by type for debugging.

            Common error types: 'network_error', 'parse_error', 'timeout'
            """
            if error_type not in self.stats:
                self.stats[error_type] = 0
            self.stats[error_type] += 1

        def print_summary(self):
            """
            Output processing summary with key performance metrics.

            Provides visibility into:
            - Total processing volume and rate
            - Logo discovery success rate
            - Processing efficiency (req/sec)
            """
            # Configure logging for metrics output
            logging.basicConfig(level=logging.INFO)
            logger = logging.getLogger("Metrics")

            runtime = time.time() - self.start_time
            total = self.stats["total_processed"]
            found = self.stats["logos_found"]

            logger.info(
                f"Processing Complete - {total} domains processed in {runtime:.1f} sec"
            )
            logger.info(
                f"Logo Discovery Rate: {found}/{total} ({found/total*100:.1f}% success)"
            )
            logger.info(f"Processing Rate: {total/runtime:.1f} domains/sec")

            # Report error statistics if any occurred
            error_types = [
                k
                for k in self.stats.keys()
                if k not in ["total_processed", "logos_found"]
            ]
            if error_types:
                logger.info("Error Breakdown:")
                for error_type in error_types:
                    count = self.stats[error_type]
                    logger.info(f"  {error_type}: {count} ({count/total*100:.1f}%)")

    def __init__(self, request_limit=10):
        """
        Initialize crawler with configurable concurrency and monitoring.
        """
        self.url_queue = asyncio.Queue()
        self.csv_queue = asyncio.Queue()

        self.request_limit = request_limit
        self.client = None
        # Control concurrent requests
        self.semaphore = asyncio.Semaphore(request_limit)
        # HTTP request timeout in seconds
        self.timeout = 10
        self.writer = csv.writer(sys.stdout)

        # Logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        self.logger = logging.getLogger(__name__)

        # Built-in metrics collection for quality monitoring (need to be improved)
        self.metrics = Crawler.Metrics()

        # TODO:Future Enhancements: User-Agent rotation to reduce blocking risk
        # self.user_agents = [
        #     'Mozilla/5.0 (compatible; LogoCrawler/1.0)',
        #     'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        # ]

        # TODO: Retry configuration with exponential backoff
        # self.max_retries = 3
        # self.retry_delay = 1.0

    async def __aenter__(self):
        """
        Initialize HTTP client with optimized settings for web crawling.

        Production Considerations:
        - Add request/response middleware for monitoring
        - Implement retry logic pattern for failing domains
        """
        self.client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=self.request_limit),
            timeout=self.timeout,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up HTTP client resources and output final metrics."""
        if self.client:
            await self.client.aclose()
        self.metrics.print_summary()

    def parse(self, url, html):
        """
        Extract logo and favicon URLs using multi-strategy parsing approach.

        NOTE FOR REVIEWER: ChatGPT helped me with the holistic about where to
            find the logos i.e. tags and properties.

        Logo Detection Strategy (in priority order):
        1. Direct <img> tags with logo-related attributes
           - Covers explicit logo images with semantic naming
           - Includes lazy-loading attributes (data-src, data-lazy)
           - Searches src, alt, class, and id attributes

        2. Meta tags for social media images
           - og:image, twitter:image often contain site logos
           - Fallback when direct logo images aren't found
           - Useful for sites that only define social sharing images

        Favicon Detection Strategy:
        - Standard link[rel=icon] tags
        - Direct favicon.ico references
        - Covers most common favicon implementations

        Future Enhancements:
        1. Logo Validation:
           - Check image accessibility before returning URL
           - Validate image dimensions (filter out tiny icons)
           - Verify file type matches image format

        2. Quality:
           - Prefer larger images when multiple candidates exist
           - Score based on semantic context (header vs footer)
           - Filter obvious non-logos (social icons, ads)
        """

        soup = BeautifulSoup(html, "html.parser")
        logo_url = ""
        favicon_url = ""

        # PRIMARY LOGO DETECTION: Multi-attribute image search
        # Enhanced selector covers various logo implementations:
        # - src/alt containing "logo" (explicit naming)
        # - class/id containing "logo" or "brand" (semantic CSS)
        # - data-src/data-lazy for lazy-loaded images (performance optimization)
        img = soup.select_one(
            """
            img[src*="logo"], 
            img[alt*="logo"], 
            img[class*="logo"],
            img[class*="brand"],
            img[id*="logo"],
            img[id*="brand"],
            img[data-src*="logo"],
            img[data-lazy*="logo"]
        """
        )

        if img:
            # Check multiple attributes for lazy-loading support
            # Priority: src (loaded) > data-src (lazy) > data-lazy (lazy)
            src = img.get("src") or img.get("data-src") or img.get("data-lazy")
            if src:
                logo_url = urljoin(url, src)
                self.metrics.record_success(has_logo=True)
                self.logger.info(f"Logo found via IMG tag: {logo_url}")
        else:
            # FALLBACK: Social media meta tags
            # Many sites define logos only for social sharing
            # og:image and twitter:image often contain primary site logos
            meta = soup.select_one('meta[property*="image"], meta[name*="image"]')
            if meta:
                content = meta.get("content")
                if content:
                    logo_url = urljoin(url, content)
                    self.metrics.record_success(has_logo=True)
                    self.logger.info(f"Logo found via meta tag: {logo_url}")

        # Always record processing attempt, even if no logo found
        if not logo_url:
            self.metrics.record_success(has_logo=False)

        # FAVICON DETECTION: Standard approach
        # Covers most common favicon implementations:
        # - link[rel*="icon"] catches icon, shortcut icon, apple-touch-icon
        # - link[href*="favicon"] catches direct favicon.ico references
        link = soup.select_one('link[rel*="icon"], link[href*="favicon"]')
        if link:
            href = link.get("href")
            if href:
                favicon_url = urljoin(url, href)

        self.logger.info(f"Parsed {url} -> Logo: {logo_url}, Favicon: {favicon_url}")
        return (logo_url, favicon_url)

    async def fetch(self, url):
        """
        Fetch HTML content with rate limiting and error handling.

        Rate Limiting:
        - 0.5s delay between requests to be respectful to servers
        - Prevents overwhelming target infrastructure
        - Reduces risk of IP-based blocking

        Future Improvements:
        1. Retry Logic:
           - Exponential backoff for transient failures
           - Differentiate retryable vs permanent errors
           - Circuit breaker for consistently failing domains
           - Adaptive delays based on server response times
           - Deal with cookies and JavaScript
        """
        # Basic rate limiting
        await asyncio.sleep(0.5)
        async with self.semaphore:
            try:
                response = await self.client.get(url)
                response.raise_for_status()
                return response.text

            except httpx.TimeoutException as e:
                self.logger.error(f"Timeout fetching {url}: {e}")
                self.metrics.record_error("timeout_error")
            except httpx.HTTPStatusError as e:
                self.logger.error(f"HTTP error {e.response.status_code} for {url}: {e}")
                self.metrics.record_error("http_error")
            except httpx.NetworkError as e:
                self.logger.error(f"Network error fetching {url}: {e}")
                self.metrics.record_error("network_error")
            except Exception as e:
                self.logger.error(f"Unexpected error fetching {url}: {e}")
                self.metrics.record_error("unknown_error")

            return None

    async def fetch_and_parse(self):
        """
        Main processing pipeline: fetch URL and extract logo information.

        Process Flow:
        1. Acquire semaphore slot (concurrency control)
        2. Fetch HTML content via HTTP request
        3. Parse content to extract logo and favicon URLs
        4. Return structured result tuple

        Concurrency Control:
        - Semaphore limits concurrent requests to prevent overwhelming servers
        - Ensures some system resource usage
        - Provides backpressure when processing large domain lists

        Future Enhancements:
        1. Result Validation:
           - Verify extracted URLs are accessible
           - Check image format and dimensions
           - Score logo quality/confidence

        2. Partial Results:
           - Return results even if parsing partially fails
           - Separate logo and favicon extraction errors
           - Include metadata about extraction confidence

        3. Caching:
           - Cache successful results to avoid re-processing
           - Handle cache invalidation for dynamic content
           - Share cache across crawler instances
        """

        # Control concurrent request load
        while True:
            domain = await self.url_queue.get()
            url = f"https://{domain}"
            try:
                # Fetch HTML content with error handling and rate limiting
                html = await self.fetch(url)
                if html is not None:
                    # Parse HTML to extract logo and favicon URLs
                    logo_url, favicon_url = self.parse(url, html)
                    await self.csv_queue.put((domain, logo_url, favicon_url))
            except Exception as e:
                # Parsing errors are separate from network errors
                self.logger.error(f"Failed to parse {url}: {e}")
                self.metrics.record_error("parse_error")
            finally:
                self.url_queue.task_done()

    async def writer_csv(self):
        self.writer.writerow(["domain", "logo_url", "favicon_url"])
        # Write successful results to CSV, skip failures
        while True:
            result = await self.csv_queue.get()

            if result is None:
                self.csv_queue.task_done()
                break

            self.writer.writerow(result)
            self.csv_queue.task_done()


async def main():
    """
    Main entry point: orchestrates domain processing and CSV output.

    Input Processing:
    - Reads domain names from stdin (one per line)
    - Converts bare domains to HTTPS URLs automatically
    - Filters empty lines for clean processing

    Concurrent Processing:
    - Creates async tasks for all domains upfront
    - Uses asyncio.gather() for parallel execution

    Output Format:
    - CSV with headers: url, logo_url, favicon_url
    - Empty strings for missing logos/favicons (I don't like null values)

    Future Improvements:
    1. Input Validation:
       - Validate domain format before processing
       - Support both HTTP/HTTPS URLs in input

    2. Streaming Output:
       - Write CSV rows as results complete (vs batching)
       - Add progress reporting for large domain lists

    3. Configuration:
       - Command-line arguments for worker count, timeout
       - Support for input/output file arguments
       - Configurable CSV format and delimiters

    4. Quality:
       - Sample validation of extracted logos
       - Precision/recall measurement against known good data
       - Confidence scoring in output
    """
    # Read and prepare domain list from stdin
    # Convert bare domains to HTTPS URLs for consistency
    domains = set(line.strip() for line in sys.stdin if line.strip())
    if not domains:
        logging.warning("No domains provided on stdin")
        return

    request_limit = 10
    async with Crawler(request_limit) as crawler:

        for domain in domains:
            crawler.url_queue.put_nowait(domain)

        work_tasks = [
            asyncio.create_task(crawler.fetch_and_parse()) for _ in range(100)
        ]

        # Start the writer
        writer_task = asyncio.create_task(crawler.writer_csv())

        # Process all URL
        await crawler.url_queue.join()

        # Stop Writing
        await crawler.csv_queue.put(None)
        await crawler.csv_queue.join()

        for t in work_tasks:
            t.cancel()
        writer_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
