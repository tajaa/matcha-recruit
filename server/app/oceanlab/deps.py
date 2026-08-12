from fastapi import Depends

from app.core.dependencies import require_admin


# Oceanlab is an internal label tool. Reuse the platform master-admin identity
# rather than maintaining a second static credential system.
AuthDep = Depends(require_admin)
