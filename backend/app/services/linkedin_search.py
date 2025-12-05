"""
LinkedIn Decision Maker Search Service

Finds company decision makers (C-Suite, HR heads, Founders/Directors) via Google search
using SerpAPI. Avoids direct LinkedIn scraping to comply with LinkedIn ToS.

Search Strategy:
1. Search Google for LinkedIn profiles: site:linkedin.com/in/ "{company}" (CEO OR Founder)
2. Parse results to extract name, job title, LinkedIn URL
3. Score and rank by role priority and relevance
4. Return top 3 with role diversity
"""

import os
import re
import logging
import asyncio
from typing import List, Dict, Optional, Tuple
from serpapi import GoogleSearch

logger = logging.getLogger(__name__)


class LinkedInSearchService:
    """
    Service for finding decision makers via LinkedIn profile search using SerpAPI.
    Uses Google Search (NOT LinkedIn API) to avoid ToS violations.
    """

    # Role classification with priority scores
    ROLE_PATTERNS = {
        'c_suite': {
            'keywords': [
                'CEO', 'Chief Executive Officer',
                'COO', 'Chief Operating Officer',
                'CFO', 'Chief Financial Officer',
                'CTO', 'Chief Technology Officer',
                'CMO', 'Chief Marketing Officer',
                'CPO', 'Chief Product Officer',
                'CIO', 'Chief Information Officer',
                'President'
            ],
            'score': 100
        },
        'founder': {
            'keywords': [
                'Founder', 'Co-Founder', 'Co Founder', 'Cofounder',
                'Managing Director', 'MD',
                'Owner', 'Proprietor'
            ],
            'score': 90
        },
        'hr': {
            'keywords': [
                'HR Director', 'HR Manager', 'Head of HR', 'Head of People',
                'CHRO', 'Chief HR Officer', 'Chief Human Resources Officer',
                'Chief People Officer', 'VP of HR', 'VP HR',
                'Director of HR', 'Director of Human Resources',
                'People Director', 'Talent Director'
            ],
            'score': 80
        },
        'director': {
            'keywords': [
                'Director', 'Board Member', 'Executive Director',
                'Non-Executive Director', 'Board Director'
            ],
            'score': 75
        },
        'executive': {
            'keywords': [
                'VP', 'Vice President', 'SVP', 'Senior Vice President',
                'General Manager', 'GM', 'Head of', 'Department Head'
            ],
            'score': 70
        }
    }

    # Exclude these patterns (not decision makers)
    EXCLUDE_PATTERNS = [
        'Recruiter', 'Recruitment', 'Talent Acquisition',
        'Student', 'Intern', 'Internship',
        'Former', 'Ex-', 'Retired',
        'Seeking', 'Looking for',
        'Freelance', 'Consultant',
        'Assistant', 'Associate', 'Junior'
    ]

    # Company suffix removal for cleaner matching
    COMPANY_SUFFIXES = [
        'Pte Ltd', 'Pte. Ltd.', 'Private Limited',
        'Ltd', 'Limited',
        'Sdn Bhd',
        'Inc', 'Incorporated',
        'Corp', 'Corporation',
        'LLC', 'LLP'
    ]

    def __init__(self):
        """Initialize the LinkedIn search service."""
        self.serpapi_key = os.getenv("SERPAPI_KEY")
        if not self.serpapi_key:
            logger.warning("SERPAPI_KEY not found - LinkedIn search will be disabled")

    async def find_decision_makers(
        self,
        company_name: str,
        max_results: int = 3
    ) -> List[Dict[str, str]]:
        """
        Find top decision makers for a company via LinkedIn search.

        Args:
            company_name: Company name to search for
            max_results: Maximum number of decision makers to return (default: 3)

        Returns:
            List of dicts with keys: name, title, linkedin_url
            Example: [
                {
                    'name': 'John Doe',
                    'title': 'CEO',
                    'linkedin_url': 'https://www.linkedin.com/in/john-doe-123456/'
                },
                ...
            ]
        """
        if not self.serpapi_key:
            logger.warning("LinkedIn search skipped - no SERPAPI_KEY")
            return []

        try:
            logger.info(f"Searching LinkedIn for decision makers: {company_name}")

            # Collect all decision maker candidates
            all_candidates = []

            # Try multiple search strategies
            search_queries = self._generate_search_queries(company_name)

            for query in search_queries:
                try:
                    results = await self._search_linkedin_profiles(query)

                    for result in results:
                        parsed = self._parse_linkedin_result(result, company_name)
                        if parsed:
                            all_candidates.append(parsed)

                    # Stop early if we have enough candidates
                    if len(all_candidates) >= max_results * 3:
                        break

                    # Rate limiting
                    await asyncio.sleep(0.5)

                except Exception as e:
                    logger.warning(f"LinkedIn search query failed: {str(e)}")
                    continue

            if not all_candidates:
                logger.info(f"No LinkedIn decision makers found for {company_name}")
                return []

            # Deduplicate, score, and rank
            decision_makers = self._deduplicate_and_rank(all_candidates, max_results)

            logger.info(f"Found {len(decision_makers)} decision makers for {company_name}")
            return decision_makers

        except Exception as e:
            logger.error(f"LinkedIn search failed for {company_name}: {str(e)}")
            return []

    def _generate_search_queries(self, company_name: str) -> List[str]:
        """
        Generate multiple LinkedIn search queries with fallback strategies.

        Args:
            company_name: Company name

        Returns:
            List of search query strings
        """
        clean_name = self._clean_company_name(company_name)

        queries = [
            # Strategy 1: Target C-Suite
            f'site:linkedin.com/in/ "{clean_name}" (CEO OR COO OR CFO) Singapore',

            # Strategy 2: Founders & Directors
            f'site:linkedin.com/in/ "{clean_name}" (Founder OR "Managing Director") Singapore',

            # Strategy 3: HR Leadership
            f'site:linkedin.com/in/ "{clean_name}" ("HR Director" OR "HR Manager" OR "Chief People Officer") Singapore',

            # Strategy 4: Broad executive search
            f'site:linkedin.com/in/ "{clean_name}" Singapore (Director OR Executive)',
        ]

        return queries

    def _clean_company_name(self, company_name: str) -> str:
        """
        Clean company name by removing common suffixes.

        Args:
            company_name: Original company name

        Returns:
            Cleaned company name
        """
        clean_name = company_name

        # Remove company suffixes
        for suffix in self.COMPANY_SUFFIXES:
            clean_name = re.sub(rf'\s*{re.escape(suffix)}\s*$', '', clean_name, flags=re.IGNORECASE)

        return clean_name.strip()

    async def _search_linkedin_profiles(self, query: str) -> List[Dict]:
        """
        Execute SerpAPI Google search for LinkedIn profiles.

        Args:
            query: Search query string

        Returns:
            List of organic search results
        """
        try:
            params = {
                "engine": "google",
                "q": query,
                "num": 20,  # Get more results for better filtering
                "hl": "en",
                "gl": "sg",
                "location": "Singapore",
                "api_key": self.serpapi_key
            }

            # Run synchronous SerpAPI call in thread pool
            loop = asyncio.get_event_loop()
            search = await loop.run_in_executor(None, lambda: GoogleSearch(params))
            results = await loop.run_in_executor(None, search.get_dict)

            organic_results = results.get("organic_results", [])
            logger.debug(f"SerpAPI returned {len(organic_results)} results for query: {query[:50]}...")

            return organic_results

        except Exception as e:
            logger.error(f"SerpAPI search failed: {str(e)}")
            return []

    def _parse_linkedin_result(
        self,
        result: Dict,
        company_name: str
    ) -> Optional[Dict]:
        """
        Extract name, title, LinkedIn URL from search result.

        Args:
            result: SerpAPI organic result dict
            company_name: Company name for validation

        Returns:
            Dict with name, title, linkedin_url, role_type, score or None if invalid
        """
        try:
            title = result.get("title", "")
            link = result.get("link", "")
            snippet = result.get("snippet", "")

            # Validate LinkedIn URL
            if "linkedin.com/in/" not in link:
                return None

            # Extract name from title
            name = self._extract_name_from_title(title)
            if not name:
                return None

            # Extract job title
            job_title = self._extract_job_title(title, snippet)
            if not job_title:
                return None

            # Classify role and get score
            role_type, role_score = self._classify_role(job_title)
            if not role_type:
                return None

            # Verify company match
            if not self._matches_company(result, company_name):
                logger.debug(f"Skipping {name} - company mismatch")
                return None

            # Check for excluded patterns
            if self._is_excluded(job_title):
                logger.debug(f"Skipping {name} - excluded role: {job_title}")
                return None

            # Score the candidate
            score = self._score_decision_maker(
                {'name': name, 'title': job_title, 'linkedin_url': link, 'role_type': role_type},
                company_name,
                title,
                snippet,
                role_score
            )

            return {
                'name': name,
                'title': job_title,
                'linkedin_url': link,
                'role_type': role_type,
                'score': score
            }

        except Exception as e:
            logger.debug(f"Failed to parse LinkedIn result: {str(e)}")
            return None

    def _extract_name_from_title(self, title: str) -> Optional[str]:
        """
        Parse name from LinkedIn title format.

        Expected formats:
        - "John Doe - CEO at ABC Company | LinkedIn"
        - "Jane Smith | LinkedIn"
        - "John Doe, CEO at ABC Company - LinkedIn"

        Args:
            title: LinkedIn page title

        Returns:
            Person's name or None
        """
        try:
            # Remove "| LinkedIn" suffix
            title = re.sub(r'\s*\|\s*LinkedIn\s*$', '', title, flags=re.IGNORECASE)

            # Remove "- LinkedIn" suffix
            title = re.sub(r'\s*-\s*LinkedIn\s*$', '', title, flags=re.IGNORECASE)

            # Extract name before " - " or " | " or ","
            match = re.match(r'^([^-|,]+)', title)
            if match:
                name = match.group(1).strip()

                # Validate name (should be 2-50 chars, no numbers)
                if 2 <= len(name) <= 50 and not re.search(r'\d', name):
                    return name

            return None

        except Exception as e:
            logger.debug(f"Name extraction failed: {str(e)}")
            return None

    def _extract_job_title(self, title: str, snippet: str) -> Optional[str]:
        """
        Extract job title from LinkedIn result.

        Args:
            title: LinkedIn page title
            snippet: LinkedIn page snippet

        Returns:
            Job title or None
        """
        try:
            # Try extracting from title first
            # Format: "Name - Job Title at Company"
            match = re.search(r'-\s*([^|]+?)\s+at\s+', title, re.IGNORECASE)
            if match:
                job_title = match.group(1).strip()
                if job_title:
                    return job_title

            # Try extracting from snippet
            # Format: "Job Title at Company · Location"
            match = re.search(r'^([^·]+?)\s+at\s+', snippet, re.IGNORECASE)
            if match:
                job_title = match.group(1).strip()
                if job_title:
                    return job_title

            # Try other patterns in snippet
            match = re.search(r'(CEO|COO|CFO|CTO|Founder|Director|Manager|Head|Chief[^·]+)', snippet, re.IGNORECASE)
            if match:
                return match.group(1).strip()

            return None

        except Exception as e:
            logger.debug(f"Job title extraction failed: {str(e)}")
            return None

    def _classify_role(self, job_title: str) -> Tuple[Optional[str], int]:
        """
        Classify role type and return priority score.

        Args:
            job_title: Job title string

        Returns:
            Tuple of (role_type, base_score) or (None, 0) if not a target role
        """
        job_title_lower = job_title.lower()

        for role_type, config in self.ROLE_PATTERNS.items():
            for keyword in config['keywords']:
                if keyword.lower() in job_title_lower:
                    return role_type, config['score']

        return None, 0

    def _matches_company(self, result: Dict, company_name: str) -> bool:
        """
        Check if LinkedIn result matches target company.

        Args:
            result: SerpAPI result dict
            company_name: Target company name

        Returns:
            True if result matches company
        """
        title = result.get("title", "").lower()
        snippet = result.get("snippet", "").lower()
        text = f"{title} {snippet}"

        # Extract keywords from company name
        clean_name = self._clean_company_name(company_name)
        keywords = [k.strip() for k in re.split(r'[\s&]+', clean_name) if len(k.strip()) > 2]

        if not keywords:
            return False

        # Count keyword matches
        matches = sum(1 for keyword in keywords if keyword.lower() in text)

        # Require at least 50% keyword match
        match_ratio = matches / len(keywords)
        return match_ratio >= 0.5

    def _is_excluded(self, job_title: str) -> bool:
        """
        Check if job title matches excluded patterns.

        Args:
            job_title: Job title string

        Returns:
            True if title should be excluded
        """
        job_title_lower = job_title.lower()

        for pattern in self.EXCLUDE_PATTERNS:
            if pattern.lower() in job_title_lower:
                return True

        return False

    def _score_decision_maker(
        self,
        dm: Dict,
        company_name: str,
        title: str,
        snippet: str,
        role_score: int
    ) -> int:
        """
        Score decision maker by role priority and relevance.

        Args:
            dm: Decision maker dict with name, title, linkedin_url, role_type
            company_name: Target company name
            title: LinkedIn page title
            snippet: LinkedIn page snippet
            role_score: Base score from role classification

        Returns:
            Total score (higher = better)
        """
        score = role_score

        # Bonus: Company name in title
        clean_name = self._clean_company_name(company_name)
        if clean_name.lower() in title.lower():
            score += 50

        # Bonus: Current position indicators
        current_keywords = ['current', 'present', 'currently']
        if any(kw in snippet.lower() for kw in current_keywords):
            score += 30

        # Bonus: Seniority keywords
        seniority_keywords = ['senior', 'head', 'chief', 'executive', 'managing']
        if any(kw in dm['title'].lower() for kw in seniority_keywords):
            score += 20

        # Bonus: Singapore location
        if 'singapore' in snippet.lower():
            score += 10

        return score

    def _deduplicate_and_rank(
        self,
        decision_makers: List[Dict],
        max_results: int
    ) -> List[Dict]:
        """
        Remove duplicates, rank by score, ensure role diversity.

        Args:
            decision_makers: List of decision maker dicts
            max_results: Maximum number of results to return

        Returns:
            Top decision makers with role diversity
        """
        # Deduplicate by LinkedIn URL
        seen_urls = set()
        unique_dms = []

        for dm in decision_makers:
            profile_id = self._extract_profile_id(dm['linkedin_url'])
            if profile_id not in seen_urls:
                seen_urls.add(profile_id)
                unique_dms.append(dm)

        # Sort by score (descending)
        unique_dms.sort(key=lambda x: x['score'], reverse=True)

        # Ensure role diversity: prefer different role types
        selected = []
        role_types_seen = set()

        for dm in unique_dms:
            role_type = dm['role_type']

            # Prioritize unseen role types
            if role_type not in role_types_seen:
                selected.append(dm)
                role_types_seen.add(role_type)
            elif len(selected) < max_results:
                # If we haven't filled quota, add even if duplicate role
                selected.append(dm)

            if len(selected) >= max_results:
                break

        # Remove scoring fields before returning
        return [
            {
                'name': dm['name'],
                'title': dm['title'],
                'linkedin_url': dm['linkedin_url']
            }
            for dm in selected
        ]

    def _extract_profile_id(self, linkedin_url: str) -> str:
        """
        Extract unique profile identifier from LinkedIn URL.

        Args:
            linkedin_url: LinkedIn profile URL

        Returns:
            Profile ID (e.g., "john-doe-123456")

        Example:
            https://linkedin.com/in/john-doe-123456/ -> john-doe-123456
        """
        match = re.search(r'linkedin\.com/in/([^/?]+)', linkedin_url)
        return match.group(1) if match else linkedin_url
