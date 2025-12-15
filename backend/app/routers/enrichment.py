from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
from app.services.excel_handler import ExcelHandler
from app.services.search import SearchService
from app.services.scraper import WebScraper
from app.services.sg_data_api import SGDataAPIService
from app.services.google_maps_search import GoogleMapsSearchService
from app.services.linkedin_search import LinkedInSearchService
import asyncio
import logging
import json
import uuid
from typing import List, Dict

logger = logging.getLogger(__name__)

# Maximum number of websites to scrape per company (to save time and API calls)
MAX_WEBSITES_TO_SCRAPE = 2

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
        logger.info("Initializing search, scraper, API, Google Maps, and LinkedIn services")
        search_service = SearchService()
        scraper = WebScraper()
        api_service = SGDataAPIService()
        maps_service = GoogleMapsSearchService()
        linkedin_service = LinkedInSearchService()

        # Enrich companies
        logger.info(f"Starting enrichment process for {len(companies)} companies")
        enriched_companies = await enrich_company_data(
            companies,
            search_service,
            scraper,
            api_service,
            maps_service,
            linkedin_service
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
    maps_service: GoogleMapsSearchService = None,
    linkedin_service: LinkedInSearchService = None
) -> List[Dict]:
    """
    Enrich company data with contact information using Google Maps only.

    WORKFLOW:
    1. Google Maps search - uses company name + address/postal code
    2. If no website from Google Maps → SKIP (only record phone if available)
    3. If website found → scrape for email only (phone already from Google Maps)
    4. LinkedIn decision maker search

    Args:
        companies: List of company dictionaries
        search_service: Search service instance
        scraper: Web scraper instance
        api_service: Singapore data API service instance
        maps_service: Google Maps search service instance
        linkedin_service: LinkedIn search service instance

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
                maps_service,
                linkedin_service
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
                'discovered_urls': '',
                'dm1_name': '',
                'dm1_title': '',
                'dm1_linkedin': '',
                'dm2_name': '',
                'dm2_title': '',
                'dm2_linkedin': '',
                'dm3_name': '',
                'dm3_title': '',
                'dm3_linkedin': '',
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


@router.get("/debug/google-maps")
async def debug_google_maps_search(
    company_name: str,
    address: str = "",
    uen: str = ""
):
    """
    Debug endpoint to test Google Maps search independently.
    Returns full SerpAPI response details for analysis.

    Usage:
        GET /api/debug/google-maps?company_name=DBS%20Bank&address=Marina%20Bay
    """
    import httpx
    import os

    maps_service = GoogleMapsSearchService()

    if not maps_service.serpapi_key:
        return {
            "error": "SERPAPI_KEY not configured",
            "serpapi_key_set": False
        }

    postal_code = maps_service._extract_postal_code(address)

    # Build query strategies to test
    query_strategies = []
    if postal_code:
        query_strategies.append(f'"{company_name}" Singapore {postal_code}')
    query_strategies.append(f'"{company_name}" Singapore')
    query_strategies.append(f'{company_name} Singapore')
    query_strategies.append(company_name)

    debug_results = []

    for query in query_strategies:
        try:
            params = {
                "engine": "google_maps",
                "q": query,
                "ll": maps_service.sg_coords,
                "type": "search",
                "hl": "en",
                "gl": "sg",
                "api_key": maps_service.serpapi_key
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    "https://serpapi.com/search",
                    params=params
                )
                data = response.json()

                query_info = {
                    "query": query,
                    "status_code": response.status_code,
                    "response_keys": list(data.keys()),
                    "has_error": "error" in data,
                    "error_message": data.get("error"),
                    "local_results_count": len(data.get("local_results", [])),
                    "has_place_results": bool(data.get("place_results")),
                    "search_metadata": data.get("search_metadata", {}),
                    "search_information": data.get("search_information", {}),
                }

                # Sample first 3 results
                local = data.get("local_results", [])[:3]
                query_info["sample_results"] = [
                    {
                        "title": r.get("title"),
                        "address": r.get("address"),
                        "phone": r.get("phone"),
                        "website": r.get("website"),
                        "rating": r.get("rating"),
                    }
                    for r in local
                ]

                debug_results.append(query_info)

                # If we found results, no need to try more queries
                if local:
                    break

        except Exception as e:
            debug_results.append({
                "query": query,
                "error": str(e)
            })

    # Also run the normal search method to compare
    normal_result = await maps_service.search_business(company_name, address, uen)

    return {
        "input": {
            "company_name": company_name,
            "address": address,
            "uen": uen,
            "extracted_postal_code": postal_code,
        },
        "serpapi_key_configured": True,
        "sg_coords": maps_service.sg_coords,
        "query_attempts": debug_results,
        "final_parsed_result": normal_result
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
        linkedin_service = LinkedInSearchService()
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
                        maps_service,
                        linkedin_service
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
                                "dm1_name": "",
                                "dm1_title": "",
                                "dm1_linkedin": "",
                                "dm2_name": "",
                                "dm2_title": "",
                                "dm2_linkedin": "",
                                "dm3_name": "",
                                "dm3_title": "",
                                "dm3_linkedin": "",
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
    maps_service: GoogleMapsSearchService = None,
    linkedin_service: LinkedInSearchService = None
) -> Dict:
    """
    Enrich a single company with contact information.

    WORKFLOW:
    1. Search Google Maps using company name + address/postal code
    2. Get phone from Google Maps (if available)
    3. If Google Maps has NO website → SKIP (only record phone, move to LinkedIn)
    4. If Google Maps HAS website → scrape it for email only
    5. Search LinkedIn for decision makers (C-Suite, HR, Founders)

    Args:
        company: Company dictionary with name, uen, address
        search_service: Search service instance
        scraper: Web scraper instance
        api_service: Singapore data API service instance
        idx: Current company index (0-based)
        total: Total number of companies
        maps_service: Google Maps search service instance
        linkedin_service: LinkedIn search service instance

    Returns:
        Enriched company dictionary
    """
    logger.info(f"\n[{idx + 1}/{total}] {company['name']}")

    phone = None
    email = None
    website = None
    all_phones = []
    status_parts = []

    # ============================================
    # STEP 1: Google Maps Search (PRIMARY & ONLY METHOD)
    # ============================================
    if maps_service:
        maps_result = await maps_service.search_business(
            company['name'],
            company['address'],
            company['uen']
        )

        if maps_result:
            maps_phone = maps_result.get('phone')
            maps_website = maps_result.get('website')

            if maps_phone:
                phone = maps_phone
                all_phones.append(maps_phone)
                status_parts.append('phone from Google Maps')

            if maps_website:
                website = maps_website
                status_parts.append('website from Google Maps')

                # ============================================
                # STEP 2: Scrape Website for Email ONLY
                # ============================================
                scrape_result = await scraper.scrape_email_only(maps_website)
                scraped_email = scrape_result.get('email') if scrape_result else None

                if scraped_email:
                    email = scraped_email
                    status_parts.append('email from website')
                else:
                    status_parts.append('no email on website')
            else:
                # No website from Google Maps → SKIP to LinkedIn
                status_parts.append('no website from Google Maps')

    # ============================================
    # STEP 3: LinkedIn Decision Maker Search
    # ============================================
    decision_makers = []
    if linkedin_service:
        try:
            decision_makers = await linkedin_service.find_decision_makers(
                company['name'],
                max_results=3
            )

            if decision_makers:
                status_parts.append(f'{len(decision_makers)} decision makers found')
        except Exception as e:
            logger.debug(f"LinkedIn search failed: {str(e)}")

    # ============================================
    # BUILD FINAL RESULT
    # ============================================
    has_data = bool(phone or email)

    if has_data:
        status = f"Success ({', '.join(status_parts)})" if status_parts else "Success"
    else:
        status = "No contact data found - " + ', '.join(status_parts) if status_parts else "No contact data found"

    # Ensure phone is in all_phones
    if phone and phone not in all_phones:
        all_phones.insert(0, phone)

    # Log final result summary
    logger.info(f"  Result: Phone={phone or 'None'}, Email={email or 'None'}, DMs={len(decision_makers)}")

    return {
        'name': company['name'],
        'uen': company['uen'],
        'address': company['address'],
        'phone_1': all_phones[0] if len(all_phones) > 0 else '',
        'phone_2': all_phones[1] if len(all_phones) > 1 else '',
        'phone_3': all_phones[2] if len(all_phones) > 2 else '',
        'email': email or '',
        'website': website or '',
        'discovered_urls': '',  # No longer using web search fallback
        # Decision maker fields
        'dm1_name': decision_makers[0]['name'] if len(decision_makers) > 0 else '',
        'dm1_title': decision_makers[0]['title'] if len(decision_makers) > 0 else '',
        'dm1_linkedin': decision_makers[0]['linkedin_url'] if len(decision_makers) > 0 else '',
        'dm2_name': decision_makers[1]['name'] if len(decision_makers) > 1 else '',
        'dm2_title': decision_makers[1]['title'] if len(decision_makers) > 1 else '',
        'dm2_linkedin': decision_makers[1]['linkedin_url'] if len(decision_makers) > 1 else '',
        'dm3_name': decision_makers[2]['name'] if len(decision_makers) > 2 else '',
        'dm3_title': decision_makers[2]['title'] if len(decision_makers) > 2 else '',
        'dm3_linkedin': decision_makers[2]['linkedin_url'] if len(decision_makers) > 2 else '',
        'status': status
    }
