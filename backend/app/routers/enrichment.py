from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from app.services.excel_handler import ExcelHandler
from app.services.search import SearchService
from app.services.scraper import WebScraper
import asyncio
from typing import List, Dict

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

        # Initialize services
        search_service = SearchService()
        scraper = WebScraper()

        # Enrich companies
        enriched_companies = await enrich_company_data(
            companies,
            search_service,
            scraper
        )

        # Close scraper
        await scraper.close()

        # Create enriched Excel file
        enriched_file = excel_handler.create_enriched_excel(enriched_companies)

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

    for company in companies:
        try:
            # Search for company website
            website = await search_service.search_company_website(
                company['name'],
                company['uen'],
                company['address']
            )

            if website:
                # Scrape contact information
                contacts = await scraper.scrape_company_contacts(website)

                enriched.append({
                    'name': company['name'],
                    'uen': company['uen'],
                    'address': company['address'],
                    'phone': contacts.get('phone', ''),
                    'email': contacts.get('email', ''),
                    'founder': contacts.get('founder', ''),
                    'website': website,
                    'status': 'Success'
                })
            else:
                # Website not found
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

    return enriched

@router.get("/status")
async def get_status():
    """Check API status"""
    return {
        "status": "online",
        "message": "Company enrichment service is running"
    }
