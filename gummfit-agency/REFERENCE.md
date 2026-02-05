# GumFit Reference - Code Removed from Matcha-Recruit

This file contains reference snippets of code that was removed from matcha-recruit
when extracting gummfit into its own repo. Use these as a guide when rebuilding.

## Auth Models (from server/app/core/models/auth.py)

- `CreatorRegister` model - registration fields for creators
- `AgencyRegister` model - registration fields for agencies  
- `CreatorProfile` model - profile response for creators
- `AgencyProfile` model - profile response for agencies
- UserRole includes: "creator", "agency", "gumfit_admin"

## Registration Endpoints (from server/app/core/routes/auth.py)

- POST /register/creator - creates user + creator profile
- POST /register/agency - creates user + agency + agency_members owner entry
- GET /me - has branches for creator and agency roles

## Database Tables (from server/app/database.py)

Tables are still in the database (not dropped). The init_db() CREATE statements
were in database.py lines 1786-2400+:
- creators, creator_platform_connections
- revenue_streams, revenue_entries, creator_expenses
- agencies, agency_members
- gumfit_invites
- brand_deals, deal_applications, deal_contracts, contract_payments
- creator_deal_matches
- contract_templates, campaigns, campaign_offers, campaign_payments
- affiliate_links, affiliate_events, creator_valuations

The users table role constraint includes: 'creator', 'agency', 'gumfit_admin'

## Client API (from client/src/api/client.ts)

- `creators` namespace (lines ~2104-2288) - creator profile, revenue, expenses, platforms
- `agencies` namespace (lines ~2290-2346) - agency profile, members
- `deals` namespace (lines ~2348-2509) - brand deals, applications, contracts
- `campaigns` namespace (lines ~2511-2660) - campaigns, offers, payments, affiliates
- `gumfit` namespace (lines ~2750-2879) - admin stats, creators, agencies, users, invites, assets
- GumFit interfaces (lines ~2662-2748)

## App Routes (from client/src/App.tsx)

- Creator routes: /app/gumfit/* (dashboard, revenue, expenses, platforms, deals, applications, contracts, offers, affiliate)
- Agency routes: /app/gumfit/agency, /app/agency/* (deals, campaigns, creators, applications, contracts)
- GumFit Admin routes: /app/gumfit/admin/* (dashboard, creators, agencies, users, invites, assets)
- Public: /gumfit-landing

## Layout Nav Sections (from client/src/components/Layout.tsx)

- Creator Hub section (roles: ['creator'])
- Agency section (roles: ['agency'])
- GumFit Admin section (roles: ['gumfit_admin'])

## Login Redirects (from client/src/pages/Login.tsx)

- creator -> /app/gumfit
- agency -> /app/gumfit/agency
- gumfit_admin -> /app/gumfit

## Types

- client/src/types/creator.ts - Creator, CreatorUpdate, etc.
- client/src/types/agency.ts - Agency, AgencyUpdate, etc.
- client/src/types/deals.ts - BrandDeal, DealApplication, etc.
- client/src/types/campaigns.ts - Campaign, CampaignOffer, etc.
- UserRole in types/index.ts includes 'creator' | 'agency' | 'gumfit_admin'
