# Thesis references (2026-11-22)

33 entries in `references.bib`: 24 papers + 1 dataset (verified by DOI against Crossref / DataCite) and 8 manual entries (book, datasheets, standards).

## Papers and dataset (DOI verified)

| Key | First author, year | Venue | DOI | Used for |
|---|---|---|---|---|
| kirkaldy2024 | Kirkaldy 2024 | Journal of Power Sources | 10.1016/j.jpowsour.2024.234185 | M50T data: OCV, R0/R1, capacity, Ea, ageing, cell spread |
| chen2020 | Chen 2020 | Journal of The Electrochemical Society | 10.1149/1945-7111/ab9050 | LG M50 parameters; earlier OCV table (comparison) |
| oregan2022 | O'Regan 2022 | Electrochimica Acta | 10.1016/j.electacta.2022.140700 | M50T thermal-electrochemical parameters (Ea check) |
| lin2014 | Lin 2014 | Journal of Power Sources | 10.1016/j.jpowsour.2014.01.097 | two-node lumped thermal model |
| bernardi1985 | Bernardi 1985 | Journal of The Electrochemical Society | 10.1149/1.2113792 | heat generation (energy balance) |
| plett2004ekf | Plett 2004 | Journal of Power Sources | 10.1016/j.jpowsour.2004.02.033 | EKF state and parameter estimation |
| plett2004pow | Plett 2004 | IEEE Transactions on Vehicular Technology | 10.1109/tvt.2004.832408 | SOP / power estimation |
| zhang2017 | Zhang 2017 | IEEE Transactions on Power Electronics | 10.1109/tpel.2016.2603229 | SOC/SOE estimation, wrong-initial-SOC convergence |
| zhao2017 | Zhao 2017 | IEEE Transactions on Control Systems Technology | 10.1109/tcst.2016.2542115 | current-sensor bias observability (b_I state) |
| barreras2016 | Barreras 2016 | IEEE Transactions on Industry Applications | 10.1109/tia.2016.2585539 | HIL BMS testing, fault categories |
| lelie2018 | Lelie 2018 | Applied Sciences | 10.3390/app8040534 | BMS hardware concepts, plausibility checks |
| haupt2013 | Haupt 2013 | IFAC Proceedings Volumes | 10.3182/20130904-4-jp-2042.00042 | HIL test of BMS, CAN restbus |
| bui2019 | Bui 2019 | 2019 23rd International Conference on Mechatronics Technology (ICMT) | 10.1109/icmect.2019.8932115 | HIL battery simulation platform |
| pandit2023 | Pandit 2023 | 2023 IEEE Transportation Electrification Conference \& Expo (ITEC) | 10.1109/itec55900.2023.10187077 | digital twin MIL/HIL framework |
| jacob2025 | Jacob 2025 | 2025 International Conference on Power Electronics Converters for Transportation and Energy Applications (PECTEA) | 10.1109/pectea61788.2025.11076276 | HIL with digital twin, test automation |
| li2020 | Li 2020 | Journal of Energy Storage | 10.1016/j.est.2020.101557 | digital twin / cloud BMS |
| naseri2023 | Naseri 2023 | Batteries | 10.3390/batteries9070382 | cloud BMS security |
| schmalstieg2014 | Schmalstieg 2014 | Journal of Power Sources | 10.1016/j.jpowsour.2014.02.012 | calendar ageing model |
| millner2010 | Millner 2010 | 2010 IEEE Conference on Innovative Technologies for an Efficient and Reliable Electricity Supply | 10.1109/citres.2010.5619782 | cycle ageing with DoD stress (Kex) |
| rumpf2017 | Rumpf 2017 | Journal of Energy Storage | 10.1016/j.est.2017.09.010 | cell-to-cell variation |
| birkl2017 | Birkl 2017 | Journal of Power Sources | 10.1016/j.jpowsour.2016.12.011 | degradation modes (LLI/LAM), resistance growth |
| edge2021 | Edge 2021 | Physical Chemistry Chemical Physics | 10.1039/d1cp00359c | degradation review |
| feng2018 | Feng 2018 | Energy Storage Materials | 10.1016/j.ensm.2017.05.013 | thermal runaway mechanism |
| waldmann2018 | Waldmann 2018 | Journal of Power Sources | 10.1016/j.jpowsour.2018.02.063 | Li plating (cold charging limits) |
| kirkaldy2024data | Kirkaldy 2024 | Zenodo (dataset) | 10.5281/zenodo.10637534 | raw / summary M50T data used in veri/*.py |

## Manual entries (check version/year at final proof-read)

| Key | Item | Used for |
|---|---|---|
| plett2015 | Plett, Battery Management Systems Vol. I (Artech House 2015) | ECM / EKF background |
| lgm50t | LG INR21700 M50T datasheet, Rev 0 (2018-07-16) | capacity, voltage/current/temperature limits |
| rm0440 | STM32G4 reference manual | FDCAN, IWDG, CRC, CORDIC, DMA |
| ds12589 | STM32G431 datasheet | pin ratings (FT_u, no pull on PA11/PA12) |
| tja1050 | NXP TJA1050 datasheet | CAN transceiver |
| iso26262 | ISO 26262:2018 | scope note: not a full functional-safety process |
| isopas8800 | ISO/PAS 8800:2024 | ML for estimation, deterministic safety layer |
| sae_j1850 | SAE J1850 | CRC-8 of CAN frames |

## Not included (future work / limitations only, add if cited)

Stress-criteria candidates in `bms_ecu/docs/stress_criteria_review.md` (Yang 2018, Tomaszewska 2019, Keil 2016, Preger 2020, Ouyang 2015, Feng 2016, Guo 2016, Jung 2017, Ryu 2018, Smith 2017, Xu 2018, Wang 2011, Wildfeuer 2023, Kirkaldy 2022, Waldmann 2014). Khan 2025 (I2ITCON, LTC6804 + STM32F4 BMS) as related work. ISO 6469-1 / UN ECE R100 if insulation monitoring is mentioned as a limitation.
