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
    Scrapes multiple websites per company to maximize data extraction success

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

            # Search for company websites (returns list of up to 5 URLs)
            websites = await search_service.search_company_websites(
                company['name'],
                company['uen'],
                company['address']
            )

            if websites:
                logger.info(f"Found {len(websites)} websites for {company['name']}, attempting to scrape all...")

                # Scrape all websites and aggregate results
                all_contacts = []
                successful_websites = []

                for website_idx, website in enumerate(websites, 1):
                    logger.info(f"Scraping website {website_idx}/{len(websites)}: {website}")

                    contacts = await scraper.scrape_company_contacts(website)

                    # Check if we got any useful data from this website
                    has_data = any([contacts.get('phone'), contacts.get('email'), contacts.get('founder')])

                    if has_data:
                        logger.info(f"✓ Website {website_idx} provided data - Phone: {contacts.get('phone', 'N/A')}, Email: {contacts.get('email', 'N/A')}, Founder: {contacts.get('founder', 'N/A')}")
                        all_contacts.append(contacts)
                        successful_websites.append(website)
                    else:
                        logger.warning(f"✗ Website {website_idx} returned no data")

                    # Small delay between scraping attempts
                    await asyncio.sleep(0.5)

                # Aggregate results from all successful sources
                aggregated = _aggregate_contacts(all_contacts)

                logger.info(f"Aggregation complete - Final results: Phone: {aggregated.get('phone', 'N/A')}, Email: {aggregated.get('email', 'N/A')}, Founder: {aggregated.get('founder', 'N/A')}")

                # Determine status and primary website
                has_contact_info = any([aggregated.get('phone'), aggregated.get('email')])
                primary_website = successful_websites[0] if successful_websites else websites[0]

                if has_contact_info:
                    status = f'Success (from {len(successful_websites)}/{len(websites)} websites)'
                else:
                    status = f'Scraped {len(websites)} websites but no contact data found'

                enriched.append({
                    'name': company['name'],
                    'uen': company['uen'],
                    'address': company['address'],
                    'phone': aggregated.get('phone', ''),
                    'email': aggregated.get('email', ''),
                    'founder': aggregated.get('founder', ''),
                    'website': primary_website,
                    'status': status
                })
            else:
                # No websites found
                logger.warning(f"No websites found for {company['name']}")
                enriched.append({
                    'name': company['name'],
                    'uen': company['uen'],
                    'address': company['address'],
                    'phone': '',
                    'email': '',
                    'founder': '',
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


def _aggregate_contacts(all_contacts: List[Dict]) -> Dict:
    """
    Aggregate contact information from multiple sources
    Takes the first valid value found for each field

    Args:
        all_contacts: List of contact dictionaries from different websites

    Returns:
        Aggregated contact dictionary with best available data
    """
    aggregated = {
        'phone': None,
        'email': None,
        'founder': None
    }

    # Collect first valid value for each field
    for contacts in all_contacts:
        if not aggregated['phone'] and contacts.get('phone'):
            aggregated['phone'] = contacts['phone']

        if not aggregated['email'] and contacts.get('email'):
            aggregated['email'] = contacts['email']

        if not aggregated['founder'] and contacts.get('founder'):
            aggregated['founder'] = contacts['founder']

    return aggregated

@router.get("/status")
async def get_status():
    """Check API status"""
    return {
        "status": "online",
        "message": "Company enrichment service is running"
    }
