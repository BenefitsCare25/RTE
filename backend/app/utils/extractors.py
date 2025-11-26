import re
from typing import List, Optional

class ContactExtractor:
    """Utility class for extracting contact information from text"""

    # Singapore phone number patterns
    PHONE_PATTERNS = [
        # +65 XXXX XXXX or +65-XXXX-XXXX or +65XXXXXXXX
        r'\+65[\s-]?[3689]\d{3}[\s-]?\d{4}',
        # 65 XXXX XXXX or 65-XXXX-XXXX or 65XXXXXXXX
        r'65[\s-]?[3689]\d{3}[\s-]?\d{4}',
        # XXXX XXXX (8 digits starting with 3, 6, 8, 9)
        r'\b[3689]\d{3}[\s-]?\d{4}\b',
    ]

    # Email pattern
    EMAIL_PATTERN = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'

    # Common email domains to exclude (generic/non-business)
    EXCLUDED_EMAIL_DOMAINS = [
        'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
        'example.com', 'test.com', 'domain.com'
    ]

    # Founder/director title patterns
    FOUNDER_TITLES = [
        r'(?:founder|co-founder|cofounder)',
        r'(?:chief executive officer|ceo)',
        r'(?:managing director|md)',
        r'(?:director)',
        r'(?:president)',
        r'(?:owner)',
        r'(?:proprietor)'
    ]

    @staticmethod
    def extract_phone_numbers(text: str) -> List[str]:
        """
        Extract Singapore phone numbers from text

        Args:
            text: Text content to search

        Returns:
            List of found phone numbers
        """
        if not text:
            return []

        phone_numbers = set()

        for pattern in ContactExtractor.PHONE_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                # Clean up the phone number
                cleaned = re.sub(r'[\s-]', '', match)

                # Ensure it starts with +65 or 65
                if cleaned.startswith('+65'):
                    phone_numbers.add(cleaned)
                elif cleaned.startswith('65') and len(cleaned) == 10:
                    phone_numbers.add('+' + cleaned)
                elif len(cleaned) == 8 and cleaned[0] in '3689':
                    phone_numbers.add('+65' + cleaned)

        return list(phone_numbers)

    @staticmethod
    def extract_emails(text: str, prefer_business: bool = True) -> List[str]:
        """
        Extract email addresses from text

        Args:
            text: Text content to search
            prefer_business: If True, prioritize business emails over generic ones

        Returns:
            List of found email addresses
        """
        if not text:
            return []

        matches = re.findall(ContactExtractor.EMAIL_PATTERN, text, re.IGNORECASE)
        emails = list(set(matches))

        if prefer_business:
            # Separate business and generic emails
            business_emails = []
            generic_emails = []

            for email in emails:
                domain = email.split('@')[1].lower()
                if domain in ContactExtractor.EXCLUDED_EMAIL_DOMAINS:
                    generic_emails.append(email)
                else:
                    business_emails.append(email)

            # Return business emails first, then generic
            return business_emails + generic_emails

        return emails

    @staticmethod
    def extract_founder_name(text: str) -> Optional[str]:
        """
        Extract founder or director name from text

        Args:
            text: Text content to search

        Returns:
            Founder/director name if found, None otherwise
        """
        if not text:
            return None

        # Look for patterns like "Founder: John Doe" or "CEO - Jane Smith"
        for title_pattern in ContactExtractor.FOUNDER_TITLES:
            # Pattern: Title followed by name
            pattern = rf'{title_pattern}[\s:,-]*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)'
            matches = re.findall(pattern, text, re.IGNORECASE)

            if matches:
                # Return the first match
                return matches[0].strip()

            # Pattern: Name followed by title
            pattern = rf'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)[\s,.-]*{title_pattern}'
            matches = re.findall(pattern, text, re.IGNORECASE)

            if matches:
                return matches[0].strip()

        return None

    @staticmethod
    def extract_all_contacts(text: str) -> dict:
        """
        Extract all contact information from text

        Args:
            text: Text content to search

        Returns:
            Dictionary with phone, email, and founder information
        """
        phones = ContactExtractor.extract_phone_numbers(text)
        emails = ContactExtractor.extract_emails(text)
        founder = ContactExtractor.extract_founder_name(text)

        return {
            'phone': phones[0] if phones else None,
            'email': emails[0] if emails else None,
            'founder': founder,
            'all_phones': phones,
            'all_emails': emails
        }

    @staticmethod
    def clean_text(html: str) -> str:
        """
        Clean HTML and extract readable text

        Args:
            html: HTML content

        Returns:
            Cleaned text content
        """
        # Remove script and style elements
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)

        # Decode HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')

        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)

        return text.strip()
