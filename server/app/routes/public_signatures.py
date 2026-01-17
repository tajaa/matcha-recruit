import html
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..models.policy import SignatureCreate, PolicySignatureResponse
from ..services.policy_service import SignatureService

router = APIRouter(prefix="/signatures", tags=["public-signatures"])


class SignatureDataResponse(BaseModel):
    id: str
    policy_id: str
    policy_title: Optional[str] = None
    policy_content: Optional[str] = None
    policy_file_url: Optional[str] = None
    policy_version: str = "1.0"
    company_name: Optional[str] = None
    signer_name: str
    signer_email: str
    status: str
    expires_at: str


class SignAction(BaseModel):
    action: str  # "sign" or "decline"
    signature_data: Optional[str] = None


# JSON API endpoints for React frontend
@router.get("/verify/{token}", response_model=SignatureDataResponse)
async def get_signature_data(token: str):
    """Get signature data as JSON for React frontend."""
    signature = await SignatureService.get_signature_by_token(token)
    if not signature:
        raise HTTPException(status_code=404, detail="Invalid or expired signature link")

    return SignatureDataResponse(
        id=str(signature.id),
        policy_id=str(signature.policy_id),
        policy_title=signature.policy_title,
        policy_content=signature.policy_content,
        policy_file_url=signature.policy_file_url,
        policy_version=signature.policy_version or "1.0",
        company_name=signature.company_name,
        signer_name=signature.signer_name,
        signer_email=signature.signer_email,
        status=signature.status,
        expires_at=signature.expires_at.isoformat(),
    )


@router.post("/verify/{token}")
async def submit_signature_json(token: str, data: SignAction, request: Request):
    """Submit signature via JSON API for React frontend."""
    signature = await SignatureService.get_signature_by_token(token)
    if not signature:
        raise HTTPException(status_code=404, detail="Invalid or expired signature link")

    if signature.status != "pending":
        raise HTTPException(status_code=410, detail="This signature request is no longer pending")

    accepted = data.action == "sign"
    signature_create = SignatureCreate(
        signature_data=data.signature_data if accepted else None,
        accepted=accepted,
    )

    ip_address = request.client.host if request.client else None
    result = await SignatureService.submit_signature(token, signature_create, ip_address)

    if not result:
        raise HTTPException(status_code=400, detail="Failed to process signature")

    return {"status": result.status, "message": "Signature recorded successfully"}


@router.get("/sign/{token}")
async def view_signature_page(token: str):
    signature = await SignatureService.get_signature_by_token(token)
    if not signature:
        return HTMLResponse(
            content="<html><body><h1>Invalid or expired signature link</h1></body></html>",
            status_code=404,
        )

    if signature.status != "pending":
        status_messages = {
            "signed": "You have already signed this policy",
            "declined": "You have declined this policy",
            "expired": "This signature link has expired",
        }
        message = status_messages.get(signature.status, "This signature link is no longer valid")
        return HTMLResponse(
            content=f"<html><body><h1>{message}</h1></body></html>",
            status_code=400,
        )

    policy_content = (signature.policy_content or "").strip()
    if policy_content:
        policy_body_html = html.escape(policy_content)
    elif signature.policy_file_url:
        file_url = html.escape(signature.policy_file_url, quote=True)
        policy_body_html = (
            f'<a href="{file_url}" target="_blank" rel="noopener noreferrer">'
            "View policy document</a>"
        )
    else:
        policy_body_html = "Policy content is unavailable."

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Sign: {signature.policy_title}</title>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }}
            h1 {{ color: #333; }}
            .policy-content {{ background: #f9f9f9; padding: 20px; border-radius: 8px; margin: 20px 0; white-space: pre-wrap; }}
            .signature-pad {{ border: 2px solid #ccc; border-radius: 8px; margin: 20px 0; }}
            canvas {{ cursor: crosshair; }}
            .actions {{ margin: 20px 0; display: flex; gap: 10px; }}
            button {{ padding: 12px 24px; font-size: 16px; border: none; border-radius: 6px; cursor: pointer; }}
            .btn-sign {{ background: #22c55e; color: white; }}
            .btn-decline {{ background: #ef4444; color: white; }}
            .btn-clear {{ background: #6b7280; color: white; }}
            button:hover {{ opacity: 0.9; }}
            button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
            .error {{ color: #dc2626; margin-top: 10px; }}
        </style>
    </head>
    <body>
        <h1>Policy Signature Request</h1>
        <p><strong>Policy:</strong> {signature.policy_title}</p>
        <p><strong>Signer:</strong> {signature.signer_name}</p>
        <p><strong>Email:</strong> {signature.signer_email}</p>
        <p><strong>Expires:</strong> {signature.expires_at.strftime('%B %d, %Y at %I:%M %p')}</p>

        <div class="policy-content">{policy_body_html}</div>

        <h2>Your Signature</h2>
        <p>Please sign below to accept this policy.</p>

        <div class="signature-pad">
            <canvas id="signaturePad" width="700" height="200"></canvas>
        </div>

        <div class="actions">
            <button class="btn-clear" onclick="clearSignature()">Clear</button>
            <button class="btn-sign" onclick="submitSignature(true)">Sign & Accept</button>
            <button class="btn-decline" onclick="submitSignature(false)">Decline</button>
        </div>

        <div id="error" class="error"></div>

        <script>
            const canvas = document.getElementById('signaturePad');
            const ctx = canvas.getContext('2d');
            let isDrawing = false;

            canvas.addEventListener('mousedown', startDrawing);
            canvas.addEventListener('mousemove', draw);
            canvas.addEventListener('mouseup', stopDrawing);
            canvas.addEventListener('mouseout', stopDrawing);

            canvas.addEventListener('touchstart', startDrawing);
            canvas.addEventListener('touchmove', draw);
            canvas.addEventListener('touchend', stopDrawing);

            function startDrawing(e) {{
                isDrawing = true;
                draw(e);
            }}

            function draw(e) {{
                if (!isDrawing) return;
                e.preventDefault();

                const rect = canvas.getBoundingClientRect();
                const x = (e.clientX || e.touches[0].clientX) - rect.left;
                const y = (e.clientY || e.touches[0].clientY) - rect.top;

                ctx.lineWidth = 2;
                ctx.lineCap = 'round';
                ctx.strokeStyle = '#000';
                ctx.lineTo(x, y);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(x, y);
            }}

            function stopDrawing() {{
                isDrawing = false;
                ctx.beginPath();
            }}

            function clearSignature() {{
                ctx.clearRect(0, 0, canvas.width, canvas.height);
            }}

            async function submitSignature(accepted) {{
                const signatureData = accepted ? canvas.toDataURL() : null;
                const errorDiv = document.getElementById('error');
                const buttons = document.querySelectorAll('button');

                buttons.forEach(btn => btn.disabled = true);
                errorDiv.textContent = '';

                try {{
                    const response = await fetch('/api/signatures/sign/{token}', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ signature_data: signatureData, accepted }})
                    }});

                    if (response.ok) {{
                        if (accepted) {{
                            document.body.innerHTML = '<h1 style="color: #22c55e; text-align: center; margin-top: 100px;">Thank you! Your signature has been recorded.</h1>';
                        }} else {{
                            document.body.innerHTML = '<h1 style="color: #ef4444; text-align: center; margin-top: 100px;">You have declined this policy.</h1>';
                        }}
                    }} else {{
                        const data = await response.json();
                        errorDiv.textContent = data.detail || 'An error occurred';
                        buttons.forEach(btn => btn.disabled = false);
                    }}
                }} catch (error) {{
                    errorDiv.textContent = 'Network error. Please try again.';
                    buttons.forEach(btn => btn.disabled = false);
                }}
            }}
        </script>
    </body>
    </html>
    """

    return HTMLResponse(content=html_content)


@router.post("/sign/{token}")
async def submit_signature(
    token: str,
    data: SignatureCreate,
    request: Request,
):
    ip_address = request.client.host if request.client else None
    signature = await SignatureService.submit_signature(token, data, ip_address)

    if not signature:
        raise HTTPException(
            status_code=400,
            detail="Invalid, expired, or already used signature link",
        )

    return {"status": signature.status, "message": "Signature recorded successfully"}
