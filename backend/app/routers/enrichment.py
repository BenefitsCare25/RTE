from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from app.services.excel_handler import ExcelHandler
from app.services.search import SearchService
from app.services.scraper import WebScraper
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
        logger.info("Initializing search and scraper services")
        search_service = SearchService()
        scraper = WebScraper()

        # Enrich companies
        logger.info(f"Starting enrichment process for {len(companies)} companies")
        enriched_companies = await enrich_company_data(
            companies,
            search_service,
            scraper
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
    scraper: WebScraper
) -> List[Dict]:
    """
    Enrich company data with contact information

    Args:
        companies: List of company dictionaries
        search_service: Search service instance
        scraper: Web scraper instance

    Returns:
        List of enriched company dictionaries
    """
    enriched = []

    for idx, company in enumerate(companies, 1):
        try:
            logger.info(f"Processing company {idx}/{len(companies)}: {company['name']}")

            # Search for company website
            website = await search_service.search_company_website(
                company['name'],
                company['uen'],
                company['address']
            )

            if website:
                logger.info(f"Website found for {company['name']}: {website}")

                # Check if this is SGPBusiness (might be blocked by Cloudflare)
                is_sgpbusiness = 'sgpbusiness.com' in website.lower()

                # Scrape contact information
                contacts = await scraper.scrape_company_contacts(website)

                logger.info(f"Scraping results - Phone: {contacts.get('phone', 'N/A')}, Email: {contacts.get('email', 'N/A')}, Founder: {contacts.get('founder', 'N/A')}")

                # If SGPBusiness returned no data (likely blocked), try API fallback
                if is_sgpbusiness and not any([contacts.get('phone'), contacts.get('email'), contacts.get('founder')]):
                    logger.warning(f"SGPBusiness blocked for {company['name']}, trying API fallback...")
                    # Force API search by temporarily disabling sgpbusiness
                    alt_website = await search_service.search_with_api_fallback(
                        company['name'],
                        company['uen'],
                        company['address']
                    )

                    if alt_website and alt_website != website:
                        logger.info(f"Found alternative website via API: {alt_website}")
                        contacts = await scraper.scrape_company_contacts(alt_website)
                        website = alt_website
                        logger.info(f"API fallback results - Phone: {contacts.get('phone', 'N/A')}, Email: {contacts.get('email', 'N/A')}")

                enriched.append({
                    'name': company['name'],
                    'uen': company['uen'],
                    'address': company['address'],
                    'phone': contacts.get('phone', ''),
                    'email': contacts.get('email', ''),
                    'founder': contacts.get('founder', ''),
                    'website': website,
                    'status': 'Success' if any([contacts.get('phone'), contacts.get('email')]) else 'No contact data found'
                })
            else:
                # Website not found
                logger.warning(f"Website not found for {company['name']}")
                enriched.append({
                    'name': company['name'],
                    'uen': company['uen'],
                    'address': company['address'],
                    'phone': '',
                    'email': '',
                    'founder': '',
                    'website': '',
                    'status': 'Website not found'
                })

        except Exception as e:
            # Error during enrichment
            logger.error(f"Error enriching {company['name']}: {str(e)}", exc_info=True)
            enriched.append({
                'name': company['name'],
                'uen': company['uen'],
                'address': company['address'],
                'phone': '',
                'email': '',
                'founder': '',
                'website': '',
                'status': f'Error: {str(e)}'
            })

        # Small delay to avoid rate limiting
        await asyncio.sleep(0.5)

    logger.info(f"Enrichment complete. Processed {len(enriched)} companies")
    return enriched

@router.get("/status")
async def get_status():
    """Check API status"""
    return {
        "status": "online",
        "message": "Company enrichment service is running"
    }
