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
    'keepital.com',        # Business contact directory
    'soopage.com',         # Singapore business directory
    'singaporebusinessguide.com',  # Business directory with category listings
    # Singapore company directories (added)
    'sgpgrid.com',
    'scam.sg',
    'companieshouse.sg',
    'sgx.com',  # Stock exchange - no contact info
    'sg.globaldatabase.com',  # Global database directory
    'singapore-corp.com',  # Singapore company directory
    # Property and real estate directories (NOT company websites)
    'propertyforsale.com.sg',  # Property listing site
    'propertyguru.com.sg',     # Property listing site
    'iproperty.com.sg',        # Property listing site
    '99.co',                   # Property listing site
    'srx.com.sg',              # Property listing site
    # Singapore info/directory aggregators
    'tellme.sg',               # Singapore business lookup
    'sg.bdir.in',              # Business directory India
    'guidesify.com',           # App guide directory
    'app.guidesify.com',       # App guide directory
    'indialei.in',             # India LEI directory (company identifier)
    'lei.info',                # LEI directory
    'lei-lookup.com',          # LEI directory
    # Legal/litigation sites (NOT company websites)
    'elitigation.sg',          # Court cases - not company info
    'lawnet.sg',               # Legal database
    'statecourts.gov.sg',      # Court records
    # International directories
    'dnb.com',
    'crunchbase.com',
    'zoominfo.com',
    'bloomberg.com',
    'yelp.com',
    'yellowpages.com',
    'rocketreach.co',      # Contact lookup directory
    'bdir.in',             # Business directory (any subdomain)
    # Trade/business directories
    'volza.com',
    'inriskable.com',
    'importgenius.com',
    'panjiva.com',
    # Generic contact services
    'contact.page',
    'contactout.com',
    # Company registries (no contact info)
    'bizfile.gov.sg',
    'acra.gov.sg',
    # Job/review sites
    'glassdoor.com',
    'indeed.com',
    'jobstreet.com',
    # Document/content sites (NOT company websites)
    'scribd.com',
    'academia.edu',
    'researchgate.net',
    'dokumen.pub',
    'issuu.com',
    # Marketplaces (NOT company websites)
    'ebay.com',
    'amazon.com',
    'lazada.sg',
    'shopee.sg',
    'carousell.com',
    'qoo10.sg',
    # Press release / news aggregators (NOT company websites)
    'mynewsdesk.com',
    'prnewswire.com',
    'businesswire.com',
    # News/media sites (NOT company websites - they report ON companies)
    'businesstimes.com.sg',    # Singapore business news
    'straitstimes.com',        # Singapore news
    'channelnewsasia.com',     # Singapore news
    'todayonline.com',         # Singapore news
    'asiaone.com',             # Singapore news
    'techinasia.com',          # Tech news
    'e27.co',                  # Tech news/startup directory
    'reuters.com',             # International news
    'ft.com',                  # Financial Times
    'wsj.com',                 # Wall Street Journal
    # Archive/library/government (no company contacts)
    'archive.org',
    'nlb.gov.sg',
    'eresources.nlb.gov.sg',
    'fraser.stlouisfed.org',
    'evols.library.manoa.hawaii.edu',
    'nas.gov.sg',          # National Archives - no company contacts
    'gov.sg',              # Government sites generally
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

# URL patterns to exclude (files, downloads, archives - not scrapable HTML)
EXCLUDED_URL_PATTERNS = [
    r'\.pdf$',
    r'\.doc[x]?$',
    r'\.xls[x]?$',
    r'\.ppt[x]?$',
    r'/bitstream/',
    r'/download/',
    r'/newspapers/',
    r'/digitised/',
    r'/document/',
]


class SearchService:
    """Service for searching company information using search engines"""

    def __init__(self):
        self.serpapi_key = os.getenv("SERPAPI_KEY")
        self.bing_key = os.getenv("BING_SEARCH_KEY")

    def _extract_company_keywords(self, company_name: str) -> List[str]:
        """
        Extract searchable keywords from company name.

        Removes company suffixes (PTE LTD, SDN BHD, etc.) and returns
        significant words (3+ chars) that can be used to match against
        domain names and page titles.

        IMPORTANT: We preserve words like ASIA, ENTERPRISES if they're the PRIMARY
        identifying words. Only filter them if other keywords exist.

        Examples:
            "ASTRABON (S) PTE LTD" → ["astrabon"]
            "A.T.E. MASKATI PRIVATE LIMITED" → ["ate", "maskati"]
            "AMOY CANNING CORPORATION" → ["amoy", "canning"]
            "ASIA ENTERPRISES (PRIVATE) LIMITED" → ["asia", "enterprises"]
        """
        # Normalize: uppercase, remove dots early (for A.T.E. → ATE)
        clean = company_name.upper()
        clean = re.sub(r'\.', ' ', clean)  # Replace dots with spaces
        clean = re.sub(r'\s+', ' ', clean).strip()

        # Remove company suffixes - apply multiple times to handle nested patterns
        suffix_patterns = [
            r'\s*\(\s*S\s*\)\s*',           # (S) with optional spaces
            r'\s*\(\s*SINGAPORE\s*\)\s*',   # (SINGAPORE)
            r'\s+PRIVATE\s+LIMITED$',
            r'\s+PTE\s+LTD$',
            r'\s+SDN\s+BHD$',
            r'\s+LIMITED$',
            r'\s+LTD$',
            r'\s+PTE$',
            r'\s+BHD$',
            r'\s+CORPORATION$',
            r'\s+CORP$',
            r'\s+INC$',
            r'\s+LLC$',
            r'\s+LLP$',
            r'\s+CO$',
        ]

        # Apply suffix removal multiple times until no more changes
        # Replace with space (not empty string) to avoid joining adjacent words
        # e.g., "ASTRABON (S) PTE LTD" should become "ASTRABON PTE LTD", not "ASTRABONPTE LTD"
        for _ in range(3):  # Max 3 iterations
            prev = clean
            for pattern in suffix_patterns:
                clean = re.sub(pattern, ' ', clean, flags=re.IGNORECASE)
            clean = re.sub(r'\s+', ' ', clean).strip()
            if clean == prev:
                break

        # Split into words, keep only significant ones (3+ chars)
        words = re.findall(r'\b[A-Z]{3,}\b', clean)

        # STRICT common words - only truly generic terms that NEVER identify a company
        # Note: Words like ASIA, ENTERPRISES, HOLDINGS, SERVICES, TRADING are kept
        # because they may be the ONLY identifying part of a company name
        strict_common = {'THE', 'AND', 'FOR', 'PTE', 'LTD', 'SDN', 'BHD', 'INC', 'LLC',
                        'COMPANY', 'PRIVATE', 'LIMITED'}

        # Secondary common words - only remove if other keywords exist
        secondary_common = {'ASIA', 'PACIFIC', 'SINGAPORE', 'GLOBAL', 'GROUP',
                          'CORPORATION', 'CORP', 'HOLDINGS', 'ENTERPRISES',
                          'SERVICES', 'TRADING', 'INTERNATIONAL'}

        # First pass: Remove strict common words
        keywords = [w.lower() for w in words if w not in strict_common]

        # Second pass: Only remove secondary common words if we have other unique keywords
        unique_keywords = [k for k in keywords if k.upper() not in secondary_common]

        if unique_keywords:
            # We have unique keywords, safe to remove secondary common words
            keywords = unique_keywords
            logger.debug(f"  Keyword extraction: removed secondary common words, kept {keywords}")
        else:
            # No unique keywords - keep secondary common words as they're the primary identifier
            # e.g., "ASIA ENTERPRISES" → ["asia", "enterprises"]
            logger.info(f"  Keyword extraction: keeping secondary common words as primary identifiers: {keywords}")

        return keywords

    def _is_relevant_to_company(self, url: str, title: str, company_name: str) -> bool:
        """
        Check if URL/title contains company name keywords.

        Returns True if ANY keyword from the company name appears in
        the domain or page title. This prevents accepting random
        unrelated sites like scribd.com or academia.edu.

        Args:
            url: The website URL
            title: The page title from search results
            company_name: The company being searched for

        Returns:
            True if relevant, False if no company keywords found
        """
        keywords = self._extract_company_keywords(company_name)

        # If no keywords extracted (very short name), allow all
        if not keywords:
            logger.info(f"  No keywords extracted from '{company_name}', allowing URL")
            return True

        domain = urlparse(url).netloc.lower()
        # Remove www. and common TLDs for better matching
        domain_clean = domain.replace('www.', '').split('.')[0]
        title_lower = title.lower()

        # Check if ANY keyword appears in domain or title
        for keyword in keywords:
            if keyword in domain_clean or keyword in title_lower:
                logger.debug(f"  Keyword '{keyword}' found in domain/title")
                return True

        logger.info(f"  No keywords {keywords} found in domain '{domain_clean}' or title")
        return False

    def _is_excluded_url_pattern(self, url: str) -> bool:
        """Check if URL matches excluded patterns (PDFs, downloads, etc.)"""
        url_lower = url.lower()
        for pattern in EXCLUDED_URL_PATTERNS:
            if re.search(pattern, url_lower):
                return True
        return False

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
        # IMPORTANT: Order matters! Remove longer patterns FIRST to avoid partial matches
        # e.g., "CORPORATION" must be removed before "CORP" otherwise you get "ORATION" left over
        clean_name = company_name
        for suffix in [' PTE. LTD.', ' PTE LTD', ' PRIVATE LIMITED', ' LIMITED', ' LTD.', ' LTD',
                       ' CORPORATION', ' CORP',  # CORPORATION before CORP - critical!
                       ' (SINGAPORE)', ' (S)', ' SINGAPORE',  # (SINGAPORE) before (S)
                       ' PTE', ' HOLDINGS', ' ENTERPRISES', ' SERVICES', ' TRADING', ' INTERNATIONAL']:
            clean_name = clean_name.replace(suffix, '').replace(suffix.lower(), '').replace(suffix.title(), '')
        clean_name = re.sub(r'\s+', ' ', clean_name).strip()  # Clean up extra spaces

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

        Uses TWO-PASS approach:
        1. First pass: Find company websites with keyword match (establish trusted domains)
        2. Second pass: Accept contact/about pages from trusted domains

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
        logger.info(f"FILTER: Two-pass - keyword match then same-domain contact pages")
        logger.info(f"{'='*80}")

        # Extract keywords once for this company
        keywords = self._extract_company_keywords(company_name)
        logger.info(f"Company keywords for matching: {keywords}")

        # Track all discovered URLs and company websites separately
        all_discovered = []
        trusted_domains = set()  # Domains confirmed to be the company's website
        categorized = {
            'company_with_match': [],    # Priority 1: Own website + name match
            'company_no_match': [],      # Priority 2: Own website, no name match
            'contact_pages': [],         # Priority 3: Contact/about pages from trusted domain
        }
        # Store pending URLs that might be contact pages for second pass
        pending_same_domain = []
        excluded_count = 0

        # Contact page indicators
        contact_indicators = ['contact', 'about', 'reach-us', 'get-in-touch', 'enquir']

        # FIRST PASS: Find company websites with keyword match
        for idx, result in enumerate(organic_results, 1):
            url = result.get("link", "")
            title = result.get("title", "")

            logger.info(f"Result #{idx}:")
            logger.info(f"  Title: {title}")
            logger.info(f"  URL:   {url}")

            cleaned_url = self._clean_url(url)
            domain = urlparse(url).netloc.lower()

            # Add ALL URLs to all_discovered (for reference column)
            if cleaned_url and cleaned_url not in all_discovered:
                all_discovered.append(cleaned_url)

            # Check if excluded (social media, etc.)
            if any(excl_domain in url for excl_domain in EXCLUDED_DOMAINS):
                excluded_domain = next(excl_domain for excl_domain in EXCLUDED_DOMAINS if excl_domain in url)
                logger.info(f"  Status: EXCLUDED (domain: {excluded_domain})")
                excluded_count += 1
                continue

            classification, priority = self._classify_url(url)

            # Skip any non-company-website results (directories get priority 99)
            if priority >= 99:
                logger.info(f"  Status: EXCLUDED ({classification})")
                excluded_count += 1
                continue

            # Check for URL pattern exclusions (PDFs, downloads, etc.)
            if self._is_excluded_url_pattern(url):
                logger.info(f"  Status: EXCLUDED (file/archive URL pattern)")
                excluded_count += 1
                continue

            # Check company name relevance
            is_relevant = self._is_relevant_to_company(url, title, company_name)

            if is_relevant:
                # This is a confirmed company website - add domain to trusted list
                trusted_domains.add(domain)

                # Check for company name match (full name match)
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
                logger.info(f"  Status: ACCEPTED - Company website (keyword match)")
                logger.info(f"  Trusted domain added: {domain}")

                if has_name_match:
                    categorized['company_with_match'].append(cleaned_url)
                else:
                    categorized['company_no_match'].append(cleaned_url)
            else:
                # Not relevant by keyword, but might be a contact page from same domain
                # Check if it's a contact-type page
                url_lower = url.lower()
                title_lower = title.lower()
                is_contact_page = any(ind in url_lower or ind in title_lower for ind in contact_indicators)

                if is_contact_page:
                    # Save for second pass - we'll check if domain becomes trusted
                    pending_same_domain.append({
                        'url': cleaned_url,
                        'domain': domain,
                        'title': title
                    })
                    logger.info(f"  Status: PENDING - Contact page, waiting for domain trust")
                else:
                    logger.info(f"  Status: EXCLUDED (no company keyword in domain/title)")
                    excluded_count += 1

        # SECOND PASS: Accept contact pages from trusted domains
        logger.info(f"{'-'*80}")
        logger.info(f"Second pass: Checking {len(pending_same_domain)} pending contact pages")
        logger.info(f"Trusted domains: {trusted_domains}")

        for pending in pending_same_domain:
            if pending['domain'] in trusted_domains:
                logger.info(f"  ACCEPTED contact page from trusted domain: {pending['url']}")
                categorized['contact_pages'].append(pending['url'])
            else:
                logger.info(f"  REJECTED contact page (domain not trusted): {pending['url']}")
                excluded_count += 1

        # Build final list - prioritize: main page, then contact pages
        logger.info(f"{'-'*80}")
        logger.info("Smart Filtering Results:")
        logger.info(f"  - Company websites with name match: {len(categorized['company_with_match'])}")
        logger.info(f"  - Company websites without name match: {len(categorized['company_no_match'])}")
        logger.info(f"  - Contact pages from trusted domains: {len(categorized['contact_pages'])}")
        logger.info(f"  - Excluded (directories/social/irrelevant): {excluded_count}")
        logger.info(f"  - Total discovered URLs: {len(all_discovered)}")
        logger.info(f"{'-'*80}")

        selected_websites = []

        # PRIORITY ORDER: Contact pages FIRST (most likely to have contact info)
        # Then main company page, then other pages

        # 1. Add contact pages first (highest priority for contact extraction)
        for url in categorized.get('contact_pages', []):
            if url not in selected_websites:
                selected_websites.append(url)
                logger.info(f"ADDED [Contact page - PRIORITY]: {url}")

        # 2. Add main company websites
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

        Uses TWO-PASS approach (same as SerpAPI):
        1. First pass: Find company websites with keyword match (establish trusted domains)
        2. Second pass: Accept contact/about pages from trusted domains

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
        logger.info(f"FILTER: Two-pass - keyword match then same-domain contact pages")
        logger.info(f"{'='*80}")

        # Extract keywords once for this company
        keywords = self._extract_company_keywords(company_name)
        logger.info(f"Company keywords for matching: {keywords}")

        # Track all discovered URLs and company websites separately
        all_discovered = []
        trusted_domains = set()
        categorized = {
            'company_with_match': [],
            'company_no_match': [],
            'contact_pages': [],
        }
        pending_same_domain = []
        excluded_count = 0

        # Contact page indicators
        contact_indicators = ['contact', 'about', 'reach-us', 'get-in-touch', 'enquir']

        # FIRST PASS: Find company websites with keyword match
        for idx, page in enumerate(web_pages, 1):
            url = page.get("url", "")
            title = page.get("name", "")

            logger.info(f"Result #{idx}:")
            logger.info(f"  Title: {title}")
            logger.info(f"  URL:   {url}")

            cleaned_url = self._clean_url(url)
            domain = urlparse(url).netloc.lower()

            # Add ALL URLs to all_discovered (for reference column)
            if cleaned_url and cleaned_url not in all_discovered:
                all_discovered.append(cleaned_url)

            # Check if excluded (social media, etc.)
            if any(excl_domain in url for excl_domain in EXCLUDED_DOMAINS):
                excluded_domain = next(excl_domain for excl_domain in EXCLUDED_DOMAINS if excl_domain in url)
                logger.info(f"  Status: EXCLUDED (domain: {excluded_domain})")
                excluded_count += 1
                continue

            classification, priority = self._classify_url(url)

            # Skip any non-company-website results (directories get priority 99)
            if priority >= 99:
                logger.info(f"  Status: EXCLUDED ({classification})")
                excluded_count += 1
                continue

            # Check for URL pattern exclusions (PDFs, downloads, etc.)
            if self._is_excluded_url_pattern(url):
                logger.info(f"  Status: EXCLUDED (file/archive URL pattern)")
                excluded_count += 1
                continue

            # Check company name relevance
            is_relevant = self._is_relevant_to_company(url, title, company_name)

            if is_relevant:
                trusted_domains.add(domain)

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
                logger.info(f"  Status: ACCEPTED - Company website (keyword match)")
                logger.info(f"  Trusted domain added: {domain}")

                if has_name_match:
                    categorized['company_with_match'].append(cleaned_url)
                else:
                    categorized['company_no_match'].append(cleaned_url)
            else:
                url_lower = url.lower()
                title_lower = title.lower()
                is_contact_page = any(ind in url_lower or ind in title_lower for ind in contact_indicators)

                if is_contact_page:
                    pending_same_domain.append({
                        'url': cleaned_url,
                        'domain': domain,
                        'title': title
                    })
                    logger.info(f"  Status: PENDING - Contact page, waiting for domain trust")
                else:
                    logger.info(f"  Status: EXCLUDED (no company keyword in domain/title)")
                    excluded_count += 1

        # SECOND PASS: Accept contact pages from trusted domains
        logger.info(f"{'-'*80}")
        logger.info(f"Second pass: Checking {len(pending_same_domain)} pending contact pages")
        logger.info(f"Trusted domains: {trusted_domains}")

        for pending in pending_same_domain:
            if pending['domain'] in trusted_domains:
                logger.info(f"  ACCEPTED contact page from trusted domain: {pending['url']}")
                categorized['contact_pages'].append(pending['url'])
            else:
                logger.info(f"  REJECTED contact page (domain not trusted): {pending['url']}")
                excluded_count += 1

        # Build final list
        logger.info(f"{'-'*80}")
        logger.info("Smart Filtering Results:")
        logger.info(f"  - Company websites with name match: {len(categorized['company_with_match'])}")
        logger.info(f"  - Company websites without name match: {len(categorized['company_no_match'])}")
        logger.info(f"  - Contact pages from trusted domains: {len(categorized['contact_pages'])}")
        logger.info(f"  - Excluded (directories/social/irrelevant): {excluded_count}")
        logger.info(f"  - Total discovered URLs: {len(all_discovered)}")
        logger.info(f"{'-'*80}")

        selected_websites = []

        # PRIORITY ORDER: Contact pages FIRST (most likely to have contact info)
        # Then main company page, then other pages

        # 1. Add contact pages first (highest priority for contact extraction)
        for url in categorized.get('contact_pages', []):
            if url not in selected_websites:
                selected_websites.append(url)
                logger.info(f"ADDED [Contact page - PRIORITY]: {url}")

        # 2. Add main company websites
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
