# Failure analysis

34 wrong answers out of 120 scored runs (0 further runs failed with API errors, listed at the end). 'Likely cause' is an automatic heuristic: confirm by hand.

## [A] L02 (lookup)
- **Question:** What was Infosys's net profit in fiscal 2026, in ₹ crore?
- **Expected:** 29440
- **Got (not_found):** I am sorry, but the provided context documents do not contain Infosys's net profit (profit for the year) for fiscal 2026. The available data only provides figures for fiscal 2024 and 2025.
- **Likely cause:** false refusal after retrieval miss

## [A] L07 (lookup)
- **Question:** What free cash flow did Infosys report for fiscal 2025, in ₹ crore?
- **Expected:** 34549
- **Got (not_found):** not_found
- **Likely cause:** false refusal after retrieval miss

## [A] L09 (lookup)
- **Question:** What was TCS's reported consolidated profit attributable to shareholders of the Company in FY 2026, in ₹ crore (the 'Reported' figure, after exceptional items)?
- **Expected:** 49210
- **Got (answered):** 52,820 crore
- **Likely cause:** retrieval miss: no expected page in what the model saw

## [A] L11 (lookup)
- **Question:** What was TCS's IT services attrition rate for FY 2025, in percent?
- **Expected:** 13.3
- **Got (not_found):** not_found
- **Likely cause:** false refusal after retrieval miss

## [A] L12 (lookup)
- **Question:** What was TCS's IT services attrition rate for FY 2026, in percent?
- **Expected:** 13.7
- **Got (not_found):** TCS's IT services attrition rate for FY 2026 was not found in the provided context.
- **Likely cause:** false refusal after retrieval miss

## [A] M03 (multi_step)
- **Question:** By what percent did TCS's consolidated profit attributable to shareholders, excluding exceptional items, grow from FY 2025 to FY 2026?
- **Expected:** 8.79
- **Got (not_found):** not_found
- **Likely cause:** false refusal after retrieval miss

## [A] M04 (multi_step)
- **Question:** What was TCS's profit margin in FY 2026, computed as consolidated profit attributable to shareholders (excluding exceptional items) divided by revenue from operations, in percent?
- **Expected:** 19.78
- **Got (not_found):** not_found
- **Likely cause:** false refusal after retrieval miss

## [A] M09 (multi_step)
- **Question:** By what percent did TCS's net worth grow from FY 2025 to FY 2026?
- **Expected:** 13.17
- **Got (not_found):** Net worth growth from FY 2025 to FY 2026
- **Likely cause:** false refusal after retrieval miss

## [A] C01 (comparison)
- **Question:** Which had the higher attrition rate in fiscal 2026, Infosys (voluntary attrition) or TCS (IT services attrition)? Give both figures.
- **Expected:** TCS was higher: 13.7% for TCS versus 12.6% for Infosys.
- **Got (not_found):** I searched for the fiscal year 2026 attrition rates for Infosys and TCS, but the provided context does not contain this information.
- **Likely cause:** false refusal after retrieval miss

## [A] C02 (comparison)
- **Question:** Which had the higher net profit margin in FY2026, Infosys (net profit) or TCS (reported consolidated profit attributable to shareholders)? Give both margins.
- **Expected:** TCS: 18.43% versus Infosys: 16.48%.
- **Got (not_found):** not_found
- **Likely cause:** false refusal after retrieval miss

## [A] C03 (comparison)
- **Question:** Among Infosys, TCS and Wipro, which grew its revenue fastest from FY2025 to FY2026 (in ₹)? Give the growth rates.
- **Expected:** Infosys, at about 9.61% versus TCS 4.58% and Wipro 4.17%.
- **Got (not_found):** not_found
- **Likely cause:** false refusal after retrieval miss

## [A] C04 (comparison)
- **Question:** Which of Infosys, TCS and Wipro had the largest revenue in FY2026 in rupee terms?
- **Expected:** TCS (₹267,021 crore), ahead of Infosys (₹178,650 crore) and Wipro (₹928,093 million, about ₹92,809 crore).
- **Got (not_found):** not_found
- **Likely cause:** false refusal after retrieval miss

## [A] C05 (comparison)
- **Question:** Whose net worth grew faster from FY2025 to FY2026, TCS or Wipro? Give both growth rates.
- **Expected:** TCS: 13.17% versus Wipro: 6.92%.
- **Got (not_found):** I am sorry, but the provided context does not contain information about TCS's net worth or its growth rate.
- **Likely cause:** false refusal: expected page was retrieved but model refused

## [A] C06 (comparison)
- **Question:** Which has the higher share of women on its Board of Directors in its latest report, Infosys or TCS? Give both percentages.
- **Expected:** TCS at 25% versus Infosys at 22.2%.
- **Got (not_found):** The provided context does not contain information regarding the share of women on the Board of Directors for TCS, nor does it provide the percentage for Infosys.
- **Likely cause:** false refusal after retrieval miss

## [A] C07 (comparison)
- **Question:** Did Infosys's voluntary attrition for permanent employees go up or down from fiscal 2025 to fiscal 2026? Give both figures.
- **Expected:** It went down: from 14.1% in fiscal 2025 to 12.6% in fiscal 2026.
- **Got (not_found):** Searched for Infosys voluntary attrition for permanent employees for fiscal 2025 and fiscal 2026, but the information was not found in the provided context.
- **Likely cause:** false refusal after retrieval miss

## [A] C08 (comparison)
- **Question:** Did TCS's IT services attrition rate rise or fall from FY 2025 to FY 2026? Give both figures.
- **Expected:** It rose slightly: from 13.3% in FY 2025 to 13.7% in FY 2026.
- **Got (not_found):** I searched for TCS's IT services attrition rate for FY 2025 and FY 2026, but the provided context does not contain this information.
- **Likely cause:** false refusal after retrieval miss

## [B] L02 (lookup)
- **Question:** What was Infosys's net profit in fiscal 2026, in ₹ crore?
- **Expected:** 29440
- **Got (not_found):** not_found
- **Likely cause:** false refusal after retrieval miss

## [B] L08 (lookup)
- **Question:** What was TCS's revenue from operations in FY 2026, in ₹ crore?
- **Expected:** 267021
- **Got (not_found):** I am sorry, but the provided context does not contain TCS's revenue from operations for FY 2026 (it only provides revenue from operations for FY 2025 and earlier, and foreign exchange earnings for FY 2026).
- **Likely cause:** false refusal after retrieval miss

## [B] L09 (lookup)
- **Question:** What was TCS's reported consolidated profit attributable to shareholders of the Company in FY 2026, in ₹ crore (the 'Reported' figure, after exceptional items)?
- **Expected:** 49210
- **Got (answered):** 52,820
- **Likely cause:** retrieval miss: no expected page in what the model saw

## [B] M03 (multi_step)
- **Question:** By what percent did TCS's consolidated profit attributable to shareholders, excluding exceptional items, grow from FY 2025 to FY 2026?
- **Expected:** 8.79
- **Got (not_found):** not_found
- **Likely cause:** false refusal after retrieval miss

## [B] M04 (multi_step)
- **Question:** What was TCS's profit margin in FY 2026, computed as consolidated profit attributable to shareholders (excluding exceptional items) divided by revenue from operations, in percent?
- **Expected:** 19.78
- **Got (not_found):** not_found
- **Likely cause:** false refusal after retrieval miss

## [B] M09 (multi_step)
- **Question:** By what percent did TCS's net worth grow from FY 2025 to FY 2026?
- **Expected:** 13.17
- **Got (not_found):** not_found
- **Likely cause:** false refusal after retrieval miss

## [B] M10 (multi_step)
- **Question:** By what percent did Infosys's basic earnings per share grow from fiscal 2025 to fiscal 2026?
- **Expected:** 10.98
- **Got (answered):** Infosys's basic earnings per share on a consolidated basis grew from ₹64.50 in fiscal 2025 to ₹71.58 in fiscal 2026.
- **Likely cause:** retrieval miss: no expected page in what the model saw

## [B] C02 (comparison)
- **Question:** Which had the higher net profit margin in FY2026, Infosys (net profit) or TCS (reported consolidated profit attributable to shareholders)? Give both margins.
- **Expected:** TCS: 18.43% versus Infosys: 16.48%.
- **Got (not_found):** Searched for net profit margins for Infosys and TCS in FY2026, but the provided context does not contain data for FY2026 net profit margins for either company.
- **Likely cause:** false refusal after retrieval miss

## [B] C03 (comparison)
- **Question:** Among Infosys, TCS and Wipro, which grew its revenue fastest from FY2025 to FY2026 (in ₹)? Give the growth rates.
- **Expected:** Infosys, at about 9.61% versus TCS 4.58% and Wipro 4.17%.
- **Got (answered):** Based on the provided context, Infosys reported revenue growth of 9.6% for FY 2026 (page 26). TCS reported revenue growth of 4.6% on a reported basis in FY 2026 (page 58). Wipro's revenue is reported in USD ($10.5 billion, a 1.6% decline in constant currency on page 21) and does not provide an overall ₹ revenue growth rate for FY2026. Therefore, among the companies with reported growth rates, Infosys grew its revenue fastest at 9.6%, followed by TCS at 4.6%.
- **Likely cause:** retrieval miss: no expected page in what the model saw

## [B] C04 (comparison)
- **Question:** Which of Infosys, TCS and Wipro had the largest revenue in FY2026 in rupee terms?
- **Expected:** TCS (₹267,021 crore), ahead of Infosys (₹178,650 crore) and Wipro (₹928,093 million, about ₹92,809 crore).
- **Got (answered):** In FY2026, TCS had a revenue from operations of ₹267,021 crore.
- **Likely cause:** reasoning/extraction error: right page retrieved, wrong answer

## [B] C05 (comparison)
- **Question:** Whose net worth grew faster from FY2025 to FY2026, TCS or Wipro? Give both growth rates.
- **Expected:** TCS: 13.17% versus Wipro: 6.92%.
- **Got (not_found):** I am sorry, but the provided context does not contain information about TCS's net worth or its growth rate.
- **Likely cause:** false refusal: expected page was retrieved but model refused

## [B] C06 (comparison)
- **Question:** Which has the higher share of women on its Board of Directors in its latest report, Infosys or TCS? Give both percentages.
- **Expected:** TCS at 25% versus Infosys at 22.2%.
- **Got (answered):** TCS has a higher share of women on its Board of Directors at 25% (as of FY26), while Infosys' latest report does not provide the exact percentage of women on its Board in the provided text.
- **Likely cause:** retrieval miss: no expected page in what the model saw

## [B] C08 (comparison)
- **Question:** Did TCS's IT services attrition rate rise or fall from FY 2025 to FY 2026? Give both figures.
- **Expected:** It rose slightly: from 13.3% in FY 2025 to 13.7% in FY 2026.
- **Got (not_found):** The provided context does not contain the voluntary IT services attrition rate for FY 2025 (it only states that for FY 2026 the rate was 13.7%). Therefore, a comparison cannot be made.
- **Likely cause:** false refusal: expected page was retrieved but model refused

## [C] L14 (lookup)
- **Question:** What was Wipro's operating margin in FY26, in percent?
- **Expected:** 16.3
- **Got (answered):** Wipro's IT Services operating margin in FY26 was 17.1%.
- **Likely cause:** reasoning/extraction error: right page retrieved, wrong answer

## [C] C02 (comparison)
- **Question:** Which had the higher net profit margin in FY2026, Infosys (net profit) or TCS (reported consolidated profit attributable to shareholders)? Give both margins.
- **Expected:** TCS: 18.43% versus Infosys: 16.48%.
- **Got (answered):** TCS had the higher net profit margin in FY2026. TCS' reported consolidated profit after tax attributable to shareholders was ₹49,210 crore on revenue from operations of ₹2,67,021 crore, giving a net profit margin of approximately 18.43% (or 19.8% including other items as stated in management's financial overview). Infosys' net profit (profit after tax) was ₹29,474 crore on revenue from operations of ₹1,78,650 crore, resulting in a net profit margin of approximately 16.5%.
- **Likely cause:** reasoning/extraction error: right page retrieved, wrong answer

## [C] C03 (comparison)
- **Question:** Among Infosys, TCS and Wipro, which grew its revenue fastest from FY2025 to FY2026 (in ₹)? Give the growth rates.
- **Expected:** Infosys, at about 9.61% versus TCS 4.58% and Wipro 4.17%.
- **Got (answered):** Among Infosys, TCS, and Wipro, **Infosys** grew its revenue the fastest from FY2025 to FY2026. 

**Consolidated Revenue Growth Rates (Revenue from Operations):**
- **Infosys:** Grew by **9.61%** (from ₹1,62,990 crore in FY2025 to ₹1,78,650 crore in FY2026)
- **TCS:** Grew by **4.58%** (from ₹2,55,324 crore in FY2025 to ₹2,67,021 crore in FY2026)
- **Wipro:** Grew by **3.97%** (from ₹890,884 million in FY2025 to ₹926,240 million in FY2026)

*(Note: On a standalone basis, Infosys grew by 9.0%, TCS grew by 2.83%, and Infosys remains the fastest growing.)*
- **Likely cause:** reasoning/extraction error: right page retrieved, wrong answer

## [C] C05 (comparison)
- **Question:** Whose net worth grew faster from FY2025 to FY2026, TCS or Wipro? Give both growth rates.
- **Expected:** TCS: 13.17% versus Wipro: 6.92%.
- **Got (not_found):** Based on the provided documents, net worth (total equity) figures and growth rates for TCS and Wipro from FY2025 to FY2026 are not sufficiently available in the search results.
- **Likely cause:** false refusal after retrieval miss

## [C] C06 (comparison)
- **Question:** Which has the higher share of women on its Board of Directors in its latest report, Infosys or TCS? Give both percentages.
- **Expected:** TCS at 25% versus Infosys at 22.2%.
- **Got (answered):** Infosys has the higher share of women on its Board of Directors in its latest report (FY26), with 30% (as of April 23, 2026, or 22.2% as of March 31, 2026), compared to TCS, which has 25% (2 out of 8 directors as of March 31, 2026).
- **Likely cause:** reasoning/extraction error: right page retrieved, wrong answer

