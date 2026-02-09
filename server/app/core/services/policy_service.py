from datetime import datetime, timedelta
from typing import Optional, List
import re
import uuid

from ...database import get_connection
from ..models.policy import (
    Policy,
    PolicyCreate,
    PolicyUpdate,
    PolicyResponse,
    SignatureStatus,
    SignerType,
    PolicySignature,
    SignatureRequest,
    SignatureCreate,
    PolicySignatureResponse,
    PolicySignatureWithToken,
)


class PolicyService:
    @staticmethod
    async def create_policy(company_id: str, data: PolicyCreate, created_by: Optional[str] = None) -> Policy:
        async with get_connection() as conn:
            policy_id = await conn.fetchval(
                """
                    INSERT INTO policies (company_id, title, description, content, file_url, version, status, created_by)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    RETURNING id
                """,
                company_id,
                data.title,
                data.description,
                data.content,
                data.file_url,
                data.version or "1.0",
                data.status or "draft",
                created_by,
            )
            return await PolicyService.get_policy_by_id(policy_id)

    @staticmethod
    async def get_policy_by_id(policy_id: str, company_id: Optional[str] = None) -> Optional[PolicyResponse]:
        async with get_connection() as conn:
            if company_id:
                row = await conn.fetchrow(
                    """
                        SELECT
                            p.*,
                            c.name as company_name,
                            COUNT(ps.id) as signature_count,
                            COUNT(CASE WHEN ps.status = 'signed' THEN 1 END) as signed_count,
                            COUNT(CASE WHEN ps.status = 'pending' THEN 1 END) as pending_signatures
                        FROM policies p
                        LEFT JOIN companies c ON p.company_id = c.id
                        LEFT JOIN policy_signatures ps ON p.id = ps.policy_id
                        WHERE p.id = $1 AND p.company_id = $2
                        GROUP BY p.id, c.name
                    """,
                    policy_id,
                    company_id,
                )
            else:
                row = await conn.fetchrow(
                    """
                        SELECT
                            p.*,
                            c.name as company_name,
                            COUNT(ps.id) as signature_count,
                            COUNT(CASE WHEN ps.status = 'signed' THEN 1 END) as signed_count,
                            COUNT(CASE WHEN ps.status = 'pending' THEN 1 END) as pending_signatures
                        FROM policies p
                        LEFT JOIN companies c ON p.company_id = c.id
                        LEFT JOIN policy_signatures ps ON p.id = ps.policy_id
                        WHERE p.id = $1
                        GROUP BY p.id, c.name
                    """,
                    policy_id,
                )
            if not row:
                return None
            return PolicyResponse(**dict(row))

    @staticmethod
    async def get_policies(company_id: str, status: Optional[str] = None) -> List[PolicyResponse]:
        async with get_connection() as conn:
            query = """
                SELECT
                    p.*,
                    c.name as company_name,
                    COUNT(ps.id) as signature_count,
                    COUNT(CASE WHEN ps.status = 'signed' THEN 1 END) as signed_count,
                    COUNT(CASE WHEN ps.status = 'pending' THEN 1 END) as pending_signatures
                FROM policies p
                LEFT JOIN companies c ON p.company_id = c.id
                LEFT JOIN policy_signatures ps ON p.id = ps.policy_id
                WHERE p.company_id = $1
            """
            params = [company_id]

            if status:
                query += " AND p.status = $2"
                params.append(status)

            query += " GROUP BY p.id, c.name ORDER BY p.updated_at DESC"

            rows = await conn.fetch(query, *params)
            return [PolicyResponse(**dict(row)) for row in rows]

    @staticmethod
    async def update_policy(policy_id: str, data: PolicyUpdate, company_id: Optional[str] = None) -> Optional[PolicyResponse]:
        async with get_connection() as conn:
            updates = []
            params = []
            param_idx = 2

            if data.title is not None:
                updates.append(f"title = ${param_idx}")
                params.append(data.title)
                param_idx += 1

            if data.description is not None:
                updates.append(f"description = ${param_idx}")
                params.append(data.description)
                param_idx += 1

            if data.content is not None:
                updates.append(f"content = ${param_idx}")
                params.append(data.content)
                param_idx += 1

            if data.file_url is not None:
                updates.append(f"file_url = ${param_idx}")
                params.append(data.file_url)
                param_idx += 1

            if data.version is not None:
                updates.append(f"version = ${param_idx}")
                params.append(data.version)
                param_idx += 1

            if data.status is not None:
                updates.append(f"status = ${param_idx}")
                params.append(data.status)
                param_idx += 1

            if not updates:
                return await PolicyService.get_policy_by_id(policy_id, company_id)

            updates.append("updated_at = NOW()")
            where = "WHERE id = $1"
            if company_id:
                where += f" AND company_id = ${param_idx}"
                params.append(company_id)
                param_idx += 1
            query = f"UPDATE policies SET {', '.join(updates)} {where} RETURNING id"
            params.insert(0, policy_id)

            result = await conn.fetchval(query, *params)
            if result is None:
                return None
            return await PolicyService.get_policy_by_id(policy_id, company_id)

    @staticmethod
    async def delete_policy(policy_id: str, company_id: Optional[str] = None) -> bool:
        async with get_connection() as conn:
            if company_id:
                result = await conn.execute(
                    "DELETE FROM policies WHERE id = $1 AND company_id = $2",
                    policy_id,
                    company_id,
                )
            else:
                result = await conn.execute(
                    "DELETE FROM policies WHERE id = $1",
                    policy_id,
                )
            return result == "DELETE 1"

    @staticmethod
    async def can_user_access_policy(user_id: str, policy_id: str) -> bool:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                    SELECT p.id FROM policies p
                    JOIN companies c ON p.company_id = c.id
                    JOIN clients cl ON c.id = cl.company_id
                    WHERE p.id = $1 AND cl.user_id = $2
                    UNION
                    SELECT p.id FROM policies p
                    WHERE p.id = $1 AND p.created_by = $2
                """,
                policy_id,
                user_id,
            )
            return row is not None


class SignatureService:
    @staticmethod
    def _extract_policy_id_from_document_type(document_type: Optional[str]) -> Optional[str]:
        """Extract policy UUID hint from doc types like `policy:<uuid>`."""
        if not document_type:
            return None

        match = re.search(r"policy[:/_-]?([0-9a-fA-F-]{36})", document_type, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    @staticmethod
    async def sync_employee_document_signature(
        company_id: str,
        employee_id: str,
        employee_name: str,
        employee_email: str,
        document_title: Optional[str],
        document_type: Optional[str],
        signature_data: Optional[str],
        ip_address: Optional[str] = None,
    ) -> Optional[PolicySignatureResponse]:
        """
        Mirror employee-portal policy document signatures into policy_signatures.

        This keeps admin policy signature dashboards/lists in sync when employees
        sign policy documents through the portal document workflow.
        """
        normalized_type = (document_type or "").strip().lower()
        if "policy" not in normalized_type and not (document_title or "").strip():
            return None

        policy_id_hint = SignatureService._extract_policy_id_from_document_type(document_type)

        async with get_connection() as conn:
            policy_id = None

            if policy_id_hint:
                policy_id = await conn.fetchval(
                    "SELECT id FROM policies WHERE id = $1 AND company_id = $2",
                    policy_id_hint,
                    company_id,
                )

            # Fallback: match policy by title when doc_type doesn't carry a policy UUID.
            if not policy_id and document_title:
                policy_id = await conn.fetchval(
                    """
                        SELECT id
                        FROM policies
                        WHERE company_id = $1 AND LOWER(title) = LOWER($2)
                        ORDER BY updated_at DESC
                        LIMIT 1
                    """,
                    company_id,
                    document_title.strip(),
                )

            if not policy_id:
                return None

            existing_signature_id = await conn.fetchval(
                """
                    SELECT id
                    FROM policy_signatures
                    WHERE policy_id = $1
                      AND signer_type = 'employee'
                      AND (
                          signer_id = $2
                          OR LOWER(signer_email) = LOWER($3)
                      )
                    ORDER BY
                        CASE WHEN status = 'pending' THEN 0 ELSE 1 END,
                        created_at DESC
                    LIMIT 1
                """,
                policy_id,
                employee_id,
                employee_email,
            )

            if existing_signature_id:
                await conn.execute(
                    """
                        UPDATE policy_signatures
                        SET status = 'signed',
                            signed_at = NOW(),
                            signature_data = $1,
                            ip_address = $2
                        WHERE id = $3
                    """,
                    signature_data,
                    ip_address,
                    existing_signature_id,
                )
                return await SignatureService.get_signature_by_id(existing_signature_id)

            signature_id = await conn.fetchval(
                """
                    INSERT INTO policy_signatures
                    (
                        policy_id,
                        signer_type,
                        signer_id,
                        signer_name,
                        signer_email,
                        token,
                        status,
                        signed_at,
                        signature_data,
                        ip_address,
                        expires_at
                    )
                    VALUES (
                        $1,
                        'employee',
                        $2,
                        $3,
                        $4,
                        $5,
                        'signed',
                        NOW(),
                        $6,
                        $7,
                        NOW() + INTERVAL '365 days'
                    )
                    RETURNING id
                """,
                policy_id,
                employee_id,
                employee_name,
                employee_email,
                str(uuid.uuid4()),
                signature_data,
                ip_address,
            )
            return await SignatureService.get_signature_by_id(signature_id)

    @staticmethod
    async def create_signature_request(
        policy_id: str,
        signer: SignatureRequest,
        expires_in_days: int = 7,
    ) -> PolicySignatureWithToken:
        token = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(days=expires_in_days)

        async with get_connection() as conn:
            sig_id = await conn.fetchval(
                """
                    INSERT INTO policy_signatures
                    (policy_id, signer_type, signer_id, signer_name, signer_email, token, expires_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING id
                """,
                policy_id,
                signer.type,
                signer.id,
                signer.name,
                signer.email,
                token,
                expires_at,
            )
            # Use get_signature_with_token_by_id to return full object including token
            sig = await SignatureService.get_signature_with_token_by_id(sig_id)
            if not sig:
                 raise ValueError("Failed to retrieve created signature")
            return sig

    @staticmethod
    async def create_batch_signature_requests(
        policy_id: str,
        signers: List[SignatureRequest],
        expires_in_days: int = 7,
    ) -> List[PolicySignatureWithToken]:
        signatures = []
        for signer in signers:
            sig = await SignatureService.create_signature_request(policy_id, signer, expires_in_days)
            signatures.append(sig)
        return signatures

    @staticmethod
    async def get_signature_by_id(sig_id: str) -> Optional[PolicySignatureResponse]:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                    SELECT
                        ps.*,
                        p.title as policy_title
                    FROM policy_signatures ps
                    JOIN policies p ON ps.policy_id = p.id
                    WHERE ps.id = $1
                """,
                sig_id,
            )
            if not row:
                return None
            return PolicySignatureResponse(**dict(row))

    @staticmethod
    async def get_signature_with_token_by_id(sig_id: str) -> Optional[PolicySignatureWithToken]:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                    SELECT
                        ps.*,
                        p.title as policy_title
                    FROM policy_signatures ps
                    JOIN policies p ON ps.policy_id = p.id
                    WHERE ps.id = $1
                """,
                sig_id,
            )
            if not row:
                return None
            return PolicySignatureWithToken(**dict(row))

    @staticmethod
    async def get_signature_by_token(token: str) -> Optional[PolicySignatureResponse]:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                    SELECT
                        ps.*,
                        p.title as policy_title,
                        p.content as policy_content,
                        p.file_url as policy_file_url,
                        p.version as policy_version,
                        c.name as company_name
                    FROM policy_signatures ps
                    JOIN policies p ON ps.policy_id = p.id
                    LEFT JOIN companies c ON p.company_id = c.id
                    WHERE ps.token = $1
                """,
                token,
            )
            if not row:
                return None
            return PolicySignatureResponse(**dict(row))

    @staticmethod
    async def get_policy_signatures(policy_id: str) -> List[PolicySignatureResponse]:
        async with get_connection() as conn:
            rows = await conn.fetch(
                """
                    SELECT
                        ps.*,
                        p.title as policy_title
                    FROM policy_signatures ps
                    JOIN policies p ON ps.policy_id = p.id
                    WHERE ps.policy_id = $1
                    ORDER BY ps.created_at DESC
                """,
                policy_id,
            )
            return [PolicySignatureResponse(**dict(row)) for row in rows]

    @staticmethod
    async def submit_signature(
        token: str,
        data: SignatureCreate,
        ip_address: Optional[str] = None,
    ) -> Optional[PolicySignatureResponse]:
        signature = await SignatureService.get_signature_by_token(token)
        if not signature or signature.status != "pending":
            return None

        if datetime.utcnow() > signature.expires_at:
            await SignatureService._mark_signature_expired(signature.id)
            return None

        async with get_connection() as conn:
            new_status = "signed" if data.accepted else "declined"
            await conn.execute(
                """
                    UPDATE policy_signatures
                    SET status = $1, signed_at = NOW(), signature_data = $2, ip_address = $3
                    WHERE id = $4
                """,
                new_status,
                data.signature_data,
                ip_address,
                signature.id,
            )
            return await SignatureService.get_signature_by_id(signature.id)

    @staticmethod
    async def delete_signature(signature_id: str) -> bool:
        async with get_connection() as conn:
            result = await conn.execute(
                "DELETE FROM policy_signatures WHERE id = $1",
                signature_id,
            )
            return result == "DELETE 1"

    @staticmethod
    async def resend_signature(signature_id: str) -> Optional[PolicySignatureWithToken]:
        signature = await SignatureService.get_signature_by_id(signature_id)
        if not signature or signature.status != "pending":
            return None

        new_token = str(uuid.uuid4())
        async with get_connection() as conn:
            await conn.execute(
                """
                    UPDATE policy_signatures
                    SET token = $1, expires_at = NOW() + INTERVAL '7 days'
                    WHERE id = $2
                """,
                new_token,
                signature_id,
            )
            return await SignatureService.get_signature_with_token_by_id(signature_id)

    @staticmethod
    async def _mark_signature_expired(signature_id: str):
        async with get_connection() as conn:
            await conn.execute(
                "UPDATE policy_signatures SET status = 'expired' WHERE id = $1",
                signature_id,
            )

    @staticmethod
    async def check_and_mark_expired_signatures():
        async with get_connection() as conn:
            await conn.execute(
                """
                    UPDATE policy_signatures
                    SET status = 'expired'
                    WHERE status = 'pending' AND expires_at < NOW()
                """
            )
