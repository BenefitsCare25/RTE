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

        IMPORTANT: Stricter matching to avoid wrong company matches.
        - Minimum score threshold of 70 (was 20)
        - Requires significant name overlap, not just word matches
        - Penalizes matches that look like buildings/hotels instead of the company

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

        # Extract company keywords for matching (ignore common suffixes)
        company_keywords = self._extract_company_keywords(company_name)
        logger.info(f"Company keywords for matching: {company_keywords}")

        # Score each result
        scored_results = []
        company_name_lower = company_name.lower()
        # Remove common suffixes for cleaner comparison
        company_name_clean = self._clean_company_name(company_name)

        for idx, result in enumerate(results):
            score = 0
            title = result.get("title", "")
            title_lower = title.lower()
            title_clean = self._clean_company_name(title)
            result_address = result.get("address", "")

            # Penalty indicators - businesses that are NOT the company we're looking for
            # Hotels, buildings, landmarks at the same address
            building_indicators = ['hotel', 'tower', 'building', 'plaza', 'centre', 'center',
                                   'mall', 'complex', 'arcade', 'court', 'house', 'mansion']
            is_building = any(ind in title_lower for ind in building_indicators)

            # Name matching (most important) - STRICTER SCORING
            if company_name_clean.lower() == title_clean.lower():
                score += 150  # Exact match after cleaning - highest confidence
                logger.info(f"  Result #{idx+1}: EXACT name match (cleaned)")
            elif company_name_lower == title_lower:
                score += 140  # Exact match
                logger.info(f"  Result #{idx+1}: EXACT name match")
            elif company_name_clean.lower() in title_clean.lower() or title_clean.lower() in company_name_clean.lower():
                score += 80  # One contains the other (after cleaning)
            elif company_name_lower in title_lower or title_lower in company_name_lower:
                score += 70  # Partial match
            else:
                # Check for keyword overlap - must have SIGNIFICANT overlap
                title_keywords = self._extract_company_keywords(title)
                if company_keywords and title_keywords:
                    matching_keywords = set(company_keywords) & set(title_keywords)
                    total_keywords = len(company_keywords)
                    match_ratio = len(matching_keywords) / total_keywords if total_keywords > 0 else 0

                    if match_ratio >= 0.5:  # At least 50% of keywords must match
                        score += int(match_ratio * 60)  # Max 60 points for keyword match
                        logger.info(f"  Result #{idx+1}: Keyword match {matching_keywords} ({match_ratio:.0%})")
                    else:
                        # Very low keyword match - likely wrong company
                        score += int(match_ratio * 20)  # Max 20 points
                        logger.info(f"  Result #{idx+1}: LOW keyword match {matching_keywords} ({match_ratio:.0%})")

            # Postal code matching (reliable for Singapore)
            # BUT: reduce weight if it looks like a building (company might be IN the building)
            if postal_code and postal_code in result_address:
                if is_building:
                    score += 20  # Reduced weight for buildings at same address
                    logger.info(f"  Result #{idx+1}: Postal match but looks like building")
                else:
                    score += 50  # Good location match (reduced from 80)

            # Penalize building/hotel matches - these are often the ADDRESS, not the company
            if is_building:
                score -= 40
                logger.info(f"  Result #{idx+1}: PENALTY - looks like building/hotel: {title}")

            # Has phone number (we want this)
            if result.get("phone"):
                score += 15

            # Has website (we want this)
            if result.get("website"):
                score += 10

            # Has rating (indicates established business)
            if result.get("rating"):
                score += 5

            logger.info(f"Result #{idx+1}: '{title}' - Score: {score}")

            scored_results.append((score, result))

        # Sort by score descending
        scored_results.sort(key=lambda x: x[0], reverse=True)

        # Get best match
        best_score, best_result = scored_results[0]

        # STRICTER threshold - must have score >= 70 to be considered a match
        # This prevents accepting random businesses with low word overlap
        MIN_MATCH_SCORE = 70

        if best_score < MIN_MATCH_SCORE:
            logger.warning(f"Best match score ({best_score}) below threshold ({MIN_MATCH_SCORE}), rejecting as likely wrong business")
            logger.warning(f"  Would have matched: '{best_result.get('title')}'")
            return {}

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
            "matched": best_score >= 80,  # Higher threshold for "matched" flag
            "match_score": best_score,
            "source": "google_maps"
        }

    def _extract_company_keywords(self, name: str) -> List[str]:
        """Extract significant keywords from company name for matching."""
        if not name:
            return []

        # Uppercase and clean
        clean = name.upper()
        clean = re.sub(r'[^\w\s]', ' ', clean)  # Remove punctuation
        clean = re.sub(r'\s+', ' ', clean).strip()

        # Remove common suffixes
        suffixes = ['PTE', 'LTD', 'LIMITED', 'PRIVATE', 'SINGAPORE', 'SDN', 'BHD',
                   'INC', 'LLC', 'CORP', 'CORPORATION', 'CO', 'COMPANY']
        words = clean.split()
        keywords = [w.lower() for w in words if len(w) >= 3 and w not in suffixes]

        return keywords

    def _clean_company_name(self, name: str) -> str:
        """Remove common suffixes from company name for comparison."""
        if not name:
            return ""

        clean = name.upper()
        # Remove common suffixes in order of specificity
        for suffix in [' PTE. LTD.', ' PTE LTD', ' PRIVATE LIMITED', ' LIMITED',
                      ' PTE.', ' LTD.', ' LTD', ' PTE', ' (S)', ' (SINGAPORE)',
                      ' CORPORATION', ' CORP', ' INC', ' LLC', ' SDN BHD', ' BHD']:
            clean = clean.replace(suffix, '')

        return clean.strip()

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

        # Handle Google redirect URLs: /url?q=https://actual-site.com/&opi=...
        if website.startswith('/url?q='):
            try:
                from urllib.parse import parse_qs, urlparse as parse_redirect
                # Extract the 'q' parameter which contains the actual URL
                query_string = website.split('?', 1)[1] if '?' in website else ''
                params = parse_qs(query_string)
                if 'q' in params and params['q']:
                    website = params['q'][0]
                    logger.debug(f"Extracted actual URL from Google redirect: {website}")
            except Exception as e:
                logger.warning(f"Failed to parse Google redirect URL: {website}, error: {e}")

        # Ensure it has a scheme
        if not website.startswith(('http://', 'https://')):
            website = 'https://' + website

        # Remove tracking parameters (but preserve the main URL)
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
