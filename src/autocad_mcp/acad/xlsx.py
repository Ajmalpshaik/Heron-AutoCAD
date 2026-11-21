"""Read and write plain .xlsx workbooks with the standard library (D-69).

An .xlsx is a zip of a few XML files, so Heron needs no new package to hand
the modeller a sheet Excel opens, or to read it back once edited. Only what a
round trip needs: text and numbers, a bold first row, column widths. Every
cell Heron writes is text, so a value such as "0050" or "1.50" stays exactly
as it was unless the modeller types over it.

Reading is careful with a file that came from outside: a size limit on the
file and on each part, shared strings and inline strings, rich text runs,
numbers given back the way Excel shows them ("100", not "100.0").

Excel turns some typing into numbers: "1:100" into a time, "05.01" or "1/50"
into a date, "50%" into 0.5. The cell then holds a number Excel only *shows*
as the text typed. Such a cell is read back as a ``Converted`` text, which
says what Excel made of it, so a caller never writes 0.0694 for a scale.
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import Any
from xml.etree import ElementTree
from xml.sax.saxutils import escape

MOST_FILE_BYTES = 20 * 1024 * 1024
MOST_PART_BYTES = 60 * 1024 * 1024
MOST_ROWS = 50000
MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC_RELS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS = {"m": MAIN}
_BAD_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_SHEET_NAME = re.compile(r"[\[\]:*?/\\]")


MOST_COLUMNS = 16384  # Excel's own limit (XFD)
# Built-in number formats that show a number as something else: percent 9-10,
# fraction 12-13, date and time 14-22, 27-36, 45-47, 50-58.
_SHOWN_AS = {9: "percent", 10: "percent", 12: "fraction", 13: "fraction"}
_SHOWN_AS.update({n: "date or time" for n in (*range(14, 23), *range(27, 37), 45, 46, 47, *range(50, 59))})


class SheetError(ValueError):
    """The workbook cannot be read; the message says why in plain words."""


class Converted(str):
    """A cell Excel turned into a number it only shows as text: a date, a time, a percent, a fraction."""

    shown_as = "a number"

    def __new__(cls, text: str, shown_as: str) -> Converted:
        made = super().__new__(cls, text)
        made.shown_as = shown_as
        return made


def _shown_as(code: str) -> str | None:
    """What a custom number format shows a number as, or None for a plain number."""
    plain = re.sub(r'"[^"]*"|\\.|\[[^\]]*\]', "", code)  # quoted text, escapes, [colour] / [h] parts
    if "%" in plain:
        return "percent"
    if re.search(r"[dmyhs]", plain, re.IGNORECASE):
        return "date or time"
    if "?/" in plain or "#/" in plain:
        return "fraction"
    return None


def _styles(archive: zipfile.ZipFile) -> list[str | None]:
    """For each cell style (s="n"): what it shows a number as, or None."""
    if "xl/styles.xml" not in archive.namelist():
        return []
    root = _xml(archive, "xl/styles.xml")
    custom = {}
    for fmt in root.findall("m:numFmts/m:numFmt", _NS):
        try:
            custom[int(fmt.get("numFmtId", "0"))] = _shown_as(fmt.get("formatCode", ""))
        except ValueError:
            continue
    kinds: list[str | None] = []
    for xf in root.findall("m:cellXfs/m:xf", _NS):
        try:
            number = int(xf.get("numFmtId", "0"))
        except ValueError:
            number = 0
        kinds.append(custom[number] if number in custom else _SHOWN_AS.get(number))
    return kinds


def column(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def column_index(letters: str) -> int:
    """A -> 0, AA -> 26."""
    number = 0
    for letter in letters.upper():
        number = number * 26 + (ord(letter) - 64)
    return number - 1


def _cell(ref: str, value: Any, bold: bool) -> str:
    # The heading is bold; every other cell is formatted as Text (number format 49), so what the
    # modeller types over it stays the text typed: "0051" keeps its zero, "1:100" is not a time.
    style = ' s="1"' if bold else ' s="2"'
    text = _BAD_CHARS.sub("", escape("" if value is None else str(value)))
    return f'<c r="{ref}" t="inlineStr"{style}><is><t xml:space="preserve">{text}</t></is></c>'


def _sheet_xml(rows: list[list[Any]], widths: list[int] | None) -> str:
    body = []
    for number, row in enumerate(rows, 1):
        cells = "".join(_cell(f"{column(i)}{number}", value, number == 1) for i, value in enumerate(row))
        body.append(f'<row r="{number}">{cells}</row>')
    cols = ""
    if widths:
        cols = "<cols>" + "".join(
            f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths, 1)
        ) + "</cols>"
    # The first row stays in view while the modeller scrolls down the list.
    frozen = (
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
        'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{MAIN}">{frozen}{cols}<sheetData>{"".join(body)}</sheetData></worksheet>'
    )


def write(sheets: list[tuple[str, list[list[Any]], list[int] | None]]) -> bytes:
    """A workbook of these sheets: (name, rows with the heading first, column widths or None)."""
    if not sheets:
        raise ValueError("a workbook needs at least one sheet")
    names = [_SHEET_NAME.sub("-", name)[:31] for name, _, _ in sheets]
    overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for i in range(1, len(sheets) + 1)
    )
    parts = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            f"{overrides}"
            '<Override PartName="/xl/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="{RELS}">'
            f'<Relationship Id="rId1" Type="{DOC_RELS}/officeDocument" Target="xl/workbook.xml"/></Relationships>'
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<workbook xmlns="{MAIN}" xmlns:r="{DOC_RELS}"><sheets>'
            + "".join(
                f'<sheet name="{escape(name, {chr(34): "&quot;"})}" sheetId="{i}" r:id="rId{i}"/>'
                for i, name in enumerate(names, 1)
            )
            + "</sheets></workbook>"
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="{RELS}">'
            + "".join(
                f'<Relationship Id="rId{i}" Type="{DOC_RELS}/worksheet" Target="worksheets/sheet{i}.xml"/>'
                for i in range(1, len(sheets) + 1)
            )
            + f'<Relationship Id="rId{len(sheets) + 1}" Type="{DOC_RELS}/styles" Target="styles.xml"/>'
            "</Relationships>"
        ),
        "xl/styles.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<styleSheet xmlns="{MAIN}">'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
            '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
            '<xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            "</styleSheet>"
        ),
    }
    for i, (_, rows, widths) in enumerate(sheets, 1):
        parts[f"xl/worksheets/sheet{i}.xml"] = _sheet_xml(rows, widths)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in parts.items():
            archive.writestr(name, text)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def _part(archive: zipfile.ZipFile, name: str) -> bytes:
    try:
        info = archive.getinfo(name)
    except KeyError:
        raise SheetError(f"the workbook has no part {name}") from None
    if info.file_size > MOST_PART_BYTES:
        raise SheetError(f"{name} is too big to read ({info.file_size // 1048576} MB)")
    return archive.read(info)


def _xml(archive: zipfile.ZipFile, name: str) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(_part(archive, name))
    except ElementTree.ParseError as exc:
        raise SheetError(f"{name} inside the workbook is damaged ({exc})") from None


def _text(node: ElementTree.Element) -> str:
    """The text of a shared or inline string, rich text runs joined, phonetic runs left out."""
    parts = []
    for child in node:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "t":
            parts.append(child.text or "")
        elif tag == "r":
            parts.extend(t.text or "" for t in child.iter(f"{{{MAIN}}}t"))
    return "".join(parts)


def number_text(raw: str) -> str:
    """A number cell as Excel shows it by default: 100 not 100.0, 1.5 not 1.50000000001."""
    try:
        value = float(raw)
    except ValueError:
        return raw
    if value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    return f"{value:.15g}"


def _target(base: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return f"{base}/{target}"


def read(content: bytes) -> dict[str, list[list[str]]]:
    """Every sheet of a workbook: {sheet name: rows of cell text}, in workbook order."""
    if len(content) > MOST_FILE_BYTES:
        raise SheetError(f"the file is bigger than {MOST_FILE_BYTES // 1048576} MB")
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise SheetError("it is not an Excel .xlsx workbook (an .xls from old Excel? save it as .xlsx)") from None
    with archive:
        book = _xml(archive, "xl/workbook.xml")
        rels = _xml(archive, "xl/_rels/workbook.xml.rels")
        targets = {rel.get("Id"): rel.get("Target", "") for rel in rels}
        styles = _styles(archive)
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = _xml(archive, "xl/sharedStrings.xml")
            shared = [_text(si) for si in strings.findall("m:si", _NS)]
        sheets: dict[str, list[list[str]]] = {}
        for sheet in book.findall("m:sheets/m:sheet", _NS):
            name = sheet.get("name", "")
            target = targets.get(sheet.get(f"{{{DOC_RELS}}}id"))
            if not target:
                continue
            root = _xml(archive, _target("xl", target))
            rows: list[list[str]] = []
            for row in root.findall("m:sheetData/m:row", _NS):
                if len(rows) >= MOST_ROWS:
                    raise SheetError(f"sheet '{name}' has more than {MOST_ROWS} rows")
                try:
                    number = int(row.get("r", len(rows) + 1))
                except ValueError:
                    number = len(rows) + 1
                if number > MOST_ROWS:
                    raise SheetError(f"sheet '{name}' has a row numbered {number}, more than {MOST_ROWS}")
                while len(rows) < number - 1:
                    rows.append([])  # an empty row Excel left out
                cells: list[str] = []
                for position, cell in enumerate(row.findall("m:c", _NS)):
                    reference = cell.get("r")
                    letters = re.match(r"[A-Za-z]+", reference or "")
                    if reference and not letters:
                        # A reference with no column letter cannot say which column it is (D-75).
                        raise SheetError(f"sheet '{name}' has a cell '{reference}' with no column letter")
                    index = column_index(letters.group(0)) if letters else position
                    if index >= MOST_COLUMNS:
                        raise SheetError(f"sheet '{name}' has a cell beyond Excel's last column")
                    kind = cell.get("t", "n")
                    value_node = cell.find("m:v", _NS)
                    raw = value_node.text if value_node is not None and value_node.text is not None else ""
                    if kind == "s":
                        text = shared[int(raw)] if raw.isdigit() and int(raw) < len(shared) else ""
                    elif kind == "inlineStr":
                        inline = cell.find("m:is", _NS)
                        text = _text(inline) if inline is not None else ""
                    elif kind == "b":
                        text = "TRUE" if raw == "1" else "FALSE"
                    elif kind == "str":
                        text = raw
                    elif kind == "e":
                        # #N/A, #REF! ...: a formula that failed, never a value to write.
                        text = Converted(raw, "an error") if raw else ""
                    else:
                        text = number_text(raw) if raw else ""
                        try:
                            style = styles[int(cell.get("s", "0"))]
                        except (ValueError, IndexError):
                            style = None
                        if text and style:
                            text = Converted(text, style)
                    while len(cells) < index:
                        cells.append("")
                    if index < len(cells):
                        cells[index] = text
                    else:
                        cells.append(text)
                rows.append(cells)
            sheets[name] = rows
        if not sheets:
            raise SheetError("the workbook has no sheets")
        return sheets
