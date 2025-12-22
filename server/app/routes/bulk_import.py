from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import PlainTextResponse

from ..database import get_connection
from ..models.bulk_import import BulkImportResult
from ..services.bulk_importer import (
    BulkImporter,
    COMPANY_CSV_TEMPLATE,
    POSITION_CSV_TEMPLATE,
)

router = APIRouter()
importer = BulkImporter()


@router.post("/companies", response_model=BulkImportResult)
async def bulk_import_companies(file: UploadFile = File(...)):
    """
    Bulk import companies from CSV or JSON file.

    CSV format:
    ```
    name,industry,size
    Acme Corp,Technology,startup
    ```

    JSON format:
    ```json
    [
        {"name": "Acme Corp", "industry": "Technology", "size": "startup"}
    ]
    ```
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    if not (file.filename.endswith(".csv") or file.filename.endswith(".json") or file.filename.endswith(".pdf")):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Use .csv, .json, or .pdf",
        )

    try:
        contents = await file.read()
        rows = importer.parse_file(contents, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")

    if not rows:
        raise HTTPException(status_code=400, detail="File is empty or has no data rows")

    async with get_connection() as conn:
        result = await importer.import_companies(rows, conn)

    return result


@router.post("/positions", response_model=BulkImportResult)
async def bulk_import_positions(file: UploadFile = File(...)):
    """
    Bulk import positions from CSV or JSON file.

    CSV format (comma-separated skills):
    ```
    company_name,title,salary_min,salary_max,salary_currency,location,employment_type,required_skills,preferred_skills,experience_level,department,remote_policy,visa_sponsorship
    Acme Corp,Software Engineer,80000,120000,USD,"San Francisco, CA",full-time,"Python,JavaScript,SQL","React,AWS",mid,Engineering,hybrid,false
    ```

    JSON format:
    ```json
    [
        {
            "company_name": "Acme Corp",
            "title": "Software Engineer",
            "salary_min": 80000,
            "salary_max": 120000,
            "required_skills": "Python,JavaScript,SQL",
            "experience_level": "mid"
        }
    ]
    ```

    Note: Company must exist before importing positions.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    if not (file.filename.endswith(".csv") or file.filename.endswith(".json") or file.filename.endswith(".pdf")):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Use .csv, .json, or .pdf",
        )

    try:
        contents = await file.read()
        rows = importer.parse_file(contents, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")

    if not rows:
        raise HTTPException(status_code=400, detail="File is empty or has no data rows")

    async with get_connection() as conn:
        result = await importer.import_positions(rows, conn)

    return result


@router.get("/templates/companies", response_class=PlainTextResponse)
async def download_company_template():
    """Download CSV template for company bulk import."""
    return PlainTextResponse(
        content=COMPANY_CSV_TEMPLATE,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=companies_template.csv"},
    )


@router.get("/templates/positions", response_class=PlainTextResponse)
async def download_position_template():
    """Download CSV template for position bulk import."""
    return PlainTextResponse(
        content=POSITION_CSV_TEMPLATE,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=positions_template.csv"},
    )
