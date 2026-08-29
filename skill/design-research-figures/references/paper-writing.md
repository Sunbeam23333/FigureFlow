# Paper Writing, Formula, Caption, and Table Craft

## Build the argument before the illustration

A strong technical section usually follows this sequence:

1. **Baseline:** what the accepted method or scaling law already explains.
2. **Gap:** the narrow residual behavior, implementation limitation, or untested transfer.
3. **Question:** one falsifiable statement rather than a broad promise.
4. **Mechanism:** why the proposed statistic or system component could affect the outcome.
5. **Evidence plan:** what is measured, what is frozen before final training, and what serves as the exact control.
6. **Decision gate:** the threshold that counts as support, null, harm, or objective mismatch.
7. **Boundary:** where the result must not be generalized.

Keep three result layers separate:

- engineering closure: the code path runs and is faithful;
- current implementation result: measured behavior in this repository;
- original scientific conclusion: supported only after the preregistered experiments.

Do not turn a successful implementation into a scientific claim.

## Claim lifecycle

Treat each paper claim as a state machine:

`proposed → implemented → simulated/forecast → measured → passed-gate or failed-gate → bounded transfer`.

The main figure, result table, caption, and prose must agree on the current state. Introduction contributions should be deliberately conditional before measurement. End the introduction with what would falsify the paper. A title or broad conclusion is earned only after its named gates pass; a failed gate remains a result rather than disappearing from the narrative.

In related work, distinguish: what is already established, what this paper actually tests, what it cannot claim as a first, and which contribution is only a conditional first. Mathematical or physical analogies should be labeled “limited but useful”; a proposition in a solvable teacher model does not automatically establish behavior in a neural network.

## Formula pedagogy

Introduce a formula in five moves:

1. explain the intuition in ordinary language;
2. define each variable and unit;
3. show the formula in vector typesetting;
4. walk through one small numerical example when useful;
5. state the condition under which the formula would be misleading.

In a figure, keep only the compact formula and one interpretation tag. Put variable definitions and caveats in the caption or surrounding text. Render formulas with LaTeX or Matplotlib mathtext set to path output; never ask a bitmap generator to typeset them.

For a mixed audience, use an explanation ladder before formal notation: begin with a concrete evolving example, identify the probe as a frozen measuring instrument, then introduce direction, spectrum/shape, soft counting, and trajectory. For each central equation provide a variable table, how to read it aloud, why it is needed, a numerical example, applicability conditions, and the theoretical boundary. Similar-sounding statistics must not be conflated—for example, participation-ratio effective rank is not automatically the classical stable rank.

## Caption contract

Use this pattern:

> **Takeaway.** What the reader should conclude. **Encoding.** What panels, colors, lines, markers, widths, shades, or arrows mean. **Evidence.** Dataset/split, aggregation, uncertainty, seed count, units, and whether values are measured, simulated, forecast, illustrative, or synthetic. **Gate.** The prespecified criterion. **Boundary.** What the visual does not demonstrate.

The caption should interpret the visual, not merely repeat its title. If a line width represents planned priority rather than effect size, say so. If a cell is forecast, mark it in the cell and explain the marker.

## Negative results and explicit non-transfer

Retain null, harmful, invalid-objective, and non-transfer outcomes. Useful encodings include:

- an orange warning row for an objective-mismatched comparison;
- a dashed red link for a claim the graph explicitly does not license;
- a hard-gate belt beneath an overview;
- a scoreboard row whose failure condition was defined before results;
- a caption sentence stating which attractive extrapolation is unsupported.

Negative boundaries belong in the visual argument, not only in a limitations paragraph.

## Quantitative figure narrative

Order panels so each answers a different question. A common four-panel sequence is:

1. did optimization remain stable?;
2. does the frozen predictor match held-out groups?;
3. does the method cross the preregistered recovery or fidelity gate?;
4. does it improve the equal-compute decision frontier?

Use a fixed random seed for synthetic or bootstrap demonstrations, export the source rows, and put evidence status into both CSV and figure. Never style a forecast so it looks measured.

## Publication tables

Use `booktabs` without vertical rules. Prefer explicit column widths, `tabularx`, and `siunitx`-compatible numerical columns. Keep units and direction arrows in headers. Use semantic backgrounds sparingly:

- gray: forecast or not-yet-measured;
- pale blue: selected method or the paper's target;
- pale orange: hybrid, warning, or known-invalid comparison;
- pale green: verified measured cell.

Long comparison or threat matrices need captions that state the audit criterion and interpretation boundary. Avoid global `\resizebox` unless the final effective type remains readable; split a dense table before shrinking it below the paper's visual floor.

## Novelty and threat audits

A novelty table should compare mechanisms and evidence, not adjectives. Useful columns include: prior line, strongest adjacent method, missing capability, this paper's differentiator, and decisive experiment. A threat-closure matrix can map reviewer concern → test → acceptance gate → failure interpretation. These tables help ensure every promised contribution has a falsifiable row.
