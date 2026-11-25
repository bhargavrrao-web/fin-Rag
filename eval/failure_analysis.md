# Failure analysis

2 wrong answers out of 15 scored runs (0 further runs failed with API errors, listed at the end). 'Likely cause' is an automatic heuristic: confirm by hand.

## [A] C01 (comparison)
- **Question:** Which had the higher attrition rate in fiscal 2026, Infosys (voluntary attrition) or TCS (IT services attrition)? Give both figures.
- **Expected:** TCS was higher: 13.7% for TCS versus 12.6% for Infosys.
- **Got (not_found):** -
- **Likely cause:** false refusal after retrieval miss

## [C] C01 (comparison)
- **Question:** Which had the higher attrition rate in fiscal 2026, Infosys (voluntary attrition) or TCS (IT services attrition)? Give both figures.
- **Expected:** TCS was higher: 13.7% for TCS versus 12.6% for Infosys.
- **Got (answered):** In fiscal 2026, TCS had the higher attrition rate. TCS's IT services turnover rate for permanent employees was 13.7% total (13.8% for males, 13.4% for females). Infosys voluntary attrition figures for FY26 were not found in the documents.
- **Likely cause:** retrieval miss: no expected page in what the model saw

