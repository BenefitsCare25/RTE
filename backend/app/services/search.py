import os
import httpx
import re
import logging
from typing import Optional, Dict, Any, List
import asyncio

logger = logging.getLogger(__name__)

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

    def _extract_websites_from_results(
        self,
        data: Dict[str, Any],
        company_name: str
    ) -> List[str]:
        """
        Extract website URLs from SerpAPI results
        Returns multiple websites to maximize data extraction success

        Args:
            data: SerpAPI response data
            company_name: Company name for validation

        Returns:
            List of website URLs (prioritized: company name matches first, then other valid results)
        """
        # Check organic results
        organic_results = data.get("organic_results", [])

        logger.info(f"{'='*80}")
        logger.info(f"SerpAPI Search Results for: {company_name}")
        logger.info(f"Total results returned: {len(organic_results)}")
        logger.info(f"{'='*80}")

        # Only exclude social media and sites that don't contain contact info
        # Note: SG business directories (sgpbusiness, companies.sg, etc.) are ALLOWED
        # because they often contain phone/email data for companies without websites
        excluded_domains = [
            'facebook.com', 'linkedin.com', 'instagram.com',
            'twitter.com', 'youtube.com', 'wikipedia.org',
            'bizfile.gov.sg',  # Official registry, no contact info
        ]

        # Display all results first
        for idx, result in enumerate(organic_results, 1):
            url = result.get("link", "")
            title = result.get("title", "")
            logger.info(f"Result #{idx}:")
            logger.info(f"  Title: {title}")
            logger.info(f"  URL:   {url}")

            # Check if excluded
            is_excluded = any(domain in url for domain in excluded_domains)
            if is_excluded:
                excluded_domain = next(domain for domain in excluded_domains if domain in url)
                logger.info(f"  Status: EXCLUDED (domain: {excluded_domain})")
            else:
                # Check if matches company name
                title_match = company_name.lower() in title.lower()
                url_match = company_name.lower() in url.lower()
                if title_match or url_match:
                    match_type = []
                    if title_match:
                        match_type.append("title")
                    if url_match:
                        match_type.append("URL")
                    logger.info(f"  Status: MATCHES company name in {', '.join(match_type)}")
                else:
                    logger.info(f"  Status: Valid but no company name match")

        logger.info(f"{'-'*80}")
        logger.info("Selection Strategy: Collecting ALL valid websites for multi-source extraction")
        logger.info(f"{'-'*80}")

        selected_websites = []

        # First pass: Collect results with company name match (priority)
        for idx, result in enumerate(organic_results, 1):
            url = result.get("link", "")
            title = result.get("title", "").lower()

            if any(domain in url for domain in excluded_domains):
                continue

            if company_name.lower() in title or company_name.lower() in url.lower():
                cleaned_url = self._clean_url(url)
                selected_websites.append(cleaned_url)
                logger.info(f"ADDED Result #{idx} (Priority: Company name match) - {cleaned_url}")

        # Second pass: Add remaining non-excluded results
        for idx, result in enumerate(organic_results, 1):
            url = result.get("link", "")
            cleaned_url = self._clean_url(url)

            if any(domain in url for domain in excluded_domains):
                continue

            if cleaned_url not in selected_websites:
                selected_websites.append(cleaned_url)
                logger.info(f"ADDED Result #{idx} (Valid alternative) - {cleaned_url}")

        logger.info(f"{'-'*80}")
        logger.info(f"TOTAL SELECTED: {len(selected_websites)} websites will be scraped")
        logger.info(f"{'='*80}")

        return selected_websites

    def _extract_websites_from_bing(
        self,
        data: Dict[str, Any],
        company_name: str
    ) -> List[str]:
        """
        Extract website URLs from Bing search results
        Returns multiple websites to maximize data extraction success

        Args:
            data: Bing API response data
            company_name: Company name for validation

        Returns:
            List of website URLs (prioritized: company name matches first, then other valid results)
        """
        web_pages = data.get("webPages", {}).get("value", [])

        # Only exclude social media and sites that don't contain contact info
        # Note: SG business directories (sgpbusiness, companies.sg, etc.) are ALLOWED
        # because they often contain phone/email data for companies without websites
        excluded_domains = [
            'facebook.com', 'linkedin.com', 'instagram.com',
            'twitter.com', 'youtube.com', 'wikipedia.org',
            'bizfile.gov.sg',  # Official registry, no contact info
        ]

        logger.info("Collecting websites from Bing results...")
        selected_websites = []

        # First pass: Collect results with company name match (priority)
        for page in web_pages:
            url = page.get("url", "")

            if any(domain in url for domain in excluded_domains):
                continue

            name = page.get("name", "").lower()
            if company_name.lower() in name or company_name.lower() in url.lower():
                cleaned_url = self._clean_url(url)
                selected_websites.append(cleaned_url)
                logger.info(f"ADDED (Priority: Company name match) - {cleaned_url}")

        # Second pass: Add remaining non-excluded results
        for page in web_pages:
            url = page.get("url", "")
            cleaned_url = self._clean_url(url)

            if any(domain in url for domain in excluded_domains):
                continue

            if cleaned_url not in selected_websites:
                selected_websites.append(cleaned_url)
                logger.info(f"ADDED (Valid alternative) - {cleaned_url}")

        logger.info(f"TOTAL SELECTED: {len(selected_websites)} websites from Bing")
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
