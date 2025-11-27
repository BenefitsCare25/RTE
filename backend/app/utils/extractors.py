import re
from typing import List, Optional, Tuple

class ContactExtractor:
    """Utility class for extracting contact information from text"""

    # Singapore phone number patterns (valid prefixes: 6=landline, 8/9=mobile)
    # Note: 3xxx numbers are VoIP/virtual numbers, not standard business phones
    PHONE_PATTERNS = [
        # +65 XXXX XXXX or +65-XXXX-XXXX or +65XXXXXXXX
        r'\+65[\s-]?[689]\d{3}[\s-]?\d{4}',
        # 65 XXXX XXXX or 65-XXXX-XXXX or 65XXXXXXXX
        r'65[\s-]?[689]\d{3}[\s-]?\d{4}',
        # XXXX XXXX (8 digits starting with 6, 8, 9)
        r'\b[689]\d{3}[\s-]?\d{4}\b',
    ]

    # Email pattern
    EMAIL_PATTERN = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'

    # Common email domains to exclude (generic/non-business)
    EXCLUDED_EMAIL_DOMAINS = [
        'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
        'example.com', 'test.com', 'domain.com'
    ]

    # Directory/aggregator site emails to exclude (these are the directory's contact, not the company's)
    DIRECTORY_EMAIL_DOMAINS = [
        'sgpbusiness.com', 'sgpgrid.com', 'singaporedirectory.com',
        'yellowpages.com.sg', 'streetdirectory.com', 'sgpcompanies.com',
        'bizfile.gov.sg', 'acra.gov.sg'
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
                elif len(cleaned) == 8 and cleaned[0] in '689':
                    phone_numbers.add('+65' + cleaned)

        # Filter and validate all phone numbers
        valid_phones = []
        for phone in phone_numbers:
            if ContactExtractor.is_valid_sg_phone(phone):
                valid_phones.append(phone)

        # Sort by preference: landlines (6xxx) first, then mobile (8/9)
        # Landlines are more likely to be business numbers
        valid_phones.sort(key=lambda p: (0 if p[3] == '6' else 1, p))

        return valid_phones

    @staticmethod
    def is_valid_sg_phone(phone: str) -> bool:
        """
        Validate if a phone number is a valid Singapore phone number

        Args:
            phone: Phone number string (should be in +65XXXXXXXX format)

        Returns:
            True if valid SG phone number (starts with 6, 8, or 9)
        """
        if not phone:
            return False

        # Remove all non-digit characters except +
        cleaned = re.sub(r'[^\d+]', '', phone)

        # Must start with +65
        if not cleaned.startswith('+65'):
            return False

        # Extract the 8-digit local number
        local_number = cleaned[3:]

        # Must be exactly 8 digits
        if len(local_number) != 8:
            return False

        # First digit must be 6, 8, or 9 (not 3 - VoIP/virtual numbers)
        if local_number[0] not in '689':
            return False

        return True

    @staticmethod
    def extract_emails(text: str, prefer_business: bool = True) -> List[str]:
        """
        Extract email addresses from text

        Args:
            text: Text content to search
            prefer_business: If True, prioritize business emails over generic ones

        Returns:
            List of found email addresses (excludes directory site emails)
        """
        if not text:
            return []

        matches = re.findall(ContactExtractor.EMAIL_PATTERN, text, re.IGNORECASE)
        emails = list(set(matches))

        # Filter out directory/aggregator site emails entirely
        # These are never the company's real email
        filtered_emails = []
        for email in emails:
            domain = email.split('@')[1].lower()
            if domain not in ContactExtractor.DIRECTORY_EMAIL_DOMAINS:
                filtered_emails.append(email)

        emails = filtered_emails

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
