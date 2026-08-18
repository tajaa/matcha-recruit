-- Seed broker-set renewal dates for Regina George LLC's book (broker
-- 574c50d6-e3d2-4bef-a4d7-4e153b6da053, ashVidales+regina@gmail.com's test
-- broker tenant). All 13 linked companies currently have renewal_date NULL,
-- which reads as "0 days to renewal" in the Book of Business Renewal column.
--
-- Additive only: each UPDATE is guarded by "AND renewal_date IS NULL" so it
-- never overwrites a broker-entered date. Spread across bands (critical <60d,
-- warning 60-90d, normal >90d) to match the existing At Risk / Watch mix
-- shown in the portal.

UPDATE broker_company_links SET renewal_date = '2026-09-12', updated_at = NOW()
  WHERE company_id = '1a1123e5-4c24-4735-8501-9a64a1dd7691' AND broker_id = '574c50d6-e3d2-4bef-a4d7-4e153b6da053' AND renewal_date IS NULL; -- 720 Behavioral, 25d
UPDATE broker_company_links SET renewal_date = '2026-09-27', updated_at = NOW()
  WHERE company_id = '19e02494-8427-44b5-9c1b-98064b7e94e1' AND broker_id = '574c50d6-e3d2-4bef-a4d7-4e153b6da053' AND renewal_date IS NULL; -- Sea Cafe, 40d
UPDATE broker_company_links SET renewal_date = '2026-10-02', updated_at = NOW()
  WHERE company_id = '3e69de7a-0c0e-4a34-ab7b-3e9462756516' AND broker_id = '574c50d6-e3d2-4bef-a4d7-4e153b6da053' AND renewal_date IS NULL; -- Bags, 45d
UPDATE broker_company_links SET renewal_date = '2026-10-12', updated_at = NOW()
  WHERE company_id = '993605b1-9e58-41f1-8115-b3e5c68bc7fc' AND broker_id = '574c50d6-e3d2-4bef-a4d7-4e153b6da053' AND renewal_date IS NULL; -- Bear Co., 55d
UPDATE broker_company_links SET renewal_date = '2026-11-01', updated_at = NOW()
  WHERE company_id = '0fd5bd51-aa6f-465a-83c7-daacf677f5e8' AND broker_id = '574c50d6-e3d2-4bef-a4d7-4e153b6da053' AND renewal_date IS NULL; -- Bookworm Books, 75d
UPDATE broker_company_links SET renewal_date = '2026-11-06', updated_at = NOW()
  WHERE company_id = '83abd6c1-461c-491c-9389-eafb198e3c0e' AND broker_id = '574c50d6-e3d2-4bef-a4d7-4e153b6da053' AND renewal_date IS NULL; -- Bowls, 80d
UPDATE broker_company_links SET renewal_date = '2026-11-21', updated_at = NOW()
  WHERE company_id = '7f2e1c52-84ad-46eb-9685-9e82788c99e4' AND broker_id = '574c50d6-e3d2-4bef-a4d7-4e153b6da053' AND renewal_date IS NULL; -- Cake, 95d
UPDATE broker_company_links SET renewal_date = '2026-12-06', updated_at = NOW()
  WHERE company_id = '4b2f5f47-f637-49be-a6a9-aac103622b2f' AND broker_id = '574c50d6-e3d2-4bef-a4d7-4e153b6da053' AND renewal_date IS NULL; -- Coffee, 110d
UPDATE broker_company_links SET renewal_date = '2026-12-26', updated_at = NOW()
  WHERE company_id = 'd32b4494-5a9b-45f4-aece-64315c2b0970' AND broker_id = '574c50d6-e3d2-4bef-a4d7-4e153b6da053' AND renewal_date IS NULL; -- Jennifer Co, 130d
UPDATE broker_company_links SET renewal_date = '2027-01-15', updated_at = NOW()
  WHERE company_id = '7501ca6a-f9ea-4a46-addf-0073b43b5e60' AND broker_id = '574c50d6-e3d2-4bef-a4d7-4e153b6da053' AND renewal_date IS NULL; -- Limbo, 150d
UPDATE broker_company_links SET renewal_date = '2027-03-06', updated_at = NOW()
  WHERE company_id = '8ec42fb4-72d0-436f-b5cf-3851a53220a6' AND broker_id = '574c50d6-e3d2-4bef-a4d7-4e153b6da053' AND renewal_date IS NULL; -- Payment Bypass, 200d
UPDATE broker_company_links SET renewal_date = '2027-04-25', updated_at = NOW()
  WHERE company_id = 'ef710ea4-417c-4c9c-987b-e8c647e2dcdc' AND broker_id = '574c50d6-e3d2-4bef-a4d7-4e153b6da053' AND renewal_date IS NULL; -- Supply Co, 250d
UPDATE broker_company_links SET renewal_date = '2027-06-14', updated_at = NOW()
  WHERE company_id = 'c91c1534-2b4e-4c87-a103-8390f221bfcb' AND broker_id = '574c50d6-e3d2-4bef-a4d7-4e153b6da053' AND renewal_date IS NULL; -- Tea Time, 300d
