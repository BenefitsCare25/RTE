import os
import httpx
import re
import logging
from typing import Optional, Dict, Any, List, Tuple
import asyncio
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Sites known to be behind Cloudflare protection - deprioritize these
CLOUDFLARE_PROTECTED_DOMAINS = [
    'sgpbusiness.com',
    'companies.sg',
    'recordowl.com',
    'sg.ltddir.com',
    'ltddir.com',
    'bizprofile.com',
]

# DIRECTORY SITES TO EXCLUDE - These are business directories, NOT company websites
# We want to find actual company domains, not directory listings
DIRECTORY_DOMAINS = [
    # Singapore business directories
    'yellowpages.com.sg',
    'streetdirectory.com',
    'yelp.com.sg',
    'sgbusiness.directory',
    'singapore-ede.com',
    'sgpbusiness.com',
    'companies.sg',
    'bizprofile.com',
    'opengovsg.com',
    'recordowl.com',
    'sg.ltddir.com',
    'ltddir.com',
    # International directories
    'dnb.com',
    'crunchbase.com',
    'zoominfo.com',
    'bloomberg.com',
    'yelp.com',
    'yellowpages.com',
    # Company registries (no contact info)
    'bizfile.gov.sg',
    'acra.gov.sg',
    # Job/review sites
    'glassdoor.com',
    'indeed.com',
    'jobstreet.com',
]

# Sites that typically work well without heavy protection
# NOTE: These are now EXCLUDED as they are directories
PREFERRED_DOMAINS = [
    # Empty - we no longer want to scrape directory sites
    # Only actual company websites should be scraped
]

# Domains to completely exclude (social media, no useful contact data)
EXCLUDED_DOMAINS = [
    # Social media
    'facebook.com', 'linkedin.com', 'instagram.com',
    'twitter.com', 'x.com', 'youtube.com', 'tiktok.com', 'pinterest.com',
    # Reference sites
    'wikipedia.org',
    # Include all directory domains in exclusion
    *DIRECTORY_DOMAINS,
]


class SearchService:
    """Service for searching company information using search engines"""

    def __init__(self):
        self.serpapi_key = os.getenv("SERPAPI_KEY")
        self.bing_key = os.getenv("BING_SEARCH_KEY")

    async def search_company_websites(
        self,
        company_name: str,
        uen: str,
        address: str
    ) -> Dict[str, List[str]]:
        """
        Search for company websites using API search (SerpAPI or Bing)
        Returns multiple websites to maximize data extraction success

        Args:
            company_name: Name of the company
            uen: UEN number
            address: Company address

        Returns:
            Dictionary with:
                - 'company_websites': List of actual company website URLs to scrape
                - 'all_discovered': List of ALL websites found (including directories)
        """
        logger.info(f"Starting website search for: {company_name} (UEN: {uen})")

        result = {
            'company_websites': [],
            'all_discovered': []
        }

        # Try SerpAPI first
        if self.serpapi_key:
            logger.info("Using SerpAPI to find company websites...")
            search_result = await self._search_with_serpapi(company_name, uen)
            if search_result:
                result = search_result
                logger.info(f"✓ Found {len(result['company_websites'])} company websites, {len(result['all_discovered'])} total discovered")
                if result['company_websites']:
                    return result

        # Fallback to Bing if SerpAPI fails or unavailable
        if self.bing_key:
            logger.info("Falling back to Bing Search API...")
            search_result = await self._search_with_bing(company_name, uen)
            if search_result:
                # Merge all_discovered from both searches
                result['all_discovered'].extend([url for url in search_result.get('all_discovered', []) if url not in result['all_discovered']])
                if search_result.get('company_websites'):
                    result['company_websites'] = search_result['company_websites']
                    logger.info(f"✓ Found {len(result['company_websites'])} company websites via Bing")
                    return result

        if not result['company_websites']:
            logger.warning(f"No company websites found for {company_name} (discovered {len(result['all_discovered'])} directory sites)")

        return result

    async def _search_with_serpapi(
        self,
        company_name: str,
        uen: str
    ) -> Dict[str, List[str]]:
        """
        Search using SerpAPI (Google Custom Search)

        Args:
            company_name: Name of the company
            uen: UEN number

        Returns:
            Dictionary with 'company_websites' and 'all_discovered' lists
        """
        try:
            query = f"{company_name} Singapore UEN {uen}"

            params = {
                "api_key": self.serpapi_key,
                "q": query,
                "location": "Singapore",
                "hl": "en",
                "gl": "sg",
                "num": 5
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    "https://serpapi.com/search",
                    params=params
                )

                if response.status_code == 200:
                    data = response.json()
                    return self._extract_websites_from_results(data, company_name)

        except Exception as e:
            logger.error(f"SerpAPI search error: {str(e)}")

        return {'company_websites': [], 'all_discovered': []}

    async def _search_with_bing(
        self,
        company_name: str,
        uen: str
    ) -> Dict[str, List[str]]:
        """
        Search using Bing Search API

        Args:
            company_name: Name of the company
            uen: UEN number

        Returns:
            Dictionary with 'company_websites' and 'all_discovered' lists
        """
        try:
            query = f"{company_name} Singapore UEN {uen}"

            headers = {
                "Ocp-Apim-Subscription-Key": self.bing_key
            }

            params = {
                "q": query,
                "count": 5,
                "mkt": "en-SG"
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    "https://api.bing.microsoft.com/v7.0/search",
                    headers=headers,
                    params=params
                )

                if response.status_code == 200:
                    data = response.json()
                    return self._extract_websites_from_bing(data, company_name)

        except Exception as e:
            logger.error(f"Bing search error: {str(e)}")

        return {'company_websites': [], 'all_discovered': []}

    def _classify_url(self, url: str) -> Tuple[str, int]:
        """
        Classify a URL and return its priority (lower = better)

        NEW PRIORITY LOGIC - Only accept actual company websites, exclude directories:
        1 - Company's own website (ONLY acceptable option)
        99 - Directory sites (EXCLUDED - do not scrape)
        99 - Cloudflare-protected directories (EXCLUDED)

        Returns:
            Tuple of (classification_label, priority_number)
        """
        domain = urlparse(url).netloc.lower()

        # FIRST: Check if it's a directory site (EXCLUDE these)
        if any(dir_domain in domain for dir_domain in DIRECTORY_DOMAINS):
            logger.info(f"EXCLUDING directory site: {domain}")
            return ("directory_excluded", 99)

        # Check if it's a Cloudflare-protected site (likely a directory)
        if any(cf_domain in domain for cf_domain in CLOUDFLARE_PROTECTED_DOMAINS):
            logger.info(f"EXCLUDING cloudflare-protected directory: {domain}")
            return ("cloudflare_excluded", 99)

        # Check for common directory URL patterns
        directory_indicators = ['directory', 'listing', 'yellowpages', 'whitepages',
                               'businesslist', 'companies', 'registry', 'profiles',
                               'bizlist', 'companylist']
        if any(ind in domain for ind in directory_indicators):
            logger.info(f"EXCLUDING URL with directory indicator: {domain}")
            return ("directory_pattern_excluded", 99)

        # If we get here, it's likely a company's own website - ACCEPT
        return ("company_website", 1)

    def _extract_websites_from_results(
        self,
        data: Dict[str, Any],
        company_name: str
    ) -> Dict[str, List[str]]:
        """
        Extract website URLs from SerpAPI results - ONLY company websites for scraping.
        Also returns ALL discovered URLs for reference.

        Args:
            data: SerpAPI response data
            company_name: Company name for validation

        Returns:
            Dictionary with:
                - 'company_websites': List of company websites to scrape
                - 'all_discovered': List of ALL URLs found (including directories)
        """
        organic_results = data.get("organic_results", [])

        logger.info(f"{'='*80}")
        logger.info(f"Web Search Results for: {company_name}")
        logger.info(f"Total results returned: {len(organic_results)}")
        logger.info(f"FILTER: Only accepting actual company websites, excluding all directories")
        logger.info(f"{'='*80}")

        # Track all discovered URLs and company websites separately
        all_discovered = []
        categorized = {
            'company_with_match': [],    # Priority 1: Own website + name match
            'company_no_match': [],      # Priority 2: Own website, no name match
        }
        excluded_count = 0

        for idx, result in enumerate(organic_results, 1):
            url = result.get("link", "")
            title = result.get("title", "")

            logger.info(f"Result #{idx}:")
            logger.info(f"  Title: {title}")
            logger.info(f"  URL:   {url}")

            cleaned_url = self._clean_url(url)

            # Add ALL URLs to all_discovered (for reference column)
            if cleaned_url and cleaned_url not in all_discovered:
                all_discovered.append(cleaned_url)

            # Check if excluded (social media, etc.)
            if any(domain in url for domain in EXCLUDED_DOMAINS):
                excluded_domain = next(domain for domain in EXCLUDED_DOMAINS if domain in url)
                logger.info(f"  Status: EXCLUDED (domain: {excluded_domain})")
                excluded_count += 1
                continue

            classification, priority = self._classify_url(url)

            # Skip any non-company-website results (directories get priority 99)
            if priority >= 99:
                logger.info(f"  Status: EXCLUDED ({classification})")
                excluded_count += 1
                continue

            # Check for company name match
            title_match = company_name.lower() in title.lower()
            url_match = company_name.lower() in url.lower()
            has_name_match = title_match or url_match

            match_info = ""
            if has_name_match:
                match_type = []
                if title_match:
                    match_type.append("title")
                if url_match:
                    match_type.append("URL")
                match_info = f", name match in {', '.join(match_type)}"

            logger.info(f"  Classification: {classification} (priority {priority}){match_info}")
            logger.info(f"  Status: ACCEPTED - Company website")

            # Only company websites make it here
            if has_name_match:
                categorized['company_with_match'].append(cleaned_url)
            else:
                categorized['company_no_match'].append(cleaned_url)

        # Build final list - ONLY company websites
        logger.info(f"{'-'*80}")
        logger.info("Smart Filtering Results:")
        logger.info(f"  - Company websites with name match: {len(categorized['company_with_match'])}")
        logger.info(f"  - Company websites without name match: {len(categorized['company_no_match'])}")
        logger.info(f"  - Excluded (directories/social): {excluded_count}")
        logger.info(f"  - Total discovered URLs: {len(all_discovered)}")
        logger.info(f"{'-'*80}")

        selected_websites = []

        for category, label in [
            ('company_with_match', 'Company website (name match)'),
            ('company_no_match', 'Company website'),
        ]:
            for url in categorized.get(category, []):
                if url not in selected_websites:
                    selected_websites.append(url)
                    logger.info(f"ADDED [{label}]: {url}")

        logger.info(f"{'-'*80}")
        if selected_websites:
            logger.info(f"TOTAL SELECTED: {len(selected_websites)} company website(s)")
        else:
            logger.info("NO company websites found - fallback will return empty")
        logger.info(f"{'='*80}")

        return {
            'company_websites': selected_websites,
            'all_discovered': all_discovered
        }

    def _extract_websites_from_bing(
        self,
        data: Dict[str, Any],
        company_name: str
    ) -> Dict[str, List[str]]:
        """
        Extract website URLs from Bing search results - ONLY company websites.
        Also returns ALL discovered URLs for reference.
        All directory sites are EXCLUDED.

        Args:
            data: Bing API response data
            company_name: Company name for validation

        Returns:
            Dictionary with 'company_websites' and 'all_discovered' lists
        """
        web_pages = data.get("webPages", {}).get("value", [])

        logger.info(f"{'='*80}")
        logger.info(f"Bing Search Results for: {company_name}")
        logger.info(f"Total results returned: {len(web_pages)}")
        logger.info(f"FILTER: Only accepting actual company websites, excluding all directories")
        logger.info(f"{'='*80}")

        # Track all discovered URLs and company websites separately
        all_discovered = []
        categorized = {
            'company_with_match': [],
            'company_no_match': [],
        }
        excluded_count = 0

        for idx, page in enumerate(web_pages, 1):
            url = page.get("url", "")
            title = page.get("name", "")

            logger.info(f"Result #{idx}:")
            logger.info(f"  Title: {title}")
            logger.info(f"  URL:   {url}")

            cleaned_url = self._clean_url(url)

            # Add ALL URLs to all_discovered (for reference column)
            if cleaned_url and cleaned_url not in all_discovered:
                all_discovered.append(cleaned_url)

            # Check if excluded (social media, etc.)
            if any(domain in url for domain in EXCLUDED_DOMAINS):
                excluded_domain = next(domain for domain in EXCLUDED_DOMAINS if domain in url)
                logger.info(f"  Status: EXCLUDED (domain: {excluded_domain})")
                excluded_count += 1
                continue

            classification, priority = self._classify_url(url)

            # Skip any non-company-website results (directories get priority 99)
            if priority >= 99:
                logger.info(f"  Status: EXCLUDED ({classification})")
                excluded_count += 1
                continue

            # Check for company name match
            title_match = company_name.lower() in title.lower()
            url_match = company_name.lower() in url.lower()
            has_name_match = title_match or url_match

            match_info = ""
            if has_name_match:
                match_type = []
                if title_match:
                    match_type.append("title")
                if url_match:
                    match_type.append("URL")
                match_info = f", name match in {', '.join(match_type)}"

            logger.info(f"  Classification: {classification} (priority {priority}){match_info}")
            logger.info(f"  Status: ACCEPTED - Company website")

            # Only company websites make it here
            if has_name_match:
                categorized['company_with_match'].append(cleaned_url)
            else:
                categorized['company_no_match'].append(cleaned_url)

        # Build final list - ONLY company websites
        logger.info(f"{'-'*80}")
        logger.info("Smart Filtering Results:")
        logger.info(f"  - Company websites with name match: {len(categorized['company_with_match'])}")
        logger.info(f"  - Company websites without name match: {len(categorized['company_no_match'])}")
        logger.info(f"  - Excluded (directories/social): {excluded_count}")
        logger.info(f"  - Total discovered URLs: {len(all_discovered)}")
        logger.info(f"{'-'*80}")

        selected_websites = []

        for category, label in [
            ('company_with_match', 'Company website (name match)'),
            ('company_no_match', 'Company website'),
        ]:
            for url in categorized.get(category, []):
                if url not in selected_websites:
                    selected_websites.append(url)
                    logger.info(f"ADDED [{label}]: {url}")

        if selected_websites:
            logger.info(f"TOTAL SELECTED: {len(selected_websites)} company website(s) from Bing")
        else:
            logger.info("NO company websites found from Bing - fallback will return empty")

        return {
            'company_websites': selected_websites,
            'all_discovered': all_discovered
        }

    @staticmethod
    def _clean_url(url: str) -> str:
        """
        Clean and normalize URL

        Args:
            url: Raw URL

        Returns:
            Cleaned URL
        """
        # Remove tracking parameters
        if '?' in url:
            base_url = url.split('?')[0]
        else:
            base_url = url

        # Ensure it starts with http/https
        if not base_url.startswith(('http://', 'https://')):
            base_url = 'https://' + base_url

        return base_url
