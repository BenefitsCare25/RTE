from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from app.services.excel_handler import ExcelHandler
from app.services.search import SearchService
from app.services.scraper import WebScraper
from app.services.sg_data_api import SGDataAPIService
import asyncio
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

router = APIRouter()
excel_handler = ExcelHandler()

@router.post("/enrich")
async def enrich_companies(file: UploadFile = File(...)):
    """
    Upload Excel file and enrich company data with contact information

    Args:
        file: Excel file containing company information

    Returns:
        Enriched Excel file with contact details
    """
    try:
        logger.info(f"Received enrichment request for file: {file.filename}")

        # Validate file type
        if not excel_handler.validate_excel_file(file.filename, file.content_type):
            logger.error(f"Invalid file type: {file.filename}, content_type: {file.content_type}")
            raise HTTPException(
                status_code=400,
                detail="Invalid file type. Please upload an Excel file (.xlsx or .xls)"
            )

        # Read file content
        content = await file.read()
        logger.info(f"File read successfully, size: {len(content)} bytes")

        # Parse Excel file
        try:
            companies = excel_handler.parse_excel(content)
            logger.info(f"Parsed {len(companies)} companies from Excel file")
        except ValueError as e:
            logger.error(f"Error parsing Excel file: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))

        if not companies:
            logger.warning("No valid company data found in Excel file")
            raise HTTPException(
                status_code=400,
                detail="No valid company data found in the Excel file"
            )

        # Initialize services
        logger.info("Initializing search, scraper, and API services")
        search_service = SearchService()
        scraper = WebScraper()
        api_service = SGDataAPIService()

        # Enrich companies
        logger.info(f"Starting enrichment process for {len(companies)} companies")
        enriched_companies = await enrich_company_data(
            companies,
            search_service,
            scraper,
            api_service
        )

        # Close scraper
        await scraper.close()
        logger.info("Scraper closed")

        # Create enriched Excel file
        enriched_file = excel_handler.create_enriched_excel(enriched_companies)
        logger.info(f"Enrichment completed. Returning file: enriched_{file.filename}")

        # Return file as download
        return StreamingResponse(
            enriched_file,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=enriched_{file.filename}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing file: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error processing file: {str(e)}"
        )

async def enrich_company_data(
    companies: List[Dict],
    search_service: SearchService,
    scraper: WebScraper,
    api_service: SGDataAPIService
) -> List[Dict]:
    """
    Enrich company data with contact information
    Scrapes multiple websites per company to maximize data extraction success
    Falls back to APIs when scraping is blocked

    Args:
        companies: List of company dictionaries
        search_service: Search service instance
        scraper: Web scraper instance
        api_service: Singapore data API service instance

    Returns:
        List of enriched company dictionaries
    """
    enriched = []

    for idx, company in enumerate(companies, 1):
        try:
            logger.info(f"Processing company {idx}/{len(companies)}: {company['name']}")

            # Search for company websites (returns list of up to 5 URLs)
            websites = await search_service.search_company_websites(
                company['name'],
                company['uen'],
                company['address']
            )

            if websites:
                logger.info(f"Found {len(websites)} websites for {company['name']}, will scrape until data found...")

                # Scrape websites in priority order, stop early when we have complete data
                all_contacts = []
                successful_websites = []
                blocked_count = 0
                have_phone = False
                have_email = False

                for website_idx, website in enumerate(websites, 1):
                    # Early exit: stop if we already have both phone and email
                    if have_phone and have_email:
                        logger.info(f"✓ Already have phone + email, skipping remaining {len(websites) - website_idx + 1} websites")
                        break

                    logger.info(f"Scraping website {website_idx}/{len(websites)}: {website}")

                    contacts = await scraper.scrape_company_contacts(website)

                    # Check if blocked by Cloudflare/bot protection
                    if contacts.get('blocked'):
                        blocked_count += 1
                        logger.warning(f"✗ Website {website_idx} blocked by protection")
                        continue

                    # Check if we got any useful data from this website (phone or email)
                    got_phone = bool(contacts.get('phone') or contacts.get('all_phones'))
                    got_email = bool(contacts.get('email') or contacts.get('all_emails'))
                    has_data = got_phone or got_email

                    if has_data:
                        logger.info(f"✓ Website {website_idx} provided data - Phone: {contacts.get('phone', 'N/A')}, Email: {contacts.get('email', 'N/A')}, All phones: {contacts.get('all_phones', [])}")
                        all_contacts.append(contacts)
                        successful_websites.append(website)

                        # Track what we've found
                        if got_phone:
                            have_phone = True
                        if got_email:
                            have_email = True
                    else:
                        logger.warning(f"✗ Website {website_idx} returned no data")

                    # Small delay between scraping attempts (only if continuing)
                    if not (have_phone and have_email):
                        await asyncio.sleep(0.5)

                # Aggregate results from all successful sources
                aggregated = _aggregate_contacts(all_contacts)

                # If all sites were blocked or no data found, try API fallback
                all_blocked = blocked_count == len(websites)
                no_data = not any([aggregated.get('phone'), aggregated.get('email')])

                if all_blocked or no_data:
                    logger.info(f"Scraping {'blocked' if all_blocked else 'returned no data'}, trying API fallback...")
                    api_result = await api_service.search_company(company['name'], company['uen'])
                    if api_result:
                        logger.info(f"API fallback found data from: {api_result.get('source')}")
                        # Merge API data
                        if api_result.get('phone') and not aggregated.get('phone'):
                            aggregated['phone'] = api_result['phone']
                            if aggregated['phone'] not in aggregated.get('all_phones', []):
                                aggregated.setdefault('all_phones', []).insert(0, aggregated['phone'])
                        if api_result.get('email') and not aggregated.get('email'):
                            aggregated['email'] = api_result['email']

                logger.info(f"Aggregation complete - Final results: Phone: {aggregated.get('phone', 'N/A')}, Email: {aggregated.get('email', 'N/A')}, All phones: {aggregated.get('all_phones', [])}")

                # Determine status and primary website
                has_contact_info = any([aggregated.get('phone'), aggregated.get('email')])
                primary_website = successful_websites[0] if successful_websites else websites[0]

                if has_contact_info:
                    if blocked_count > 0:
                        status = f'Success (from {len(successful_websites)}/{len(websites)} websites, {blocked_count} blocked)'
                    else:
                        status = f'Success (from {len(successful_websites)}/{len(websites)} websites)'
                else:
                    if all_blocked:
                        status = f'All {len(websites)} websites blocked by Cloudflare'
                    else:
                        status = f'Scraped {len(websites)} websites but no contact data found'

                # Build company record with multiple phone columns
                # Join all successful websites with newlines for Excel display
                websites_text = '\n'.join(successful_websites) if successful_websites else websites[0] if websites else ''

                company_record = {
                    'name': company['name'],
                    'uen': company['uen'],
                    'address': company['address'],
                    'email': aggregated.get('email', ''),
                    'website': websites_text,
                    'status': status
                }

                # Add individual phone columns (Phone 1, Phone 2, Phone 3)
                all_phones = aggregated.get('all_phones', [])
                for i in range(3):  # Support up to 3 phone numbers
                    phone_key = f'phone_{i+1}'
                    company_record[phone_key] = all_phones[i] if i < len(all_phones) else ''

                enriched.append(company_record)
            else:
                # No websites found - try API as primary source
                logger.warning(f"No websites found for {company['name']}, trying API...")
                api_result = await api_service.search_company(company['name'], company['uen'])

                if api_result and (api_result.get('phone') or api_result.get('email')):
                    logger.info(f"API found data for {company['name']}")
                    enriched.append({
                        'name': company['name'],
                        'uen': company['uen'],
                        'address': company['address'],
                        'phone_1': api_result.get('phone', ''),
                        'phone_2': '',
                        'phone_3': '',
                        'email': api_result.get('email', ''),
                        'website': api_result.get('registry_url', ''),
                        'status': f"Data from API ({api_result.get('source', 'unknown')})"
                    })
                else:
                    enriched.append({
                        'name': company['name'],
                        'uen': company['uen'],
                        'address': company['address'],
                        'phone_1': '',
                        'phone_2': '',
                        'phone_3': '',
                        'email': '',
                        'website': '',
                        'status': 'No websites found'
                    })

        except Exception as e:
            # Error during enrichment
            logger.error(f"Error enriching {company['name']}: {str(e)}", exc_info=True)
            enriched.append({
                'name': company['name'],
                'uen': company['uen'],
                'address': company['address'],
                'phone_1': '',
                'phone_2': '',
                'phone_3': '',
                'email': '',
                'website': '',
                'status': f'Error: {str(e)}'
            })

        # Small delay to avoid rate limiting
        await asyncio.sleep(0.5)

    logger.info(f"Enrichment complete. Processed {len(enriched)} companies")
    return enriched


def _aggregate_contacts(all_contacts: List[Dict]) -> Dict:
    """
    Aggregate contact information from multiple sources
    Collects all unique phone numbers and emails across all sources

    Args:
        all_contacts: List of contact dictionaries from different websites

    Returns:
        Aggregated contact dictionary with all phones and emails
    """
    aggregated = {
        'phone': None,
        'email': None,
        'all_phones': [],
        'all_emails': []
    }

    # Collect all unique phones and emails from all sources
    seen_phones = set()
    seen_emails = set()

    for contacts in all_contacts:
        # Collect all phones
        all_phones = contacts.get('all_phones', [])
        if contacts.get('phone') and contacts['phone'] not in all_phones:
            all_phones = [contacts['phone']] + all_phones

        for phone in all_phones:
            if phone and phone not in seen_phones:
                seen_phones.add(phone)
                aggregated['all_phones'].append(phone)

        # Collect all emails
        all_emails = contacts.get('all_emails', [])
        if contacts.get('email') and contacts['email'] not in all_emails:
            all_emails = [contacts['email']] + all_emails

        for email in all_emails:
            if email and email not in seen_emails:
                seen_emails.add(email)
                aggregated['all_emails'].append(email)

    # Set primary phone and email (first in list)
    if aggregated['all_phones']:
        aggregated['phone'] = aggregated['all_phones'][0]
    if aggregated['all_emails']:
        aggregated['email'] = aggregated['all_emails'][0]

    return aggregated

@router.get("/status")
async def get_status():
    """Check API status"""
    return {
        "status": "online",
        "message": "Company enrichment service is running"
    }
