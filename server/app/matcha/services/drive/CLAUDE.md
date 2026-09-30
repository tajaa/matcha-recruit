# Matcha Drive — `matcha_drive` (default ❌)

Company document store on the business `/work` surface. Service
`drive_service.py`, pure access model `drive_access.py`, routes
`routes/matcha_work/drive.py` (`/matcha-work/drive/*`), migration `mdrive01`.
Requires `matcha_work`; personal workspaces 403.

## Access model (`drive_access.py`, pure)

| Work level (`work_permissions.resolve_work_access`) | `general` | `hr` |
|---|---|---|
| `admin` (owner, platform admin, explicit admin) | list/read/add/manage/grant | same |
| `operator` (business admin default) | list/read/add/manage | nothing |
| `reviewer` / `member` | list/read | nothing |
| `guest` | nothing | nothing |

Per-user grants on a folder apply to it and every descendant, and only ever
widen: `view` = list+read, `upload` = add only (a drop-box — the holder can
submit a file but cannot list or read the folder), `edit` = list/read/add/
manage. No grant confers `grant`; only Work `admin` manages grants.

`clients.is_hr_approver` is **not** an input: that column is documented as
notification targeting only. HR approvers reach the HR space through an
ordinary `edit` grant on `hr_root` that `ensure_system_folders` seeds **once**,
in the same transaction that first creates `hr_root`. Revoking it is a normal
grant removal and is never re-seeded.

## Invariants

- Bytes go to the **private** bucket only (`upload_private_file`, prefix
  `drive/<company>/<space>`); downloads are 5-minute presigned URLs. No
  response ever includes `storage_path`.
- A folder or file the actor has no capability on returns **404**, not 403 —
  a folder name in HR is itself information. 403 is only for "you can see it
  but can't do that".
- System folders (`system_key`: `general_root`, `hr_root`, `hr_templates`,
  `hr_discipline`, `hr_discipline_drafts`, `hr_discipline_signed`) cannot be
  renamed, moved or deleted. The HR cases flow files into them by key. A
  user folder with the same name in the same place is adopted, not duplicated.
- Nothing moves between spaces (folders or files).
- Deleting a folder requires it to be empty of subfolders and live files;
  soft-deleted files are re-homed onto the space root so the RESTRICT FK
  doesn't pin an "empty" folder.
- Search computes readable folders in memory first and queries only those —
  an unreadable file is never returned, not even by filename.
- Text extraction (`ERDocumentParser`, pdf/docx/txt/md/csv, 200k chars) runs
  in `prepare_file` **before** a connection is taken, and never fails an
  upload (`text_status` = ok/empty/failed/unsupported).
- `store_file(actor=None)` is the system path (HR case filing) and skips the
  capability check. Routes always pass an actor.
- HR-space adds/reads/downloads/moves/deletes and every grant change write
  `drive_audit_log` on the caller's connection.
