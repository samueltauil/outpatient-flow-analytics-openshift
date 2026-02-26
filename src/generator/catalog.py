"""
Procedure catalog with 58 outpatient procedure types and their
log-normal duration distribution parameters.

Each procedure has four duration phases (checkin→preop, preop→op, op→postop, postop→discharge).
Parameters are (mu, sigma) for log-normal distribution where the generated
value in minutes = exp(Normal(mu, sigma)).
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple

@dataclass(frozen=True)
class ProcedureDef:
    procedure_type: str
    service_line: str
    checkin_to_preop: Tuple[float, float]   # (mu, sigma)
    preop_to_op: Tuple[float, float]
    op_to_postop: Tuple[float, float]
    postop_to_discharge: Tuple[float, float]


# Facility definitions with procedure-mix weights
FACILITIES = {
    "HOSP_A": {
        "name": "Metro General Ambulatory Center",
        "timezone": "America/New_York",
        "bias": {"GI": 2.0, "Ophthalmology": 1.5, "Dermatology": 1.5},
        "daily_volume": (60, 100),  # min, max cases per day
    },
    "HOSP_B": {
        "name": "Lakeside Outpatient Surgery Center",
        "timezone": "America/Chicago",
        "bias": {"Orthopedics": 2.0, "Pain": 2.0, "General": 1.5},
        "daily_volume": (40, 80),
    },
    "HOSP_C": {
        "name": "Pacific Coast Surgical Institute",
        "timezone": "America/Los_Angeles",
        "bias": {"ENT": 1.5, "Urology": 1.5, "Gynecology": 1.5, "Cardiology": 1.5},
        "daily_volume": (50, 90),
    },
}

# Anesthesia types and their relative weights per service line
ANESTHESIA_TYPES: Dict[str, List[Tuple[str, float]]] = {
    "GI":            [("MAC", 0.6), ("Conscious sedation", 0.3), ("General", 0.1)],
    "Ophthalmology": [("Topical", 0.4), ("Local", 0.3), ("MAC", 0.3)],
    "ENT":           [("General", 0.7), ("MAC", 0.2), ("Local", 0.1)],
    "Orthopedics":   [("General", 0.4), ("Regional", 0.4), ("MAC", 0.2)],
    "Pain":          [("Local", 0.5), ("MAC", 0.3), ("Conscious sedation", 0.2)],
    "Urology":       [("General", 0.3), ("MAC", 0.3), ("Spinal", 0.2), ("Local", 0.2)],
    "Gynecology":    [("General", 0.5), ("MAC", 0.3), ("Regional", 0.2)],
    "Dermatology":   [("Local", 0.7), ("MAC", 0.2), ("Conscious sedation", 0.1)],
    "General":       [("General", 0.6), ("MAC", 0.2), ("Regional", 0.2)],
    "Cardiology":    [("MAC", 0.4), ("Conscious sedation", 0.3), ("General", 0.3)],
}

PROCEDURES: List[ProcedureDef] = [
    # GI / Endoscopy
    ProcedureDef("Diagnostic colonoscopy",              "GI", (2.71,0.35),(2.89,0.30),(2.89,0.25),(3.22,0.35)),
    ProcedureDef("Screening colonoscopy (average-risk)","GI", (2.71,0.35),(2.89,0.30),(2.77,0.25),(3.00,0.30)),
    ProcedureDef("Screening colonoscopy (high-risk)",   "GI", (2.71,0.35),(2.89,0.30),(3.00,0.30),(3.22,0.35)),
    ProcedureDef("Colonoscopy with biopsy",            "GI", (2.71,0.35),(2.89,0.30),(3.00,0.30),(3.22,0.35)),
    ProcedureDef("Colonoscopy with polypectomy",       "GI", (2.71,0.35),(2.89,0.30),(3.18,0.30),(3.40,0.35)),
    ProcedureDef("EGD with biopsy",                    "GI", (2.71,0.35),(2.89,0.30),(2.71,0.25),(3.00,0.30)),
    ProcedureDef("Upper endoscopy (diagnostic)",       "GI", (2.71,0.30),(2.89,0.25),(2.56,0.25),(2.89,0.30)),
    ProcedureDef("Flexible sigmoidoscopy",             "GI", (2.71,0.30),(2.77,0.25),(2.56,0.25),(2.77,0.30)),
    ProcedureDef("ERCP",                               "GI", (2.89,0.35),(3.00,0.30),(3.69,0.35),(3.91,0.40)),
    ProcedureDef("Capsule endoscopy",                  "GI", (2.56,0.30),(2.56,0.25),(2.30,0.20),(2.56,0.25)),
    # Ophthalmology
    ProcedureDef("Cataract extraction with IOL",       "Ophthalmology", (2.89,0.30),(2.89,0.25),(2.56,0.25),(3.22,0.30)),
    ProcedureDef("YAG laser capsulotomy",              "Ophthalmology", (2.56,0.25),(2.56,0.20),(1.95,0.20),(2.56,0.25)),
    ProcedureDef("Pterygium excision",                 "Ophthalmology", (2.77,0.30),(2.89,0.25),(2.89,0.30),(3.00,0.30)),
    ProcedureDef("Blepharoplasty",                     "Ophthalmology", (2.89,0.30),(3.00,0.25),(3.40,0.35),(3.40,0.35)),
    # ENT
    ProcedureDef("Tympanostomy tube placement",        "ENT", (2.71,0.30),(2.89,0.25),(2.30,0.20),(2.89,0.30)),
    ProcedureDef("Tonsillectomy",                      "ENT", (2.89,0.30),(3.00,0.25),(3.22,0.30),(3.69,0.40)),
    ProcedureDef("Adenoidectomy",                      "ENT", (2.77,0.30),(2.89,0.25),(2.89,0.25),(3.40,0.35)),
    ProcedureDef("Septoplasty",                        "ENT", (2.89,0.35),(3.00,0.30),(3.69,0.35),(3.69,0.40)),
    ProcedureDef("FESS (sinus surgery)",               "ENT", (2.89,0.35),(3.00,0.30),(3.91,0.35),(3.91,0.40)),
    ProcedureDef("Inferior turbinate reduction",       "ENT", (2.77,0.30),(2.89,0.25),(2.89,0.25),(3.22,0.30)),
    # Orthopedics
    ProcedureDef("Knee arthroscopy with meniscectomy", "Orthopedics", (2.89,0.35),(3.22,0.30),(3.69,0.35),(4.09,0.40)),
    ProcedureDef("Knee arthroscopy (diagnostic)",      "Orthopedics", (2.89,0.35),(3.22,0.30),(3.40,0.30),(3.91,0.40)),
    ProcedureDef("Shoulder arthroscopy",               "Orthopedics", (2.89,0.35),(3.22,0.30),(4.09,0.40),(4.25,0.45)),
    ProcedureDef("Rotator cuff repair",                "Orthopedics", (2.89,0.35),(3.22,0.30),(4.25,0.40),(4.38,0.45)),
    ProcedureDef("Carpal tunnel release",              "Orthopedics", (2.71,0.30),(2.89,0.25),(2.56,0.25),(3.00,0.30)),
    ProcedureDef("Trigger finger release",             "Orthopedics", (2.56,0.30),(2.77,0.25),(2.30,0.20),(2.77,0.25)),
    ProcedureDef("ACL reconstruction",                 "Orthopedics", (3.00,0.35),(3.40,0.30),(4.38,0.40),(4.50,0.45)),
    ProcedureDef("Ankle arthroscopy",                  "Orthopedics", (2.89,0.35),(3.22,0.30),(3.69,0.35),(3.91,0.40)),
    ProcedureDef("Bunionectomy",                       "Orthopedics", (2.89,0.35),(3.22,0.30),(3.69,0.35),(4.09,0.40)),
    ProcedureDef("Hammertoe correction",               "Orthopedics", (2.77,0.35),(3.00,0.30),(3.22,0.30),(3.69,0.35)),
    # Pain
    ProcedureDef("Lumbar epidural steroid injection",   "Pain", (2.56,0.30),(2.71,0.25),(2.30,0.20),(2.77,0.30)),
    ProcedureDef("Lumbar facet joint injection",        "Pain", (2.56,0.30),(2.71,0.25),(2.30,0.20),(2.77,0.30)),
    ProcedureDef("RF ablation facet joint nerves",      "Pain", (2.71,0.30),(2.89,0.25),(2.89,0.30),(3.22,0.35)),
    ProcedureDef("Cervical epidural steroid injection", "Pain", (2.56,0.30),(2.77,0.25),(2.30,0.20),(2.89,0.30)),
    ProcedureDef("Spinal cord stimulator trial",        "Pain", (2.89,0.35),(3.22,0.30),(3.91,0.40),(4.09,0.45)),
    # Urology
    ProcedureDef("Cystoscopy (diagnostic)",            "Urology", (2.56,0.30),(2.77,0.25),(2.30,0.20),(2.77,0.25)),
    ProcedureDef("Ureteroscopy with stent",            "Urology", (2.89,0.35),(3.00,0.30),(3.40,0.35),(3.69,0.40)),
    ProcedureDef("Vasectomy",                          "Urology", (2.56,0.30),(2.71,0.25),(2.56,0.25),(2.89,0.30)),
    ProcedureDef("Prostate biopsy",                    "Urology", (2.71,0.30),(2.89,0.25),(2.77,0.25),(3.22,0.35)),
    ProcedureDef("ESWL (lithotripsy)",                 "Urology", (2.77,0.35),(2.89,0.30),(3.22,0.30),(3.69,0.40)),
    # Gynecology
    ProcedureDef("Dilation and curettage",             "Gynecology", (2.71,0.30),(2.89,0.25),(2.56,0.25),(3.22,0.35)),
    ProcedureDef("Hysteroscopy with polypectomy",      "Gynecology", (2.77,0.30),(2.89,0.25),(2.89,0.25),(3.40,0.35)),
    ProcedureDef("Endometrial ablation",               "Gynecology", (2.77,0.30),(2.89,0.25),(3.00,0.30),(3.40,0.35)),
    ProcedureDef("LEEP procedure",                     "Gynecology", (2.56,0.30),(2.77,0.25),(2.56,0.25),(2.89,0.30)),
    ProcedureDef("Uterine fibroid embolization",       "Gynecology", (2.89,0.35),(3.22,0.30),(3.91,0.40),(4.25,0.45)),
    ProcedureDef("Tubal ligation",                     "Gynecology", (2.77,0.30),(3.00,0.25),(3.22,0.30),(3.69,0.40)),
    # Dermatology
    ProcedureDef("Skin lesion excision",               "Dermatology", (2.56,0.25),(2.56,0.20),(2.56,0.25),(2.56,0.25)),
    ProcedureDef("Mohs surgery",                       "Dermatology", (2.71,0.30),(2.89,0.25),(3.69,0.40),(3.40,0.35)),
    ProcedureDef("Incision and drainage of abscess",   "Dermatology", (2.30,0.25),(2.30,0.20),(2.30,0.20),(2.56,0.25)),
    ProcedureDef("Scar revision",                      "Dermatology", (2.71,0.30),(2.77,0.25),(3.00,0.30),(3.00,0.30)),
    ProcedureDef("Lipoma excision",                    "Dermatology", (2.56,0.25),(2.56,0.20),(2.71,0.25),(2.71,0.25)),
    # General Surgery
    ProcedureDef("Laparoscopic cholecystectomy",       "General", (3.00,0.35),(3.22,0.30),(3.91,0.35),(4.09,0.40)),
    ProcedureDef("Inguinal hernia repair",             "General", (2.89,0.35),(3.22,0.30),(3.69,0.35),(4.09,0.40)),
    ProcedureDef("Umbilical hernia repair",            "General", (2.89,0.35),(3.00,0.30),(3.40,0.30),(3.69,0.35)),
    ProcedureDef("Hemorrhoidectomy",                   "General", (2.71,0.30),(2.89,0.25),(3.00,0.30),(3.40,0.35)),
    ProcedureDef("Breast lumpectomy",                  "General", (2.89,0.35),(3.22,0.30),(3.69,0.35),(4.09,0.40)),
    # Cardiology
    ProcedureDef("Diagnostic cardiac catheterization", "Cardiology", (3.00,0.40),(3.40,0.35),(3.91,0.40),(4.38,0.45)),
    ProcedureDef("Cardioversion",                      "Cardiology", (2.77,0.30),(2.89,0.25),(2.56,0.25),(3.40,0.35)),
]

SERVICE_LINES = sorted(set(p.service_line for p in PROCEDURES))

def get_procedures_by_service_line(service_line: str) -> List[ProcedureDef]:
    return [p for p in PROCEDURES if p.service_line == service_line]
