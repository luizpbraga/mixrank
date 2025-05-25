import csv
import sys
import asyncio
import httpx
import logging
from urllib.parse import urljoin
from bs4 import BeautifulSoup


class Crawler:
    def __init__(self, workers=10):
        self.workers = workers
        self.client = None
        self.semaphore = asyncio.Semaphore(workers)
        self.timeout = 10
        self.writer = csv.writer(sys.stdout)

        # LOGS
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        # TODO: Let's try not to be blocked
        # self.user_agents = []
        # self.retry = 3

    async def __aenter__(self):
        """Async context manager entry"""
        self.client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=self.workers),
            timeout=self.timeout,
            # headers={'User-Agent': 'Mozilla/5.0 (compatible; LogoCrawler/1.0)'},
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.client:
            await self.client.aclose()

    # TODO: Implement data validation
    def parse(self, url, html):
        soup = BeautifulSoup(html, "html.parser")

        logo_url = ""
        favicon_url = ""

        # alem de src, tem: srcset data-src, data-srcet, data-lazy, dala-origin
        # img = soup.find("img", src=self.regex)
        # img = soup.select_one('img[src*="logo"], img[alt*="logo"], img[class*="logo"]')
        img = soup.select_one('img[src*="logo"], img[alt*="logo"], img[class*="logo"]')
        if img:
            src = img.get("src", None)
            if src:
                logo_url = urljoin(url, src)
        else:
            # meta = soup.find("meta", content=self.regex, property= lambda s: s and s in ["twitter:image", "og:image"])
            # meta_properties = ['og:image', 'og:image:url', 'twitter:image', 'twitter:image:src']
            meta = soup.select_one('meta[property*="image"], meta[name*="image"]')
            if meta:
                meta = meta.get("content", None)
                if meta:
                    logo_url = urljoin(url, meta)

        # areibuto rel: "icon" "shortcut icon" "apple-touch-icon" "mask-icon"
        # link = soup.select_one('link[href*="logo"], link[title*="logo"], link[rel*="logo"]')
        # link = soup.find("link", href=self.regex)
        link = soup.select_one('link[rel*="icon"], link[href*="favicon"]')
        if link:
            href = link.get("href", None)
            if href:
                favicon_url = urljoin(url, href)
                
        self.logger.info( f"[OK] {url} -> logo: {logo_url}, favicon: {favicon_url}")
        return (url, logo_url, favicon_url)

    # TODO: Implement fetch with retry logic
    # TODO: Implement erros rotations
    async def fetch(self, url):
        await asyncio.sleep(0.5)
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.text
        except Exception as e:
            self.logger.error(f"Failed to fetch {url}: {e}")
            # self.logger.warning(f"[ERROR] {url} -> {e}")

    async def fetch_and_parse(self, url):
        async with self.semaphore:
            html = await self.fetch(url)
            if html is None:
                return

            try:
                return self.parse(url, html)
            except Exception as e:
                self.logger.error(f"Parsing {url} -> {e}")
                return None


async def main():
    urls = [f"https://{line.strip()}" for line in sys.stdin if line.strip()]

    workers = 10
    async with Crawler(workers) as crawler:
        tasks = [asyncio.create_task(crawler.fetch_and_parse(url)) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        crawler.writer.writerow(["url", "logo_url", "favicon_url"])
        for result in results:
            if isinstance(result, tuple):
                url, logo_url, favicon_url = result
                crawler.writer.writerow([url, logo_url, favicon_url])


if __name__ == "__main__":
    asyncio.run(main())
