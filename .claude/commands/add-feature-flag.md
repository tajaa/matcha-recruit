Wire a new per-company feature flag end-to-end (backend defaults, gate dependency, frontend sidebar, FeatureGate wrapper, root CLAUDE.md table entry).

Parse the flag name and default value from: $ARGUMENTS
Usage: `/add-feature-flag <flag_name> <true|false>` (e.g. `/add-feature-flag training false`).

If the default is omitted, default to `false` (most new flags ship dark).
If only one arg is given and it's `true`/`false`, ask the user for the flag name first.

---

## Step 1: Add backend default

Edit `server/app/core/feature_flags.py`. Find the `DEFAULT_COMPANY_FEATURES` dict literal and add a new entry:

```python
"<flag_name>": <true|false>,
```

Keep alphabetical ordering within its semantic group (handbooks/accommodations/risk_assessment/discipline up top — "always-on by default"; everything else listed after).

## Step 2: Document in root CLAUDE.md

Edit `/Users/finch/Documents/github/matcha/CLAUDE.md`. Find the Feature Flags table and add a row:

```
| `<flag_name>` | ✅ or ❌ | <short purpose> |
```

✅ = default on, ❌ = default off. Match the default in step 1.

## Step 3: Gate the backend router (if applicable)

Find the relevant router mount in `server/app/matcha/routes/__init__.py` and add the feature gate:

```python
matcha_router.include_router(<your>_router, prefix="/<path>", tags=["<tag>"],
                             dependencies=[Depends(require_feature("<flag_name>"))])
```

If the flag is sub-feature scope (e.g. flips behavior inside an existing router rather than enabling a whole router), skip this step — gate at the endpoint level inside the router instead:

```python
@router.post("/...", dependencies=[Depends(require_feature("<flag_name>"))])
```

## Step 4: Frontend FeatureGate wrapper

Find the route page that exposes this feature. Add `<FeatureGate flag="<flag_name>">` around its top-level JSX so URL-hoppers see the `<UpgradeUpsellCard>` instead of a 403:

```tsx
import { FeatureGate } from '../../components/FeatureGate'

export function MyFeaturePage() {
  return (
    <FeatureGate flag="<flag_name>">
      {/* existing page contents */}
    </FeatureGate>
  )
}
```

## Step 5: Frontend sidebar entry

Add the nav entry to the relevant sidebar shell (`client/src/components/ClientSidebar.tsx` for full Matcha, `client/src/components/ir-only/IrSidebar.tsx` for matcha-lite, or both). Gate the entry with `hasFeature`:

```tsx
const { hasFeature } = useMe()
// ...
{hasFeature('<flag_name>') && (
  <SidebarLink to="/app/<path>" label="<Label>" icon={SomeIcon} />
)}
```

## Step 6: Verify

```bash
cd /Users/finch/Documents/github/matcha/server && ./venv/bin/python -c "
from app.core.feature_flags import DEFAULT_COMPANY_FEATURES
assert '<flag_name>' in DEFAULT_COMPANY_FEATURES, 'flag missing from defaults'
print('OK:', DEFAULT_COMPANY_FEATURES['<flag_name>'])
"
cd /Users/finch/Documents/github/matcha/client && npx tsc --noEmit
```

Report back: the 5 files touched and the flag's effective default.

---

## Notes

- `enabled_features` in the `companies` table is a JSONB column; per-company overrides win over `DEFAULT_COMPANY_FEATURES`. New flags don't need a migration — they appear automatically.
- Don't add the flag to `signup_source`-specific tier handlers (e.g. matcha-lite Stripe webhook) unless the user explicitly asks for tier-gated enablement.
- Frontend: `useMe()` exposes both `hasFeature()` and `companyFeatures`. Prefer `hasFeature()` — it handles unknown flags correctly (returns false rather than throwing).
