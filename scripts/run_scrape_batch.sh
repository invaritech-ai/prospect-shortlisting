#!/usr/bin/env bash
set -euo pipefail

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required but not installed."
  exit 1
fi

BASE="${BASE:-http://127.0.0.1:8001}"
URL_FILE="${1:-data/url_batches/client_batch_2026-03-05.txt}"
GENERAL_MODEL="${GENERAL_MODEL:-openai/gpt-5-nano}"
CLASSIFY_MODEL="${CLASSIFY_MODEL:-inception/mercury-2}"

if [[ ! -f "$URL_FILE" ]]; then
  echo "URL file not found: $URL_FILE"
  exit 1
fi

RUN_ID="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="data/batch_runs/${RUN_ID}"
PAGES_DIR="${OUT_DIR}/pages"
mkdir -p "$PAGES_DIR"

SUMMARY_CSV="${OUT_DIR}/summary.csv"
echo "url,job_id,domain,status,pages_fetched_count,fetch_failures_count,markdown_pages_count,llm_used_count,llm_failed_count,last_error_code" > "$SUMMARY_CSV"

echo "Running batch from: $URL_FILE"
echo "Output dir: $OUT_DIR"
echo

total=0
while IFS= read -r raw || [[ -n "$raw" ]]; do
  url="$(echo "$raw" | xargs)"
  [[ -z "$url" || "$url" =~ ^# ]] && continue
  total=$((total + 1))
done < "$URL_FILE"

idx=0
while IFS= read -r raw || [[ -n "$raw" ]]; do
  url="$(echo "$raw" | xargs)"
  [[ -z "$url" || "$url" =~ ^# ]] && continue
  idx=$((idx + 1))
  echo "[${idx}/${total}] ${url}"

  create_payload="$(
    jq -n \
      --arg website_url "$url" \
      --arg general_model "$GENERAL_MODEL" \
      --arg classify_model "$CLASSIFY_MODEL" \
      '{
        website_url: $website_url,
        js_fallback: true,
        include_sitemap: true,
        general_model: $general_model,
        classify_model: $classify_model
      }'
  )"

  create_json="$(curl -sS -X POST "$BASE/v1/scrape-jobs" -H "Content-Type: application/json" -d "$create_payload")"
  job_id="$(echo "$create_json" | jq -r '.id // empty')"
  if [[ -z "$job_id" ]]; then
    echo "  create failed: $create_json"
    continue
  fi
  echo "  job_id=$job_id"

  job_json="$(curl -sS "$BASE/v1/scrape-jobs/${job_id}")"
  pages_json="$(curl -sS "$BASE/v1/scrape-jobs/${job_id}/pages?limit=2000")"
  echo "$job_json" > "${OUT_DIR}/${job_id}_job.json"
  echo "$pages_json" > "${PAGES_DIR}/${job_id}_pages.json"

  echo "$job_json" | jq -r --arg url "$url" \
    '[ $url, .id, .domain, .status, .pages_fetched_count, .fetch_failures_count, .markdown_pages_count, .llm_used_count, .llm_failed_count, (.last_error_code // "") ] | @csv' \
    >> "$SUMMARY_CSV"
done < "$URL_FILE"

PREVIEW_MD="${OUT_DIR}/markdown_previews.md"
python3 - "$SUMMARY_CSV" "$PREVIEW_MD" <<'PY'
import csv
import sqlite3
import sys
from pathlib import Path

summary_path = Path(sys.argv[1])
preview_path = Path(sys.argv[2])
db_path = Path("data/scrape_service.db")

conn = sqlite3.connect(str(db_path))
cur = conn.cursor()

lines = ["# Batch Markdown Previews", ""]
with summary_path.open("r", encoding="utf-8") as fh:
    reader = csv.DictReader(fh)
    for row in reader:
        job_id = (row["job_id"] or "").replace("-", "")
        url = row["url"]
        domain = row["domain"]
        status = row["status"]
        lines.append(f"## {domain} ({status})")
        lines.append(f"- source_url: {url}")
        lines.append(f"- job_id: {row['job_id']}")
        cur.execute(
            """
            SELECT url, markdown_content
            FROM scrapepage
            WHERE job_id = ?
              AND markdown_content <> ''
            ORDER BY LENGTH(markdown_content) DESC
            LIMIT 3
            """,
            (job_id,),
        )
        rows = cur.fetchall()
        if not rows:
            lines.append("- no markdown pages")
            lines.append("")
            continue
        for page_url, markdown in rows:
            snippet = (markdown or "").strip().replace("\r\n", "\n")
            snippet = snippet[:500]
            lines.append(f"- page: {page_url}")
            lines.append("```markdown")
            lines.append(snippet)
            lines.append("```")
        lines.append("")

preview_path.write_text("\n".join(lines), encoding="utf-8")
conn.close()
PY

echo
echo "Done."
echo "Summary CSV: $SUMMARY_CSV"
echo "Markdown preview: $PREVIEW_MD"
