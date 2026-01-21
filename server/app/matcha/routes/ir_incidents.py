"""IR (Incident Report) API Routes.

Incident Report management for HR departments:
- Incidents CRUD
- Document upload
- AI analysis (categorization, severity, root cause, recommendations)
- Analytics dashboard
"""

import json
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Request, Query

from ...database import get_connection
from ...core.dependencies import require_admin
from ..dependencies import require_admin_or_client
from ...config import get_settings
from ...core.services.storage import get_storage
from ..models.ir_incident import (
    IRIncidentCreate,
    IRIncidentUpdate,
    IRIncidentResponse,
    IRIncidentListResponse,
    IRDocumentResponse,
    IRDocumentUploadResponse,
    CategorizationAnalysis,
    SeverityAnalysis,
    RootCauseAnalysis,
    RecommendationsAnalysis,
    SimilarIncidentsAnalysis,
    AnalyticsSummary,
    TrendsAnalysis,
    TrendDataPoint,
    LocationAnalysis,
    LocationHotspot,
    IRAuditLogEntry,
    IRAuditLogResponse,
    Witness,
)

router = APIRouter()


# ===========================================
# Helper Functions
# ===========================================

def generate_incident_number() -> str:
    """Generate a unique incident number."""
    now = datetime.now(timezone.utc)
    random_suffix = secrets.token_hex(2).upper()
    return f"IR-{now.year}-{now.month:02d}-{random_suffix}"


async def log_audit(
    conn,
    incident_id: Optional[str],
    user_id: str,
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
):
    """Log an action to the audit trail."""
    await conn.execute(
        """
        INSERT INTO ir_audit_log (incident_id, user_id, action, entity_type, entity_id, details, ip_address)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        incident_id,
        user_id,
        action,
        entity_type,
        entity_id,
        json.dumps(details) if details else None,
        ip_address,
    )


def parse_witnesses(witnesses_json) -> list[Witness]:
    """Parse witnesses from JSONB."""
    if not witnesses_json:
        return []
    try:
        if isinstance(witnesses_json, str):
            witnesses_json = json.loads(witnesses_json)
        return [Witness(**w) for w in witnesses_json]
    except:
        return []


def row_to_response(row, document_count: int = 0) -> IRIncidentResponse:
    """Convert a database row to IRIncidentResponse."""
    return IRIncidentResponse(
        id=row["id"],
        incident_number=row["incident_number"],
        title=row["title"],
        description=row["description"],
        incident_type=row["incident_type"],
        severity=row["severity"],
        status=row["status"],
        occurred_at=row["occurred_at"],
        location=row["location"],
        reported_by_name=row["reported_by_name"],
        reported_by_email=row["reported_by_email"],
        reported_at=row["reported_at"],
        assigned_to=row["assigned_to"],
        witnesses=parse_witnesses(row.get("witnesses")),
        category_data=json.loads(row["category_data"]) if isinstance(row.get("category_data"), str) else (row.get("category_data") or {}),
        root_cause=row["root_cause"],
        corrective_actions=row["corrective_actions"],
        document_count=document_count,
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        resolved_at=row["resolved_at"],
    )


# ===========================================
# Incidents CRUD
# ===========================================

@router.post("", response_model=IRIncidentResponse)
async def create_incident(
    incident: IRIncidentCreate,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Create a new incident report."""
    incident_number = generate_incident_number()

    # Ensure occurred_at is naive UTC for TIMESTAMP column
    occurred_at = incident.occurred_at
    if occurred_at.tzinfo:
        occurred_at = occurred_at.astimezone(timezone.utc).replace(tzinfo=None)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO ir_incidents (
                incident_number, title, description, incident_type, severity,
                occurred_at, location, reported_by_name, reported_by_email,
                witnesses, category_data, created_by
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING *
            """,
            incident_number,
            incident.title,
            incident.description,
            incident.incident_type,
            incident.severity,
            occurred_at,
            incident.location,
            incident.reported_by_name,
            incident.reported_by_email,
            json.dumps([w.model_dump() for w in incident.witnesses]),
            json.dumps(incident.category_data or {}),
            str(current_user.id),
        )

        # Log audit
        await log_audit(
            conn,
            str(row["id"]),
            str(current_user.id),
            "incident_created",
            "incident",
            str(row["id"]),
            {"title": incident.title, "type": incident.incident_type},
            request.client.host if request.client else None,
        )

        return row_to_response(row, 0)


@router.get("", response_model=IRIncidentListResponse)
async def list_incidents(
    status: Optional[str] = None,
    incident_type: Optional[str] = None,
    severity: Optional[str] = None,
    location: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user=Depends(require_admin_or_client),
):
    """List incidents with filters."""
    async with get_connection() as conn:
        # Build dynamic query
        conditions = []
        params = []
        param_idx = 1

        if status:
            conditions.append(f"i.status = ${param_idx}")
            params.append(status)
            param_idx += 1

        if incident_type:
            conditions.append(f"i.incident_type = ${param_idx}")
            params.append(incident_type)
            param_idx += 1

        if severity:
            conditions.append(f"i.severity = ${param_idx}")
            params.append(severity)
            param_idx += 1

        if location:
            conditions.append(f"i.location ILIKE ${param_idx}")
            params.append(f"%{location}%")
            param_idx += 1

        if from_date:
            conditions.append(f"i.occurred_at >= ${param_idx}")
            params.append(from_date)
            param_idx += 1

        if to_date:
            conditions.append(f"i.occurred_at <= ${param_idx}")
            params.append(to_date)
            param_idx += 1

        if search:
            conditions.append(f"(i.title ILIKE ${param_idx} OR i.description ILIKE ${param_idx})")
            params.append(f"%{search}%")
            param_idx += 1

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

        # Get total count
        count_query = f"SELECT COUNT(*) FROM ir_incidents i{where_clause}"
        total = await conn.fetchval(count_query, *params)

        # Get incidents with document count
        query = f"""
            SELECT i.*, COUNT(d.id) as document_count
            FROM ir_incidents i
            LEFT JOIN ir_incident_documents d ON i.id = d.incident_id
            {where_clause}
            GROUP BY i.id
            ORDER BY i.occurred_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([limit, offset])

        rows = await conn.fetch(query, *params)

        return IRIncidentListResponse(
            incidents=[row_to_response(row, row["document_count"]) for row in rows],
            total=total,
        )


@router.get("/{incident_id}", response_model=IRIncidentResponse)
async def get_incident(
    incident_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Get a single incident by ID."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT i.*, COUNT(d.id) as document_count
            FROM ir_incidents i
            LEFT JOIN ir_incident_documents d ON i.id = d.incident_id
            WHERE i.id = $1
            GROUP BY i.id
            """,
            str(incident_id),
        )

        if not row:
            raise HTTPException(status_code=404, detail="Incident not found")

        return row_to_response(row, row["document_count"])


@router.put("/{incident_id}", response_model=IRIncidentResponse)
async def update_incident(
    incident_id: UUID,
    incident: IRIncidentUpdate,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Update an incident report."""
    async with get_connection() as conn:
        # Check exists
        existing = await conn.fetchrow(
            "SELECT id, status FROM ir_incidents WHERE id = $1",
            str(incident_id),
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Incident not found")

        # Build update query dynamically
        updates = []
        params = []
        param_idx = 1
        changes = {}

        if incident.title is not None:
            updates.append(f"title = ${param_idx}")
            params.append(incident.title)
            changes["title"] = incident.title
            param_idx += 1

        if incident.description is not None:
            updates.append(f"description = ${param_idx}")
            params.append(incident.description)
            param_idx += 1

        if incident.incident_type is not None:
            updates.append(f"incident_type = ${param_idx}")
            params.append(incident.incident_type)
            changes["incident_type"] = incident.incident_type
            param_idx += 1

        if incident.severity is not None:
            updates.append(f"severity = ${param_idx}")
            params.append(incident.severity)
            changes["severity"] = incident.severity
            param_idx += 1

        if incident.status is not None:
            updates.append(f"status = ${param_idx}")
            params.append(incident.status)
            changes["status"] = incident.status
            param_idx += 1
            # Set resolved_at if status is resolved or closed
            if incident.status in ("resolved", "closed") and existing["status"] not in ("resolved", "closed"):
                updates.append(f"resolved_at = ${param_idx}")
                params.append(datetime.now(timezone.utc))
                param_idx += 1

        if incident.occurred_at is not None:
            updates.append(f"occurred_at = ${param_idx}")
            # Ensure occurred_at is naive UTC for TIMESTAMP column
            occurred_at = incident.occurred_at
            if occurred_at.tzinfo:
                occurred_at = occurred_at.astimezone(timezone.utc).replace(tzinfo=None)
            params.append(occurred_at)
            param_idx += 1

        if incident.location is not None:
            updates.append(f"location = ${param_idx}")
            params.append(incident.location)
            param_idx += 1

        if incident.assigned_to is not None:
            updates.append(f"assigned_to = ${param_idx}")
            params.append(str(incident.assigned_to))
            changes["assigned_to"] = str(incident.assigned_to)
            param_idx += 1

        if incident.witnesses is not None:
            updates.append(f"witnesses = ${param_idx}")
            params.append(json.dumps([w.model_dump() for w in incident.witnesses]))
            param_idx += 1

        if incident.category_data is not None:
            updates.append(f"category_data = ${param_idx}")
            params.append(json.dumps(incident.category_data))
            param_idx += 1

        if incident.root_cause is not None:
            updates.append(f"root_cause = ${param_idx}")
            params.append(incident.root_cause)
            param_idx += 1

        if incident.corrective_actions is not None:
            updates.append(f"corrective_actions = ${param_idx}")
            params.append(incident.corrective_actions)
            param_idx += 1

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updates.append(f"updated_at = ${param_idx}")
        params.append(datetime.now(timezone.utc))
        param_idx += 1

        params.append(str(incident_id))
        query = f"""
            UPDATE ir_incidents
            SET {", ".join(updates)}
            WHERE id = ${param_idx}
            RETURNING *
        """

        row = await conn.fetchrow(query, *params)

        # Get document count
        doc_count = await conn.fetchval(
            "SELECT COUNT(*) FROM ir_incident_documents WHERE incident_id = $1",
            str(incident_id),
        )

        # Log audit
        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "incident_updated",
            "incident",
            str(incident_id),
            changes if changes else None,
            request.client.host if request.client else None,
        )

        return row_to_response(row, doc_count)


@router.delete("/{incident_id}")
async def delete_incident(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Delete an incident and all related data."""
    async with get_connection() as conn:
        # Check exists
        row = await conn.fetchrow(
            "SELECT id, incident_number, title FROM ir_incidents WHERE id = $1",
            str(incident_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Incident not found")

        # Delete (cascade will handle documents, analysis, etc.)
        await conn.execute(
            "DELETE FROM ir_incidents WHERE id = $1",
            str(incident_id),
        )

        # Log audit
        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "incident_deleted",
            "incident",
            str(incident_id),
            {"incident_number": row["incident_number"], "title": row["title"]},
            request.client.host if request.client else None,
        )

        return {"message": "Incident deleted successfully"}


# ===========================================
# Documents
# ===========================================

@router.post("/{incident_id}/documents", response_model=IRDocumentUploadResponse)
async def upload_document(
    incident_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    document_type: str = Form("other"),
    current_user=Depends(require_admin_or_client),
):
    """Upload a document to an incident."""
    # Validate incident exists
    async with get_connection() as conn:
        incident = await conn.fetchrow(
            "SELECT id FROM ir_incidents WHERE id = $1",
            str(incident_id),
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

    # Validate document type
    valid_types = ["photo", "form", "statement", "other"]
    if document_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid document type. Must be one of: {valid_types}")

    # Validate file extension
    allowed_extensions = {".pdf", ".doc", ".docx", ".txt", ".png", ".jpg", ".jpeg", ".gif", ".csv", ".json"}
    file_ext = "." + file.filename.split(".")[-1].lower() if "." in file.filename else ""
    if file_ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"File type not allowed. Allowed: {allowed_extensions}")

    # Read file content
    content = await file.read()
    file_size = len(content)

    # Upload to storage
    storage = get_storage()
    file_path = f"ir-incidents/{incident_id}/{file.filename}"

    try:
        storage.upload_file(content, file_path, file.content_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")

    # Save to database
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO ir_incident_documents (
                incident_id, document_type, filename, file_path, mime_type, file_size, uploaded_by
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            str(incident_id),
            document_type,
            file.filename,
            file_path,
            file.content_type,
            file_size,
            str(current_user.id),
        )

        # Log audit
        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "document_uploaded",
            "document",
            str(row["id"]),
            {"filename": file.filename, "document_type": document_type},
            request.client.host if request.client else None,
        )

        return IRDocumentUploadResponse(
            document=IRDocumentResponse(
                id=row["id"],
                incident_id=row["incident_id"],
                document_type=row["document_type"],
                filename=row["filename"],
                mime_type=row["mime_type"],
                file_size=row["file_size"],
                uploaded_by=row["uploaded_by"],
                created_at=row["created_at"],
            ),
            message="Document uploaded successfully",
        )


@router.get("/{incident_id}/documents", response_model=list[IRDocumentResponse])
async def list_documents(
    incident_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """List all documents for an incident."""
    async with get_connection() as conn:
        # Verify incident exists
        incident = await conn.fetchrow(
            "SELECT id FROM ir_incidents WHERE id = $1",
            str(incident_id),
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        rows = await conn.fetch(
            """
            SELECT * FROM ir_incident_documents
            WHERE incident_id = $1
            ORDER BY created_at DESC
            """,
            str(incident_id),
        )

        return [
            IRDocumentResponse(
                id=row["id"],
                incident_id=row["incident_id"],
                document_type=row["document_type"],
                filename=row["filename"],
                mime_type=row["mime_type"],
                file_size=row["file_size"],
                uploaded_by=row["uploaded_by"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


@router.delete("/{incident_id}/documents/{document_id}")
async def delete_document(
    incident_id: UUID,
    document_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Delete a document from an incident."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id, filename, file_path FROM ir_incident_documents WHERE id = $1 AND incident_id = $2",
            str(document_id),
            str(incident_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")

        # Delete from storage
        try:
            storage = get_storage()
            storage.delete_file(row["file_path"])
        except Exception:
            pass  # Continue even if storage delete fails

        # Delete from database
        await conn.execute(
            "DELETE FROM ir_incident_documents WHERE id = $1",
            str(document_id),
        )

        # Log audit
        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "document_deleted",
            "document",
            str(document_id),
            {"filename": row["filename"]},
            request.client.host if request.client else None,
        )

        return {"message": "Document deleted successfully"}


# ===========================================
# Analytics
# ===========================================

@router.get("/analytics/summary", response_model=AnalyticsSummary)
async def get_analytics_summary(
    current_user=Depends(require_admin_or_client),
):
    """Get summary analytics for the dashboard."""
    async with get_connection() as conn:
        # Total incidents
        total = await conn.fetchval("SELECT COUNT(*) FROM ir_incidents")

        # By status
        status_rows = await conn.fetch(
            "SELECT status, COUNT(*) as count FROM ir_incidents GROUP BY status"
        )
        by_status = {row["status"]: row["count"] for row in status_rows}

        # By type
        type_rows = await conn.fetch(
            "SELECT incident_type, COUNT(*) as count FROM ir_incidents GROUP BY incident_type"
        )
        by_type = {row["incident_type"]: row["count"] for row in type_rows}

        # By severity
        severity_rows = await conn.fetch(
            "SELECT severity, COUNT(*) as count FROM ir_incidents GROUP BY severity"
        )
        by_severity = {row["severity"]: row["count"] for row in severity_rows}

        # Recent (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_count = await conn.fetchval(
            "SELECT COUNT(*) FROM ir_incidents WHERE occurred_at >= $1",
            thirty_days_ago,
        )

        # Average resolution time (days) for resolved/closed incidents
        avg_resolution = await conn.fetchval(
            """
            SELECT AVG(EXTRACT(EPOCH FROM (resolved_at - occurred_at)) / 86400)
            FROM ir_incidents
            WHERE resolved_at IS NOT NULL
            """
        )

        return AnalyticsSummary(
            total_incidents=total or 0,
            by_status=by_status,
            by_type=by_type,
            by_severity=by_severity,
            recent_count=recent_count or 0,
            avg_resolution_days=round(avg_resolution, 1) if avg_resolution else None,
        )


@router.get("/analytics/trends", response_model=TrendsAnalysis)
async def get_analytics_trends(
    period: str = Query("daily", enum=["daily", "weekly", "monthly"]),
    days: int = Query(30, ge=7, le=365),
    current_user=Depends(require_admin_or_client),
):
    """Get incident trends over time."""
    async with get_connection() as conn:
        start_date = datetime.utcnow() - timedelta(days=days)

        if period == "daily":
            date_trunc = "day"
        elif period == "weekly":
            date_trunc = "week"
        else:
            date_trunc = "month"

        rows = await conn.fetch(
            f"""
            SELECT
                DATE_TRUNC('{date_trunc}', occurred_at) as period_start,
                COUNT(*) as count,
                incident_type
            FROM ir_incidents
            WHERE occurred_at >= $1
            GROUP BY period_start, incident_type
            ORDER BY period_start
            """,
            start_date,
        )

        # Aggregate by period
        data_map = {}
        for row in rows:
            date_str = row["period_start"].strftime("%Y-%m-%d")
            if date_str not in data_map:
                data_map[date_str] = {"count": 0, "by_type": {}}
            data_map[date_str]["count"] += row["count"]
            data_map[date_str]["by_type"][row["incident_type"]] = row["count"]

        data = [
            TrendDataPoint(date=date, count=info["count"], by_type=info["by_type"])
            for date, info in sorted(data_map.items())
        ]

        return TrendsAnalysis(
            data=data,
            period=period,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=datetime.utcnow().strftime("%Y-%m-%d"),
        )


@router.get("/analytics/locations", response_model=LocationAnalysis)
async def get_analytics_locations(
    limit: int = Query(10, ge=1, le=50),
    current_user=Depends(require_admin_or_client),
):
    """Get incident hotspots by location."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                location,
                COUNT(*) as count,
                incident_type,
                AVG(CASE
                    WHEN severity = 'critical' THEN 4
                    WHEN severity = 'high' THEN 3
                    WHEN severity = 'medium' THEN 2
                    ELSE 1
                END) as severity_score
            FROM ir_incidents
            WHERE location IS NOT NULL AND location != ''
            GROUP BY location, incident_type
            ORDER BY count DESC
            """
        )

        # Aggregate by location
        location_map = {}
        for row in rows:
            loc = row["location"]
            if loc not in location_map:
                location_map[loc] = {"count": 0, "by_type": {}, "severity_scores": []}
            location_map[loc]["count"] += row["count"]
            location_map[loc]["by_type"][row["incident_type"]] = row["count"]
            location_map[loc]["severity_scores"].append(row["severity_score"])

        # Sort by count and limit
        sorted_locations = sorted(location_map.items(), key=lambda x: x[1]["count"], reverse=True)[:limit]

        hotspots = [
            LocationHotspot(
                location=loc,
                count=info["count"],
                by_type=info["by_type"],
                avg_severity_score=round(sum(info["severity_scores"]) / len(info["severity_scores"]), 2),
            )
            for loc, info in sorted_locations
        ]

        return LocationAnalysis(
            hotspots=hotspots,
            total_locations=len(location_map),
        )


# ===========================================
# Audit Log
# ===========================================

@router.get("/{incident_id}/audit-log", response_model=IRAuditLogResponse)
async def get_audit_log(
    incident_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user=Depends(require_admin_or_client),
):
    """Get the audit log for an incident."""
    async with get_connection() as conn:
        # Verify incident exists
        incident = await conn.fetchrow(
            "SELECT id FROM ir_incidents WHERE id = $1",
            str(incident_id),
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        total = await conn.fetchval(
            "SELECT COUNT(*) FROM ir_audit_log WHERE incident_id = $1",
            str(incident_id),
        )

        rows = await conn.fetch(
            """
            SELECT * FROM ir_audit_log
            WHERE incident_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            str(incident_id),
            limit,
            offset,
        )

        entries = [
            IRAuditLogEntry(
                id=row["id"],
                incident_id=row["incident_id"],
                user_id=row["user_id"],
                action=row["action"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                details=json.loads(row["details"]) if row["details"] else None,
                ip_address=row["ip_address"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

        return IRAuditLogResponse(entries=entries, total=total or 0)


# ===========================================
# AI Analysis
# ===========================================

@router.post("/{incident_id}/analyze/categorize", response_model=CategorizationAnalysis)
async def analyze_categorization(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Auto-categorize an incident using AI."""
    from ..services.ir_analysis import get_ir_analyzer

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id, title, description, location, reported_by_name FROM ir_incidents WHERE id = $1",
            str(incident_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Incident not found")

        # Check for cached analysis
        cached = await conn.fetchrow(
            """
            SELECT analysis_data FROM ir_incident_analysis
            WHERE incident_id = $1 AND analysis_type = 'categorization'
            ORDER BY created_at DESC LIMIT 1
            """,
            str(incident_id),
        )

        if cached:
            result = json.loads(cached["analysis_data"]) if isinstance(cached["analysis_data"], str) else cached["analysis_data"]
            return CategorizationAnalysis(
                suggested_type=result["suggested_type"],
                confidence=result["confidence"],
                reasoning=result["reasoning"],
                generated_at=result["generated_at"],
            )

        # Run AI analysis
        analyzer = get_ir_analyzer()
        result = await analyzer.categorize_incident(
            title=row["title"],
            description=row["description"],
            location=row["location"],
            reported_by=row["reported_by_name"],
        )

        # Cache the result
        await conn.execute(
            """
            INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
            VALUES ($1, 'categorization', $2)
            """,
            str(incident_id),
            json.dumps(result),
        )

        # Log audit
        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "analysis_run",
            "analysis",
            None,
            {"type": "categorization"},
            request.client.host if request.client else None,
        )

        return CategorizationAnalysis(
            suggested_type=result["suggested_type"],
            confidence=result["confidence"],
            reasoning=result["reasoning"],
            generated_at=result["generated_at"],
        )


@router.post("/{incident_id}/analyze/severity", response_model=SeverityAnalysis)
async def analyze_severity(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Assess incident severity using AI."""
    from ..services.ir_analysis import get_ir_analyzer

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM ir_incidents WHERE id = $1",
            str(incident_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Incident not found")

        # Check for cached analysis
        cached = await conn.fetchrow(
            """
            SELECT analysis_data FROM ir_incident_analysis
            WHERE incident_id = $1 AND analysis_type = 'severity'
            ORDER BY created_at DESC LIMIT 1
            """,
            str(incident_id),
        )

        if cached:
            result = json.loads(cached["analysis_data"]) if isinstance(cached["analysis_data"], str) else cached["analysis_data"]
            return SeverityAnalysis(
                suggested_severity=result["suggested_severity"],
                factors=result["factors"],
                reasoning=result["reasoning"],
                generated_at=result["generated_at"],
            )

        # Run AI analysis
        analyzer = get_ir_analyzer()
        category_data = json.loads(row["category_data"]) if isinstance(row.get("category_data"), str) else row.get("category_data")

        result = await analyzer.assess_severity(
            title=row["title"],
            description=row["description"],
            incident_type=row["incident_type"],
            location=row["location"],
            category_data=category_data,
        )

        # Cache the result
        await conn.execute(
            """
            INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
            VALUES ($1, 'severity', $2)
            """,
            str(incident_id),
            json.dumps(result),
        )

        # Log audit
        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "analysis_run",
            "analysis",
            None,
            {"type": "severity"},
            request.client.host if request.client else None,
        )

        return SeverityAnalysis(
            suggested_severity=result["suggested_severity"],
            factors=result["factors"],
            reasoning=result["reasoning"],
            generated_at=result["generated_at"],
        )


@router.post("/{incident_id}/analyze/root-cause", response_model=RootCauseAnalysis)
async def analyze_root_cause(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Perform root cause analysis using AI."""
    from ..services.ir_analysis import get_ir_analyzer

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM ir_incidents WHERE id = $1",
            str(incident_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Incident not found")

        # Check for cached analysis
        cached = await conn.fetchrow(
            """
            SELECT analysis_data FROM ir_incident_analysis
            WHERE incident_id = $1 AND analysis_type = 'root_cause'
            ORDER BY created_at DESC LIMIT 1
            """,
            str(incident_id),
        )

        if cached:
            result = json.loads(cached["analysis_data"]) if isinstance(cached["analysis_data"], str) else cached["analysis_data"]
            return RootCauseAnalysis(
                primary_cause=result["primary_cause"],
                contributing_factors=result["contributing_factors"],
                prevention_suggestions=result["prevention_suggestions"],
                reasoning=result["reasoning"],
                generated_at=result["generated_at"],
            )

        # Run AI analysis
        analyzer = get_ir_analyzer()
        category_data = json.loads(row["category_data"]) if isinstance(row.get("category_data"), str) else row.get("category_data")
        witnesses = parse_witnesses(row.get("witnesses"))

        result = await analyzer.analyze_root_cause(
            title=row["title"],
            description=row["description"],
            incident_type=row["incident_type"],
            severity=row["severity"],
            location=row["location"],
            category_data=category_data,
            witnesses=[w.model_dump() for w in witnesses],
        )

        # Cache the result
        await conn.execute(
            """
            INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
            VALUES ($1, 'root_cause', $2)
            """,
            str(incident_id),
            json.dumps(result),
        )

        # Log audit
        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "analysis_run",
            "analysis",
            None,
            {"type": "root_cause"},
            request.client.host if request.client else None,
        )

        return RootCauseAnalysis(
            primary_cause=result["primary_cause"],
            contributing_factors=result["contributing_factors"],
            prevention_suggestions=result["prevention_suggestions"],
            reasoning=result["reasoning"],
            generated_at=result["generated_at"],
        )


@router.post("/{incident_id}/analyze/recommendations", response_model=RecommendationsAnalysis)
async def analyze_recommendations(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Generate corrective action recommendations using AI."""
    from ..services.ir_analysis import get_ir_analyzer

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM ir_incidents WHERE id = $1",
            str(incident_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Incident not found")

        # Check for cached analysis
        cached = await conn.fetchrow(
            """
            SELECT analysis_data FROM ir_incident_analysis
            WHERE incident_id = $1 AND analysis_type = 'recommendations'
            ORDER BY created_at DESC LIMIT 1
            """,
            str(incident_id),
        )

        if cached:
            result = json.loads(cached["analysis_data"]) if isinstance(cached["analysis_data"], str) else cached["analysis_data"]
            from ..models.ir_incident import RecommendationItem
            return RecommendationsAnalysis(
                recommendations=[RecommendationItem(**r) for r in result["recommendations"]],
                summary=result["summary"],
                generated_at=result["generated_at"],
            )

        # Run AI analysis
        analyzer = get_ir_analyzer()
        result = await analyzer.generate_recommendations(
            title=row["title"],
            description=row["description"],
            incident_type=row["incident_type"],
            severity=row["severity"],
            root_cause=row["root_cause"],
        )

        # Cache the result
        await conn.execute(
            """
            INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
            VALUES ($1, 'recommendations', $2)
            """,
            str(incident_id),
            json.dumps(result),
        )

        # Log audit
        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "analysis_run",
            "analysis",
            None,
            {"type": "recommendations"},
            request.client.host if request.client else None,
        )

        from ..models.ir_incident import RecommendationItem
        return RecommendationsAnalysis(
            recommendations=[RecommendationItem(**r) for r in result["recommendations"]],
            summary=result["summary"],
            generated_at=result["generated_at"],
        )


@router.post("/{incident_id}/analyze/similar", response_model=SimilarIncidentsAnalysis)
async def analyze_similar_incidents(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Find similar historical incidents using AI."""
    from ..services.ir_analysis import get_ir_analyzer

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM ir_incidents WHERE id = $1",
            str(incident_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Incident not found")

        # Get historical incidents (last 12 months, excluding current)
        twelve_months_ago = datetime.utcnow() - timedelta(days=365)
        historical = await conn.fetch(
            """
            SELECT id, incident_number, title, description, incident_type, location, occurred_at
            FROM ir_incidents
            WHERE id != $1 AND occurred_at >= $2
            ORDER BY occurred_at DESC
            LIMIT 100
            """,
            str(incident_id),
            twelve_months_ago,
        )

        historical_list = [
            {
                "id": str(h["id"]),
                "incident_number": h["incident_number"],
                "title": h["title"],
                "description": h["description"],
                "incident_type": h["incident_type"],
                "location": h["location"],
                "occurred_at": h["occurred_at"].isoformat() if h["occurred_at"] else None,
            }
            for h in historical
        ]

        # Run AI analysis
        analyzer = get_ir_analyzer()
        result = await analyzer.find_similar_incidents(
            title=row["title"],
            description=row["description"],
            incident_type=row["incident_type"],
            location=row["location"],
            occurred_at=row["occurred_at"],
            historical_incidents=historical_list,
        )

        # Cache the result
        await conn.execute(
            """
            INSERT INTO ir_incident_analysis (incident_id, analysis_type, analysis_data)
            VALUES ($1, 'similar', $2)
            """,
            str(incident_id),
            json.dumps(result),
        )

        # Log audit
        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "analysis_run",
            "analysis",
            None,
            {"type": "similar"},
            request.client.host if request.client else None,
        )

        from ..models.ir_incident import SimilarIncident
        similar_incidents = []
        for s in result.get("similar_incidents", []):
            try:
                similar_incidents.append(SimilarIncident(
                    incident_id=s["incident_id"],
                    incident_number=s["incident_number"],
                    title=s["title"],
                    incident_type=s.get("incident_type", row["incident_type"]),
                    similarity_score=s["similarity_score"],
                    common_factors=s["common_factors"],
                ))
            except Exception:
                continue  # Skip invalid entries

        return SimilarIncidentsAnalysis(
            similar_incidents=similar_incidents,
            pattern_summary=result.get("pattern_summary"),
            generated_at=result["generated_at"],
        )


@router.delete("/{incident_id}/analyze/{analysis_type}")
async def clear_analysis_cache(
    incident_id: UUID,
    analysis_type: str,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Clear cached analysis to force re-analysis."""
    valid_types = ["categorization", "severity", "root_cause", "recommendations", "similar"]
    if analysis_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid analysis type. Must be one of: {valid_types}")

    async with get_connection() as conn:
        # Verify incident exists
        incident = await conn.fetchrow(
            "SELECT id FROM ir_incidents WHERE id = $1",
            str(incident_id),
        )
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        # Delete cached analysis
        await conn.execute(
            """
            DELETE FROM ir_incident_analysis
            WHERE incident_id = $1 AND analysis_type = $2
            """,
            str(incident_id),
            analysis_type,
        )

        # Log audit
        await log_audit(
            conn,
            str(incident_id),
            str(current_user.id),
            "analysis_cleared",
            "analysis",
            None,
            {"type": analysis_type},
            request.client.host if request.client else None,
        )

        return {"message": f"Analysis cache cleared for {analysis_type}"}
