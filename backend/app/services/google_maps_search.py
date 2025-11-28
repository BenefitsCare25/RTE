"""
Google Maps Search Service using SerpAPI
Searches for business listings to extract phone, website, and address
"""

import os
import re
import json
import httpx
import logging
import asyncio
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class GoogleMapsSearchService:
    """Service for searching Google Maps business listings via SerpAPI"""

    def __init__(self):
        self.serpapi_key = os.getenv("SERPAPI_KEY")
        # Singapore center coordinates with zoom level
        self.sg_coords = "@1.3521,103.8198,12z"
        self._request_count = 0

    async def search_business(
        self,
        company_name: str,
        address: str,
        uen: str = ""
    ) -> Dict[str, Any]:
        """
        Search Google Maps for a business listing using multiple query strategies.

        Args:
            company_name: Name of the company
            address: Full address including postal code
            uen: UEN number (optional, for logging)

        Returns:
            Dictionary with:
                - phone: Phone number if found
                - website: Website URL if found
                - maps_address: Address from Google Maps
                - rating: Business rating
                - reviews_count: Number of reviews
                - place_id: Google Place ID for further lookups
                - matched: True if result seems to match the company
                - source: 'google_maps'
        """
        if not self.serpapi_key:
            logger.warning("SERPAPI_KEY not configured, skipping Google Maps search")
            return {}

        logger.info(f"Google Maps search starting for: {company_name}")
        logger.info(f"Address: {address}")

        # Extract address components
        postal_code = self._extract_postal_code(address)
        street_name = self._extract_street_name(address)

        logger.info(f"Extracted - Postal: {postal_code}, Street: {street_name}")

        # Build query strategies in order of expected effectiveness
        query_strategies = []

        # Strategy 1: Company + Postal Code (most precise for Singapore)
        if postal_code:
            query_strategies.append(f"{company_name} Singapore {postal_code}")

        # Strategy 2: Company + Street Name
        if street_name:
            query_strategies.append(f"{company_name} {street_name} Singapore")

        # Strategy 3: Company name with Singapore
        query_strategies.append(f"{company_name} Singapore")

        # Strategy 4: Just company name (broadest)
        query_strategies.append(company_name)

        # Try each query strategy until we get results
        for idx, query in enumerate(query_strategies):
            logger.info(f"Query Strategy {idx + 1}/{len(query_strategies)}: {query}")

            result = await self._execute_maps_search(query, company_name, postal_code, address)

            if result:
                logger.info(f"SUCCESS with strategy {idx + 1}: {query}")
                return result

            # Small delay between queries to avoid rate limiting
            if idx < len(query_strategies) - 1:
                await asyncio.sleep(0.3)

        logger.warning(f"All {len(query_strategies)} query strategies failed for {company_name}")
        return {}

    async def _execute_maps_search(
        self,
        query: str,
        company_name: str,
        postal_code: Optional[str],
        original_address: str
    ) -> Dict[str, Any]:
        """Execute a single Google Maps search query and return parsed results."""
        try:
            params = {
                "engine": "google_maps",
                "q": query,
                "ll": self.sg_coords,
                "type": "search",
                "hl": "en",
                "gl": "sg",
                "api_key": self.serpapi_key
            }

            # Log request parameters (excluding API key)
            safe_params = {k: v for k, v in params.items() if k != 'api_key'}
            logger.info(f"SerpAPI Request params: {json.dumps(safe_params)}")

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    "https://serpapi.com/search",
                    params=params
                )

                self._request_count += 1
                logger.info(f"SerpAPI request #{self._request_count} - Status: {response.status_code}")

                if response.status_code != 200:
                    logger.error(f"Google Maps API error: {response.status_code}")
                    logger.error(f"Response body: {response.text[:500]}")
                    return {}

                data = response.json()

                # ============================================
                # DEBUG LOGGING - Full response analysis
                # ============================================
                logger.info(f"=== SerpAPI Response Debug for '{company_name}' ===")
                logger.info(f"Response keys: {list(data.keys())}")

                # Log search metadata
                if "search_metadata" in data:
                    metadata = data["search_metadata"]
                    logger.info(f"Search status: {metadata.get('status')}")
                    logger.info(f"Search ID: {metadata.get('id')}")
                    logger.info(f"Total time: {metadata.get('total_time_taken')}s")

                # Log search parameters echo
                if "search_parameters" in data:
                    logger.info(f"Search params echo: {data['search_parameters']}")

                # Log search information
                if "search_information" in data:
                    logger.info(f"Search info: {data['search_information']}")

                # Check all possible result keys
                result_keys = ['local_results', 'place_results', 'inline_local', 'organic_results']
                for key in result_keys:
                    if key in data:
                        results = data[key]
                        if isinstance(results, list):
                            logger.info(f"Found {len(results)} items in '{key}'")
                            if results:
                                first = results[0]
                                logger.info(f"First {key} sample: title='{first.get('title')}', "
                                          f"phone='{first.get('phone')}', website='{first.get('website')}', "
                                          f"address='{first.get('address')}'")
                        elif isinstance(results, dict):
                            logger.info(f"Found '{key}' (dict) with keys: {list(results.keys())}")
                    else:
                        logger.info(f"'{key}' NOT in response")

                logger.info(f"=== End SerpAPI Debug ===")

                # Check for API errors
                if "error" in data:
                    logger.error(f"SerpAPI error: {data['error']}")
                    return {}

                # Find best matching result
                return self._find_best_match(data, company_name, postal_code, original_address)

        except Exception as e:
            logger.error(f"Google Maps search error: {str(e)}", exc_info=True)
            return {}

    def _extract_postal_code(self, address: str) -> Optional[str]:
        """
        Extract Singapore postal code from address
        Singapore postal codes are 6 digits
        """
        if not address:
            return None

        # Pattern for Singapore postal code (6 digits)
        # May appear as "Singapore 123456" or just "123456" at end
        patterns = [
            r'Singapore\s*(\d{6})',
            r'S\s*\(?(\d{6})\)?',
            r'\b(\d{6})\b(?!.*\d{6})'  # Last 6-digit number in string
        ]

        for pattern in patterns:
            match = re.search(pattern, address, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _extract_street_name(self, address: str) -> Optional[str]:
        """Extract main street name from Singapore address for query building"""
        if not address:
            return None

        # Common Singapore street suffixes and Malay road names (Jalan, Lorong, etc.)
        street_patterns = [
            # Standard English street names
            r'(?:BLK\s+\d+[A-Z]?\s*,?\s*)?([A-Z][A-Z\s]+(?:ROAD|STREET|AVENUE|DRIVE|LANE|PLACE|WAY|CRESCENT|TERRACE|BOULEVARD|CLOSE|HILL|PARK|WALK|LINK|RISE|VIEW|HEIGHTS|GARDENS))',
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Road|Street|Avenue|Drive|Lane|Place|Way|Crescent|Terrace|Boulevard|Close|Hill|Park|Walk|Link|Rise|View|Heights|Gardens))',
            # Malay road names (Jalan, Lorong, Taman, etc.)
            r'(JALAN\s+[A-Z][A-Z\s]+)',
            r'(JLN\.?\s+[A-Z][A-Z\s]+)',
            r'(LORONG\s+[A-Z0-9][A-Z0-9\s]*)',
            r'(TAMAN\s+[A-Z][A-Z\s]+)',
            r'(Jalan\s+[A-Za-z][A-Za-z\s]+)',
            r'(Lorong\s+[A-Za-z0-9][A-Za-z0-9\s]*)',
        ]

        for pattern in street_patterns:
            match = re.search(pattern, address, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def _find_best_match(
        self,
        data: Dict[str, Any],
        company_name: str,
        postal_code: Optional[str],
        original_address: str
    ) -> Dict[str, Any]:
        """
        Find the best matching business from Google Maps results.
        Checks multiple response keys as SerpAPI may return different structures.

        Args:
            data: SerpAPI response data
            company_name: Company name to match
            postal_code: Postal code to verify
            original_address: Original address for verification

        Returns:
            Best matching result with extracted contact info
        """
        # Check multiple possible result keys
        results = []

        # Primary: local_results (most common for Maps search)
        local_results = data.get("local_results", [])
        if local_results:
            results.extend(local_results)
            logger.info(f"Using {len(local_results)} results from 'local_results'")

        # Alternative: place_results (single place detail)
        place_results = data.get("place_results")
        if place_results:
            if isinstance(place_results, dict):
                results.append(place_results)
                logger.info("Found 1 result in 'place_results' (dict)")
            elif isinstance(place_results, list):
                results.extend(place_results)
                logger.info(f"Found {len(place_results)} results in 'place_results' (list)")

        # Alternative: inline_local (sometimes used for embedded results)
        inline_local = data.get("inline_local", {})
        if isinstance(inline_local, dict) and "results" in inline_local:
            results.extend(inline_local["results"])
            logger.info(f"Found {len(inline_local['results'])} results in 'inline_local.results'")

        if not results:
            logger.warning(f"No Google Maps results found for {company_name} (checked: local_results, place_results, inline_local)")
            return {}

        logger.info(f"Total {len(results)} Google Maps results to evaluate")

        # Score each result
        scored_results = []
        company_name_lower = company_name.lower()

        for idx, result in enumerate(results):
            score = 0
            title = result.get("title", "").lower()
            result_address = result.get("address", "")

            # Name matching (most important)
            if company_name_lower == title:
                score += 100  # Exact match
            elif company_name_lower in title or title in company_name_lower:
                score += 50  # Partial match
            else:
                # Check for word overlap
                name_words = set(company_name_lower.split())
                title_words = set(title.split())
                overlap = len(name_words & title_words)
                score += overlap * 10

            # Postal code matching (very reliable for Singapore)
            if postal_code and postal_code in result_address:
                score += 80  # Strong location match

            # Has phone number (we want this)
            if result.get("phone"):
                score += 20

            # Has website (we want this)
            if result.get("website"):
                score += 15

            # Has rating (indicates established business)
            if result.get("rating"):
                score += 5

            logger.debug(f"Result #{idx+1}: '{result.get('title')}' - Score: {score}")

            scored_results.append((score, result))

        # Sort by score descending
        scored_results.sort(key=lambda x: x[0], reverse=True)

        # Get best match
        best_score, best_result = scored_results[0]

        # Only accept if score is reasonable
        if best_score < 20:
            logger.warning(f"Best match score too low ({best_score}), may not be correct business")

        # Log the match
        logger.info(f"Best match: '{best_result.get('title')}' (score: {best_score})")
        logger.info(f"  Phone: {best_result.get('phone', 'N/A')}")
        logger.info(f"  Website: {best_result.get('website', 'N/A')}")
        logger.info(f"  Address: {best_result.get('address', 'N/A')}")

        # Extract and return relevant data
        return {
            "phone": self._clean_phone(best_result.get("phone")),
            "website": self._clean_website(best_result.get("website")),
            "maps_address": best_result.get("address", ""),
            "rating": best_result.get("rating"),
            "reviews_count": best_result.get("reviews"),
            "place_id": best_result.get("place_id"),
            "gps_coordinates": best_result.get("gps_coordinates"),
            "matched": best_score >= 50,
            "match_score": best_score,
            "source": "google_maps"
        }

    def _clean_phone(self, phone: Optional[str]) -> Optional[str]:
        """Clean and normalize phone number"""
        if not phone:
            return None

        # Remove common prefixes and clean up
        cleaned = phone.strip()

        # Remove any non-digit characters except + at start
        if cleaned.startswith('+'):
            cleaned = '+' + re.sub(r'[^\d]', '', cleaned[1:])
        else:
            cleaned = re.sub(r'[^\d]', '', cleaned)

        # Format Singapore numbers
        if cleaned.startswith('65') and len(cleaned) == 10:
            cleaned = f"+65 {cleaned[2:6]} {cleaned[6:]}"
        elif len(cleaned) == 8:
            cleaned = f"+65 {cleaned[:4]} {cleaned[4:]}"

        return cleaned if cleaned else None

    def _clean_website(self, website: Optional[str]) -> Optional[str]:
        """Clean and validate website URL"""
        if not website:
            return None

        website = website.strip()

        # Ensure it has a scheme
        if not website.startswith(('http://', 'https://')):
            website = 'https://' + website

        # Remove tracking parameters
        if '?' in website:
            website = website.split('?')[0]

        # Validate it looks like a real URL
        try:
            parsed = urlparse(website)
            if parsed.netloc:
                return website
        except:
            pass

        return None

    async def get_place_details(self, place_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific place
        Useful for getting more contact info if initial search was incomplete

        Args:
            place_id: Google Place ID from search results

        Returns:
            Detailed place information
        """
        if not self.serpapi_key or not place_id:
            return {}

        try:
            params = {
                "engine": "google_maps",
                "type": "place",
                "place_id": place_id,
                "hl": "en",
                "gl": "sg",
                "api_key": self.serpapi_key
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    "https://serpapi.com/search",
                    params=params
                )

                if response.status_code == 200:
                    data = response.json()
                    place_results = data.get("place_results", {})

                    return {
                        "phone": self._clean_phone(place_results.get("phone")),
                        "website": self._clean_website(place_results.get("website")),
                        "address": place_results.get("address"),
                        "hours": place_results.get("hours"),
                        "rating": place_results.get("rating"),
                        "source": "google_maps_details"
                    }

        except Exception as e:
            logger.error(f"Place details error: {str(e)}")

        return {}
