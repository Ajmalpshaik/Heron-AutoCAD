# 15 - Attribute sheets, folder checks and the Companion page

**Design note for issues #96, #97 and #91**, from the 2026-11-21 comparison with Heron AI for
Revit. The ideas are Revit's. The code here is Heron for AutoCAD's own. None of this has been run
in AutoCAD yet: the live rows are [NEEDS-CHECKING group Y](NEEDS-CHECKING.md), all NOT RUN.

---

## 1. Attributes out to Excel and back ([D-69](DECISIONS.md), #96)

**What the modeller does:** "give me the equipment tags in Excel" → edit them in Excel → "put
them back".

| Step | Tool | Padlock | What happens |
|---|---|---|---|
| Export | `autocad_export_attribute_sheet` | Publish (it writes a file) | A new `<drawing> - attributes - <date>.xlsx` next to the drawing: one row per block, one column per tag, Handle / Block / Layout first. Never over an earlier one (` (2)`). |
| Edit | Excel | - | The modeller edits the tag columns on the **Attributes** sheet. |
| Apply | `autocad_apply_attribute_sheet` | Changes | Heron reads the file, compares it outside AutoCAD, writes only the changed cells in one undo step, and lists each one old -> new. `dry_run=true` lists them first. |

**The compare, cell by cell.** The workbook carries a second sheet, **As exported**: the same
table, untouched. With it, each cell is one of these:

| Sheet | Drawing now | Result |
|---|---|---|
| blank | any | nothing (a blank never empties an attribute; use `autocad_set_attributes`) |
| same as the drawing | any | nothing |
| changed | as exported | **written** |
| as exported | changed since | kept: the drawing's newer value wins (`kept_drawing`) |
| changed | changed since | **conflict**: listed, not written; the modeller decides |

A plain CSV (any file with a Handle column) has no As exported sheet, so it is compared with the
drawing alone. A row whose block is gone is listed (`missing_handles`); a value under a tag the
block does not have is listed (`unknown_tags`), never added. A handle twice, no Handle column, or
more than 10,000 changes: refused, nothing written.

**Why no new package.** An `.xlsx` is a zip of XML files: `acad/xlsx.py` writes and reads it with
the standard library, as the check-list report does (D-65). Every cell Heron writes is text, so
"0050" and "1.50" stay as they are unless the modeller types over them.

## 2. Check a folder of drawings ([D-70](DECISIONS.md), #97)

`autocad_check_folder(folder, name)` runs one check list (D-52, D-64) over every `.dwg` in a
folder, in name order (`subfolders` too, `max_drawings` up to 200):

1. Open the drawing **read only** (`Documents.Open(path, True)`). One that is already open is
   checked where it is, and left open.
2. Run the list with that drawing's own project changes, exactly as `autocad_checklist` would.
3. Close it **without saving** (`Close(False)`).
4. At the end, make the modeller's own drawing active again.

It is a **View** tool, like `autocad_open_drawing`: it changes which drawing is open, never what
is in one, so it needs no Changes padlock and stays in `--read-only` mode. Each drawing gets its
verdict and coverage line, worst first. A drawing that will not open (a newer format, damaged, a
box the dialog watch closed, D-66) is NOT RUN with AutoCAD's reason, and the rest go on.
HERONSTOP leaves the rest out. PASS means the checked value is met for what Heron read, never
that a drawing complies (D-64).

**Not done yet:** saving the folder's results as one report (the drawing's own report is
`autocad_checklist_report`); checks that need more than one drawing at a time.

## 3. The Heron Companion page ([D-71](DECISIONS.md), #91)

Revit's companion is a local web page beside Revit (its docs/40). AutoCAD's first one is
deliberately small:

- **A file, not a server.** `autocad_companion` writes one HTML file per chat in
  `%LOCALAPPDATA%\Heron\autocad\companion` and gives its path. The modeller opens it in a
  browser beside AutoCAD. From then on the gate rewrites it after every Heron job in that chat;
  the page reloads itself every 5 s.
- **Nothing to attack.** No port is opened, nothing listens, the page runs no script and fetches
  nothing (a Content-Security-Policy says so), and every value on it is escaped.
- **No COM outside a job.** The activity list, the drawing Heron last checked and the change
  `autocad_undo_last` could take back come from what the gate already holds. The drawing's units,
  layout, view and selection are read once, inside `autocad_companion`'s own Read job, and the
  page says when ("read at 10:42:07"). Ask the chat to refresh the page to read them again.
- **It never fails a job.** A page that cannot be written is skipped.
- Pages of chats that ended more than 7 days ago are removed; `stop=true` ends the updates.

**Later, not in this first page:** Revit's editable tables and dashboard. Those would need the
page to send something back, which means a local server with a token; that is a decision of its
own, made when it is needed.
