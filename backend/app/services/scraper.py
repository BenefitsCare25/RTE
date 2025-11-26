from playwright.async_api import async_playwright, Browser, Page
from typing import Optional, Dict, List
import asyncio
from app.utils.extractors import ContactExtractor

class WebScraper:
    """Service for scraping company websites to extract contact information"""

    def __init__(self):
        self.browser: Optional[Browser] = None
        self.extractor = ContactExtractor()

    async def initialize(self):
        """Initialize Playwright browser"""
        if not self.browser:
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )

    async def close(self):
        """Close Playwright browser"""
        if self.browser:
            await self.browser.close()
            self.browser = None

    async def scrape_company_contacts(self, website: str) -> Dict[str, any]:
        """
        Scrape company website for contact information

        Args:
            website: Company website URL

        Returns:
            Dictionary with contact information
        """
        try:
            await self.initialize()

            # Create a new page
            page = await self.browser.new_page()

            # Set timeout
            page.set_default_timeout(30000)

            # Navigate to website
            await page.goto(website, wait_until='domcontentloaded')

            # Extract contact information from main page
            main_page_content = await page.content()
            contacts = self.extractor.extract_all_contacts(main_page_content)

            # If contact info not found, try to find contact page
            if not (contacts['phone'] or contacts['email']):
                contact_page_url = await self._find_contact_page(page, website)

                if contact_page_url:
                    await page.goto(contact_page_url, wait_until='domcontentloaded')
                    contact_page_content = await page.content()
                    contacts = self.extractor.extract_all_contacts(contact_page_content)

            # Try About page if still no founder information
            if not contacts['founder']:
                about_page_url = await self._find_about_page(page, website)

                if about_page_url:
                    await page.goto(about_page_url, wait_until='domcontentloaded')
                    about_page_content = await page.content()
                    about_contacts = self.extractor.extract_all_contacts(about_page_content)

                    if about_contacts['founder']:
                        contacts['founder'] = about_contacts['founder']

            await page.close()

            return {
                'phone': contacts['phone'],
                'email': contacts['email'],
                'founder': contacts['founder'],
                'website': website
            }

        except Exception as e:
            print(f"Scraping error for {website}: {str(e)}")
            return {
                'phone': None,
                'email': None,
                'founder': None,
                'website': website
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
            print(f"Error finding contact page: {str(e)}")

        return None

    async def _find_about_page(self, page: Page, base_url: str) -> Optional[str]:
        """
        Find about page URL

        Args:
            page: Playwright page object
            base_url: Base website URL

        Returns:
            About page URL if found
        """
        try:
            # Common about page patterns
            about_selectors = [
                'a[href*="about"]',
                'a[href*="About"]',
                'a[href*="ABOUT"]',
                'a[href*="team"]',
                'a[href*="our-story"]',
                'a:has-text("About")',
                'a:has-text("About Us")',
                'a:has-text("Our Team")',
                'a:has-text("Our Story")',
            ]

            for selector in about_selectors:
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
            print(f"Error finding about page: {str(e)}")

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
                        'founder': None,
                        'website': None
                    })
                else:
                    results.append(result)

        return results
