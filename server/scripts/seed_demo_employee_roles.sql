-- Give Sea Cafe (org 19e02494…) realistic, REPEATED job roles with intra-role pay
-- spread, so the agentic features (WC class-code auto-map + pay-equity dispersion)
-- produce meaningful demo output. The faker seed gave every employee a unique
-- gibberish title, which defeats both. UPDATE only (no insert/delete); idempotent.
--   docker exec -i matcha-postgres psql -U matcha -d matcha < server/scripts/seed_demo_employee_roles.sql

WITH ranked AS (
  SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS rn
  FROM employees WHERE org_id = '19e02494-8427-44b5-9c1b-98064b7e94e1'
),
asg(rn, title, cls, rate) AS (VALUES
  (1,'Barista','hourly',16.50),(2,'Barista','hourly',17.00),(3,'Barista','hourly',18.00),
  (4,'Barista','hourly',19.50),(5,'Barista','hourly',21.00),(6,'Barista','hourly',22.00),
  (7,'Line Cook','hourly',18.00),(8,'Line Cook','hourly',20.00),(9,'Line Cook','hourly',22.00),
  (10,'Line Cook','hourly',24.00),(11,'Line Cook','hourly',26.00),
  (12,'Cashier','hourly',15.00),(13,'Cashier','hourly',16.00),(14,'Cashier','hourly',17.00),
  (15,'Shift Supervisor','hourly',24.00),(16,'Shift Supervisor','hourly',26.00),(17,'Shift Supervisor','hourly',28.00),
  (18,'General Manager','exempt',68000.00),(19,'General Manager','exempt',95000.00),
  (20,'Assistant Manager','exempt',58000.00)
)
UPDATE employees e
SET job_title = asg.title, pay_classification = asg.cls, pay_rate = asg.rate
FROM ranked r JOIN asg ON asg.rn = r.rn
WHERE e.id = r.id;
