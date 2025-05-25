import csv
import sys
import asyncio
import httpx
from urllib.parse import urljoin
from bs4 import BeautifulSoup


class Crawler:
    def __init__(self, workers=10):
        self.workers = workers
        self.client = None
        self.semaphore = asyncio.Semaphore(workers)
        self.timeout = 10
        self.writer = csv.writer(sys.stdout)

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

    async def fetch_page(self, url):
        await asyncio.sleep(0.5)
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.text

        # TODO: use logs; more robust error handling
        except Exception as e:
            print(f"ERROR: fetching {url}: {e}")

        return None

    def parse(self, url, html):
        soup = BeautifulSoup(html, "html.parser")

        logo_url = ""
        favicon_url = ""

        # alem de src, tem: srcset data-src, data-srcet, data-lazy, dala-origin
        # img = soup.find("img", src=self.regex)
        # img = soup.select_one('img[src*="logo"], img[alt*="logo"], img[class*="logo"]')
        img = soup.select_one(
            """ img[src*="logo"], img[alt*="logo"], img[class*="logo"] """
        )
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

        return (logo_url, favicon_url)

    async def fetch_and_parse(self, url):
        async with self.semaphore:
            try:
                response = await self.client.get(url)
                response.raise_for_status()

                html = response.text
                if html is None:
                    return

                title = self.parse(url, html)
                print(f"[OK] {url} -> {title}")
                # return {"url": url, "title": title, "html": html}

            except Exception as e:
                print(f"[ERROR] {url} -> {e}")
                return None


async def main():
    urls = [f"https://{line.strip()}" for line in sys.stdin if line.strip()]

    async with Crawler(10) as crawler:
        tasks = [asyncio.create_task(crawler.fetch_and_parse(url)) for url in urls]
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
