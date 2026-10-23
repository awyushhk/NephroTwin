/**
 * web/src/lib/sample-data.ts — Bundled realistic patient profiles from the repository assets.
 */

// Sourced from frontend/assets/cascade_patient.json (58yo male with clinical risk factors)
export const CASCADE_EXAMPLE_PATIENT: Record<string, any> = {
  age: 58,
  gender: "Male",
  ethnicity: "Non-Hispanic Asian",
  education_level: 4,
  poverty_income_ratio: 2.5,
  bmi: 28.4,
  height_cm: 172,
  bp_systolic: 145,
  bp_diastolic: 92,
  blood_urea_nitrogen: 28,
  albumin_serum: 3.8,
  phosphorus: 4.2,
  bicarbonate: 22,
  calcium: 9.1,
  uric_acid: 7.4,
  diabetes: "Yes",
  insulin_use: "No",
  diabetes_pills: "Yes",
  smoking_status: "Former",
};

// Sourced from models/kidney/tabular/examples/patient.json (28yo low-risk female)
export const LOW_RISK_EXAMPLE_PATIENT: Record<string, any> = {
  age: 28,
  gender: "Female",
  ethnicity: "Non-Hispanic Asian",
  education_level: 5,
  poverty_income_ratio: 4.5,
  bmi: 22.0,
  height_cm: 165,
  bp_systolic: 110,
  bp_diastolic: 70,
  blood_urea_nitrogen: 12,
  albumin_serum: 4.5,
  phosphorus: 3.5,
  bicarbonate: 24,
  calcium: 9.5,
  uric_acid: 4.0,
  diabetes: "No",
  insulin_use: "No",
  diabetes_pills: "No",
  smoking_status: "Never",
};
