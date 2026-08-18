-- Undo for regina_renewal_dates.sql — clears the seeded renewal_date back to
-- NULL for the same 13 companies. Safe even if a broker later edited one of
-- them by hand (that write already flipped broker_company_links.updated_at,
-- but there is no seeded-vs-real marker on this column — re-running the undo
-- after a real edit would erase it too, so only run this before any manual
-- renewal edits are made on these test accounts).

UPDATE broker_company_links SET renewal_date = NULL
  WHERE company_id IN (
    '1a1123e5-4c24-4735-8501-9a64a1dd7691', -- 720 Behavioral
    '19e02494-8427-44b5-9c1b-98064b7e94e1', -- Sea Cafe
    '3e69de7a-0c0e-4a34-ab7b-3e9462756516', -- Bags
    '993605b1-9e58-41f1-8115-b3e5c68bc7fc', -- Bear Co.
    '0fd5bd51-aa6f-465a-83c7-daacf677f5e8', -- Bookworm Books
    '83abd6c1-461c-491c-9389-eafb198e3c0e', -- Bowls
    '7f2e1c52-84ad-46eb-9685-9e82788c99e4', -- Cake
    '4b2f5f47-f637-49be-a6a9-aac103622b2f', -- Coffee
    'd32b4494-5a9b-45f4-aece-64315c2b0970', -- Jennifer Co
    '7501ca6a-f9ea-4a46-addf-0073b43b5e60', -- Limbo
    '8ec42fb4-72d0-436f-b5cf-3851a53220a6', -- Payment Bypass
    'ef710ea4-417c-4c9c-987b-e8c647e2dcdc', -- Supply Co
    'c91c1534-2b4e-4c87-a103-8390f221bfcb'  -- Tea Time
  )
  AND broker_id = '574c50d6-e3d2-4bef-a4d7-4e153b6da053';
