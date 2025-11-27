from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
from app.services.excel_handler import ExcelHandler
from app.services.search import SearchService
from app.services.scraper import WebScraper
from app.services.sg_data_api import SGDataAPIService
from app.services.google_maps_search import GoogleMapsSearchService
import asyncio
import logging
import json
import uuid
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
        logger.info("Initializing search, scraper, API, and Google Maps services")
        search_service = SearchService()
        scraper = WebScraper()
        api_service = SGDataAPIService()
        maps_service = GoogleMapsSearchService()

        # Enrich companies
        logger.info(f"Starting enrichment process for {len(companies)} companies")
        enriched_companies = await enrich_company_data(
            companies,
            search_service,
            scraper,
            api_service,
            maps_service
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
    api_service: SGDataAPIService,
    maps_service: GoogleMapsSearchService = None
) -> List[Dict]:
    """
    Enrich company data with contact information using Google Maps as primary source.

    NEW FLOW:
    1. Google Maps search (primary) - uses company name + address/postal code
    2. Web search + scraping (fallback) - if Maps fails
    3. API fallback (last resort)

    Args:
        companies: List of company dictionaries
        search_service: Search service instance
        scraper: Web scraper instance
        api_service: Singapore data API service instance
        maps_service: Google Maps search service instance

    Returns:
        List of enriched company dictionaries
    """
    enriched = []

    for idx, company in enumerate(companies, 1):
        try:
            enriched_company = await enrich_single_company(
                company,
                search_service,
                scraper,
                api_service,
                idx - 1,  # 0-based index
                len(companies),
                maps_service
            )
            enriched.append(enriched_company)

        except Exception as e:
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


@router.post("/enrich-stream")
async def enrich_companies_stream(file: UploadFile = File(...)):
    """
    Upload Excel file and enrich company data with streaming progress updates.
    Returns Server-Sent Events (SSE) stream with progress for each company.

    Event types:
    - session_start: Processing started, includes total count
    - company_processed: Single company completed, includes full data
    - complete: All processing finished
    - error: An error occurred

    Args:
        file: Excel file containing company information

    Returns:
        SSE stream with progress events
    """
    # Validate file type
    if not excel_handler.validate_excel_file(file.filename, file.content_type):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload an Excel file (.xlsx or .xls)"
        )

    # Read file content
    content = await file.read()

    # Parse Excel file
    try:
        companies = excel_handler.parse_excel(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not companies:
        raise HTTPException(
            status_code=400,
            detail="No valid company data found in the Excel file"
        )

    session_id = str(uuid.uuid4())
    original_filename = file.filename

    async def event_generator():
        # Initialize services
        logger.info(f"SSE stream starting for session {session_id}, {len(companies)} companies")
        search_service = SearchService()
        scraper = WebScraper()
        api_service = SGDataAPIService()
        maps_service = GoogleMapsSearchService()
        logger.info("All services initialized")

        try:
            # Yield session start event IMMEDIATELY
            logger.info(f"Sending session_start event for {len(companies)} companies")
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": "session_start",
                    "session_id": session_id,
                    "total_companies": len(companies),
                    "original_filename": original_filename
                })
            }
            logger.info("session_start event sent")

            # Process each company and yield progress
            for idx, company in enumerate(companies):
                try:
                    enriched = await enrich_single_company(
                        company,
                        search_service,
                        scraper,
                        api_service,
                        idx,
                        len(companies),
                        maps_service
                    )

                    yield {
                        "event": "message",
                        "data": json.dumps({
                            "type": "company_processed",
                            "index": idx,
                            "total": len(companies),
                            "data": enriched
                        })
                    }

                except Exception as e:
                    logger.error(f"Error processing company {company['name']}: {str(e)}")
                    # Yield error data for this company but continue processing
                    yield {
                        "event": "message",
                        "data": json.dumps({
                            "type": "company_processed",
                            "index": idx,
                            "total": len(companies),
                            "data": {
                                "name": company["name"],
                                "uen": company["uen"],
                                "address": company["address"],
                                "phone_1": "",
                                "phone_2": "",
                                "phone_3": "",
                                "email": "",
                                "website": "",
                                "status": f"Error: {str(e)}"
                            }
                        })
                    }

                # Small delay between companies
                await asyncio.sleep(0.5)

            # Yield completion event
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": "complete",
                    "session_id": session_id
                })
            }

        finally:
            # Clean up scraper
            await scraper.close()

    return EventSourceResponse(
        event_generator(),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"  # Disable nginx buffering on Render
        }
    )


async def enrich_single_company(
    company: Dict,
    search_service: SearchService,
    scraper: WebScraper,
    api_service: SGDataAPIService,
    idx: int,
    total: int,
    maps_service: GoogleMapsSearchService = None
) -> Dict:
    """
    Enrich a single company with contact information.

    NEW FLOW (Google Maps Primary):
    1. Search Google Maps using company name + address/postal code
    2. Get phone and website directly from Maps result
    3. If website found, scrape it for email only
    4. Fallback to web search if Maps fails

    Args:
        company: Company dictionary with name, uen, address
        search_service: Search service instance
        scraper: Web scraper instance
        api_service: Singapore data API service instance
        idx: Current company index (0-based)
        total: Total number of companies
        maps_service: Google Maps search service instance

    Returns:
        Enriched company dictionary
    """
    logger.info(f"Processing company {idx + 1}/{total}: {company['name']}")

    phone = None
    email = None
    website = None
    all_phones = []
    status_parts = []

    # ============================================
    # STEP 1: Google Maps Search (PRIMARY METHOD)
    # ============================================
    if maps_service:
        logger.info(f"Step 1: Searching Google Maps for {company['name']}")
        maps_result = await maps_service.search_business(
            company['name'],
            company['address'],
            company['uen']
        )

        if maps_result:
            maps_phone = maps_result.get('phone')
            maps_website = maps_result.get('website')
            match_score = maps_result.get('match_score', 0)

            logger.info(f"Google Maps result: Phone={maps_phone}, Website={maps_website}, Score={match_score}")

            if maps_phone:
                phone = maps_phone
                all_phones.append(maps_phone)
                status_parts.append('phone from Google Maps')

            if maps_website:
                website = maps_website

                # ============================================
                # STEP 2: Scrape Website for Email
                # ============================================
                logger.info(f"Step 2: Scraping {maps_website} for email")
                scraped_email = await scraper.scrape_email_only(maps_website)

                if scraped_email:
                    email = scraped_email
                    status_parts.append('email from website')
                    logger.info(f"Found email: {email}")
                else:
                    logger.info(f"No email found on {maps_website}")

            # If we have phone from Maps, consider it a success even without email
            if phone:
                if not email:
                    status_parts.append('no email found')

    # ============================================
    # STEP 3: Fallback to Web Search if needed
    # ============================================
    if not phone and not website:
        logger.info(f"Step 3: Fallback to web search for {company['name']}")

        websites = await search_service.search_company_websites(
            company['name'],
            company['uen'],
            company['address']
        )

        if websites:
            logger.info(f"Found {len(websites)} websites via web search")

            # Scrape websites until we have phone + email
            all_contacts = []
            successful_websites = []
            blocked_count = 0
            have_phone = bool(phone)
            have_email = bool(email)

            for website_idx, site_url in enumerate(websites, 1):
                if have_phone and have_email:
                    break

                logger.info(f"Scraping website {website_idx}/{len(websites)}: {site_url}")
                contacts = await scraper.scrape_company_contacts(site_url)

                if contacts.get('blocked'):
                    blocked_count += 1
                    continue

                got_phone = bool(contacts.get('phone') or contacts.get('all_phones'))
                got_email = bool(contacts.get('email') or contacts.get('all_emails'))

                if got_phone or got_email:
                    all_contacts.append(contacts)
                    successful_websites.append(site_url)

                    if got_phone and not have_phone:
                        have_phone = True
                    if got_email and not have_email:
                        have_email = True

                if not (have_phone and have_email):
                    await asyncio.sleep(0.5)

            # Aggregate results from web scraping
            aggregated = _aggregate_contacts(all_contacts)

            if not phone and aggregated.get('phone'):
                phone = aggregated['phone']
                status_parts.append('phone from web search')

            if not email and aggregated.get('email'):
                email = aggregated['email']
                status_parts.append('email from web search')

            # Collect all phones
            for p in aggregated.get('all_phones', []):
                if p and p not in all_phones:
                    all_phones.append(p)

            # Set website from successful scrapes
            if not website and successful_websites:
                website = '\n'.join(successful_websites)

            # Update status for blocked sites
            if blocked_count > 0:
                status_parts.append(f'{blocked_count} sites blocked')

    # ============================================
    # STEP 4: API Fallback (last resort)
    # ============================================
    if not phone and not email:
        logger.info(f"Step 4: API fallback for {company['name']}")
        api_result = await api_service.search_company(company['name'], company['uen'])

        if api_result:
            if api_result.get('phone') and not phone:
                phone = api_result['phone']
                if phone not in all_phones:
                    all_phones.insert(0, phone)
                status_parts.append('phone from API')

            if api_result.get('email') and not email:
                email = api_result['email']
                status_parts.append('email from API')

            if not website and api_result.get('registry_url'):
                website = api_result['registry_url']

    # ============================================
    # BUILD FINAL RESULT
    # ============================================
    has_data = bool(phone or email)

    if has_data:
        status = f"Success ({', '.join(status_parts)})" if status_parts else "Success"
    else:
        status = "No contact data found"

    # Ensure phone is in all_phones
    if phone and phone not in all_phones:
        all_phones.insert(0, phone)

    return {
        'name': company['name'],
        'uen': company['uen'],
        'address': company['address'],
        'phone_1': all_phones[0] if len(all_phones) > 0 else '',
        'phone_2': all_phones[1] if len(all_phones) > 1 else '',
        'phone_3': all_phones[2] if len(all_phones) > 2 else '',
        'email': email or '',
        'website': website or '',
        'status': status
    }
