"""
build_inventory_data.py
FloSports BI TOC – inventory processor
Generates data/site-data.json and data/clean_inventory.csv from the Domo export.
"""

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
SOURCE = WORKSPACE / "TOC_export.csv"
DATA_DIR = WORKSPACE / "data"
DOCS_DIR = WORKSPACE / "docs"
TODAY = datetime(2026, 6, 18, tzinfo=timezone.utc)

DATA_DIR.mkdir(exist_ok=True)
DOCS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# TOC Area classification rules
# Priority order matters — first match wins after scoring
# Each tuple: (Area label, [page/title/dataset keywords])
# ---------------------------------------------------------------------------
CATEGORY_RULES = [
    (
        "Executive",
        [
            "exec dashboard", "exec summary", "board deck", "ceo dash",
            "slt deck", "slt metrics", "monthly kpi", "scorecard",
            "investor deck", "weekly metrics presentation",
            "okr", "kpi sheet", "company plan", "leadership",
        ],
    ),
    (
        "Subscriber Health",
        [
            "retention", "churn", "renewal", "subscriber", "subscribers",
            "subscription", "subscriptions", "stc", "active sub",
            "active subs", "reactivat", "ltv", "m1", "y1",
            "period", "pause", "pausing", "college sub", "ahl subs",
        ],
    ),
    (
        "Acquisition & Funnel",
        [
            "signup", "signups", "funnel", "conversion", "cvr",
            "acquisition", "trial", "plans page", "pay page",
            "attribution forecast", "organic search", "landing page",
            "today's signups", "signup forecast", "signup pacing",
            "ms signups", "milesplit signups",
        ],
    ),
    (
        "Marketing",
        [
            "marketing", "paid media", "campaign", "email marketing",
            "utm", "seo", "sem", "brand", "affiliate",
            "channel attribution", "marketing channels", "marketing wbr",
            "growth marketing", "display", "webflow marketing",
            "hashtag", "iterable",
        ],
    ),
    (
        "Revenue & Finance",
        [
            "revenue", "arr", "mrr", "cash", "booking", "bookings",
            "financial report", "finance", "budget", "forecast",
            "invoice", "expense", "cost", "ebitda", "margin",
            "accounting", "p&l", "pnl", "netsuite", "eca",
            "raq", "weighted pipeline", "unit economics", "ltv",
            "ad sales revenue", "ad revenue", "editorial revenue",
            "cloud spend", "cloud cost", "finops",
        ],
    ),
    (
        "Ad Sales",
        [
            "ad sales", "ad revenue", "display ad", "pip ads",
            "fast channel", "social monetization", "live events and display",
            "netsuite",
        ],
    ),
    (
        "Content & Viewership",
        [
            "content", "viewership", "video", "vod", "live stream",
            "stream", "event deep dive", "event viewership",
            "rights deep dive", "rights", "programming",
            "films", "studio shows", "social media post",
            "sprout social", "live to social", "event post",
            "event intensity", "video views", "stream perf",
            "stream stat", "stream quality", "total views",
            "total viewership", "vod value",
        ],
    ),
    (
        "Social & Editorial",
        [
            "social media", "editorial", "social post", "hashtag",
            "instagram", "twitter", "facebook", "tiktok",
            "article", "site content pacing", "milesplit referral",
        ],
    ),
    (
        "Audience & Traffic",
        [
            "audience", "traffic", "visit", "visits", "session",
            "viewership", "watch", "engagement", "wau", "mau",
            "unique viewer", "google analytics", "web traffic",
            "vertical performance", "platform comparison", "device",
            "buffering", "uptime", "internet dashboard",
        ],
    ),
    (
        "Product & Tech",
        [
            "product", "app", "android", "ios", "platform",
            "feature", "device", "browse", "reader app",
            "onboarding", "stream performance", "encoders",
            "stream date", "app reviews",
        ],
    ),
    (
        "Partnerships",
        [
            "partner", "global partner", "psat", "rights contract",
            "rights terms", "pma", "hockeytv", "milesplit partner",
            "resonate", "racing segmentation",
        ],
    ),
    (
        "Customer Success",
        [
            "customer service", "csat", "support", "disputes",
            "survey", "cancellation survey", "churn survey",
            "verbatim", "voice of customer", "uaa",
        ],
    ),
    (
        "Operations",
        [
            "operations", "ops", "workflow", "qa", "fulfillment",
            "load management", "mttr", "mttm", "incident",
            "fsm", "mm operations",
        ],
    ),
    (
        "Domo Admin",
        [
            "domo stats", "domo cost", "instance governance",
            "domo dashboard", "dashboard usage", "dataset",
            "dataflow", "sot log", "sot poc", "de church",
            "data engineering",
        ],
    ),
]


def parse_date(value):
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def clean_text(value):
    return re.sub(r"\s+", " ", (value or "").strip())


def normalize(value):
    value = clean_text(value).lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def is_noise_page(page_name):
    """Flag pages that are clearly clutter/personal and should be retired."""
    p = page_name.lower()
    noise = [
        "sandbox", "graveyard", "scratch", "test", "temp",
        "wip ", "draft", "dep - ", "dep warning", "dep-",
        "deprecated", "depracated", "archive", "zz -",
        "copy of ", "murman goofin", "orphan",
    ]
    personal = [
        "joe's", "charles c.", "matthew w", "sam's", "adair",
        "cyon's", "dave s.", "leah's", "emi's", "bart ",
        "landon", "madhu", "trevor's", "gunter's", "dl wip",
        "jh dash", "lj's", "daniel test", "sam puri",
        "christie", "murman sand",
    ]
    return any(n in p for n in noise + personal)


def categorize(row):
    """Score a row against all category rules; return best match."""
    page = row.get("Page", "") or ""
    title = row.get("Title", "") or ""
    dataset = row.get("Dataset Name", "") or ""
    desc = row.get("Description", "") or ""
    haystack = " ".join([page, title, dataset, desc]).lower()

    scores = []
    for area, terms in CATEGORY_RULES:
        score = sum(1 for term in terms if term in haystack)
        if score:
            scores.append((score, area))

    if not scores:
        return "Unmapped"
    scores.sort(reverse=True)
    return scores[0][1]


def first_pass_action(item):
    """Assign a cleanup action based on flags and category."""
    page = (item.get("page") or "").lower()
    title = (item.get("title") or "").lower()

    if item["isNoisePage"]:
        return "Retire"
    if item["pageId"] in ("-100002", "-100002.0") or page == "shared":
        return "Triage"
    if item["ageDays"] is not None and item["ageDays"] >= 730:
        return "Review → Retire"
    if item["ageDays"] is not None and item["ageDays"] >= 365:
        return "Review → Keep or Retire"
    if item["duplicateTitlePages"] > 1:
        return "Merge"
    if not item["description"]:
        return "Document"
    return "Keep"


def pct(value, total):
    if not total:
        return 0
    return round(value / total * 100, 1)


def top_counter(counter, n):
    return [{"name": k, "count": v} for k, v in counter.most_common(n)]


def main():
    print(f"Reading {SOURCE} …")
    with SOURCE.open(encoding="utf-8-sig") as fh:
        raw_rows = list(csv.DictReader(fh))
    print(f"  {len(raw_rows):,} rows loaded.")

    # Deduplicate on Card ID (keep first)
    seen_ids = set()
    rows = []
    for r in raw_rows:
        cid = r.get("Card ID", "").strip()
        if cid not in seen_ids:
            seen_ids.add(cid)
            rows.append(r)
    print(f"  {len(rows):,} rows after dedup on Card ID.")

    # Identify duplicate titles across pages
    title_page_map = defaultdict(set)
    for r in rows:
        nt = normalize(r.get("Title", ""))
        page = clean_text(r.get("Page", ""))
        if nt:
            title_page_map[nt].add(page)

    inventory = []
    for r in rows:
        card_id = clean_text(r.get("Card ID", ""))
        title = clean_text(r.get("Title", ""))
        page = clean_text(r.get("Page", ""))
        page_id = clean_text(r.get("Page ID", ""))
        owner_name = clean_text(r.get("Owner Name", ""))
        card_type = clean_text(r.get("Card Type", ""))
        dataset_name = clean_text(r.get("Dataset Name", ""))
        description = clean_text(r.get("Description", ""))
        locked = r.get("Locked", "").strip().lower() == "true"
        batch_last_run = clean_text(r.get("_BATCH_LAST_RUN_", ""))

        modified_dt = parse_date(r.get("Last Modified Date/Time", ""))
        last_modified = modified_dt.strftime("%Y-%m-%d") if modified_dt else ""
        age_days = (TODAY - modified_dt).days if modified_dt else None

        norm_title = normalize(title)
        dup_pages = len(title_page_map.get(norm_title, set()))
        noise_page = is_noise_page(page)

        item = {
            "cardId": card_id,
            "title": title,
            "normalizedTitle": norm_title,
            "page": page,
            "pageId": page_id,
            "ownerName": owner_name,
            "cardType": card_type,
            "datasetName": dataset_name,
            "description": description,
            "locked": locked,
            "lastModified": last_modified,
            "ageDays": age_days,
            "duplicateTitlePages": dup_pages,
            "isNoisePage": noise_page,
            "batchLastRun": batch_last_run,
        }

        item["category"] = categorize(r)
        item["action"] = first_pass_action(item)
        item["flags"] = _build_flags(item, dup_pages)
        inventory.append(item)

    total = len(inventory)
    page_counter = Counter(item["page"] for item in inventory)
    owner_counter = Counter(item["ownerName"] or "Unknown" for item in inventory)
    dataset_counter = Counter(item["datasetName"] or "Unknown" for item in inventory)
    type_counter = Counter(item["cardType"] or "Unknown" for item in inventory)
    category_counter = Counter(item["category"] for item in inventory)
    action_counter = Counter(item["action"] for item in inventory)
    flag_counter = Counter(flag for item in inventory for flag in item["flags"])

    stale_365 = sum(1 for i in inventory if i["ageDays"] is not None and i["ageDays"] >= 365)
    stale_730 = sum(1 for i in inventory if i["ageDays"] is not None and i["ageDays"] >= 730)
    recent_90 = sum(1 for i in inventory if i["ageDays"] is not None and i["ageDays"] <= 90)
    no_description = sum(1 for i in inventory if not i["description"])
    no_dataset = sum(1 for i in inventory if not i["datasetName"])
    locked_count = sum(1 for i in inventory if i["locked"])
    duplicate_cards = sum(1 for i in inventory if i["duplicateTitlePages"] > 1)
    noise_cards = sum(1 for i in inventory if i["isNoisePage"])

    page_stats = _build_page_stats(inventory, page_counter)
    category_stats = _build_category_stats(inventory, category_counter)
    stale_buckets = _build_stale_buckets(inventory)

    clean_rows = [
        {
            "Card ID": i["cardId"],
            "Title": i["title"],
            "Current Page": i["page"],
            "Proposed Area": i["category"],
            "Action": i["action"],
            "Flags": "; ".join(i["flags"]),
            "Owner": i["ownerName"],
            "Card Type": i["cardType"],
            "Dataset": i["datasetName"],
            "Last Modified": i["lastModified"],
            "Age Days": i["ageDays"],
            "Has Description": "Yes" if i["description"] else "No",
            "Locked": "Yes" if i["locked"] else "No",
        }
        for i in inventory
    ]
    clean_csv = DATA_DIR / "clean_inventory.csv"
    with clean_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(clean_rows[0].keys()))
        writer.writeheader()
        writer.writerows(clean_rows)
    print(f"  Wrote {clean_csv}")

    summary = {
        "sourceFile": str(SOURCE),
        "generatedAt": TODAY.strftime("%Y-%m-%d"),
        "batchLastRun": max(
            (i["batchLastRun"] for i in inventory if i["batchLastRun"]), default=""
        ),
        "totals": {
            "cards": total,
            "pages": len(page_counter),
            "owners": len(owner_counter),
            "datasets": len(dataset_counter),
            "cardTypes": len(type_counter),
            "stale365": stale_365,
            "stale365Pct": pct(stale_365, total),
            "veryStale730": stale_730,
            "veryStale730Pct": pct(stale_730, total),
            "recent90": recent_90,
            "recent90Pct": pct(recent_90, total),
            "missingDescriptions": no_description,
            "missingDescriptionsPct": pct(no_description, total),
            "missingDatasets": no_dataset,
            "missingDatasetsPct": pct(no_dataset, total),
            "locked": locked_count,
            "lockedPct": pct(locked_count, total),
            "duplicateTitleCards": duplicate_cards,
            "duplicateTitleCardsPct": pct(duplicate_cards, total),
            "singleCardPages": sum(1 for _, c in page_counter.items() if c == 1),
            "noisePageCards": noise_cards,
            "noisePageCardsPct": pct(noise_cards, total),
        },
        "topPages": page_stats[:50],
        "categoryStats": category_stats,
        "topOwners": top_counter(owner_counter, 25),
        "topDatasets": top_counter(dataset_counter, 25),
        "cardTypes": top_counter(type_counter, 20),
        "actions": top_counter(action_counter, 10),
        "flags": top_counter(flag_counter, 20),
        "staleBuckets": stale_buckets,
    }

    site_inventory = [
        {
            "id": i["cardId"],
            "title": i["title"],
            "page": i["page"],
            "category": i["category"],
            "action": i["action"],
            "flags": i["flags"],
            "owner": i["ownerName"] or "Unknown",
            "type": i["cardType"] or "Unknown",
            "dataset": i["datasetName"] or "Unknown",
            "lastModified": i["lastModified"],
            "ageDays": i["ageDays"],
            "isNoisePage": i["isNoisePage"],
        }
        for i in inventory
    ]

    site_data_path = DATA_DIR / "site-data.json"
    with site_data_path.open("w", encoding="utf-8") as fh:
        json.dump({**summary, "inventory": site_inventory}, fh, indent=2)
    print(f"  Wrote {site_data_path}")

    _write_summary_md(summary, page_stats, category_stats)
    print("\nTotals:")
    print(json.dumps(summary["totals"], indent=2))


def _build_flags(item, dup_pages):
    flags = []
    if item["ageDays"] is not None and item["ageDays"] >= 730:
        flags.append("Very stale (2+ yrs)")
    elif item["ageDays"] is not None and item["ageDays"] >= 365:
        flags.append("Stale (1+ yr)")
    if not item["description"]:
        flags.append("No description")
    if not item["datasetName"]:
        flags.append("No dataset")
    if item["locked"]:
        flags.append("Locked")
    if dup_pages > 1:
        flags.append("Duplicate title")
    if item["isNoisePage"]:
        flags.append("Noise page")
    if item["page"].lower() == "shared" or item["pageId"] in ("-100002", "-100002.0"):
        flags.append("Shared/root")
    if item["page"].lower() == "orphan":
        flags.append("Orphan")
    return flags


def _build_page_stats(inventory, page_counter):
    page_stats = []
    for page, count in page_counter.most_common():
        page_items = [i for i in inventory if i["page"] == page]
        stale_count = sum(1 for i in page_items if i["ageDays"] is not None and i["ageDays"] >= 365)
        no_desc_count = sum(1 for i in page_items if not i["description"])
        dup_count = sum(1 for i in page_items if i["duplicateTitlePages"] > 1)
        categories = Counter(i["category"] for i in page_items)
        owners = Counter(i["ownerName"] or "Unknown" for i in page_items)
        datasets = Counter(i["datasetName"] or "Unknown" for i in page_items)
        latest = max((i["lastModified"] for i in page_items if i["lastModified"]), default="")
        noise = page_items[0]["isNoisePage"] if page_items else False
        page_stats.append(
            {
                "page": page,
                "cards": count,
                "category": categories.most_common(1)[0][0],
                "isNoise": noise,
                "staleCards": stale_count,
                "stalePct": pct(stale_count, count),
                "missingDescription": no_desc_count,
                "missingDescriptionPct": pct(no_desc_count, count),
                "duplicateTitleCards": dup_count,
                "duplicateTitlePct": pct(dup_count, count),
                "owners": len(owners),
                "datasets": len(datasets),
                "latestModified": latest,
            }
        )
    return page_stats


def _build_category_stats(inventory, category_counter):
    category_stats = []
    for category, count in category_counter.most_common():
        cat_items = [i for i in inventory if i["category"] == category]
        pages = Counter(i["page"] for i in cat_items)
        stale_count = sum(1 for i in cat_items if i["ageDays"] is not None and i["ageDays"] >= 365)
        dup_count = sum(1 for i in cat_items if i["duplicateTitlePages"] > 1)
        missing_count = sum(1 for i in cat_items if not i["description"])
        category_stats.append(
            {
                "category": category,
                "cards": count,
                "pages": len(pages),
                "staleCards": stale_count,
                "stalePct": pct(stale_count, count),
                "duplicateTitleCards": dup_count,
                "duplicateTitlePct": pct(dup_count, count),
                "missingDescription": missing_count,
                "missingDescriptionPct": pct(missing_count, count),
                "topPages": [{"name": p, "count": c} for p, c in pages.most_common(6)],
            }
        )
    return category_stats


def _build_stale_buckets(inventory):
    return [
        {"bucket": "0–90 days", "count": sum(1 for i in inventory if i["ageDays"] is not None and i["ageDays"] <= 90)},
        {"bucket": "91–180 days", "count": sum(1 for i in inventory if i["ageDays"] is not None and 91 <= i["ageDays"] <= 180)},
        {"bucket": "181–365 days", "count": sum(1 for i in inventory if i["ageDays"] is not None and 181 <= i["ageDays"] <= 365)},
        {"bucket": "1–2 years", "count": sum(1 for i in inventory if i["ageDays"] is not None and 366 <= i["ageDays"] <= 730)},
        {"bucket": "2+ years", "count": sum(1 for i in inventory if i["ageDays"] is not None and i["ageDays"] > 730)},
        {"bucket": "Unknown", "count": sum(1 for i in inventory if i["ageDays"] is None)},
    ]


def _write_summary_md(summary, page_stats, category_stats):
    t = summary["totals"]
    md = [
        "# Domo Inventory — Spring Cleaning First Pass",
        "",
        f"Source: `{Path(summary['sourceFile']).name}`  |  Generated: `{summary['generatedAt']}`",
        "",
        "## Snapshot",
        "",
        f"| Metric | Count | % of total |",
        f"|---|---|---|",
        f"| Total cards | {t['cards']:,} | — |",
        f"| Total pages | {t['pages']:,} | — |",
        f"| Owners | {t['owners']:,} | — |",
        f"| Datasets | {t['datasets']:,} | — |",
        f"| Stale 12+ months | {t['stale365']:,} | {t['stale365Pct']}% |",
        f"| Very stale 24+ months | {t['veryStale730']:,} | {t['veryStale730Pct']}% |",
        f"| Missing descriptions | {t['missingDescriptions']:,} | {t['missingDescriptionsPct']}% |",
        f"| Duplicate-title cards | {t['duplicateTitleCards']:,} | {t['duplicateTitleCardsPct']}% |",
        f"| Single-card pages | {t['singleCardPages']:,} | — |",
        f"| Noise/sandbox pages | {t['noisePageCards']:,} | {t['noisePageCardsPct']}% |",
        "",
        "## Proposed TOC Areas",
        "",
    ]
    for row in category_stats:
        md.append(
            f"- **{row['category']}**: {row['cards']:,} cards across {row['pages']:,} pages "
            f"({row['stalePct']}% stale, {row['missingDescriptionPct']}% undocumented)"
        )
    md += [
        "",
        "## Largest Current Pages (Top 20)",
        "",
    ]
    for row in page_stats[:20]:
        noise_flag = " ⚠️ NOISE" if row["isNoise"] else ""
        md.append(
            f"- **{row['page']}**{noise_flag}: {row['cards']:,} cards, "
            f"{row['owners']} owners, {row['stalePct']}% stale"
        )
    md += [
        "",
        "## Recommended Next Steps",
        "",
        "1. Confirm area labels for the top 20 pages.",
        "2. Retire all DEP / sandbox / graveyard pages (auto-flagged as 'Noise').",
        "3. Consolidate Orphan (450 cards) and Shared (265 cards) — triage individually.",
        "4. Merge duplicate-title cards across pages.",
        "5. Add descriptions to surviving cards (only 11% have them today).",
        "6. Define a page owner for each new TOC area page.",
    ]
    (DOCS_DIR / "inventory_summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"  Wrote {DOCS_DIR / 'inventory_summary.md'}")


if __name__ == "__main__":
    main()
