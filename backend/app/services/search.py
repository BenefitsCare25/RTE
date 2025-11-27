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

# Sites that typically work well without heavy protection
PREFERRED_DOMAINS = [
    'yellowpages.com.sg',
    'streetdirectory.com',
    'yelp.com.sg',
    'sgbusiness.directory',
    'singapore-ede.com',
    'dnb.com',
    'crunchbase.com',
    'zoominfo.com',
]

# Domains to completely exclude (no useful contact data)
EXCLUDED_DOMAINS = [
    'facebook.com', 'linkedin.com', 'instagram.com',
    'twitter.com', 'youtube.com', 'wikipedia.org',
    'bizfile.gov.sg',  # Official registry, no contact info
    'tiktok.com', 'pinterest.com',
    'sgpbusiness.com',  # Directory site, no direct contact info
    'opengovsg.com',  # Government data aggregator, no contact info
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
    ) -> List[str]:
        """
        Search for company websites using API search (SerpAPI or Bing)
        Returns multiple websites to maximize data extraction success

        Args:
            company_name: Name of the company
            uen: UEN number
            address: Company address

        Returns:
            List of company website URLs (up to 5), empty list if none found
        """
        logger.info(f"Starting website search for: {company_name} (UEN: {uen})")

        # Try SerpAPI first
        if self.serpapi_key:
            logger.info("Using SerpAPI to find company websites...")
            websites = await self._search_with_serpapi(company_name, uen)
            if websites:
                logger.info(f"✓ Found {len(websites)} websites via SerpAPI: {websites}")
                return websites
            else:
                logger.warning("SerpAPI search returned no results")

        # Fallback to Bing if SerpAPI fails or unavailable
        if self.bing_key:
            logger.info("Falling back to Bing Search API...")
            websites = await self._search_with_bing(company_name, uen)
            if websites:
                logger.info(f"✓ Found {len(websites)} websites via Bing: {websites}")
                return websites
            else:
                logger.warning("Bing search returned no results")

        logger.error(f"Failed to find websites for {company_name} - no search API keys configured or no results found")
        return []

    async def _search_with_serpapi(
        self,
        company_name: str,
        uen: str
    ) -> List[str]:
        """
        Search using SerpAPI (Google Custom Search)

        Args:
            company_name: Name of the company
            uen: UEN number

        Returns:
            List of website URLs (up to 5)
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

        return []

    async def _search_with_bing(
        self,
        company_name: str,
        uen: str
    ) -> List[str]:
        """
        Search using Bing Search API

        Args:
            company_name: Name of the company
            uen: UEN number

        Returns:
            List of website URLs (up to 5)
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

        return []

    def _classify_url(self, url: str) -> Tuple[str, int]:
        """
        Classify a URL and return its priority (lower = better)

        Priority levels:
        1 - Company's own website (highest priority)
        2 - Preferred domains (known to work well)
        3 - Other valid domains
        4 - Cloudflare-protected domains (lowest priority, try last)

        Returns:
            Tuple of (classification_label, priority_number)
        """
        domain = urlparse(url).netloc.lower()

        # Check if it's a Cloudflare-protected site
        if any(cf_domain in domain for cf_domain in CLOUDFLARE_PROTECTED_DOMAINS):
            return ("cloudflare_protected", 4)

        # Check if it's a preferred domain
        if any(pref_domain in domain for pref_domain in PREFERRED_DOMAINS):
            return ("preferred", 2)

        # Check if it's likely a company's own website (not a directory)
        directory_indicators = ['directory', 'listing', 'business', 'companies', 'corp', 'registry']
        if not any(ind in domain for ind in directory_indicators):
            return ("company_website", 1)

        return ("other", 3)

    def _extract_websites_from_results(
        self,
        data: Dict[str, Any],
        company_name: str
    ) -> List[str]:
        """
        Extract website URLs from SerpAPI results with smart prioritization

        Priority order:
        1. Company's own website with name match
        2. Preferred domains (yellowpages, etc.)
        3. Other valid domains
        4. Cloudflare-protected domains (last resort)

        Args:
            data: SerpAPI response data
            company_name: Company name for validation

        Returns:
            List of website URLs sorted by priority
        """
        organic_results = data.get("organic_results", [])

        logger.info(f"{'='*80}")
        logger.info(f"SerpAPI Search Results for: {company_name}")
        logger.info(f"Total results returned: {len(organic_results)}")
        logger.info(f"{'='*80}")

        # Categorize all results
        categorized = {
            'company_with_match': [],    # Priority 1: Own website + name match
            'company_no_match': [],      # Priority 2: Own website, no name match
            'preferred': [],             # Priority 3: Preferred domains
            'other': [],                 # Priority 4: Other valid domains
            'cloudflare': [],            # Priority 5: CF-protected (last resort)
        }

        for idx, result in enumerate(organic_results, 1):
            url = result.get("link", "")
            title = result.get("title", "")

            logger.info(f"Result #{idx}:")
            logger.info(f"  Title: {title}")
            logger.info(f"  URL:   {url}")

            # Check if excluded
            if any(domain in url for domain in EXCLUDED_DOMAINS):
                excluded_domain = next(domain for domain in EXCLUDED_DOMAINS if domain in url)
                logger.info(f"  Status: EXCLUDED (domain: {excluded_domain})")
                continue

            cleaned_url = self._clean_url(url)
            classification, priority = self._classify_url(url)

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

            # Categorize based on classification and name match
            if classification == "company_website":
                if has_name_match:
                    categorized['company_with_match'].append(cleaned_url)
                else:
                    categorized['company_no_match'].append(cleaned_url)
            elif classification == "preferred":
                categorized['preferred'].append(cleaned_url)
            elif classification == "cloudflare_protected":
                categorized['cloudflare'].append(cleaned_url)
            else:
                categorized['other'].append(cleaned_url)

        # Build final list in priority order
        logger.info(f"{'-'*80}")
        logger.info("Smart Prioritization Strategy:")
        logger.info("  1. Company websites with name match (best)")
        logger.info("  2. Company websites without name match")
        logger.info("  3. Preferred domains (yellowpages, etc.)")
        logger.info("  4. Other valid domains")
        logger.info("  5. Cloudflare-protected domains (last resort)")
        logger.info(f"{'-'*80}")

        selected_websites = []

        for category, label in [
            ('company_with_match', 'Company website (name match)'),
            ('company_no_match', 'Company website'),
            ('preferred', 'Preferred domain'),
            ('other', 'Other valid'),
            ('cloudflare', 'Cloudflare-protected (fallback)'),
        ]:
            for url in categorized[category]:
                if url not in selected_websites:
                    selected_websites.append(url)
                    logger.info(f"ADDED [{label}]: {url}")

        logger.info(f"{'-'*80}")
        logger.info(f"TOTAL SELECTED: {len(selected_websites)} websites (sorted by scraping success likelihood)")
        logger.info(f"{'='*80}")

        return selected_websites

    def _extract_websites_from_bing(
        self,
        data: Dict[str, Any],
        company_name: str
    ) -> List[str]:
        """
        Extract website URLs from Bing search results with smart prioritization

        Args:
            data: Bing API response data
            company_name: Company name for validation

        Returns:
            List of website URLs sorted by priority
        """
        web_pages = data.get("webPages", {}).get("value", [])

        logger.info(f"{'='*80}")
        logger.info(f"Bing Search Results for: {company_name}")
        logger.info(f"Total results returned: {len(web_pages)}")
        logger.info(f"{'='*80}")

        # Categorize all results (same logic as SerpAPI)
        categorized = {
            'company_with_match': [],
            'company_no_match': [],
            'preferred': [],
            'other': [],
            'cloudflare': [],
        }

        for idx, page in enumerate(web_pages, 1):
            url = page.get("url", "")
            title = page.get("name", "")

            logger.info(f"Result #{idx}:")
            logger.info(f"  Title: {title}")
            logger.info(f"  URL:   {url}")

            # Check if excluded
            if any(domain in url for domain in EXCLUDED_DOMAINS):
                excluded_domain = next(domain for domain in EXCLUDED_DOMAINS if domain in url)
                logger.info(f"  Status: EXCLUDED (domain: {excluded_domain})")
                continue

            cleaned_url = self._clean_url(url)
            classification, priority = self._classify_url(url)

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

            # Categorize
            if classification == "company_website":
                if has_name_match:
                    categorized['company_with_match'].append(cleaned_url)
                else:
                    categorized['company_no_match'].append(cleaned_url)
            elif classification == "preferred":
                categorized['preferred'].append(cleaned_url)
            elif classification == "cloudflare_protected":
                categorized['cloudflare'].append(cleaned_url)
            else:
                categorized['other'].append(cleaned_url)

        # Build final list in priority order
        selected_websites = []

        for category, label in [
            ('company_with_match', 'Company website (name match)'),
            ('company_no_match', 'Company website'),
            ('preferred', 'Preferred domain'),
            ('other', 'Other valid'),
            ('cloudflare', 'Cloudflare-protected (fallback)'),
        ]:
            for url in categorized[category]:
                if url not in selected_websites:
                    selected_websites.append(url)
                    logger.info(f"ADDED [{label}]: {url}")

        logger.info(f"TOTAL SELECTED: {len(selected_websites)} websites from Bing (sorted by priority)")
        return selected_websites

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
