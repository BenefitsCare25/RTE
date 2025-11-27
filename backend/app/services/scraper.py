from playwright.async_api import async_playwright, Browser, Page, Playwright
from typing import Optional, Dict, List
import asyncio
import logging
import random
import os
from app.utils.extractors import ContactExtractor

logger = logging.getLogger(__name__)

# Rotating user agents to appear more human-like
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
]

# Viewport sizes to rotate
VIEWPORTS = [
    {'width': 1920, 'height': 1080},
    {'width': 1366, 'height': 768},
    {'width': 1536, 'height': 864},
    {'width': 1440, 'height': 900},
    {'width': 1280, 'height': 720},
]


class WebScraper:
    """Service for scraping company websites to extract contact information"""

    def __init__(self):
        self.browser: Optional[Browser] = None
        self.playwright: Optional[Playwright] = None
        self.extractor = ContactExtractor()
        self._request_count = 0

        # Proxy configuration (optional - set via environment variables)
        self.proxy_server = os.getenv("PROXY_SERVER")  # e.g., "http://proxy.example.com:8080"
        self.proxy_username = os.getenv("PROXY_USERNAME")
        self.proxy_password = os.getenv("PROXY_PASSWORD")

    def _get_proxy_config(self) -> Optional[Dict]:
        """Get proxy configuration if available"""
        if not self.proxy_server:
            return None

        proxy_config = {"server": self.proxy_server}
        if self.proxy_username and self.proxy_password:
            proxy_config["username"] = self.proxy_username
            proxy_config["password"] = self.proxy_password

        return proxy_config

    async def initialize(self):
        """Initialize Playwright browser with anti-detection features"""
        if not self.browser:
            self.playwright = await async_playwright().start()

            # Browser launch arguments for stealth
            launch_args = [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--disable-infobars',
                '--disable-background-networking',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-breakpad',
                '--disable-component-extensions-with-background-pages',
                '--disable-component-update',
                '--disable-default-apps',
                '--disable-extensions',
                '--disable-features=TranslateUI',
                '--disable-hang-monitor',
                '--disable-ipc-flooding-protection',
                '--disable-popup-blocking',
                '--disable-prompt-on-repost',
                '--disable-renderer-backgrounding',
                '--disable-sync',
                '--enable-features=NetworkService,NetworkServiceInProcess',
                '--force-color-profile=srgb',
                '--metrics-recording-only',
                '--no-first-run',
                '--password-store=basic',
                '--use-mock-keychain',
                '--export-tagged-pdf',
                '--window-size=1920,1080',
            ]

            # Add proxy if configured
            proxy_config = self._get_proxy_config()
            launch_options = {
                'headless': True,
                'args': launch_args,
            }
            if proxy_config:
                launch_options['proxy'] = proxy_config
                logger.info(f"Using proxy server: {self.proxy_server}")

            self.browser = await self.playwright.chromium.launch(**launch_options)

    async def close(self):
        """Close Playwright browser and playwright instance"""
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None

    async def _apply_stealth_scripts(self, page: Page):
        """Apply stealth JavaScript to avoid detection"""
        # Override navigator.webdriver
        await page.add_init_script("""
            // Override webdriver property
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // Override chrome property
            window.chrome = {
                runtime: {}
            };

            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );

            // Override plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });

            // Override languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en', 'sg']
            });

            // Override platform
            Object.defineProperty(navigator, 'platform', {
                get: () => 'Win32'
            });

            // Override hardware concurrency
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8
            });

            // Override device memory
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8
            });
        """)

    async def _random_delay(self, min_ms: int = 500, max_ms: int = 2000):
        """Add random delay to appear more human-like"""
        delay = random.randint(min_ms, max_ms) / 1000
        await asyncio.sleep(delay)

    async def scrape_company_contacts(self, website: str) -> Dict[str, any]:
        """
        Scrape company website for contact information with stealth features

        Args:
            website: Company website URL

        Returns:
            Dictionary with contact information
        """
        try:
            await self.initialize()
            self._request_count += 1
            logger.info(f"Browser initialized, navigating to: {website} (request #{self._request_count})")

            # Rotate user agent and viewport for each request
            user_agent = random.choice(USER_AGENTS)
            viewport = random.choice(VIEWPORTS)

            # Create a new browser context with stealth settings
            context = await self.browser.new_context(
                user_agent=user_agent,
                viewport=viewport,
                locale='en-SG',
                timezone_id='Asia/Singapore',
                geolocation={'latitude': 1.3521, 'longitude': 103.8198},  # Singapore
                permissions=['geolocation'],
                extra_http_headers={
                    'Accept-Language': 'en-SG,en-US;q=0.9,en;q=0.8',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Cache-Control': 'max-age=0',
                    'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                    'Sec-Ch-Ua-Mobile': '?0',
                    'Sec-Ch-Ua-Platform': '"Windows"',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'Upgrade-Insecure-Requests': '1',
                }
            )

            page = await context.new_page()

            # Apply stealth scripts before navigation
            await self._apply_stealth_scripts(page)

            # Disable timeout completely to prevent frontend disruption
            # Pages will either load successfully or fail gracefully
            page.set_default_timeout(0)  # 0 = no timeout

            # Add random delay between requests to appear more human
            if self._request_count > 1:
                await self._random_delay(1000, 3000)

            # Navigate to website (no timeout - let it complete naturally)
            logger.info(f"Loading page: {website}")
            await page.goto(website, wait_until='networkidle', timeout=0)

            # Wait for Cloudflare challenge with random variation
            logger.info("Waiting for Cloudflare challenge to resolve...")
            await self._random_delay(4000, 6000)

            logger.info(f"Page loaded successfully: {website}")

            # Extract contact information from main page
            main_page_content = await page.content()
            logger.info(f"Retrieved HTML content, length: {len(main_page_content)} characters")

            # Log a snippet of the content for debugging
            text_content = await page.inner_text('body')
            logger.info(f"Page text snippet (first 500 chars): {text_content[:500]}")

            # Check if still blocked by Cloudflare
            cloudflare_indicators = [
                'verifying you are human',
                'checking your browser',
                'please wait while we verify',
                'ray id:',
                'cloudflare',
                'ddos protection',
            ]
            text_lower = text_content.lower()
            is_blocked = any(indicator in text_lower for indicator in cloudflare_indicators)

            if is_blocked and len(text_content) < 2000:  # Short page with CF indicators = blocked
                logger.warning(f"Cloudflare/bot protection still blocking access to {website}")
                await context.close()
                return {
                    'phone': None,
                    'email': None,
                    'website': website,
                    'all_phones': [],
                    'all_emails': [],
                    'blocked': True
                }

            contacts = self.extractor.extract_all_contacts(main_page_content)
            logger.info(f"Extraction results - Phones found: {contacts.get('all_phones', [])}, Emails found: {contacts.get('all_emails', [])}")

            # If contact info not found, try to find contact page
            if not (contacts['phone'] or contacts['email']):
                logger.info("No contact info found on main page, searching for contact page...")
                contact_page_url = await self._find_contact_page(page, website)

                if contact_page_url:
                    logger.info(f"Found contact page: {contact_page_url}")
                    await self._random_delay(1000, 2000)  # Random delay before navigation
                    await page.goto(contact_page_url, wait_until='domcontentloaded')
                    contact_page_content = await page.content()
                    contacts = self.extractor.extract_all_contacts(contact_page_content)
                    logger.info(f"Contact page extraction - Phones: {contacts.get('all_phones', [])}, Emails: {contacts.get('all_emails', [])}")
                else:
                    logger.info("No contact page found")

            await context.close()

            final_result = {
                'phone': contacts['phone'],
                'email': contacts['email'],
                'website': website,
                'all_phones': contacts.get('all_phones', []),
                'all_emails': contacts.get('all_emails', []),
                'blocked': False
            }
            logger.info(f"Final scraping result for {website}: {final_result}")
            return final_result

        except Exception as e:
            logger.error(f"Scraping error for {website}: {str(e)}", exc_info=True)
            return {
                'phone': None,
                'email': None,
                'website': website,
                'all_phones': [],
                'all_emails': [],
                'blocked': False
            }

    async def _find_contact_page(self, page: Page, base_url: str) -> Optional[str]:
        """
        Find contact page URL

        Args:
            page: Playwright page object
            base_url: Base website URL

        Returns:
            Contact page URL if found
        """
        try:
            # Common contact page patterns
            contact_selectors = [
                'a[href*="contact"]',
                'a[href*="Contact"]',
                'a[href*="CONTACT"]',
                'a[href*="get-in-touch"]',
                'a[href*="reach-us"]',
                'a:has-text("Contact")',
                'a:has-text("Contact Us")',
                'a:has-text("Get in Touch")',
            ]

            for selector in contact_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        href = await element.get_attribute('href')
                        if href:
                            # Handle relative URLs
                            if href.startswith('/'):
                                return base_url.rstrip('/') + href
                            elif href.startswith('http'):
                                return href
                            else:
                                return base_url.rstrip('/') + '/' + href
                except:
                    continue

        except Exception as e:
            logger.error(f"Error finding contact page: {str(e)}")

        return None

    async def scrape_multiple_companies(
        self,
        websites: List[str],
        batch_size: int = 5
    ) -> List[Dict[str, any]]:
        """
        Scrape multiple company websites with batching

        Args:
            websites: List of website URLs
            batch_size: Number of concurrent scraping tasks

        Returns:
            List of contact information dictionaries
        """
        results = []

        # Process in batches to avoid overwhelming resources
        for i in range(0, len(websites), batch_size):
            batch = websites[i:i + batch_size]
            batch_results = await asyncio.gather(
                *[self.scrape_company_contacts(url) for url in batch],
                return_exceptions=True
            )

            for result in batch_results:
                if isinstance(result, Exception):
                    results.append({
                        'phone': None,
                        'email': None,
                        'website': None,
                        'all_phones': [],
                        'all_emails': []
                    })
                else:
                    results.append(result)

        return results
