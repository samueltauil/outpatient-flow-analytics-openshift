-- =============================================================================
-- Seed Data: Facilities and Procedure Catalog (50+ procedures)
-- Synthetic Outpatient Flow Analytics Demo
-- =============================================================================

-- Facilities
INSERT INTO facility (facility_id, facility_name, timezone) VALUES
    ('HOSP_A', 'Metro General Ambulatory Center',    'America/New_York'),
    ('HOSP_B', 'Lakeside Outpatient Surgery Center', 'America/Chicago'),
    ('HOSP_C', 'Pacific Coast Surgical Institute',   'America/Los_Angeles')
ON CONFLICT (facility_id) DO NOTHING;

-- =============================================================================
-- Procedure Catalog
-- Duration parameters are log-normal (mu, sigma) for minutes.
-- ln(median_minutes) ≈ mu; sigma controls spread.
-- =============================================================================

-- GI / Endoscopy (high volume, short procedures)
INSERT INTO procedure_catalog (procedure_type, service_line,
    checkin_to_preop_mu, checkin_to_preop_sigma,
    preop_to_op_mu, preop_to_op_sigma,
    op_to_postop_mu, op_to_postop_sigma,
    postop_to_discharge_mu, postop_to_discharge_sigma) VALUES
('Diagnostic colonoscopy',              'GI',           2.71, 0.35, 2.89, 0.30, 2.89, 0.25, 3.22, 0.35),
('Screening colonoscopy (average-risk)','GI',           2.71, 0.35, 2.89, 0.30, 2.77, 0.25, 3.00, 0.30),
('Screening colonoscopy (high-risk)',   'GI',           2.71, 0.35, 2.89, 0.30, 3.00, 0.30, 3.22, 0.35),
('Colonoscopy with biopsy',            'GI',           2.71, 0.35, 2.89, 0.30, 3.00, 0.30, 3.22, 0.35),
('Colonoscopy with polypectomy',       'GI',           2.71, 0.35, 2.89, 0.30, 3.18, 0.30, 3.40, 0.35),
('EGD with biopsy',                    'GI',           2.71, 0.35, 2.89, 0.30, 2.71, 0.25, 3.00, 0.30),
('Upper endoscopy (diagnostic)',       'GI',           2.71, 0.30, 2.89, 0.25, 2.56, 0.25, 2.89, 0.30),
('Flexible sigmoidoscopy',            'GI',           2.71, 0.30, 2.77, 0.25, 2.56, 0.25, 2.77, 0.30),
('ERCP',                               'GI',           2.89, 0.35, 3.00, 0.30, 3.69, 0.35, 3.91, 0.40),
('Capsule endoscopy',                  'GI',           2.56, 0.30, 2.56, 0.25, 2.30, 0.20, 2.56, 0.25),

-- Ophthalmology (short intra-op, moderate recovery)
('Cataract extraction with IOL',       'Ophthalmology', 2.89, 0.30, 2.89, 0.25, 2.56, 0.25, 3.22, 0.30),
('YAG laser capsulotomy',             'Ophthalmology', 2.56, 0.25, 2.56, 0.20, 1.95, 0.20, 2.56, 0.25),
('Pterygium excision',                'Ophthalmology', 2.77, 0.30, 2.89, 0.25, 2.89, 0.30, 3.00, 0.30),
('Blepharoplasty',                    'Ophthalmology', 2.89, 0.30, 3.00, 0.25, 3.40, 0.35, 3.40, 0.35),

-- ENT / Otolaryngology
('Tympanostomy tube placement',        'ENT',           2.71, 0.30, 2.89, 0.25, 2.30, 0.20, 2.89, 0.30),
('Tonsillectomy',                      'ENT',           2.89, 0.30, 3.00, 0.25, 3.22, 0.30, 3.69, 0.40),
('Adenoidectomy',                      'ENT',           2.77, 0.30, 2.89, 0.25, 2.89, 0.25, 3.40, 0.35),
('Septoplasty',                        'ENT',           2.89, 0.35, 3.00, 0.30, 3.69, 0.35, 3.69, 0.40),
('FESS (sinus surgery)',               'ENT',           2.89, 0.35, 3.00, 0.30, 3.91, 0.35, 3.91, 0.40),
('Inferior turbinate reduction',       'ENT',           2.77, 0.30, 2.89, 0.25, 2.89, 0.25, 3.22, 0.30),

-- Orthopedics / Sports Medicine (moderate-long intra-op, longer recovery)
('Knee arthroscopy with meniscectomy', 'Orthopedics',   2.89, 0.35, 3.22, 0.30, 3.69, 0.35, 4.09, 0.40),
('Knee arthroscopy (diagnostic)',      'Orthopedics',   2.89, 0.35, 3.22, 0.30, 3.40, 0.30, 3.91, 0.40),
('Shoulder arthroscopy',               'Orthopedics',   2.89, 0.35, 3.22, 0.30, 4.09, 0.40, 4.25, 0.45),
('Rotator cuff repair',               'Orthopedics',   2.89, 0.35, 3.22, 0.30, 4.25, 0.40, 4.38, 0.45),
('Carpal tunnel release',             'Orthopedics',   2.71, 0.30, 2.89, 0.25, 2.56, 0.25, 3.00, 0.30),
('Trigger finger release',            'Orthopedics',   2.56, 0.30, 2.77, 0.25, 2.30, 0.20, 2.77, 0.25),
('ACL reconstruction',                'Orthopedics',   3.00, 0.35, 3.40, 0.30, 4.38, 0.40, 4.50, 0.45),
('Ankle arthroscopy',                  'Orthopedics',   2.89, 0.35, 3.22, 0.30, 3.69, 0.35, 3.91, 0.40),
('Bunionectomy',                       'Orthopedics',   2.89, 0.35, 3.22, 0.30, 3.69, 0.35, 4.09, 0.40),
('Hammertoe correction',              'Orthopedics',   2.77, 0.35, 3.00, 0.30, 3.22, 0.30, 3.69, 0.35),

-- Pain / Spine Interventions (short procedure, short recovery)
('Lumbar epidural steroid injection',  'Pain',          2.56, 0.30, 2.71, 0.25, 2.30, 0.20, 2.77, 0.30),
('Lumbar facet joint injection',       'Pain',          2.56, 0.30, 2.71, 0.25, 2.30, 0.20, 2.77, 0.30),
('RF ablation facet joint nerves',     'Pain',          2.71, 0.30, 2.89, 0.25, 2.89, 0.30, 3.22, 0.35),
('Cervical epidural steroid injection','Pain',          2.56, 0.30, 2.77, 0.25, 2.30, 0.20, 2.89, 0.30),
('Spinal cord stimulator trial',       'Pain',          2.89, 0.35, 3.22, 0.30, 3.91, 0.40, 4.09, 0.45),

-- Urology
('Cystoscopy (diagnostic)',            'Urology',       2.56, 0.30, 2.77, 0.25, 2.30, 0.20, 2.77, 0.25),
('Ureteroscopy with stent',           'Urology',       2.89, 0.35, 3.00, 0.30, 3.40, 0.35, 3.69, 0.40),
('Vasectomy',                          'Urology',       2.56, 0.30, 2.71, 0.25, 2.56, 0.25, 2.89, 0.30),
('Prostate biopsy',                    'Urology',       2.71, 0.30, 2.89, 0.25, 2.77, 0.25, 3.22, 0.35),
('ESWL (lithotripsy)',                 'Urology',       2.77, 0.35, 2.89, 0.30, 3.22, 0.30, 3.69, 0.40),

-- Gynecology
('Dilation and curettage',            'Gynecology',    2.71, 0.30, 2.89, 0.25, 2.56, 0.25, 3.22, 0.35),
('Hysteroscopy with polypectomy',      'Gynecology',    2.77, 0.30, 2.89, 0.25, 2.89, 0.25, 3.40, 0.35),
('Endometrial ablation',              'Gynecology',    2.77, 0.30, 2.89, 0.25, 3.00, 0.30, 3.40, 0.35),
('LEEP procedure',                     'Gynecology',    2.56, 0.30, 2.77, 0.25, 2.56, 0.25, 2.89, 0.30),
('Uterine fibroid embolization',       'Gynecology',    2.89, 0.35, 3.22, 0.30, 3.91, 0.40, 4.25, 0.45),
('Tubal ligation',                     'Gynecology',    2.77, 0.30, 3.00, 0.25, 3.22, 0.30, 3.69, 0.40),

-- Dermatology / Plastic / Minor
('Skin lesion excision',               'Dermatology',   2.56, 0.25, 2.56, 0.20, 2.56, 0.25, 2.56, 0.25),
('Mohs surgery',                       'Dermatology',   2.71, 0.30, 2.89, 0.25, 3.69, 0.40, 3.40, 0.35),
('Incision and drainage of abscess',   'Dermatology',   2.30, 0.25, 2.30, 0.20, 2.30, 0.20, 2.56, 0.25),
('Scar revision',                      'Dermatology',   2.71, 0.30, 2.77, 0.25, 3.00, 0.30, 3.00, 0.30),
('Lipoma excision',                    'Dermatology',   2.56, 0.25, 2.56, 0.20, 2.71, 0.25, 2.71, 0.25),

-- General Surgery (ambulatory)
('Laparoscopic cholecystectomy',       'General',       3.00, 0.35, 3.22, 0.30, 3.91, 0.35, 4.09, 0.40),
('Inguinal hernia repair',            'General',       2.89, 0.35, 3.22, 0.30, 3.69, 0.35, 4.09, 0.40),
('Umbilical hernia repair',           'General',       2.89, 0.35, 3.00, 0.30, 3.40, 0.30, 3.69, 0.35),
('Hemorrhoidectomy',                   'General',       2.71, 0.30, 2.89, 0.25, 3.00, 0.30, 3.40, 0.35),
('Breast lumpectomy',                  'General',       2.89, 0.35, 3.22, 0.30, 3.69, 0.35, 4.09, 0.40),

-- Cardiology (selected outpatient)
('Diagnostic cardiac catheterization', 'Cardiology',    3.00, 0.40, 3.40, 0.35, 3.91, 0.40, 4.38, 0.45),
('Cardioversion',                      'Cardiology',    2.77, 0.30, 2.89, 0.25, 2.56, 0.25, 3.40, 0.35)
ON CONFLICT (procedure_type) DO NOTHING;
