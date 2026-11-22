# Thesis outline (skeleton)

Working skeleton built 2026-11-22 from existing results only (feature freeze: no new experiments).
Each section lists its figures/tables and the numbers to quote. All figures are in `results/` unless a path is given.
Numbers come from the final regeneration (2026-11-22, M50T GITT OCV model); where the thesis notes give two values, use the FINAL one.
Text language: English. ✅ = figure/table exists, ✍️ = text only (material in the thesis notes), ⚠️ = needs a small check before use.

---

## Abstract (≈250 words, write last)
One line per point:
- Problem: a BMS must estimate hidden states (SOC, core temperature) and act safely on faults; testing that on real cells is slow, costly and unsafe.
- What: BMS software for a 19S12P LG INR21700 M50T pack, register-level C on an STM32G431. It is verified closed-loop over CAN against a digital twin running on a separate MCU (Arduino Uno).
- Methods: 5-state SOC EKF, core-temperature observer, thermal anomaly detector, multi-criteria stress index Ψ, graded decision NORMAL/DERATE/LIMP/SAFE, CAN E2E protection, IWDG + flash CRC.
- Key numbers: SOC RMSE 0.277 %; 1000/1000 on-target Monte Carlo PASS with board and PC giving identical verdicts; external-heat detection median 8.0 s; HIL found 3 design flaws missed by MIL/SIL/PIL; 30 min remote monitoring with 0 % loss and median RTT 102 ms.

## 1 Introduction
- 1.1 Motivation: EV pack safety, why estimation and graded response matter. ✍️
- 1.2 Aim and scope: controller-HIL (communication-based); out of scope: AFE, insulation monitoring, pre-charge. ✍️
- 1.3 Contributions (six points in the thesis notes, "PROJECT SUMMARY + VALUE"). ✍️
- 1.4 Structure of the thesis. ✍️

## 2 Background and related work
- 2.1 Li-ion cell behaviour: OCV, ECM (2-RC), Arrhenius temperature dependence, two-node thermal model. ✍️
- 2.2 State estimation: EKF, sensor-bias observability (Zhao 2017), power limits / SOP (Plett 2004). ✍️
- 2.3 BMS hardware concepts and safety layers (Lelie 2018). ✍️
- 2.4 HIL testing of BMS: taxonomy in four groups (Zhang 2017, Barreras 2016, Bui 2019, Jacob 2025, Pandit 2023, Khan 2025, Haupt 2013). The synthesis paragraph and "gap we fill" are ready in the notes. ✍️
- 2.5 Cloud monitoring of batteries (docs/bulut_panel.md references; anchor Li 2020). ✍️

## 3 System design
- 3.1 Architecture and hardware: ✅ `system_block_diagram.png`; "why each part" list from the notes. ✍️
- 3.2 Cell and pack parameters; parameter provenance table (sourced vs assumed). ✍️ → make a table from the notes.
- 3.3 Digital twin: 19 groups, spread table, weak group 7, vehicle + drive cycle, sensor noise. ✅ `twin_ekf_overview.png`, `01_twin_overview.png`
- 3.4 CAN communication design: signal packing (3 reasons), E2E counter + CRC-8 including the ID, timeout rules.
  ✅ `can_frame_layout.png`, `can_bus_load.png`, `can_la_frame_0x110.png`, `can_monitor.png`.
  Measured: 246 frames, all ACK/CRC OK, 8.07 kbit/s = 1.61 % bus load.
  Appendix: `bms_ecu/tools/can/bms.dbc` (11 messages, 101 signals, verified against bms_can.c on 14 000 frames).
- 3.5 Software structure: bms_init/bms_step, 100 ms step, register-level C, interrupt-driven UART (lesson: blocking UART overflowed the 3-deep CAN FIFO). ✍️

## 4 Model identification and validation
- 4.1 OCV from GITT (Kirkaldy M50T): cross-validation on cells E–H, voltage RMSE Chen 2020 64.7 → C/10 36.7 → GITT-OCV 17.0 mV. ✅ `ocv_dogrulama.png`, `ocv_kirkaldy.png`
- 4.2 RC branches: the fit window changes the parameters, but RMSE changes by < 2 mV between RC sets → 2-RC is a compromise. ✅ `gitt_dogrulama.png` (quote only the relative statement; its absolute RMSE is method-specific).
- 4.3 Activation energies: Ea_R0 6.2 ± 0.3 kJ/mol; polarisation 28.3/17.5/14.3 kJ/mol (1/10/30 s). ✅ `ea_kirkaldy.png`
- 4.4 Ageing: k_R = 1 + 1.31 (1 − SOH), SOH 80 % → 1.26 (40 cells / 224 RPTs). ✅ `age_resistance.png`, `aging_*.png`
- 4.5 Twin cross-validation (Simulink = Python = C). ✅ `twin_crossvalidation.png`

## 5 Estimation algorithms
- 5.1 SOC EKF [SOC V1 V2 b_I k_R]: RMSE after 60 s 0.277 % (max 0.517 %); hot day 0.311 %; comparison: fixed-R0 EKF 0.724 %, Coulomb 0.863 %, OCV lookup 17.0 %.
  ✅ `estimator_comparison_normal.png`, `estimator_comparison_table.png`, `estimator_comparison.csv`
- 5.2 Start-up zero-current check (A9): offset ≥ 4 A detected in 0.9 s (was 1000–1660 s); SOC RMSE flat within ±3 A. ✅ `bias_sweep.png`
- 5.3 Resistance scale k_R (5th state) and sensitivity analysis: 25/25 cases safe; R0 ×1.2/×0.8 SOC RMSE 0.29/0.22 % (was 2.09/0.94). ✅ `sensitivity.png`
- 5.4 Core-temperature observer [Tc Ts g] and cooling-fault detection. ✅ `thermal_observer_py.png`, `thermal_observer_cooling_fault.png`
- 5.5 Hidden heat: the observer cannot see unmodelled heat (A2 finding) → measurement-anchored bound T_ss + thermal anomaly detector (adiabatic envelope). Detection median 8.0 s / max 11.7 s; internal 5 W in 74 s; 0 false alarms in 48 runs; core-estimate error after the fault −52 → −5 °C. ✅ `thermal_anomaly.png`
  Negative result worth a paragraph: CUSUM on the thermal innovation was rejected (misses internal heat, false alarm after warm restart). ✍️
- 5.6 Sensor diagnostics (range, frozen value, filtered rate). ✅ `sensor_fault_open_ntc.png`, `prefilter_*.png`
- 5.7 ML SOH estimate (decision tree, Kirkaldy data). Leave-one-cell-out RMSE: tree (Usage + R) 2.57 %, gradient boosting 1.93 %, physics model 3.03 %. The tree was chosen for MCU size.
  Aged-pack demo: SOC RMSE 1.44 % (new-cell BMS) → 0.48 % (ML-updated) vs oracle 0.29 %.
  ✅ `ml_model_comparison.png`, `ml_depth_sweep.png`, `ml_cv_leakage.png`, `ml_aged_pack_soc.png`
  ⚠️ Limitation: online rint never fires on the smooth twin cycle → SOH output stays ~100 % on the bench; say so.

## 6 Decision logic and the multi-criteria stress index
- 6.1 States and graded response; datasheet limits; SOP with temperature-dependent R and k_R. ✅ `decision_closed_loop.png`, `limiter_test.png`
- 6.2 Stress index Ψ = max + κ(sum − max), κ = 0.25; criteria Ψ_T (45→55 °C), Ψ_C (cooling alarm, 0.3), Ψ_Tdot (3→10 °C/min, 0.5); Ψ_H display only.
  Explain the dropped criteria with data: σ_SOC max 0.75 %, I²t max 49 %, nominal ΔV 18–46 mV, k_R jump at boot.
  ✅ `stress_index_drive.png`
- 6.3 Passive balancing (10/5 mV hysteresis, 60 s, off while driving): ΔV 21.7 → 8.9 mV with ×500 acceleration (state the acceleration). ✍️ (⚠️ no figure yet; the twin_emu_run CSV exists in build/, optional)
- 6.4 Thermal event after shutdown (cause 2048, UN GTR 20): bench 1.0 s after SAFE; 90 s soak guard; 1 W/cell not detected. ✍️

## 7 Verification
- 7.1 Verification chain MIL → SIL → PIL → CAN replay → HIL (diagram optional). ✍️
- 7.2 SIL/PIL: C = Python = MATLAB; PIL 3/3 PASS; bms_step max 92 µs on 170 MHz. ✍️
- 7.3 On-target Monte Carlo: 1000 runs × 600 s, 623× real time, 16 min; 1000/1000 PASS; board vs PC identical verdicts 1000/1000. Fault reactions: NTC open 0 s, offset 0.9 s, external heat SAFE with core 58–59 °C; 0 false alarms in fault-free runs. ✅ `mc_overview.png`, `mc_summary.txt`
- 7.4 HIL bench: twin on Uno, ECU on STM32, scripted scenarios (demo_run.py), button tests with measured reaction times (NORMAL 2–6 s, DERATE 0.1 s, LIMP 0.0 s, STOP 0.5 s, watchdog 1.1 s, overheating LIMP 6.1 s / SAFE 65.5 s, cooling fault 105.8 s). ✍️ (⚠️ `build/demo_*.png` exist; restyle one into results/ if you want a figure)
- 7.5 **Design flaws found only by HIL** (key argument): cooling-alarm chatter (fixed with hysteresis 18/15), warm-restart false cooling alarm (21/32 → 0 with 120 s blanking), thermal lag (SAFE at true core 66.4 → 60.0 °C with T_ss). One short table. ✍️
- 7.6 Safety mechanisms on the bench: CAN cable pulled → SAFE < 1 s (ACK-error exception, no bus-off), watchdog, flash CRC. ✍️

## 8 Safety analysis
- FMEA-style table, 13 hazards with measured reaction times: ✅ `safety_analysis.md` / `.csv`. State that it is not a full ISO 26262 process. Map to Barreras 2016 Table II categories.

## 9 Remote monitoring
- Architecture: PC gateway → HTTPS → PHP + SQLite on shared hosting; monitor only, safety decisions stay on the ECU. The ESP-01 path is designed but optional. ✍️
- Link quality, 30 min: 18 046 rows, 0 % loss; RTT p50/p95 102/134 ms; end-to-end 155 ms (newest row) to 1.16 s (oldest row; ≈1 s is batching); jitter p95 34 ms. One-way delay unusable (clock offset). ✅ `link_quality_20261121.png`, `web_dashboard_live.jpg`
- Lesson: jitter between two free-running clocks needs detrending (~500 ppm drift). ✍️

## 10 Discussion
- Comparison with literature (cost, white-box ECU, measured detection times). ✍️
- Model fidelity vs test value: an assumed-parameter twin is still useful because the flaws found were structural. ✍️

## 11 Limitations
✍️ Communication-based HIL (no AFE, no analog cell voltages); 10 Hz loop (no ms-scale events); one pack temperature sensor; no capacity estimation (aged SOC error up to 4.7 %); online R estimator inactive on smooth cycles; slow internal heat < known-heat margin; 1 W/cell thermal event not detected; no pre-charge/weld/insulation monitoring; no redundant voltage path; CRC ≠ security (no SecOC/secure boot); assumed parameters (R2/τ2, R_u, noise).

## 12 Conclusion and future work
- Closing line from the notes: "a working BMS, a cheap platform that safely tests it, and a thesis whose own data shows why both are needed together."
- Future work: UDS/DTC; SecOC + secure boot; capacity estimation; Ψ candidates in docs/stress_criteria_review.md; real cell-monitor board in place of the twin; ISO 26262 HARA/ASIL; LIN/Ethernet. ✍️

## Appendices
- A: CAN database (bms.dbc) and frame layouts.
- B: Parameter table (bms_config.h with source per value).
- C: Monte Carlo verdict criteria (mc_core.c).
- D: Safety analysis table (if not in chapter 8).

---
Before writing the final numbers: check each quote against the FINAL REGENERATION section of the thesis notes.
