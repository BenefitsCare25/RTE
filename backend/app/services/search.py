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

        # Try SerpAPI first with multiple query strategies
        if self.serpapi_key:
            logger.info("Using SerpAPI with multi-strategy search...")
            search_result = await self._search_with_serpapi(company_name, uen, address)
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

    def _generate_search_queries(self, company_name: str, uen: str, address: str) -> List[Dict[str, str]]:
        """
        Generate multiple search query strategies to find actual company websites.

        The key insight: Directory sites rank for "UEN" searches, but company's own
        websites rank for "official website", "contact", and branded searches.

        Returns list of query strategies in priority order.
        """
        # Clean company name - remove common suffixes for cleaner search
        clean_name = company_name
        for suffix in [' PTE LTD', ' PTE. LTD.', ' PRIVATE LIMITED', ' LIMITED', ' LTD', ' LTD.',
                       ' PTE', ' SINGAPORE', ' (S)', ' (SINGAPORE)', ' CORP', ' CORPORATION',
                       ' HOLDINGS', ' ENTERPRISES', ' SERVICES', ' TRADING', ' INTERNATIONAL']:
            clean_name = clean_name.replace(suffix, '').replace(suffix.lower(), '').replace(suffix.title(), '')
        clean_name = clean_name.strip()

        # Extract postal code from address if available
        postal_match = re.search(r'Singapore\s*(\d{6})', address, re.IGNORECASE)
        postal_code = postal_match.group(1) if postal_match else None

        queries = [
            # Strategy 1: Official website search - most likely to return company's own site
            {
                "query": f'"{clean_name}" official website Singapore',
                "strategy": "official_website",
                "description": "Search for official website mention"
            },
            # Strategy 2: Contact us page - companies have contact pages, directories don't
            {
                "query": f'"{clean_name}" Singapore contact email',
                "strategy": "contact_page",
                "description": "Search for contact page with email"
            },
            # Strategy 3: Exclude common directories explicitly
            {
                "query": f'"{clean_name}" Singapore -yellowpages -directory -sgpbusiness -linkedin -facebook',
                "strategy": "exclude_directories",
                "description": "Company name excluding known directories"
            },
            # Strategy 4: Site-specific search for .com.sg or .sg domains (Singapore company domains)
            {
                "query": f'site:*.com.sg OR site:*.sg "{clean_name}"',
                "strategy": "sg_domain",
                "description": "Search Singapore domains only"
            },
            # Strategy 5: Original query as last resort (may return directories)
            {
                "query": f"{company_name} Singapore",
                "strategy": "basic",
                "description": "Basic company name search"
            },
        ]

        return queries

    async def _search_with_serpapi(
        self,
        company_name: str,
        uen: str,
        address: str = ""
    ) -> Dict[str, List[str]]:
        """
        Search using SerpAPI with multiple query strategies.

        Tries different search queries until it finds actual company websites,
        not just directory listings.

        Args:
            company_name: Name of the company
            uen: UEN number
            address: Company address (for postal code extraction)

        Returns:
            Dictionary with 'company_websites' and 'all_discovered' lists
        """
        all_discovered_urls = []

        # Generate multiple search strategies
        queries = self._generate_search_queries(company_name, uen, address)

        for query_info in queries:
            query = query_info["query"]
            strategy = query_info["strategy"]
            description = query_info["description"]

            logger.info(f"SerpAPI Strategy [{strategy}]: {description}")
            logger.info(f"  Query: {query}")

            try:
                params = {
                    "api_key": self.serpapi_key,
                    "q": query,
                    "location": "Singapore",
                    "hl": "en",
                    "gl": "sg",
                    "num": 10  # Get more results to increase chances
                }

                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(
                        "https://serpapi.com/search",
                        params=params
                    )

                    if response.status_code == 200:
                        data = response.json()
                        result = self._extract_websites_from_results(data, company_name)

                        # Collect all discovered URLs across all strategies
                        for url in result.get('all_discovered', []):
                            if url not in all_discovered_urls:
                                all_discovered_urls.append(url)

                        # If we found actual company websites, return immediately
                        if result.get('company_websites'):
                            logger.info(f"SUCCESS with strategy [{strategy}]: Found {len(result['company_websites'])} company website(s)")
                            result['all_discovered'] = all_discovered_urls
                            return result
                        else:
                            logger.info(f"Strategy [{strategy}] returned only directories, trying next strategy...")

                    # Small delay between API calls to be respectful
                    await asyncio.sleep(0.3)

            except Exception as e:
                logger.error(f"SerpAPI search error with strategy [{strategy}]: {str(e)}")
                continue

        # If no strategy found company websites, return all discovered URLs for reference
        logger.warning(f"All {len(queries)} search strategies failed to find company websites")
        return {'company_websites': [], 'all_discovered': all_discovered_urls}

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
