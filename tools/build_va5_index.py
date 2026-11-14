"""Build data/va5_index.json: every Vital Articles Level 5 title with its place on the blueprint pages.

Reads the v1 build's cache of the Level 5 list pages (va5_pages.json: {"pages": {title: {"rev", "text"}}}) and parses it
with the same rules as the testbed's gen_rabbit.py "corpus" step (topic order from the main table, headings, first
occurrence wins, non-article namespaces skipped), so the shelf order matches the v1 build.

Output (compact):
  {"v": 1, "fetched": unix, "count": N,
   "lists":  [sub-list display name, ...],
   "paths":  [[list index, "Heading › Subheading › ..."], ...],      headings below the sub-list
   "runs":   [[path index, root floor, draft floor or 0, [title, ...]], ...]}   in shelf order
The root page (v0.3) and the v0.4 draft read the same file; the draft moves literature articles to its tower 12.

Usage: python -I tools/build_va5_index.py <va5_pages.json> <out.json> [--check <corpus_titles.json>]
"""
import argparse
import collections
import html
import json
import re
import sys

NAMES = ["People", "History", "Geography", "Arts", "Everyday life", "Philosophy and religion", "Society and social sciences",
         "Biology and health sciences", "Physical sciences", "Mathematics", "Technology"]
NS_SKIP = re.compile(r"^(file|image|category|wikipedia|wp|project|help|template|portal|user|user talk|talk|special|media|mediawiki|"
                     r"module|draft|book|timedtext|wikt|wiktionary|s|wikisource|q|wikiquote|b|wikibooks|n|wikinews|v|wikiversity|"
                     r"voy|wikivoyage|commons|c|d|wikidata|species|meta|m|mw|foundation|wmf|w|outreach|incubator|phab|doi|"
                     r"[a-z]{2,3}(-[a-z]+)?)\s*:", re.I)
P = "Wikipedia:Vital articles/Level 5/"

# Sub-list page -> floor on the pages (root v0.3 and draft v0.4 share these; several sub-lists fold into one floor)
FLOOR = {
    P + "People/Writers and journalists": "1.1",
    P + "People/Artists, musicians, and composers": "1.2",
    P + "People/Entertainers, directors, producers, and screenwriters": "1.3",
    P + "People/Philosophers, historians, political and social scientists": "1.4",
    P + "People/Religious figures": "1.5",
    P + "People/Politicians and leaders": "1.6",
    P + "People/Military personnel, revolutionaries, and activists": "1.7",
    P + "People/Scientists, inventors, and mathematicians": "1.8",
    P + "People/Sports figures": "1.9",
    P + "People/Miscellaneous": "1.10",
    P + "History": "2.1",
    P + "Geography/Technical": "3.1",            # folded: Basics and technical geography -> Physical geography
    P + "Geography/Physical": "3.1",
    P + "Geography/Regions and countries": "3.2",
    P + "Geography/Cities": "3.3",
    P + "Arts/Audiovisual arts": "4.1",          # folded: both Arts sub-lists -> one Arts floor
    P + "Arts/Narrative arts": "4.1",
    P + "Philosophy and religion": "5.1",
    P + "Everyday life": "6.1",
    P + "Everyday life/Sports, games and recreation": "6.2",
    P + "Society and social sciences/Social studies": "7.1",
    P + "Society and social sciences/Politics and economics": "7.2",
    P + "Society and social sciences/Culture": "7.3",
    P + "Biology and health sciences/Biology": "8.1",
    P + "Biology and health sciences/Animals": "8.2",
    P + "Biology and health sciences/Plants": "8.3",
    P + "Biology and health sciences/Health": "8.4",
    P + "Physical sciences/Basics and measurement": "9.1",
    P + "Physical sciences/Astronomy": "9.2",
    P + "Physical sciences/Chemistry": "9.3",
    P + "Physical sciences/Earth science": "9.4",
    P + "Physical sciences/Physics": "9.5",
    P + "Technology": "10.1",                    # folded: all six Technology sub-lists -> one Technology floor
    P + "Technology/Agriculture": "10.1",
    P + "Technology/Computing and communication": "10.1",
    P + "Technology/Optical, navigation and astronomical": "10.1",
    P + "Technology/Transportation": "10.1",
    P + "Technology/Weapons": "10.1",
    P + "Mathematics": "11.1",
}


def wiki_inline_text(s):
    for _ in range(4):
        s = re.sub(r"\{\{[^{}]*\}\}", "", s)
    s = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("'''", "").replace("''", "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def norm_title(t):
    t = html.unescape(t).replace("_", " ").replace(" ", " ")
    t = re.sub(r"\s+", " ", t).strip()
    if t.startswith(":"):
        t = t[1:].strip()
    return t[:1].upper() + t[1:] if t else t


def topics_of(pages):
    main = pages["Wikipedia:Vital articles/Level 5"]["text"]
    topics, names = [], set(NAMES)
    for line in main.split("\n"):
        if not line.startswith("|") or line[:2] in ("|-", "|}", "|+"):
            continue
        first = line.lstrip("|").split("||")[0].strip()
        m = re.search(r"\[\[(Wikipedia:Vital articles/Level 5[^|\]]*)\|([^\]]*)\]\]", first)
        if first.startswith("''") and "&nbsp;" not in first:
            nm = wiki_inline_text(first)
            if nm in names:
                topics.append([nm, []])
                if m:
                    topics[-1][1].append((m.group(1), nm))
        elif "&nbsp;" in first and m and topics:
            page, disp = m.group(1), wiki_inline_text(m.group(2))
            same = [i for i, (p, _) in enumerate(topics[-1][1]) if p == page]
            if same:
                topics[-1][1][same[0]] = (page, disp)
            else:
                topics[-1][1].append((page, disp))
    if [t[0] for t in topics] != NAMES:
        raise SystemExit("topic order changed: %r" % [t[0] for t in topics])
    return topics


def lit_floor(path, title):
    """Draft v0.4 only: a literature article's floor in tower 12 (by form first, then by language where the list says)"""
    p, t = path.lower(), title.lower()
    if "poetry" in p or "poetic works" in p:
        return "12.7"
    if "drama" in p or "shakespeare" in p:
        return "12.8"
    if "children's" in p:
        return "12.9"
    if "fiction of antiquity" in p or "antiquity from europe" in p:
        return "12.5"
    if "literatures by religion, language and region" in p:
        if "latin american" in t:
            return "12.6"
        if t.startswith(("english", "british")):
            return "12.1"
        if t.startswith("american"):
            return "12.2"
        if t.startswith("french"):
            return "12.3"
        if t.startswith("german"):
            return "12.4"
        if t.startswith(("ancient greek", "latin literature", "classical")):
            return "12.5"
    return "12.6"


def build(src):
    va = json.load(open(src, encoding="utf-8"))
    pages = va["pages"]
    lists, list_idx = [], {}
    paths, path_idx = [], {}
    runs, seen, order = [], set(), []
    stats = collections.Counter()
    for tname, subl in topics_of(pages):
        for page, disp in subl:
            if page not in pages:
                raise SystemExit("missing list page " + page)
            if page not in FLOOR:
                raise SystemExit("no floor for list page " + page)
            if disp not in list_idx:
                list_idx[disp] = len(lists)
                lists.append(disp)
            li = list_idx[disp]
            txt = re.sub(r"<!--.*?-->", "", pages[page]["text"], flags=re.S)
            heads = {}
            for line in txt.split("\n"):
                hm = re.match(r"^(={1,6})\s*(.*?)\s*\1\s*$", line)
                if hm:
                    lv = len(hm.group(1))
                    heads = {k: v for k, v in heads.items() if k < lv}
                    heads[lv] = wiki_inline_text(hm.group(2))
                    continue
                if line[:1] not in ("#", "*") or "[[" not in line:
                    continue
                lm = re.search(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", line)
                if not lm:
                    continue
                tgt = lm.group(1)
                if NS_SKIP.match(tgt.strip().lstrip(":")):
                    continue
                title = norm_title(tgt.split("#")[0])
                if not title or title in seen:
                    stats["duplicates"] += bool(title)
                    continue
                seen.add(title)
                order.append(title)
                hp = " › ".join(heads[k] for k in sorted(heads) if k >= 2)
                key = (li, hp)
                if key not in path_idx:
                    path_idx[key] = len(paths)
                    paths.append([li, hp])
                pi = path_idx[key]
                root = FLOOR[page]
                draft = 0
                if page == P + "Arts/Narrative arts" and heads.get(2) == "Literature":
                    below = " › ".join(heads[k] for k in sorted(heads) if k > 2)
                    draft = lit_floor(below, title)
                    stats["draft " + draft] += 1
                if runs and runs[-1][0] == pi and runs[-1][1] == root and runs[-1][2] == draft:
                    runs[-1][3].append(title)
                else:
                    runs.append([pi, root, draft, [title]])
                stats["floor " + root] += 1
    index = {"v": 1, "fetched": va["fetched"], "count": len(order), "lists": lists, "paths": paths, "runs": runs}
    return index, order, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--check", help="the v1 build's corpus_titles.json, to confirm the same titles in the same order")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    index, order, stats = build(a.src)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))
    size = len(json.dumps(index, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    print(json.dumps({"titles": index["count"], "runs": len(index["runs"]), "paths": len(index["paths"]), "lists": len(index["lists"]),
                      "bytes": size, "stats": dict(sorted(stats.items()))}, ensure_ascii=False, indent=1))
    if a.check:
        ref = json.load(open(a.check, encoding="utf-8"))
        same = ref == order
        print("check against build:", "identical titles and order" if same else
              "DIFFERENT: build %d titles, index %d; first difference at %s" % (
                  len(ref), len(order), next((i for i, (x, y) in enumerate(zip(ref, order)) if x != y), min(len(ref), len(order)))))
        if not same:
            sys.exit(1)


if __name__ == "__main__":
    main()
