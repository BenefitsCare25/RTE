from playwright.async_api import async_playwright, Browser, Page
from typing import Optional, Dict, List
import asyncio
import logging
from app.utils.extractors import ContactExtractor

logger = logging.getLogger(__name__)

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
            logger.info(f"Browser initialized, navigating to: {website}")

            # Create a new page
            page = await self.browser.new_page()

            # Set timeout
            page.set_default_timeout(30000)

            # Navigate to website
            logger.info(f"Loading page: {website}")
            await page.goto(website, wait_until='domcontentloaded')
            logger.info(f"Page loaded successfully: {website}")

            # Extract contact information from main page
            main_page_content = await page.content()
            logger.info(f"Retrieved HTML content, length: {len(main_page_content)} characters")

            # Log a snippet of the content for debugging
            text_content = await page.inner_text('body')
            logger.info(f"Page text snippet (first 500 chars): {text_content[:500]}")

            contacts = self.extractor.extract_all_contacts(main_page_content)
            logger.info(f"Extraction results - Phones found: {contacts.get('all_phones', [])}, Emails found: {contacts.get('all_emails', [])}")

            # If contact info not found, try to find contact page
            if not (contacts['phone'] or contacts['email']):
                logger.info("No contact info found on main page, searching for contact page...")
                contact_page_url = await self._find_contact_page(page, website)

                if contact_page_url:
                    logger.info(f"Found contact page: {contact_page_url}")
                    await page.goto(contact_page_url, wait_until='domcontentloaded')
                    contact_page_content = await page.content()
                    contacts = self.extractor.extract_all_contacts(contact_page_content)
                    logger.info(f"Contact page extraction - Phones: {contacts.get('all_phones', [])}, Emails: {contacts.get('all_emails', [])}")
                else:
                    logger.info("No contact page found")

            # Try About page if still no founder information
            if not contacts['founder']:
                logger.info("No founder found, searching for about page...")
                about_page_url = await self._find_about_page(page, website)

                if about_page_url:
                    logger.info(f"Found about page: {about_page_url}")
                    await page.goto(about_page_url, wait_until='domcontentloaded')
                    about_page_content = await page.content()
                    about_contacts = self.extractor.extract_all_contacts(about_page_content)

                    if about_contacts['founder']:
                        logger.info(f"Found founder on about page: {about_contacts['founder']}")
                        contacts['founder'] = about_contacts['founder']
                else:
                    logger.info("No about page found")

            await page.close()

            final_result = {
                'phone': contacts['phone'],
                'email': contacts['email'],
                'founder': contacts['founder'],
                'website': website
            }
            logger.info(f"Final scraping result for {website}: {final_result}")
            return final_result

        except Exception as e:
            logger.error(f"Scraping error for {website}: {str(e)}", exc_info=True)
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
            logger.error(f"Error finding contact page: {str(e)}")

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
            logger.error(f"Error finding about page: {str(e)}")

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
