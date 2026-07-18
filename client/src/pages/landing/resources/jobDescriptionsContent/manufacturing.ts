import type { JDContent } from './types'

export const manufacturing: Record<string, JDContent> = {
  'production-operator': {
    summary: 'The Production Operator runs, monitors, and maintains manufacturing equipment to produce goods that meet quality and output targets. You will follow standardized work procedures, perform quality checks, and participate in lean/continuous improvement activities to maximize efficiency and reduce waste.',
    responsibilities: [
      'Set up, operate, and monitor production machinery per work instructions and production schedules',
      'Inspect finished products against quality standards and document findings',
      'Identify and report equipment malfunctions, quality deviations, or safety hazards',
      'Perform basic first-level preventive maintenance and machine cleaning tasks',
      'Maintain accurate production logs, counts, and downtime records',
      'Follow all GMP, ISO, and company safety standards',
      'Participate in 5S, kaizen, and continuous improvement initiatives',
    ],
    requirements: [
      'High school diploma or GED',
      '1+ year of manufacturing or production experience',
      'Ability to lift up to 50 lbs, stand for extended periods, and work in a manufacturing environment',
      'Basic mechanical aptitude and attention to quality detail',
      'Availability to work assigned shift including overtime as required',
    ],
    preferred: [
      'Lean Manufacturing or Six Sigma Yellow Belt training',
      'Experience in a regulated manufacturing environment (food, medical device, pharma)',
      'Forklift or scissor-lift certification',
    ],
  },

  'forklift-operator': {
    summary: 'The Forklift Operator safely moves materials and product throughout the warehouse or production floor using sit-down, stand-up, reach, or order-picker equipment. You will maintain accurate inventory locations, perform equipment inspections, and support a safe, efficient warehouse operation.',
    responsibilities: [
      'Operate sit-down counterbalance, reach truck, or order-picker forklift to move product',
      'Complete pre-shift equipment inspections and report deficiencies to maintenance',
      'Place, retrieve, and transfer pallets accurately based on WMS direction or verbal instruction',
      'Assist with receiving, put-away, and outbound staging activities',
      'Perform cycle counts and physical inventory tasks',
      'Maintain clear aisles, floor markings, and organized rack locations',
      'Adhere strictly to OSHA forklift safety standards and speed limits',
    ],
    requirements: [
      'Current OSHA-compliant forklift certification for applicable equipment types',
      '1+ year of forklift operation in a warehouse or distribution center',
      'Clean safety record and demonstrated commitment to forklift safety protocols',
      'Ability to lift up to 50 lbs and work in varying temperature environments',
      'Availability to work assigned shifts including weekends and overtime',
    ],
    preferred: [
      'Experience with WMS platforms (Manhattan, SAP WM, or similar)',
      'Certification on multiple forklift types (sit-down, reach, order picker)',
      'OSHA 10 General Industry certification',
    ],
  },

  'warehouse-associate': {
    summary: 'The Warehouse Associate performs core fulfillment operations including receiving, picking, packing, and shipping. You will use RF scanners and WMS systems to process transactions accurately and efficiently, supporting the distribution center\'s throughput and on-time delivery goals.',
    responsibilities: [
      'Pick orders accurately from warehouse locations using RF scanner and WMS',
      'Pack outbound orders to shipping standards and apply correct labels',
      'Receive inbound freight, verify counts against purchase orders, and putaway to assigned locations',
      'Perform cycle counts and assist with physical inventory events',
      'Keep work area clean and organized per 5S standards',
      'Operate manual pallet jacks and hand trucks safely',
      'Report discrepancies, damaged goods, and safety concerns promptly',
    ],
    requirements: [
      'High school diploma or GED',
      'Ability to lift up to 50 lbs repetitively and stand for an entire shift',
      'Basic computer and RF scanner proficiency',
      'Attention to detail and accuracy in order processing',
      'Availability to work assigned shifts including weekends and seasonal overtime',
    ],
    preferred: [
      '1+ year of warehouse or distribution-center experience',
      'Familiarity with WMS software (SAP, Manhattan, or equivalent)',
      'Forklift or pallet-jack certification',
    ],
  },

  'shipping-receiving-clerk': {
    summary: 'The Shipping & Receiving Clerk manages the documentation, processing, and tracking of all inbound and outbound freight. You will coordinate with carriers, verify shipment accuracy, maintain inventory transaction records, and resolve discrepancies promptly to keep the supply chain flowing.',
    responsibilities: [
      'Process inbound receipts by verifying quantities, conditions, and purchase orders in the ERP/WMS',
      'Prepare outbound shipments including packing lists, bills of lading (BOLs), and carrier labels',
      'Schedule carrier pickups and communicate tracking information to internal stakeholders',
      'Resolve discrepancies between POs, packing slips, and physical counts',
      'Maintain shipping/receiving logs and file freight documentation accurately',
      'Coordinate with purchasing, operations, and customer service on order status',
      'Follow proper procedures for hazardous materials documentation where applicable',
    ],
    requirements: [
      'High school diploma or equivalent',
      '2+ years of shipping/receiving, logistics, or supply-chain experience',
      'Proficiency with ERP or WMS software (SAP, Oracle, NetSuite, or similar)',
      'Strong attention to detail and document accuracy',
      'Ability to lift up to 50 lbs and operate a manual pallet jack',
    ],
    preferred: [
      "Associate's degree in Logistics, Supply Chain, or Business",
      'Experience with international freight and customs documentation',
      'Forklift certification',
    ],
  },

  'maintenance-technician': {
    summary: 'The Maintenance Technician performs preventive and reactive maintenance on manufacturing or facility equipment to maximize uptime and equipment life. You will troubleshoot mechanical, electrical, hydraulic, and pneumatic systems and work closely with production to minimize unplanned downtime.',
    responsibilities: [
      'Execute the preventive maintenance schedule for assigned equipment and systems',
      'Diagnose and repair mechanical, electrical, hydraulic, and pneumatic failures',
      'Document all maintenance activities and findings in the CMMS',
      'Respond to equipment breakdowns and collaborate with production to reduce downtime',
      'Order and manage spare parts inventory for critical assets',
      'Assist with installation, commissioning, and relocation of production equipment',
      'Follow all LOTO, confined-space, and electrical safety procedures',
    ],
    requirements: [
      '3+ years of maintenance experience in a manufacturing or industrial environment',
      'Proficiency in electrical troubleshooting (reading schematics, using a multimeter, basic PLC knowledge)',
      'Mechanical skills across motors, gearboxes, conveyors, and pneumatic systems',
      'OSHA 10 certification',
      'Ability to lift up to 50 lbs and work in physically demanding environments',
    ],
    preferred: [
      'Industrial Maintenance Mechanic certification or equivalent trade credential',
      'Experience with CMMS systems (SAP PM, Maximo, Fiix)',
      'Welding (MIG/TIG) skills',
    ],
  },

  'quality-inspector': {
    summary: 'The Quality Inspector verifies that products, components, or processes meet established specifications and quality standards. You will use precision measurement tools, maintain inspection records, and work cross-functionally to identify root causes of non-conformances and drive corrective action.',
    responsibilities: [
      'Perform incoming, in-process, and final inspections using calipers, gauges, CMM, and visual inspection',
      'Compare measurements and attributes to engineering drawings, specifications, and control plans',
      'Document inspection results in quality management systems and maintain traceability records',
      'Write Non-Conformance Reports (NCRs) and facilitate disposition of rejected material',
      'Support root cause analysis and corrective/preventive action (CAPA) processes',
      'Participate in supplier audits, customer audits, and internal quality audits',
      'Assist with calibration of measuring equipment per established schedules',
    ],
    requirements: [
      "High school diploma; associate's degree or technical certificate in Quality, Manufacturing, or related field preferred",
      '2+ years of quality inspection or quality control experience in a manufacturing environment',
      'Proficiency with precision measurement tools (calipers, micrometers, height gauges, CMM)',
      'Familiarity with ISO 9001 quality management system requirements',
      'Detail-oriented with strong documentation skills',
    ],
    preferred: [
      'ASQ Certified Quality Inspector (CQI) or Certified Quality Technician (CQT)',
      'Experience with GD&T (Geometric Dimensioning and Tolerancing)',
      'Knowledge of SPC (Statistical Process Control) methods',
    ],
  },
}
