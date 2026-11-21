# Disclaimer - what Heron's checks mean

Heron AI for AutoCAD checks drawings. It does not approve them.

## PASS means the checked value is met

When a check list line (`autocad_checklist`) or a standards rule (`autocad_check_standards`) says
**PASS**, it means one thing only: **the checked value is met**, for what Heron could read in this
drawing, against the source named on that line. The source is the clause the modeller gave the
check (for example "Office CAD standard 3.1"), or the check list or rules file itself.

It does **not** mean:

- that the drawing meets a code, a client standard or an authority's rules;
- that the design is right, safe or buildable;
- that anything Heron did not check is fine.

**Heron never says a drawing complies.** It has no way to know, and it does not sign anything off.
A competent person checks the drawing and signs it, as before.

## The four results

| Result | What it means |
|---|---|
| PASS | The checked value is met, against the named source. |
| FAIL | The checked value is not met. The objects are named, so you can zoom to them. |
| NO DATA | Heron could not decide: what the check needs is not in the drawing or could not be read (no such title block, xrefs unreadable, only part of the objects read). **Never counted as a PASS.** |
| NOT RUN | The check was switched off for this project. |

Every run ends with a coverage line, for example **"3 of 5 decided, 1 no data, 1 not run"**. Read
it with the result: a PASS that decided 1 of 5 checks says very little.

## Reports

A saved report (`autocad_checklist_report`, an Excel workbook and an HTML page next to the drawing)
carries the same words. It is a record of what was checked and when, not a certificate.

## Your responsibility

Heron is a tool for the modeller. The modeller and the engineer remain responsible for the drawing,
for choosing the checks, and for what is issued. The software is provided "as is", without warranty
of any kind; see [LICENSE](LICENSE).
