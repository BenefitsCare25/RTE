import os
import httpx
from typing import Optional, Dict, Any
import asyncio

class SearchService:
    """Service for searching company information using search engines"""

    def __init__(self):
        self.serpapi_key = os.getenv("SERPAPI_KEY")
        self.bing_key = os.getenv("BING_SEARCH_KEY")

    async def search_company_website(
        self,
        company_name: str,
        uen: str,
        address: str
    ) -> Optional[str]:
        """
        Search for company website using available search APIs

        Args:
            company_name: Name of the company
            uen: UEN number
            address: Company address

        Returns:
            Company website URL if found, None otherwise
        """
        # Try SerpAPI first
        if self.serpapi_key:
            website = await self._search_with_serpapi(company_name, uen)
            if website:
                return website

        # Fallback to Bing if available
        if self.bing_key:
            website = await self._search_with_bing(company_name, uen)
            if website:
                return website

        return None

    async def _search_with_serpapi(
        self,
        company_name: str,
        uen: str
    ) -> Optional[str]:
        """
        Search using SerpAPI (Google Custom Search)

        Args:
            company_name: Name of the company
            uen: UEN number

        Returns:
            Website URL if found
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
                    return self._extract_website_from_results(data, company_name)

        except Exception as e:
            print(f"SerpAPI search error: {str(e)}")

        return None

    async def _search_with_bing(
        self,
        company_name: str,
        uen: str
    ) -> Optional[str]:
        """
        Search using Bing Search API

        Args:
            company_name: Name of the company
            uen: UEN number

        Returns:
            Website URL if found
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
                    return self._extract_website_from_bing(data, company_name)

        except Exception as e:
            print(f"Bing search error: {str(e)}")

        return None

    def _extract_website_from_results(
        self,
        data: Dict[str, Any],
        company_name: str
    ) -> Optional[str]:
        """
        Extract website URL from SerpAPI results

        Args:
            data: SerpAPI response data
            company_name: Company name for validation

        Returns:
            Website URL if found
        """
        # Check organic results
        organic_results = data.get("organic_results", [])

        for result in organic_results:
            url = result.get("link", "")

            # Skip common non-company sites
            excluded_domains = [
                'facebook.com', 'linkedin.com', 'instagram.com',
                'twitter.com', 'youtube.com', 'wikipedia.org',
                'bizfile.gov.sg', 'dnb.com', 'bloomberg.com'
            ]

            if any(domain in url for domain in excluded_domains):
                continue

            # Prefer results with company name in URL or title
            title = result.get("title", "").lower()
            if company_name.lower() in title or company_name.lower() in url.lower():
                return self._clean_url(url)

        # If no match with company name, return first non-excluded result
        if organic_results:
            for result in organic_results:
                url = result.get("link", "")
                if not any(domain in url for domain in excluded_domains):
                    return self._clean_url(url)

        return None

    def _extract_website_from_bing(
        self,
        data: Dict[str, Any],
        company_name: str
    ) -> Optional[str]:
        """
        Extract website URL from Bing search results

        Args:
            data: Bing API response data
            company_name: Company name for validation

        Returns:
            Website URL if found
        """
        web_pages = data.get("webPages", {}).get("value", [])

        excluded_domains = [
            'facebook.com', 'linkedin.com', 'instagram.com',
            'twitter.com', 'youtube.com', 'wikipedia.org',
            'bizfile.gov.sg', 'dnb.com', 'bloomberg.com'
        ]

        for page in web_pages:
            url = page.get("url", "")

            if any(domain in url for domain in excluded_domains):
                continue

            name = page.get("name", "").lower()
            if company_name.lower() in name or company_name.lower() in url.lower():
                return self._clean_url(url)

        # Return first non-excluded result
        if web_pages:
            for page in web_pages:
                url = page.get("url", "")
                if not any(domain in url for domain in excluded_domains):
                    return self._clean_url(url)

        return None

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
