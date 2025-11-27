"""
Singapore Company Data API Service

Provides fallback data sources for Singapore company information when web scraping fails.
Uses publicly available APIs and data sources.
"""
import os
import httpx
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class SGDataAPIService:
    """
    Service for fetching Singapore company data from official/public APIs

    This serves as a fallback when web scraping fails due to Cloudflare or other blocks.
    """

    def __init__(self):
        # Data.gov.sg API (free, no key required for most endpoints)
        self.data_gov_base = "https://data.gov.sg/api/action"

        # OpenCorporates API (free tier available)
        self.opencorp_key = os.getenv("OPENCORPORATES_API_KEY")
        self.opencorp_base = "https://api.opencorporates.com/v0.4"

    async def search_company(
        self,
        company_name: str,
        uen: str
    ) -> Optional[Dict[str, Any]]:
        """
        Search for company data from available APIs

        Args:
            company_name: Company name
            uen: UEN number

        Returns:
            Dictionary with company data or None
        """
        logger.info(f"Searching APIs for company: {company_name} (UEN: {uen})")

        # Try OpenCorporates first (has more detailed data)
        if self.opencorp_key:
            result = await self._search_opencorporates(company_name, uen)
            if result:
                return result

        # Fallback to Data.gov.sg datasets
        result = await self._search_data_gov(company_name, uen)
        if result:
            return result

        return None

    async def _search_opencorporates(
        self,
        company_name: str,
        uen: str
    ) -> Optional[Dict[str, Any]]:
        """
        Search OpenCorporates API for company data

        Args:
            company_name: Company name
            uen: UEN number

        Returns:
            Dictionary with company data or None
        """
        try:
            # Search by company number (UEN) in Singapore jurisdiction
            params = {
                "q": company_name,
                "jurisdiction_code": "sg",
                "api_token": self.opencorp_key,
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.opencorp_base}/companies/search",
                    params=params
                )

                if response.status_code == 200:
                    data = response.json()
                    companies = data.get("results", {}).get("companies", [])

                    for company in companies:
                        company_data = company.get("company", {})
                        # Check if UEN matches
                        if company_data.get("company_number") == uen:
                            logger.info(f"Found company in OpenCorporates: {company_name}")
                            return self._parse_opencorp_data(company_data)

                    # If no exact UEN match, return first result
                    if companies:
                        logger.info(f"Found similar company in OpenCorporates for: {company_name}")
                        return self._parse_opencorp_data(companies[0].get("company", {}))

        except Exception as e:
            logger.error(f"OpenCorporates API error: {str(e)}")

        return None

    def _parse_opencorp_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse OpenCorporates data into standard format"""
        return {
            'source': 'opencorporates',
            'name': data.get('name'),
            'uen': data.get('company_number'),
            'status': data.get('current_status'),
            'address': data.get('registered_address_in_full'),
            'incorporation_date': data.get('incorporation_date'),
            'company_type': data.get('company_type'),
            'registry_url': data.get('registry_url'),
            # OpenCorporates doesn't typically have contact info
            'phone': None,
            'email': None,
        }

    async def _search_data_gov(
        self,
        company_name: str,
        uen: str
    ) -> Optional[Dict[str, Any]]:
        """
        Search Data.gov.sg for company data

        Note: Data.gov.sg has limited company datasets publicly available.
        This searches available business-related datasets.

        Args:
            company_name: Company name
            uen: UEN number

        Returns:
            Dictionary with company data or None
        """
        try:
            # Data.gov.sg uses CKAN API
            # Search for resources containing business/company data
            params = {
                "q": f"{company_name} {uen}",
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.data_gov_base}/package_search",
                    params=params
                )

                if response.status_code == 200:
                    data = response.json()
                    results = data.get("result", {}).get("results", [])

                    # Log available datasets (for debugging)
                    if results:
                        logger.info(f"Found {len(results)} potential datasets in Data.gov.sg")
                        for result in results[:3]:  # Log first 3
                            logger.debug(f"  - {result.get('title')}")

                    # Note: Most data.gov.sg datasets require additional processing
                    # This is a placeholder for actual implementation based on available datasets

        except Exception as e:
            logger.error(f"Data.gov.sg API error: {str(e)}")

        return None

    async def enrich_from_apis(
        self,
        company_name: str,
        uen: str,
        existing_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Attempt to enrich existing company data using APIs

        This is useful when scraping partially succeeded but some fields are missing.

        Args:
            company_name: Company name
            uen: UEN number
            existing_data: Existing scraped data

        Returns:
            Enriched data dictionary
        """
        # Only query APIs if we're missing key data
        missing_phone = not existing_data.get('phone')
        missing_email = not existing_data.get('email')

        if not (missing_phone or missing_email):
            return existing_data

        logger.info(f"Attempting API enrichment for {company_name} (missing: phone={missing_phone}, email={missing_email})")

        api_data = await self.search_company(company_name, uen)

        if api_data:
            # Merge API data with existing data (existing takes priority)
            if missing_phone and api_data.get('phone'):
                existing_data['phone'] = api_data['phone']
                logger.info(f"Added phone from API: {api_data['phone']}")

            if missing_email and api_data.get('email'):
                existing_data['email'] = api_data['email']
                logger.info(f"Added email from API: {api_data['email']}")

            # Add API source info
            existing_data['api_source'] = api_data.get('source')

        return existing_data
