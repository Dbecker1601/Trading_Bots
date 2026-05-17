# Intraday Strategy aus Video: "Intraday trading strategy with Python and AMT"

## Quellen
- Video: https://www.youtube.com/watch?v=gopjGcgciXg
- Repo (aus Videobeschreibung): https://github.com/QuantextCapital/MarketProfile/tree/main/AMT
- Begleitvideo (80%-Rule/Backtesting): https://www.youtube.com/watch?v=kRSZ1AN4UcU

## Kurzfazit (was die Strategie ist)
Im Kern werden **zwei Intraday-Systeme** gebaut und verglichen:
1. **Pure Price Action Baseline** (`priceaction.py`)
2. **AMT + Price Action (80%-Rule-artig)** (`amt_price_action.py`)

Ziel laut Video/Code: einfache, robuste Intraday-Logik mit geringer Overnight-Exponierung, dann schrittweise mit Auction Market Theory (Market Profile) verbessern.

---

## Daten- und Feature-Pipeline (beide Varianten)
1. 1-Minuten-Daten laden (NIFTY50/Einzeltitel; im Repo ist Link zur Minute-Daten-Quelle).
2. In-Sample/Out-of-Sample Split (hälftig).
3. Auf **15-Minuten** resamplen.
4. Market-Profile/TPO-Features berechnen über `tpo_helper_intra`:
   - `VAH` (Value Area High)
   - `VAL` (Value Area Low)
   - `POC` (Point of Control)
   - `TPO_Net`, LVN/Excess u.a.
5. Zusätzliche Features:
   - `rf` (im Repo über `get_rf`), plus `rf_small` (2er Summe), `rf_long` (5er Summe)
   - `AR` = 20-Tage Average Range
   - `POC_trend` = +1 wenn POC steigt, sonst -1
   - Tages-Open (`DayOpen`)
   - Session-Zeitfilter für Entries

---

## System 1: Pure Price Action (`priceaction.py`)
### Entry Long
- Aktuelles Hoch > vorheriges 5-Bar-Hoch (`High > High_5.shift(1)`)
- `rf_small > rf_long`
- `rf > rf.shift(1)`
- Zeitfenster: **09:44 bis 13:29**

### Entry Short
- Aktuelles Tief < vorheriges 5-Bar-Tief (`Low < Low_5.shift(1)`)
- `rf_small < rf_long`
- `rf < rf.shift(1)`
- Zeitfenster: **09:44 bis 13:29**

### Exit / Risk
- Harte Tagesglattstellung um **15:29**
- Stop-artiger Exit über Average Range:
  - Long raus, wenn `Low < Entry - AR/n1`
  - Short raus, wenn `High > Entry + AR/n1`
- `n1` wird per Grid Search optimiert.

---

## System 2: AMT + Price Action (`amt_price_action.py`)
Idee: Value-Area-Reentry + Richtungskontext aus AMT.

### Entry Long
- `Close > VAL.shift(1)`
- `Close.shift(1) < VAL.shift(2)`
  -> Preis kommt von unterhalb wieder in/über die Value-Area (Long-Reentry-Idee)
- `rf > rf.shift(1)`
- `POC_trend == 1`
- `DayOpen < VAH`
- Zeitfenster: **09:44 bis 13:29**

### Entry Short
- `Close < VAH.shift(1)`
- `Close.shift(1) > VAH.shift(2)`
  -> Preis kommt von oberhalb wieder in/unter die Value-Area (Short-Reentry-Idee)
- `rf < rf.shift(1)`
- `POC_trend == -1`
- `DayOpen > VAL`
- Zeitfenster: **09:44 bis 13:29**

### Exit / Risk
- Ebenfalls Tagesglattstellung um **15:29**
- AR-basierter Stop analog zu System 1 (`AR/n1`)
- Optimierung über `n1` (Grid Search)

---

## Backtest-Setup im Repo
- Framework: `backtesting.py`
- Beispielparameter:
  - `cash = 500_000`
  - `commission = 0.0005`
  - `trade_on_close = True`
- Zusätzliche Reports/Plots über `def_btxtra.py`

---

## Wie ich die Strategie in eigenen Worten verstehe
- Erst wird ein simples Intraday-Breakout-System als Baseline gebaut.
- Danach wird dieselbe Grundidee mit Market-Profile-Kontext erweitert:
  Reentry über Value-Area-Grenzen (VAL/VAH), gefiltert durch kurzfristigen Orderflow/Trend (`rf`, `POC_trend`).
- Risiko wird pragmatisch über Zeit (kein Overnight) + Volatilität (`AR`) gesteuert.

---

## Offene Punkte für unsere gemeinsame Weiterentwicklung
1. Exakte Bedeutung/Skalierung von `rf` im Helper prüfen.
2. Robuste Walk-Forward-Validierung statt nur einmaligem Split.
3. Slippage/realistische Kosten und Fill-Modell strenger machen.
4. Parameter-Stabilität (`freq`, Zeitfenster, AR-Multiplikator) über mehrere Märkte testen.
5. Saubere Trennung von In-/Out-of-Sample + Report als JSON/HTML in unserem Workflow.

---

## Ergänzungen aus weiteren 2 Videos (Strategie-Verbesserung)
Zusätzliche Quellen:
- https://www.youtube.com/watch?v=xPrCMCArhOo  (Open Types / Szenarien)
- https://www.youtube.com/watch?v=Xjnj7JGkNx4  (Market Profile Basics + Python/Repo)

Hinweis zur Datengrundlage: Transcript-API war in der Cloud-Umgebung durch YouTube-IP-Blockade nicht nutzbar. Inhalte wurden aus Video-Beschreibungen, verlinkten Repo-Dateien und den verlinkten Mindmap-Grafiken rekonstruiert.

### A) Pre-Market Klassifikation (neu vor jedem Handelstag)
Vor Entry-Logik erst den Tag klassifizieren:
1. Gap-Status bestimmen (gegenüber Vortagesschluss):
   - kleines Gap / großes Gap
2. Open-Location bestimmen:
   - außerhalb Vortags-Range
   - innerhalb Vortags-Range, aber außerhalb Value
   - innerhalb Value-Area
3. Open-Kontext gegen Vortagesschluss:
   - Akzeptanz oberhalb/unterhalb? Oder schnelle Rejection?

### B) Open-Type Entscheidungsregeln
1. Großes Gap + News + hohes Opening-Volumen
   -> Continuation wahrscheinlicher -> Momentum-Modus aktiv.
2. Kleines Gap + schwaches Volumen + keine starke News
   -> Gap-Fill / Mean-Reversion wahrscheinlicher.
3. Open außerhalb Vortags-Range
   -> stärkere Imbalance, meist besseres CRV für Directional-Trades.
4. Open innerhalb Value & Range
   -> eher Rotation/Chop; reduziertes Risiko/Positionsgröße oder no-trade bis klare Struktur.

### C) Integration der 80%-Regel als Zustandswechsel
Wenn Preis wieder in die Value-Area zurückkehrt und dort akzeptiert wird:
- von Momentum-Modus auf Value-Rotation-Modus umschalten,
- Zielzone gegenüberliegende Value-Grenze.

### D) OTF/Bestätigungs-Filter (verbessert Entries)
- Long-Bestätigung:
  - Akzeptanz über Vortagesschluss + über Value (VAH/VAL-Kontext)
  - optional: erster Pullback hält über Open/VAH.
- Short-Bestätigung:
  - Akzeptanz unter Vortagesschluss + unter Value
  - optional: Pullback scheitert an Open/VAL.
- Schnelle Rejection von Open-Niveaus = Warnsignal gegen Fortsetzung.

### E) Konkrete Verbesserung für unseren Algo (v2-Idee)
Zusätzliche Features/Filter vor Entry:
1. `open_type` (categorical):
   - `gap_large_continuation`, `gap_small_fill`, `open_outside_range`, `open_inside_value` usw.
2. `acceptance_flag`:
   - Zeitbasierte Akzeptanz (z.B. erste N Bars ober/unter Referenzlevel).
3. `first_hour_ib`:
   - Initial-Balance (IB high/low) als Breakout/Failure-Filter.
4. `mode_switch`:
   - Momentum vs Mean-Reversion dynamisch nach Open-Type + Value-Reentry.
5. `risk_scaler`:
   - Positionsgröße/Stopfaktor an Open-Type koppeln (z.B. kleiner in Chop-Phasen).

### F) Priorisierte Implementierungs-Reihenfolge
1. Open-Type Labeling + Backtest-Tagging (nur Analyse, noch ohne Trades ändern).
2. Danach Trades nur in „guten“ Open-Typen erlauben.
3. Danach 80%-Regel als alternativen Exit/Target-Pfad integrieren.
4. Danach IB-Filter und Acceptance-Filter aktivieren.
5. Final: Walk-Forward + Robustheitscheck pro Open-Type.

---

## Strategie-Framework: 1) Kontext 2) Zonen 3) Setup

### 1) Kontext (Bias/Regime des Tages)
Passend aus AMT/Open-Type-Logik:
- Open-Type bestimmen:
  - Gap groß + News + hohes Open-Volumen => Trend-/Momentum-Kontext
  - Gap klein/kein Gap + in Value => Rotations-/Mean-Reversion-Kontext
- Open-Location vs Vortag:
  - außerhalb Vortags-Range => starke Imbalance
  - innerhalb Vortags-Range/Value => Balance/Rotation
- Akzeptanz in den ersten Bars (z. B. 2–4 x 15m):
  - über VAH/unter VAL akzeptiert => Trendfortsetzung wahrscheinlicher
  - schnelle Rejection zurück in Value => Rotation wahrscheinlicher
- Zusatzfilter:
  - POC_trend (auf/ab)
  - rf-Momentum (rf > rf.shift(1) bzw. umgekehrt)

Ergebnis: Tagesmodus = `momentum` oder `rotation`.

### 2) Zonen (Handelsbereiche) – Market-Profile „Berge/Täler“-Logik
Du hast recht: DayOpen/IB-High/IB-Low sind eher Kontext-/Trigger-Level.
Die wirklich „gehandelten“ Zonen kommen aus der Profil-Verteilung (TPO/Volume).

Primäre Profil-Zonen (Priorität hoch, ohne POC-Fokus):
- HVN-Edges (nicht HVN-Mitte): obere/untere Kante eines Volumen-Clusters
- LVN-Gates: schmale Low-Volume-Übergänge zwischen zwei HVNs
- VAH / VAL: Grenzen der Value Area (ca. 70% Akzeptanzbereich)
- Single Prints / Thin Prints (TPO): dünn besetzte Preisbereiche mit Repricing-Potenzial
- Naked Levels aus Vortagen: ungetestete VAH/VAL/HVN-Kanten

Sekundäre Levels (Kontext, nicht Hauptzonen):
- DayOpen
- IB High / IB Low
- PDH / PDL / PDC

Berge-Theorie praktisch:
- Berg (HVN/POC): Markt akzeptiert Preis -> Rotation/Mean-Reversion wahrscheinlicher
- Tal (LVN): Markt akzeptiert Preis schlecht -> Durchlauf/Impuls wahrscheinlicher
- Value-Area-Rand (VAH/VAL): Entscheidungspunkt zwischen Rejection (zurück in Value) vs Acceptance (Trendfortsetzung)

Zonen-Nutzung nach Regime:
- Rotationstag:
  - Entries eher an VAH/VAL/HVN-Rejections
  - Ziele Richtung POC/HVN
- Trendtag:
  - Entries bei Acceptance außerhalb Value oder nach LVN-Durchbruch
  - Ziele nächster HVN/Profil-Cluster
- Stops:
  - Hinter der jeweils invalidierten Profilzone (z. B. hinter VAH/VAL oder jenseits LVN-Reclaim)

Kurz: Ja — für deine Idee sollten wir die Hauptzonen aus POC/HVN/LVN/VAH/VAL bauen und DayOpen/IB nur als Zusatzkontext nutzen.

### 3) Setup (klare Handelsauslöser)

Setup A: Momentum-Continuation (für `momentum`-Kontext)
- Long:
  - Open außerhalb Value nach oben ODER Re-Akzeptanz über VAH
  - rf steigt + POC_trend positiv
  - Trigger: Break/Close über IB High oder über letztem Swing
- Short analog unter VAL/IB Low
- Stop: hinter Trigger-Zone oder AR-basiert (AR/n1)
- Ziel: nächstes Strukturlevel / R-Multiple / Trailing

Setup B: Value-Reentry / 80%-Rotation (für `rotation`-Kontext)
- Long:
  - Preis war unter VAL und wird wieder in Value akzeptiert
  - Trigger: Bestätigungs-Close zurück über VAL + kein sofortiger Fehlausbruch
- Short:
  - Preis war über VAH und fällt wieder in Value
- Stop: knapp außerhalb Reentry-Zone (unter VAL/über VAH)
- Ziel: gegenüberliegende Value-Grenze (80%-Rule-Idee)

Setup C: Open-Rejection (False Break am Open)
- Wenn Open außerhalb wichtiger Zone startet, aber in den ersten Bars klar zurückgewiesen wird
- Entry in Richtung der Rejection zurück zur Value
- Stop über/unter Rejection-Extrem
- Ziel: POC bzw. Mittelbereich der Value

---

## Minimal-Regelsatz (direkt umsetzbar)
1. Erst Tagesmodus bestimmen (`momentum` vs `rotation`).
2. Nur Setups handeln, die zum Tagesmodus passen.
3. Immer an vordefinierten Profil-Zonen (HVN-Kanten/LVN/VAH/VAL) triggern.
4. Jede Position braucht: Trigger, invalidation (Stop), Target-Logik.
5. Kein Trade im "inside value chop" ohne klaren Trigger.

Ergänzende konkrete Orderflow-Kanten-Setups:
- `strategy_knowledge/orderflow_edge_setups_v1.md`
