"""Who may see HR cases.

HR access = Work `admin`, or READ on Drive's `HR / Discipline` system folder
(an explicit, visible, revocable grant — HR approvers get one seeded when the
HR folders are first created). One rule for the page, the routes and Huume,
so "can open the HR Cases page" and "can read the letters" never diverge.

A GM who is on a case (gm_user_id) is NOT given HR access by that: they hear
about their own case through notifications and Huume, never the case list.
"""

from __future__ import annotations

from uuid import UUID

from app.matcha.services.drive import drive_service
from app.matcha.services.drive.drive_access import DriveCap
from app.matcha.services.drive.drive_service import DriveError


async def has_hr_access(conn, *, user, company_id: UUID) -> bool:
    actor = await drive_service.load_actor(conn, user=user, company_id=company_id)
    if actor.work_level == "admin":
        return True
    folders = await drive_service.ensure_system_folders(conn, company_id)
    try:
        _, caps = await drive_service.folder_caps(
            conn, company_id=company_id, folder_id=folders["hr_discipline"], actor=actor,
        )
    except DriveError:
        return False
    return DriveCap.READ in caps
