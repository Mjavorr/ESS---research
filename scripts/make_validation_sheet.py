#!/usr/bin/env python3
"""Build the workbook for the independent manual validation (filled in by a human).

Four checks, random cases with a fixed seed, no automatic answers in the sheet:
  A  30 migrations not checked before: did the commit remove the deprecated usage?
  B  30 migration authors (15 classified core, 15 external): the author-association
     badge GitHub shows on the pull request
  C  every repository that never migrated: is the deprecated usage still present
     in the collected snapshot?
  D  20 exposed pairs not re-coded before: RQ5 codes assigned with the codebook

The selection (without answers) is written next to the workbook; the automatic
answers stay in the data files and are compared after the sheet is filled in.

Usage:
  python3 scripts/make_validation_sheet.py <clones_dir> <out_dir> [seed]
"""
import csv
import os
import random
import re
import subprocess
import sys

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from patterns import ARTIFACT_ALL, SET_OUTPUT  # noqa: E402

STRICT = {"artifact_v3": ARTIFACT_ALL["ere"], "set_output": SET_OUTPUT["ere"]}

GH = "https://github.com"
EVENT_SK = {"artifact_v3": "artifact actions v1–v3", "set_output": "set-output / save-state"}
LOOK_FOR = {"artifact_v3": "upload-artifact@ / download-artifact@ s verziou v1, v2 alebo v3 "
                           "(aj v3.1.3 alebo hash s komentárom # v3)",
            "set_output": "::set-output alebo ::save-state v run: krokoch"}
FONT = "Arial"
YELLOW = PatternFill("solid", fgColor="FFF2CC")
GREY = PatternFill("solid", fgColor="EDEDED")
HEAD = PatternFill("solid", fgColor="D9E2F3")


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if r.returncode not in (0, 1):
        raise RuntimeError(f"git {' '.join(args)} failed in {repo}: {r.stderr[:200]}")
    return r.stdout.strip()


def read(path):
    return list(csv.DictReader(open(path), delimiter="\t"))


def link(cell, url, text):
    cell.value = text
    cell.hyperlink = url
    cell.font = Font(name=FONT, color="0563C1", underline="single")


def sheet(wb, title, intro, headers, widths):
    ws = wb.create_sheet(title)
    ws["A1"] = intro
    ws["A1"].font = Font(name=FONT, bold=True)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    ws["A1"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[1].height = 48
    for i, (h, w) in enumerate(zip(headers, widths), 1):
        c = ws.cell(row=2, column=i, value=h)
        c.font = Font(name=FONT, bold=True)
        c.fill = HEAD
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.column_dimensions[c.column_letter].width = w
    ws.freeze_panes = "A3"
    return ws


def style_row(ws, row, ncols, fill_cols, example=False):
    for col in range(1, ncols + 1):
        c = ws.cell(row=row, column=col)
        if c.hyperlink is None:
            c.font = Font(name=FONT, italic=example, color="7F7F7F" if example else "000000")
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if example:
            c.fill = GREY
        elif col in fill_cols:
            c.fill = YELLOW


def dropdown(ws, col_letter, options, first, last):
    dv = DataValidation(type="list", formula1='"' + ",".join(options) + '"', allow_blank=True)
    dv.add(f"{col_letter}{first}:{col_letter}{last}")
    ws.add_data_validation(dv)


def pr_number(subject):
    m = re.search(r"Merge pull request #(\d+)|\(#(\d+)\)\s*$", subject or "")
    return (m.group(1) or m.group(2)) if m else None


def main(clones, out_dir, seed=20261110):
    rng = random.Random(seed)
    os.makedirs(out_dir, exist_ok=True)
    scan = {(r["repo"], r["event"]): r for r in read("data/sample/scan_all.tsv")}
    feats = {(r["repo"], r["event"]): r for r in read("data/sample/features.tsv")}
    checked = {(r["repo"], r["event"]) for r in read("data/sample/validation_subsample.tsv")}
    spot = {(r["repo"], r["event"]) for r in read("data/sample/rq5_spotcheck.tsv")}
    exposed = sorted(k for k, r in scan.items() if r["exposed_at_warning"] not in ("0", ""))
    migrated = [k for k in exposed if scan[k]["migration_commit"]]
    never = [k for k in exposed if not scan[k]["migration_commit"]]
    selection = []

    wb = Workbook()
    guide = wb.active
    guide.title = "Navod"
    lines = [
        ("Nezávislá ručná kontrola dát", True),
        ("", False),
        ("Čo robiť: v každom hárku otvor odkaz v riadku, pozri sa na GitHube a vyplň ŽLTÉ bunky.", False),
        ("Šedý riadok na začiatku každého hárku je vyplnený príklad, ten nemeň.", False),
        ("Kde je rozbaľovací zoznam, vyber hodnotu z neho. Ak si nie si istý, vyber 'neviem' a napíš poznámku.", False),
        ("Nepozeraj sa do súborov v data/sample/ ani do výsledkov, aby ťa automatické odpovede neovplyvnili.", False),
        ("", False),
        ("A_migracie  (30 riadkov, ~45 min): odstránil commit deprecovaný zápis?", False),
        ("B_autori    (30 riadkov, ~45 min): aký štítok má autor pull requestu?", False),
        ("C_nemigrovane (všetky, ~20 min): je deprecovaný zápis v uloženej verzii stále tam?", False),
        ("D_RQ5       (20 riadkov, ~60 min): zakóduj migráciu podľa codebooku (docs/rq5_codebook.md).", False),
        ("", False),
        ("Udalosti:", True),
        ("artifact actions v1–v3: actions/upload-artifact a actions/download-artifact vo verzii v1, v2 alebo v3 "
         "(v uses: riadku workflowu). GitHub ich vypol (v1/v2 30. 6. 2024, v3 30. 1. 2025).", False),
        ("set-output / save-state: príkazy echo \"::set-output name=...::...\" v run: krokoch; náhrada je zápis "
         "do $GITHUB_OUTPUT. Ohlásené vypnutie 31. 5. 2023 GitHub odložil.", False),
        ("", False),
        ("Po vyplnení súbor ulož pod rovnakým menom a pošli ho späť; zhodu spočítame skriptom.", False),
    ]
    for i, (t, bold) in enumerate(lines, 1):
        c = guide.cell(row=i, column=1, value=t)
        c.font = Font(name=FONT, bold=bold, size=12 if i == 1 else 10)
    guide.column_dimensions["A"].width = 130

    # ---------------- A: migrations
    pool = [k for k in migrated if k not in checked]
    pick = rng.sample(pool, min(30, len(pool)))
    ws = sheet(wb, "A_migracie",
               "A: Otvor commit. Pozri diff súborov v .github/workflows. Odstránil tento commit (alebo pull request, "
               "ktorý zlučuje) deprecovaný zápis tak, že po ňom v repozitári žiadny nezostal?",
               ["ID", "Repozitár", "Udalosť", "Čo hľadať v diffe", "Commit", "Dátum commitu",
                "Odstránil deprecovaný zápis?", "Ako (bump / úprava / zmazanie / iné)", "Poznámka"],
               [7, 32, 20, 40, 14, 12, 16, 22, 40])
    ws.append(["príklad", "redis/redis", EVENT_SK["artifact_v3"], LOOK_FOR["artifact_v3"],
               "e3b9397", "2025-02-01", "áno", "bump", "v3 → v4 v jednom súbore"])
    link(ws.cell(row=3, column=5), f"{GH}/redis/redis/commit/e3b9397dfe", "e3b9397")
    style_row(ws, 3, 9, [], example=True)
    for i, k in enumerate(pick, 1):
        r = scan[k]
        ws.append([f"A{i:02d}", k[0], EVENT_SK[k[1]], LOOK_FOR[k[1]], "", r["migration_date"], "", "", ""])
        link(ws.cell(row=ws.max_row, column=5), f"{GH}/{k[0]}/commit/{r['migration_commit']}", r["migration_commit"])
        style_row(ws, ws.max_row, 9, [7, 8, 9])
        selection.append(["A", f"A{i:02d}", k[0], k[1], r["migration_commit"]])
    dropdown(ws, "G", ["áno", "nie", "neviem"], 4, ws.max_row)
    dropdown(ws, "H", ["bump", "úprava", "zmazanie", "iné"], 4, ws.max_row)

    # ---------------- B: authors
    human = [k for k in migrated if feats[k].get("author_kind") in ("core", "external")]
    core = [k for k in human if feats[k]["author_kind"] == "core"]
    ext = [k for k in human if feats[k]["author_kind"] == "external"]
    pick = rng.sample(core, min(15, len(core))) + rng.sample(ext, min(15, len(ext)))
    rng.shuffle(pick)
    ws = sheet(wb, "B_autori",
               "B: Otvor commit. Pod správou commitu GitHub ukazuje odkaz na pull request (napr. #1234); otvor ho. "
               "Pri mene autora PR je štítok (Owner, Member, Collaborator, Contributor, First-time contributor). "
               "Ak PR neexistuje (commit išiel priamo na hlavnú vetvu), vyber 'bez PR'.",
               ["ID", "Repozitár", "Autor zmeny (meno v gite)", "Commit so zmenou", "Pull request",
                "Štítok autora PR", "GitHub login autora PR", "Poznámka"],
               [7, 32, 26, 14, 14, 22, 22, 40])
    ws.append(["príklad", "bazelbuild/rules_pkg", "Régis Desgroppes", "93d561d", "(cez commit)", "Contributor",
               "rdesgroppes", "externý prispievateľ"])
    link(ws.cell(row=3, column=4), f"{GH}/bazelbuild/rules_pkg/commit/93d561d", "93d561d")
    style_row(ws, 3, 8, [], example=True)
    for i, k in enumerate(pick, 1):
        f, r = feats[k], scan[k]
        ws.append([f"B{i:02d}", k[0], f["author"], "", "", "", "", ""])
        link(ws.cell(row=ws.max_row, column=4), f"{GH}/{k[0]}/commit/{f['change_commit']}", f["change_commit"])
        n = pr_number(r["migration_subject"])
        if n:
            link(ws.cell(row=ws.max_row, column=5), f"{GH}/{k[0]}/pull/{n}", f"#{n}")
        else:
            ws.cell(row=ws.max_row, column=5, value="(cez commit)")
        style_row(ws, ws.max_row, 8, [6, 7, 8])
        selection.append(["B", f"B{i:02d}", k[0], k[1], f["change_commit"]])
    dropdown(ws, "F", ["Owner", "Member", "Collaborator", "Contributor", "First-time contributor",
                       "bez štítku", "bez PR", "neviem"], 4, ws.max_row)

    # ---------------- C: never migrated
    ws = sheet(wb, "C_nemigrovane",
               "C: Odkaz vedie na súbor v presne tej verzii, ktorú sme analyzovali (dátum zberu dát). Na označenom "
               "riadku by mal byť deprecovaný zápis. Je tam naozaj a je aktívny (nie zakomentovaný)?",
               ["ID", "Repozitár", "Udalosť", "Čo hľadať", "Odkaz na riadok", "Je tam aktívny deprecovaný zápis?",
                "Poznámka"],
               [7, 32, 20, 40, 34, 18, 40])
    ws.append(["príklad", "httpie/cli", EVENT_SK["artifact_v3"], LOOK_FOR["artifact_v3"], "release-linux-standalone.yml",
               "áno", "upload-artifact@v3 v kroku Upload"])
    link(ws.cell(row=3, column=5), f"{GH}/httpie/cli/blob/HEAD/.github/workflows/release-linux-standalone.yml",
         "release-linux-standalone.yml")
    style_row(ws, 3, 7, [], example=True)
    for i, k in enumerate(never, 1):
        repo = os.path.join(clones, k[0].replace("/", "__", 1))
        head = git(repo, "rev-parse", "HEAD")
        hit = git(repo, "grep", "-n", "-E", STRICT[k[1]], head, "--", ".github/workflows").splitlines()
        url, text = f"{GH}/{k[0]}/tree/{head}/.github/workflows", "workflows"
        if hit:
            _, path, line = hit[0].split(":", 3)[:3]
            url, text = f"{GH}/{k[0]}/blob/{head}/{path}#L{line}", f"{os.path.basename(path)}:{line}"
        ws.append([f"C{i:02d}", k[0], EVENT_SK[k[1]], LOOK_FOR[k[1]], "", "", ""])
        link(ws.cell(row=ws.max_row, column=5), url, text)
        style_row(ws, ws.max_row, 7, [6, 7])
        selection.append(["C", f"C{i:02d}", k[0], k[1], head[:10]])
    dropdown(ws, "F", ["áno", "nie", "neviem"], 4, ws.max_row)

    # ---------------- D: RQ5 coding
    pool = [k for k in exposed if k not in spot]
    pick = rng.sample(pool, min(20, len(pool)))
    ws = sheet(wb, "D_RQ5",
               "D: Zakóduj podľa docs/rq5_codebook.md v repozitári. Typ zmeny a spúšťač: jedna hodnota. Problém: "
               "hlavný problém (ak sú dva, druhý napíš do poznámky). Pri nemigrovaných je typ 'none' a spúšťač prázdny.",
               ["ID", "Repozitár", "Udalosť", "Migračný commit / workflowy", "Typ zmeny", "Spúšťač", "Problém",
                "Poznámka"],
               [7, 32, 20, 22, 14, 14, 16, 40])
    ws.append(["príklad", "mhammond/pywin32", EVENT_SK["artifact_v3"], "373bb5cfad", "adapt", "targeted",
               "incompatibility", "unikátne mená artefaktov + merge krok"])
    link(ws.cell(row=3, column=4), f"{GH}/mhammond/pywin32/commit/373bb5cfad", "373bb5cfad")
    style_row(ws, 3, 8, [], example=True)
    for i, k in enumerate(pick, 1):
        r = scan[k]
        ws.append([f"D{i:02d}", k[0], EVENT_SK[k[1]], "", "", "", "", ""])
        if r["migration_commit"]:
            link(ws.cell(row=ws.max_row, column=4), f"{GH}/{k[0]}/commit/{r['migration_commit']}", r["migration_commit"])
        else:
            link(ws.cell(row=ws.max_row, column=4), f"{GH}/{k[0]}/tree/HEAD/.github/workflows", "nemigrované")
        style_row(ws, ws.max_row, 8, [5, 6, 7, 8])
        selection.append(["D", f"D{i:02d}", k[0], k[1], r["migration_commit"]])
    dropdown(ws, "E", ["bump", "adapt", "remove", "replace", "none"], 4, ws.max_row)
    dropdown(ws, "F", ["bot", "breakage", "deprecation", "targeted", "routine", "incidental"], 4, ws.max_row)
    dropdown(ws, "G", ["none", "incompatibility", "environment", "regression", "multiline", "deferral"], 4, ws.max_row)
    ws["E2"].comment = Comment("bump / adapt / remove / replace / none — definície v docs/rq5_codebook.md", "ESS")

    wb.save(os.path.join(out_dir, "manual_validation.xlsx"))
    with open(os.path.join(out_dir, "selection.tsv"), "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["check", "id", "repo", "event", "commit"])
        w.writerows(selection)
    print({c: sum(1 for s in selection if s[0] == c) for c in "ABCD"})


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], *(int(a) for a in sys.argv[3:4]))
