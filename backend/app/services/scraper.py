from playwright.async_api import async_playwright, Browser, Page, Playwright, BrowserContext
from typing import Optional, Dict, List
import asyncio
import logging
import random
import os
import httpx
from app.utils.extractors import ContactExtractor

logger = logging.getLogger(__name__)

# Try to import playwright_stealth, fall back to manual stealth if not available
try:
    from playwright_stealth import stealth_async
    STEALTH_AVAILABLE = True
    logger.info("playwright-stealth package available")
except ImportError:
    STEALTH_AVAILABLE = False
    logger.warning("playwright-stealth not installed, using manual stealth scripts")

# Rotating user agents - latest Chrome versions
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0',
]

# Viewport sizes to rotate
VIEWPORTS = [
    {'width': 1920, 'height': 1080},
    {'width': 1366, 'height': 768},
    {'width': 1536, 'height': 864},
    {'width': 1440, 'height': 900},
    {'width': 1680, 'height': 1050},
]

# Cloudflare detection indicators
CLOUDFLARE_INDICATORS = [
    'verifying you are human',
    'checking your browser',
    'please wait while we verify',
    'just a moment',
    'enable javascript and cookies',
    'ray id:',
    'cloudflare',
    'ddos protection',
    'security check',
    'access denied',
    'attention required',
]


class WebScraper:
    """
    Advanced web scraper with Cloudflare bypass techniques:
    1. playwright-stealth for anti-detection
    2. Human-like behavior simulation (mouse, scroll, delays)
    3. Session/cookie persistence for retry
    4. FlareSolverr integration as fallback
    5. Smart retry logic
    """

    def __init__(self):
        self.browser: Optional[Browser] = None
        self.playwright: Optional[Playwright] = None
        self.extractor = ContactExtractor()
        self._request_count = 0
        self._session_cookies: Dict[str, List] = {}  # Store cookies per domain

        # Proxy configuration
        self.proxy_server = os.getenv("PROXY_SERVER")
        self.proxy_username = os.getenv("PROXY_USERNAME")
        self.proxy_password = os.getenv("PROXY_PASSWORD")

        # FlareSolverr configuration (optional fallback)
        self.flaresolverr_url = os.getenv("FLARESOLVERR_URL")  # e.g., "http://localhost:8191/v1"

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

            # Extensive browser launch arguments for stealth
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
                '--disable-features=TranslateUI,BlinkGenPropertyTrees',
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
                '--window-size=1920,1080',
                '--start-maximized',
            ]

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

    async def _apply_manual_stealth(self, page: Page):
        """Apply manual stealth scripts when playwright-stealth is not available"""
        await page.add_init_script("""
            // Comprehensive stealth script

            // 1. Override webdriver property
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // 2. Override chrome property
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };

            // 3. Override permissions query
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );

            // 4. Override plugins to look realistic
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    const plugins = [
                        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                        { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
                    ];
                    plugins.item = (i) => plugins[i];
                    plugins.namedItem = (name) => plugins.find(p => p.name === name);
                    plugins.refresh = () => {};
                    return plugins;
                }
            });

            // 5. Override languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });

            // 6. Override platform
            Object.defineProperty(navigator, 'platform', {
                get: () => 'Win32'
            });

            // 7. Override hardware concurrency
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8
            });

            // 8. Override device memory
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8
            });

            // 9. Override WebGL vendor/renderer
            const getParameterProxyHandler = {
                apply: function(target, thisArg, argumentsList) {
                    const param = argumentsList[0];
                    const gl = thisArg;
                    if (param === 37445) return 'Intel Inc.';  // UNMASKED_VENDOR_WEBGL
                    if (param === 37446) return 'Intel Iris OpenGL Engine';  // UNMASKED_RENDERER_WEBGL
                    return Reflect.apply(target, thisArg, argumentsList);
                }
            };

            try {
                const canvas = document.createElement('canvas');
                const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                if (gl) {
                    gl.getParameter = new Proxy(gl.getParameter, getParameterProxyHandler);
                }
            } catch(e) {}

            // 10. Remove automation-related properties
            delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
            delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
            delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;

            // 11. Mock connection type
            Object.defineProperty(navigator, 'connection', {
                get: () => ({
                    effectiveType: '4g',
                    rtt: 50,
                    downlink: 10,
                    saveData: false
                })
            });
        """)

    async def _simulate_human_behavior(self, page: Page):
        """Simulate human-like behavior to bypass bot detection"""
        try:
            viewport = page.viewport_size or {'width': 1920, 'height': 1080}

            # 1. Random mouse movements (5-8 movements)
            for _ in range(random.randint(5, 8)):
                x = random.randint(100, viewport['width'] - 100)
                y = random.randint(100, viewport['height'] - 100)
                # Move with variable steps to simulate human movement
                await page.mouse.move(x, y, steps=random.randint(10, 30))
                await asyncio.sleep(random.uniform(0.1, 0.3))

            # 2. Scroll down in chunks
            for _ in range(random.randint(2, 4)):
                scroll_amount = random.randint(100, 400)
                await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
                await asyncio.sleep(random.uniform(0.3, 0.8))

            # 3. Small pause
            await asyncio.sleep(random.uniform(0.5, 1.0))

            # 4. Scroll back up a bit
            await page.evaluate(f"window.scrollBy(0, -{random.randint(50, 200)})")
            await asyncio.sleep(random.uniform(0.2, 0.5))

            # 5. Random click on safe area (not on links)
            safe_x = random.randint(50, 200)
            safe_y = random.randint(50, 200)
            await page.mouse.click(safe_x, safe_y)

        except Exception as e:
            logger.debug(f"Human behavior simulation error (non-critical): {e}")

    async def _wait_for_cloudflare(self, page: Page, max_wait: int = 15) -> bool:
        """
        Wait for Cloudflare challenge to resolve with human behavior
        Returns True if page is accessible, False if still blocked
        """
        start_time = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - start_time) < max_wait:
            try:
                text_content = await page.inner_text('body')
                text_lower = text_content.lower()

                # Check if still showing Cloudflare challenge
                is_blocked = any(indicator in text_lower for indicator in CLOUDFLARE_INDICATORS)

                if not is_blocked or len(text_content) > 3000:
                    # Page seems to have loaded real content
                    return True

                # Still blocked - simulate human behavior and wait
                await self._simulate_human_behavior(page)
                await asyncio.sleep(random.uniform(1.0, 2.0))

            except Exception as e:
                logger.debug(f"Error checking Cloudflare status: {e}")
                await asyncio.sleep(1.0)

        return False

    async def _try_flaresolverr(self, website: str) -> Optional[Dict]:
        """
        Try to get page content via FlareSolverr as fallback
        FlareSolverr is a proxy server that solves Cloudflare challenges
        """
        if not self.flaresolverr_url:
            return None

        try:
            logger.info(f"Attempting FlareSolverr fallback for: {website}")

            async with httpx.AsyncClient(timeout=None) as client:  # No timeout
                response = await client.post(
                    self.flaresolverr_url,
                    json={
                        "cmd": "request.get",
                        "url": website,
                        "maxTimeout": 300000  # 5 min for FlareSolverr challenge
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "ok":
                        solution = data.get("solution", {})
                        html_content = solution.get("response", "")

                        if html_content:
                            logger.info(f"FlareSolverr successfully retrieved content for: {website}")
                            contacts = self.extractor.extract_all_contacts(html_content)
                            return {
                                'phone': contacts['phone'],
                                'email': contacts['email'],
                                'website': website,
                                'all_phones': contacts.get('all_phones', []),
                                'all_emails': contacts.get('all_emails', []),
                                'blocked': False,
                                'source': 'flaresolverr'
                            }
                    else:
                        logger.warning(f"FlareSolverr failed: {data.get('message', 'Unknown error')}")

        except Exception as e:
            logger.error(f"FlareSolverr error: {e}")

        return None

    async def _get_domain(self, url: str) -> str:
        """Extract domain from URL"""
        from urllib.parse import urlparse
        return urlparse(url).netloc

    async def scrape_company_contacts(self, website: str, retry_count: int = 0) -> Dict[str, any]:
        """
        Scrape company website with advanced Cloudflare bypass techniques

        Features:
        1. playwright-stealth for anti-detection
        2. Human-like behavior simulation
        3. Cookie persistence for retry
        4. FlareSolverr fallback
        5. Smart retry logic
        """
        max_retries = 1  # One retry with different approach

        try:
            await self.initialize()
            self._request_count += 1
            logger.info(f"Scraping: {website} (request #{self._request_count}, attempt {retry_count + 1})")

            # Rotate user agent and viewport
            user_agent = random.choice(USER_AGENTS)
            viewport = random.choice(VIEWPORTS)
            domain = await self._get_domain(website)

            # Create browser context with stealth settings
            context = await self.browser.new_context(
                user_agent=user_agent,
                viewport=viewport,
                locale='en-SG',
                timezone_id='Asia/Singapore',
                geolocation={'latitude': 1.3521, 'longitude': 103.8198},
                permissions=['geolocation'],
                extra_http_headers={
                    'Accept-Language': 'en-SG,en-US;q=0.9,en;q=0.8',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache',
                    'Sec-Ch-Ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
                    'Sec-Ch-Ua-Mobile': '?0',
                    'Sec-Ch-Ua-Platform': '"Windows"',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'Upgrade-Insecure-Requests': '1',
                }
            )

            # Restore cookies from previous session if available
            if domain in self._session_cookies and self._session_cookies[domain]:
                await context.add_cookies(self._session_cookies[domain])
                logger.info(f"Restored {len(self._session_cookies[domain])} cookies for {domain}")

            page = await context.new_page()

            # Apply stealth - use playwright-stealth if available, otherwise manual
            if STEALTH_AVAILABLE:
                await stealth_async(page)
                logger.debug("Applied playwright-stealth")
            else:
                await self._apply_manual_stealth(page)
                logger.debug("Applied manual stealth scripts")

            # No timeout to prevent frontend disruption
            page.set_default_timeout(0)

            # Random delay between requests
            if self._request_count > 1:
                await asyncio.sleep(random.uniform(1.5, 3.5))

            # Navigate to website
            logger.info(f"Loading page: {website}")
            await page.goto(website, wait_until='domcontentloaded', timeout=0)

            # Simulate human behavior immediately
            await self._simulate_human_behavior(page)

            # Wait for Cloudflare with active human simulation
            page_accessible = await self._wait_for_cloudflare(page, max_wait=20)

            # Get page content
            text_content = await page.inner_text('body')

            # Check if blocked
            text_lower = text_content.lower()
            is_blocked = any(indicator in text_lower for indicator in CLOUDFLARE_INDICATORS)
            is_blocked = is_blocked and len(text_content) < 3000

            if is_blocked:
                logger.warning(f"Cloudflare blocking access to {website}")

                # Save any cookies we got (might help on retry)
                cookies = await context.cookies()
                if cookies:
                    self._session_cookies[domain] = cookies
                    logger.info(f"Saved {len(cookies)} cookies for potential retry")

                await context.close()

                # Retry with FlareSolverr if available
                if self.flaresolverr_url:
                    flaresolverr_result = await self._try_flaresolverr(website)
                    if flaresolverr_result:
                        return flaresolverr_result

                # One retry with saved cookies
                if retry_count < max_retries:
                    logger.info(f"Retrying {website} with saved cookies...")
                    await asyncio.sleep(random.uniform(3, 5))
                    return await self.scrape_company_contacts(website, retry_count + 1)

                return {
                    'phone': None,
                    'email': None,
                    'website': website,
                    'all_phones': [],
                    'all_emails': [],
                    'blocked': True
                }

            # Success! Save cookies for future use
            cookies = await context.cookies()
            if cookies:
                self._session_cookies[domain] = cookies

            # Extract contacts from main page
            main_page_content = await page.content()
            logger.info(f"Retrieved HTML content, length: {len(main_page_content)} characters")

            contacts = self.extractor.extract_all_contacts(main_page_content)
            logger.info(f"Main page extraction: Phones={contacts.get('all_phones', [])}, Emails={contacts.get('all_emails', [])}")

            # Try contact page if EITHER phone OR email is missing
            # This ensures we get complete contact info even if main page only has partial data
            if not contacts['phone'] or not contacts['email']:
                missing = []
                if not contacts['phone']:
                    missing.append('phone')
                if not contacts['email']:
                    missing.append('email')
                logger.info(f"Missing {', '.join(missing)} on main page, searching for contact page...")

                contact_page_url = await self._find_contact_page(page, website)

                if contact_page_url:
                    logger.info(f"Found contact page: {contact_page_url}")
                    await asyncio.sleep(random.uniform(1, 2))
                    await self._simulate_human_behavior(page)
                    try:
                        await page.goto(contact_page_url, wait_until='networkidle', timeout=30000)
                        await asyncio.sleep(1)  # Wait for page to settle
                        contact_page_content = await page.content()
                        contact_page_contacts = self.extractor.extract_all_contacts(contact_page_content)
                        logger.info(f"Contact page extraction: Phones={contact_page_contacts.get('all_phones', [])}, Emails={contact_page_contacts.get('all_emails', [])}")

                        # Merge contact page results with main page results
                        # Only fill in missing data, don't overwrite existing
                        if not contacts['phone'] and contact_page_contacts.get('phone'):
                            contacts['phone'] = contact_page_contacts['phone']
                            logger.info(f"Got phone from contact page: {contacts['phone']}")
                        if not contacts['email'] and contact_page_contacts.get('email'):
                            contacts['email'] = contact_page_contacts['email']
                            logger.info(f"Got email from contact page: {contacts['email']}")

                        # Merge all_phones and all_emails lists
                        existing_phones = set(contacts.get('all_phones', []))
                        for phone in contact_page_contacts.get('all_phones', []):
                            if phone and phone not in existing_phones:
                                contacts.setdefault('all_phones', []).append(phone)
                                existing_phones.add(phone)

                        existing_emails = set(contacts.get('all_emails', []))
                        for email in contact_page_contacts.get('all_emails', []):
                            if email and email not in existing_emails:
                                contacts.setdefault('all_emails', []).append(email)
                                existing_emails.add(email)

                    except Exception as e:
                        logger.warning(f"Failed to load contact page {contact_page_url}: {e}")

            await context.close()

            return {
                'phone': contacts['phone'],
                'email': contacts['email'],
                'website': website,
                'all_phones': contacts.get('all_phones', []),
                'all_emails': contacts.get('all_emails', []),
                'blocked': False
            }

        except Exception as e:
            logger.error(f"Scraping error for {website}: {str(e)}", exc_info=True)

            # Try FlareSolverr as last resort on error
            if self.flaresolverr_url and retry_count == 0:
                flaresolverr_result = await self._try_flaresolverr(website)
                if flaresolverr_result:
                    return flaresolverr_result

            return {
                'phone': None,
                'email': None,
                'website': website,
                'all_phones': [],
                'all_emails': [],
                'blocked': False
            }

    async def _find_contact_page(self, page: Page, base_url: str) -> Optional[str]:
        """Find contact page URL"""
        try:
            contact_selectors = [
                'a[href*="contact"]',
                'a[href*="Contact"]',
                'a[href*="CONTACT"]',
                'a[href*="get-in-touch"]',
                'a[href*="reach-us"]',
                'a[href*="enquir"]',
                'a:has-text("Contact")',
                'a:has-text("Contact Us")',
                'a:has-text("Get in Touch")',
                'a:has-text("Enquiry")',
            ]

            for selector in contact_selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        href = await element.get_attribute('href')
                        if href:
                            if href.startswith('/'):
                                return base_url.rstrip('/') + href
                            elif href.startswith('http'):
                                return href
                            elif not href.startswith('#') and not href.startswith('mailto:'):
                                return base_url.rstrip('/') + '/' + href
                except:
                    continue

        except Exception as e:
            logger.error(f"Error finding contact page: {str(e)}")

        return None

    async def scrape_email_only(self, website: str) -> Optional[str]:
        """
        Scrape a website specifically for email addresses.
        Used when we already have phone from Google Maps but need email.

        This is a lighter-weight scrape that focuses on:
        1. Main page email extraction
        2. Contact page email extraction

        Args:
            website: Company website URL

        Returns:
            Primary email address if found, None otherwise
        """
        try:
            await self.initialize()
            self._request_count += 1
            logger.info(f"Scraping for email only: {website}")

            # Rotate user agent and viewport
            user_agent = random.choice(USER_AGENTS)
            viewport = random.choice(VIEWPORTS)
            domain = await self._get_domain(website)

            # Create browser context
            context = await self.browser.new_context(
                user_agent=user_agent,
                viewport=viewport,
                locale='en-SG',
                timezone_id='Asia/Singapore',
                extra_http_headers={
                    'Accept-Language': 'en-SG,en-US;q=0.9,en;q=0.8',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                }
            )

            # Restore cookies if available
            if domain in self._session_cookies and self._session_cookies[domain]:
                await context.add_cookies(self._session_cookies[domain])

            page = await context.new_page()

            # Apply stealth
            if STEALTH_AVAILABLE:
                await stealth_async(page)
            else:
                await self._apply_manual_stealth(page)

            page.set_default_timeout(0)

            # Random delay
            if self._request_count > 1:
                await asyncio.sleep(random.uniform(1.0, 2.5))

            # Navigate to main page
            await page.goto(website, wait_until='domcontentloaded', timeout=0)
            await self._simulate_human_behavior(page)

            # Wait for Cloudflare
            page_accessible = await self._wait_for_cloudflare(page, max_wait=15)

            if not page_accessible:
                logger.warning(f"Email scrape blocked for {website}")
                await context.close()
                return None

            # Extract emails from main page
            main_content = await page.content()
            contacts = self.extractor.extract_all_contacts(main_content)

            if contacts.get('email'):
                logger.info(f"Found email on main page: {contacts['email']}")
                await context.close()
                return contacts['email']

            # Try contact page
            contact_page_url = await self._find_contact_page(page, website)
            if contact_page_url:
                logger.info(f"Checking contact page for email: {contact_page_url}")
                try:
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                    await page.goto(contact_page_url, wait_until='networkidle', timeout=30000)
                    contact_content = await page.content()
                    contacts = self.extractor.extract_all_contacts(contact_content)

                    if contacts.get('email'):
                        logger.info(f"Found email on contact page: {contacts['email']}")
                        await context.close()
                        return contacts['email']
                except Exception as e:
                    logger.warning(f"Failed to load contact page: {e}")

            # Try common contact page patterns
            common_patterns = ['/contact', '/contact-us', '/about', '/about-us']
            from urllib.parse import urlparse, urljoin

            for pattern in common_patterns:
                try:
                    test_url = urljoin(website, pattern)
                    if test_url != contact_page_url:  # Don't retry same page
                        await asyncio.sleep(random.uniform(0.5, 1.0))
                        response = await page.goto(test_url, wait_until='domcontentloaded', timeout=15000)
                        if response and response.ok:
                            pattern_content = await page.content()
                            contacts = self.extractor.extract_all_contacts(pattern_content)
                            if contacts.get('email'):
                                logger.info(f"Found email at {pattern}: {contacts['email']}")
                                await context.close()
                                return contacts['email']
                except:
                    continue

            await context.close()
            logger.info(f"No email found on {website}")
            return None

        except Exception as e:
            logger.error(f"Email scrape error for {website}: {str(e)}")
            return None

    async def scrape_multiple_companies(
        self,
        websites: List[str],
        batch_size: int = 1  # Process one at a time to avoid FlareSolverr memory issues
    ) -> List[Dict[str, any]]:
        """Scrape multiple company websites sequentially to conserve memory"""
        results = []

        for website in websites:
            try:
                result = await self.scrape_company_contacts(website)
                results.append(result)
            except Exception as e:
                logger.error(f"Error scraping {website}: {e}")
                results.append({
                    'phone': None,
                    'email': None,
                    'website': website,
                    'all_phones': [],
                    'all_emails': [],
                    'blocked': False
                })

        return results
