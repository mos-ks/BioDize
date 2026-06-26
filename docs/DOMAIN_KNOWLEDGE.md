# Domain Knowledge — Batch Production Record (BPR)

Derived by reading the sample `data/scanned_batch_documentation.pdf` page-by-page. This is the
ground truth the extraction and validation are built from.

## 1. What the document is
A real biopharma **Batch Production Record**, anonymized as **"Herstellung von Kuchen"** (cake baking).
The cake vocabulary maps back to process terms via the **abbreviation key on page 45** (e.g.
`Baker Four = Deviation/Abweichung`, `Kap. = Kapitel`). Treat the document as a regulated GMP record:
every value is attributable, every block is processed (`Bearbeitet`) and checked (`Geprüft`).

- **Doc-Nr:** `AB-ABC-123456` · **Rev:** 7 · **Projektcode:** `ABC`
- **Generated (print date):** `09.06.2026` (page 1, "Batch Production Record generiert am")
- **Executed:** `10.06.2026`
- **Declared length:** "Seite N von **45**"; the PDF has **46** physical pages — page 46 is intentionally
  blank because content ends with a **Kreuzung** (closing diagonal strike). *Not* a missing-page error.

## 2. Reliable anchors vs. variable content  *(this drives "don't hardcode parameters")*
| Reliable → hardcode-able | Variable → must be discovered |
|---|---|
| Page number in footer (`Seite N von 45`) | Section numbers (TOC numbers are **off-by-one** from body: TOC `6.3` prints as body `5.3`) |
| `Dok-Nr.: AB-ABC-123456` (constant header) | Parameter labels (may read `m_Tara`, `Tara`, `Leergewicht`, …) |
| Footer `RL-ABCD-78567 / Rev. 5` | Field positions, number of rows, which blocks apply |
| Header band `Herstellung von Kuchen` | Handwritten values |

**Consequence:** anchor everything on **page number**, recognize **block templates** by structure, and
assign each field a **semantic role** from context (position, printed formula, units, neighbours) — never
by string-matching the label.

## 3. Structural vocabulary (defined by the document itself, page 6)
- **Feld (Field):** one or more rows up to the next frame line.
- **Block:** all connected fields up to an empty row / end of a table.
- **Kapitel (Chapter):** several fields/blocks, marked by a chapter number.
- **👁 :** *Prüfung im 4-Augen-Prinzip* (four-eyes check) — i.e. the `Bearbeitet`/`Geprüft` pair.

→ Data model hierarchy: **Document → Chapter → Block → Field** (mirrors this exactly).

## 4. Recurring block templates (≈7 types, not 45 unique pages)
1. **Bilanzierung / mass balance** (p11, 12, 19, 40): `m_Tara, m_Brutto, m_Netto, V_Netto, c (Blocking IPC),
   Start/Erlaubte Haltezeit, Haltetemperatur (Soll range + Ja)`.
2. **Calculation block** (p25, 26, 36, 37): a **printed formula** + inputs (some carried "siehe Kapitel X")
   + a result + **`(N NKS)`** stating the required decimal places.
3. **Equipment table** (p16, 18, 27, 29): `Bezeichnung | Anlagennummer | Einsatzbereit (Ja / Kein Einsatz) | Bearbeitet | Geprüft`.
4. **Single-select checkbox group** (p9 room id, p10/27 oven id): exactly one `O` filled.
5. **Conditional gate** (p12, 14, 16, 23, 38, 39): `⊙ Ja` vs `O Nein, … findet keine Anwendung` (scoped — see §6).
6. **Signature pair `Bearbeitet`/`Geprüft`** (every page): date + Kürzel, the 4-eyes block.
7. **Soll / range field** (p10, 17, 24, 34, 38, 39): `Soll: X` or `Soll: min – max` (sometimes `Soll: target (min – max)`).

## 5. Semantic roles (extensible — bind rules to these, not labels)
`tare_mass`, `gross_mass`, `net_mass`, `volume`, `density (ρ, given)`, `concentration (c, given)`,
`hold_start`, `hold_end`, `hold_duration`, `temperature_setpoint`, `calc_input`, `calc_result`,
`required_decimals (NKS)`, `signature_processed (Bearbeitet)`, `signature_checked (Geprüft)`,
`gate`, `checkbox_single`, `checkbox_bool`, `sample_id`, `equipment_id`, `deviation_ref`.

## 6. Conditional applicability — "findet keine Anwendung" has a **scope**
A gate declares a region intentionally blank. A field is only "missing" if it is required **and** in an
applicable region. The inverse — content present in an N-A region — is an error.

| Gate text (in the doc) | Nullifies | Pages |
|---|---|---|
| `Nein, Feld findet keine Anwendung` | the field | p38, p42 |
| `Nein, Block findet keine Anwendung` | the block | p12, p39 |
| `Nein, Kapitel 5.x findet keine Anwendung` | the whole chapter | p14, p15 |
| `Nein, restliches Kapitel findet keine Anwendung` | **everything after this point** in the chapter | **p44** |
| `Nein, … weiter mit Kapitel 5.7` | **skip/jump**; pages in between are N-A | p16 |
| `Ja, weiter im Kapitel` | continue normally | p16 |
| **Kreuzung** (diagonal strike) + `N/A date Kürzel` | the struck rows / remaining space | p4, p43 |

The engine carries an **applicability state** updated as it walks pages.

## 7. Calculations (physics-based; `c` is given, not computed)
- `net_mass = gross_mass − tare_mass`  (p11 ✓ 200=300−100; p40 nPZ ✗ 200≠100−100)
- `volume = net_mass × ρ` with the **given ρ**  (p11 200×1.1=220 ✓; p40 200×1.18=236 ✓; p12 300×1.81=543 ✓)
- **Multi-input formulas** printed on the page, recomputed with stated `ρ`, `c` and **NKS rounding**:
  - p25 `m[g] = m_net[kg] / ρ × c[g/L]` → e.g. `220 / 1,81 × 3,94 = 479 (0 NKS)`
  - p36 `LoadVolume = (flux_oven × dur_h) − (flux_pump × dur_h)` and `dur_h = dur_min / 60`
  - p37 `Beladung = V_load × c / V_oven`
- Cross-chapter **Übertrag** ("siehe Kapitel X") — a carried value must equal its source.

## 8. Key reference values seen (for priors / range checks)
- Hold temperature setpoints: `2–8 °C`, `18–25 °C`. Hold durations: `≤ 65 h`, `≤ 72 h`, `≤ 82 h`.
- p34 ranges: pH `8,56–9,30` (val 8,67), LF `7,32–11,16 mS/cm` (val 10,4), Baker Five `8–165 mS/cm` (val 80).
- p17 Wippgeschwindigkeit `Soll 25 (20–30) Hübe/min`. p24 oven `Anzahl bisheriger Zyklen Soll ≤ 4`.
- p26/37 Beladung target window `7–19 g_Cake/L_Milk`.
- Densities used: `ρ = 1,10 / 1,18 / 1,31 / 1,81 kg/L`.
- Registered personnel (Kürzel, page 4): `han` (Hans Mustermann), `ohe`.

## 9. Planted errors in the sample = our demo test-cases
| # | Page | What | Severity | Category |
|---|---|---|---|---|
| 1 | p36 | Load-Volumen uses minutes (`45,00`) where formula needs hours (`0,750`); result `2021,78` ~1000× wrong | error | calculation |
| 2 | p39 | Tempering duration `2 h` vs `Soll 72–75 h` | error/warning* | range |
| 3 | p17 | Wippgeschwindigkeit `32` vs `Soll 20–30` — **has** a deviation on p44 | warning | range+deviation |
| 4 | p10 §5.2 | `Geprüft 09.06` before `Bearbeitet 10.06` | error | four_eyes |
| 5 | many | `Bearbeitet == Geprüft == ohe` (same person both roles) | error | four_eyes |
| 6 | p38 | Carried `Start Haltezeit 09.06 8:27` ≠ source p11 `10.06 8:46` | error | cross_reference |
| 7 | p40 | `m_Netto nPZ = 200` but `gross − tare = 0` | error | calculation |
| 8 | p43 | Remark literally says **"Fehler 404"** | warning | extraction/remark |

\* p39 is `error` if no deviation is documented for it, `warning` if one is (the §VALIDATION rule).

## 10. Page-by-page map (anchor = page number)
| Page | Chapter (body) | Content / template |
|---|---|---|
| 1 | cover | Doc id, Prozessstufe B20, Production Code, Batch No., Bearbeitet, **generation date 09.06** |
| 2 | Änderungsindex | revision history (printed) |
| 3 | Inhaltsverzeichnis | TOC (numbers off-by-one vs body) |
| 4 | 1 Beteiligte Personen | personnel table + **Kürzel registry**; empty rows struck (N-A) |
| 5 | Mitgeltende Dokumente | printed references |
| 6 | Definitionen / Prozessbeschreibung | **Feld/Block/Kapitel/👁 definitions**; prose (drop) |
| 7 | 4.1 Geräte | equipment list (printed) |
| 8 | 4.2 Materialien | planned materials + buffers (printed reference qty) |
| 9 | 4.3 Line Clearance | single-select room id + Ja boxes + sig |
| 10 | 5.1 Zyklus / 5.2 Produktionsbereich | Soll-match (`Zyklus 1`), `HZ ≤ 3`; **§5.2 4-eyes date violation** |
| 11 | 5.3.1 Bilanzierung | **mass balance** (ABCE) — calc anchor |
| 12 | 5.3.2 Bilanzierung Forts. | gate `B10-PP vorhanden? Ja`; mass balance (B10-PP) |
| 13 | 5.3.3 Ausdrucke | printout placeholder (blank box) |
| 14 | 5.4 Temperierung Z1 | gate `Nein, Kapitel 5.4 keine Anwendung`; transfer time |
| 15 | 5.5 Temperierung Z2 | gate `Ja`; transfer time |
| 16 | 5.6 Pooling | gate `Ja, weiter im Kapitel`; equipment table |
| 17 | 5.6.2 Durchführung | **Wippgeschw. 32 (OOS)**; times; new intermediate B20-ST |
| 18 | 5.7.1 Geräte | equipment table (B20-ST) |
| 19 | 5.7.2 Bilanzierung | gate; mass balance vPz/nPZ; sample checkboxes |
| 20 | 5.7.3 Probenzug | LIMS sampling; labels; times |
| 21 | 5.7.4 Probenanalytik | `LF B20-ST 14,34 mS/cm (2 NKS)` |
| 22 | 5.7.5 Ausdrucke | blank box |
| 23 | 5.7.6 Haltezeit | gate; Prozessverzögerung start/end/duration; `> 4h?` |
| 24 | 5.8 ProzessOfen | oven release; Soll ranges; `Zyklen ≤ 4` |
| 25 | 5.9 Berechnung der Beladung | **multi-input formulas** + NKS; product masses |
| 26 | 5.9.1 Forts. | `Beladung = m/V`; **Nein, Anpassung** (OOS acknowledged) |
| 27 | 5.10 Setup Backsystem | single-select oven ids; sig |
| 28 | 5.10.2 | many Ja checkboxes; date `TTMMJJJJ` |
| 29 | 5.11 Vorbereitung | equipment table |
| 30 | 5.11.2 | materials checked; B20-PP id |
| 31 | 5.11.3 SAP Etiketten | label counts; `SAP gebucht Ja` |
| 32 | 5.11.4 Durchführung | Ja checkboxes; **sig both ohe** |
| 33 | 5.12 Puffermengen | buffer coupling counts |
| 34 | 5.12.1 | **ranges** pH/LF/Baker; Standzeit `≤ 82h`; warnings/alarms |
| 35 | 5.12.2 Ausdrucke | blank box |
| 36 | 5.12.3 Loadvolumen | **calc with unit error** (#1) |
| 37 | 5.12.4 Ofenbeladung | concentration + Beladung calc; carried inputs |
| 38 | 5.12.5 Haltezeit B10-PP | **cross-ref carried times** (#6); `≤ 65h`; Zyklus-2 N-A |
| 39 | 5.12.6 Temperierung | **duration 2h vs 72–75h** (#2) |
| 40 | 5.13 / 5.14 | mass balance (B20-PP) (#7); peak-cuts mAU |
| 41 | 5.14 Forts. | Probenzug; 2025 reference dates |
| 42 | 6 Bemerkungen | empty (`Nein, keine Anwendung`) |
| 43 | 7 Bemerkungen Forts. | remark **"Fehler 404"** (#8); rest struck (Kreuzung) |
| 44 | 8 Abweichungen | deviations `zu Seite 17`, `zu Seite 34` (EV→DEVI) |
| 45 | 9 Review / 10 Abkürzungen | review signature; **abbreviation key** |
| 46 | — | blank (after Kreuzung) |
