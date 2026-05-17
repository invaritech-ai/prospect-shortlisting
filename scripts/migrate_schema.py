#!/usr/bin/env python3
"""
Schema migration script — simplified 14-table design.

Usage:
    # Step 1: build new schema in temp DB and migrate data (safe, never touches prod)
    uv run python scripts/migrate_schema.py --setup-temp \\
        --source-db postgresql://... \\
        --temp-db postgresql://...

    # Step 2: replicate temp DB to prod (only after you're satisfied with testing)
    uv run python scripts/migrate_schema.py --apply-prod \\
        --temp-db postgresql://... \\
        --prod-db postgresql://...
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import textwrap
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, MofNCompleteColumn
from rich.table import Table
from rich import print as rprint

console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def confirm(prompt: str) -> None:
    answer = console.input(f"\n[bold yellow]{prompt}[/bold yellow] [yes/no]: ").strip().lower()
    if answer not in ("yes", "y"):
        console.print("[red]Aborted.[/red]")
        sys.exit(0)


def make_engine(url: str) -> sa.Engine:
    return create_engine(url, future=True)


def row_counts(conn: sa.Connection, tables: list[str]) -> dict[str, int]:
    counts = {}
    for t in tables:
        try:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {t}"))
            counts[t] = result.scalar() or 0
        except Exception:
            counts[t] = -1  # table doesn't exist
    return counts


def print_counts(label: str, counts: dict[str, int]) -> None:
    table = Table(title=label, show_header=True, header_style="bold cyan")
    table.add_column("Table", style="dim")
    table.add_column("Rows", justify="right")
    for name, count in sorted(counts.items()):
        val = f"{count:,}" if count >= 0 else "[red]missing[/red]"
        table.add_row(name, val)
    console.print(table)


NEW_TABLES = [
    "campaigns", "uploads", "uploaded_domains",
    "scrape_settings", "scrape_batches", "scrape_results",
    "decision_settings", "classification_batches", "classification_results",
    "role_fetch_criteria", "email_fetch_batches", "contacts",
    "verification_batches", "integration_secrets",
]

OLD_TABLES = [
    "campaigns", "uploads", "companies",
    "scrape_prompts", "scrape_runs", "scrape_run_items", "scrapejob", "scrapepage",
    "crawl_jobs", "crawl_artifacts",
    "prompts", "analysis_jobs", "classification_results", "company_feedback",
    "title_match_rules",
    "contact_fetch_batches", "contact_fetch_jobs", "contact_provider_attempts",
    "contact_reveal_batches", "contact_verify_jobs",
    "contacts",
    "job_events", "pipeline_runs", "pipeline_run_events",
    "ai_usage_events", "contact_fetch_runtime_controls",
    "integration_secrets",
]


# ---------------------------------------------------------------------------
# Phase 1: create new schema in temp DB
# ---------------------------------------------------------------------------

def phase1_create_schema(temp_url: str) -> None:
    print("\n=== Phase 1: Creating new schema in TEMP DB ===")
    engine = make_engine(temp_url)
    with engine.connect() as conn:
        # Drop new tables in reverse FK order so we start clean on re-runs.
        drop_order = [
            "classification_results", "scrape_results", "contacts",
            "classification_batches", "scrape_batches", "email_fetch_batches",
            "verification_batches", "uploaded_domains",
            "decision_settings", "scrape_settings", "role_fetch_criteria",
            "uploads", "campaigns", "integration_secrets", "alembic_version",
        ]
        for t in drop_order:
            conn.execute(text(f"DROP TABLE IF EXISTS {t} CASCADE"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
        conn.commit()
    # env.py reads PS_DATABASE_URL from settings, so we must override the env var.
    import os
    original = os.environ.get("PS_DATABASE_URL")
    os.environ["PS_DATABASE_URL"] = temp_url
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")
    finally:
        if original is not None:
            os.environ["PS_DATABASE_URL"] = original
        else:
            os.environ.pop("PS_DATABASE_URL", None)
    print("  Schema created and Alembic stamped.")


# ---------------------------------------------------------------------------
# Phase 2: transform and load data
# ---------------------------------------------------------------------------

def _serialize_row(row: dict) -> dict:
    """Serialize dict/list values to JSON strings for psycopg3 compatibility."""
    out = {}
    for k, v in row.items():
        if isinstance(v, (dict, list)):
            out[k] = json.dumps(v, default=str)
        else:
            out[k] = v
    return out


def bulk_insert(conn: sa.Connection, table: str, rows: list[dict]) -> None:
    """Insert rows using explicit column names, with JSON serialization for psycopg3."""
    if not rows:
        return
    cols = list(rows[0].keys())
    col_str = ", ".join(cols)
    param_str = ", ".join(f":{c}" for c in cols)
    conn.execute(text(f"INSERT INTO {table} ({col_str}) VALUES ({param_str})"), [_serialize_row(r) for r in rows])


def _hash(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:32]


def _normalize_name(s: str) -> str:
    return s.strip().lower()


def _step(progress: Progress, task_id: Any, label: str, fetched: int, inserted: int, skipped: int = 0) -> None:
    """Log a completed migration step."""
    msg = f"[green]✓[/green] [bold]{label}[/bold]: {inserted:,} inserted"
    if skipped:
        msg += f", [yellow]{skipped:,} skipped[/yellow]"
    if fetched != inserted + skipped:
        msg += f" (from {fetched:,} source rows)"
    console.log(msg)
    progress.advance(task_id)


def phase2_transform(source_url: str, temp_url: str) -> None:
    console.rule("[bold blue]Phase 2: Transforming and loading data into TEMP DB")
    src = make_engine(source_url)
    dst = make_engine(temp_url)

    steps = [
        "integration_secrets", "campaigns", "uploads", "uploaded_domains",
        "scrape_settings", "scrape_batches", "scrape_results",
        "decision_settings", "classification_results",
        "role_fetch_criteria", "email_fetch_batches",
        "verification_batches", "contacts",
    ]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        overall = progress.add_task("[cyan]Migrating tables...", total=len(steps))

        with src.connect() as s, dst.connect() as d:

            # --- integration_secrets (copy as-is) ---
            progress.update(overall, description="[cyan]integration_secrets...")
            rows = s.execute(text("SELECT * FROM integration_secrets")).mappings().all()
            data = [dict(r) for r in rows]
            if data:
                bulk_insert(d, "integration_secrets", data)
            _step(progress, overall, "integration_secrets", len(rows), len(data))

            # --- campaigns ---
            progress.update(overall, description="[cyan]campaigns...")
            rows = s.execute(text(
                "SELECT id, name, description, created_at, updated_at FROM campaigns"
            )).mappings().all()
            data = [dict(r) for r in rows]
            if data:
                bulk_insert(d, "campaigns", data)
            _step(progress, overall, "campaigns", len(rows), len(data))

            # --- uploads ---
            progress.update(overall, description="[cyan]uploads...")
            rows = s.execute(text(
                "SELECT id, campaign_id, filename, checksum, row_count, created_at FROM uploads"
            )).mappings().all()
            data = [dict(r) for r in rows]
            if data:
                bulk_insert(d, "uploads", data)
            _step(progress, overall, "uploads", len(rows), len(data))

            # --- uploaded_domains ← companies ---
            progress.update(overall, description="[cyan]uploaded_domains ← companies...")
            companies = s.execute(text("""
                SELECT c.id, c.raw_url, c.normalized_url, c.domain, c.created_at,
                       u.campaign_id, c.upload_id
                FROM companies c
                JOIN uploads u ON u.id = c.upload_id
            """)).mappings().all()
            domain_rows = [
                {
                    "id": r["id"],
                    "campaign_id": r["campaign_id"],
                    "upload_id": r["upload_id"],
                    "raw_url": r["raw_url"],
                    "normalized_url": r["normalized_url"],
                    "domain": r["domain"],
                    "dedupe_key": r["normalized_url"],
                    "scrape_status": None,
                    "decision_status": None,
                    "fetch_status": None,
                    "verify_status": None,
                    "created_at": r["created_at"],
                }
                for r in companies
            ]
            if domain_rows:
                bulk_insert(d, "uploaded_domains", domain_rows)
            # Build domain→campaign map for downstream steps
            domain_campaign = {
                str(r["id"]): str(r["campaign_id"])
                for r in d.execute(text("SELECT id, campaign_id FROM uploaded_domains")).mappings().all()
            }
            _step(progress, overall, "uploaded_domains ← companies", len(companies), len(domain_rows))

            # --- scrape_settings ← scrape_prompts ---
            progress.update(overall, description="[cyan]scrape_settings ← scrape_prompts...")
            rows = s.execute(text(
                "SELECT id, intent_text, compiled_prompt_text, scrape_rules_structured, "
                "created_at, is_active FROM scrape_prompts"
            )).mappings().all()
            ss_rows = [
                {
                    "id": r["id"],
                    "campaign_id": None,
                    "name": f"Migrated scrape settings {i+1}",
                    "instruction_text": r["intent_text"],
                    "structured_rules_json": r["scrape_rules_structured"],
                    "settings_hash": _hash({"text": r["compiled_prompt_text"], "rules": r["scrape_rules_structured"]}),
                    "is_active": r["is_active"],
                    "created_at": r["created_at"],
                }
                for i, r in enumerate(rows)
            ]
            if ss_rows:
                bulk_insert(d, "scrape_settings", ss_rows)
            _step(progress, overall, "scrape_settings ← scrape_prompts", len(rows), len(ss_rows))

            # --- scrape_batches ← scrape_runs ---
            progress.update(overall, description="[cyan]scrape_batches ← scrape_runs...")
            rows = s.execute(text(
                "SELECT id, campaign_id, requested_count, queued_count, failed_count, "
                "created_at, finished_at FROM scrape_runs"
            )).mappings().all()
            sb_rows = [
                {
                    "id": r["id"],
                    "campaign_id": r["campaign_id"],
                    "scrape_settings_id": None,
                    "settings_snapshot_json": None,
                    "settings_hash": None,
                    "state": "succeeded",
                    "selected_domain_count": r["requested_count"] or 0,
                    "queued_count": r["queued_count"] or 0,
                    "success_count": (r["requested_count"] or 0) - (r["failed_count"] or 0),
                    "failed_count": r["failed_count"] or 0,
                    "created_at": r["created_at"],
                    "finished_at": r["finished_at"],
                }
                for r in rows
            ]
            if sb_rows:
                bulk_insert(d, "scrape_batches", sb_rows)
            _step(progress, overall, "scrape_batches ← scrape_runs", len(rows), len(sb_rows))

            # --- scrape_results ← crawl_artifacts + scrapepage ---
            progress.update(overall, description="[cyan]scrape_results ← crawl_artifacts + scrapepage...")
            artifacts = s.execute(text("""
                SELECT ca.id, ca.company_id, ca.created_at
                FROM crawl_artifacts ca
                JOIN crawl_jobs cj ON cj.company_id = ca.company_id
                WHERE cj.state = 'succeeded'
            """)).mappings().all()
            console.log(f"  fetched {len(artifacts):,} crawl artifacts, loading scrapepage...")

            pages_by_company: dict[str, list[dict]] = {}
            pages = s.execute(text(
                "SELECT job_id, url, page_kind, status_code, text_len "
                "FROM scrapepage WHERE markdown_content != ''"
            )).mappings().all()
            console.log(f"  fetched {len(pages):,} scraped pages, grouping by company...")
            for p in pages:
                pages_by_company.setdefault(str(p["job_id"]), []).append({
                    "url": p["url"],
                    "page_kind": p["page_kind"],
                    "status_code": p["status_code"],
                    "markdown_len": p["text_len"],
                })

            sr_rows = []
            for r in artifacts:
                company_id = str(r["company_id"])
                page_list = pages_by_company.get(company_id, [])
                campaign_id = domain_campaign.get(company_id)
                if not campaign_id:
                    continue
                sr_rows.append({
                    "id": r["id"],
                    "campaign_id": campaign_id,
                    "domain_id": r["company_id"],
                    "scrape_batch_id": None,
                    "state": "succeeded",
                    "pages_attempted_count": len(page_list),
                    "pages_success_count": len([p for p in page_list if p["status_code"] == 200]),
                    "markdown_pages_count": len(page_list),
                    "scraped_pages_json": page_list or None,
                    "error_code": None,
                    "created_at": r["created_at"],
                    "updated_at": r["created_at"],
                })

            skipped_sr = len(artifacts) - len(sr_rows)
            if sr_rows:
                bulk_insert(d, "scrape_results", sr_rows)
            _step(progress, overall, "scrape_results ← crawl_artifacts", len(artifacts), len(sr_rows), skipped_sr)

            # --- decision_settings ← prompts ---
            progress.update(overall, description="[cyan]decision_settings ← prompts...")
            rows = s.execute(text("SELECT id, name, prompt_text, enabled, created_at FROM prompts")).mappings().all()
            ds_rows = [
                {
                    "id": r["id"],
                    "campaign_id": None,
                    "name": r["name"],
                    "instruction_text": r["prompt_text"],
                    "model": "",
                    "settings_hash": _hash({"text": r["prompt_text"]}),
                    "is_active": r["enabled"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]
            if ds_rows:
                bulk_insert(d, "decision_settings", ds_rows)
            _step(progress, overall, "decision_settings ← prompts", len(rows), len(ds_rows))

            # --- classification_results ← classification_results + company_feedback ---
            progress.update(overall, description="[cyan]classification_results ← classification_results + company_feedback...")
            results = s.execute(text("""
                SELECT cr.id, cr.predicted_label, cr.confidence,
                       cr.reasoning_json, cr.evidence_json, cr.input_hash, cr.created_at,
                       aj.company_id
                FROM classification_results cr
                JOIN analysis_jobs aj ON aj.id = cr.analysis_job_id
            """)).mappings().all()
            console.log(f"  fetched {len(results):,} classification results")

            feedback = {
                str(r["company_id"]): r
                for r in s.execute(text(
                    "SELECT company_id, manual_label, thumbs, comment, updated_at FROM company_feedback"
                )).mappings().all()
            }
            console.log(f"  fetched {len(feedback):,} company feedback rows")

            cr_rows, cr_skipped = [], 0
            for r in results:
                company_id = str(r["company_id"])
                campaign_id = domain_campaign.get(company_id)
                if not campaign_id:
                    cr_skipped += 1
                    continue
                fb = feedback.get(company_id)
                cr_rows.append({
                    "id": r["id"],
                    "campaign_id": campaign_id,
                    "domain_id": r["company_id"],
                    "scrape_result_id": None,
                    "classification_batch_id": None,
                    "state": "succeeded",
                    "predicted_label": r["predicted_label"],
                    "confidence": r["confidence"],
                    "reasoning_json": r["reasoning_json"],
                    "evidence_json": r["evidence_json"],
                    "input_hash": r["input_hash"],
                    "settings_hash": None,
                    "manual_label": fb["manual_label"] if fb else None,
                    "manual_thumbs": fb["thumbs"] if fb else None,
                    "manual_comment": fb["comment"] if fb else None,
                    "manually_reviewed_at": fb["updated_at"] if fb else None,
                    "created_at": r["created_at"],
                })
            if cr_rows:
                bulk_insert(d, "classification_results", cr_rows)
            _step(progress, overall, "classification_results", len(results), len(cr_rows), cr_skipped)

            # --- role_fetch_criteria ← title_match_rules ---
            progress.update(overall, description="[cyan]role_fetch_criteria ← title_match_rules...")
            rules = s.execute(text(
                "SELECT campaign_id, rule_type, match_type, keywords, created_at FROM title_match_rules"
            )).mappings().all()
            by_campaign: dict[str, dict] = {}
            for r in rules:
                if r["campaign_id"] is None:
                    continue
                cid = str(r["campaign_id"])
                if cid not in by_campaign:
                    by_campaign[cid] = {"include": [], "exclude": [], "created_at": r["created_at"]}
                rule_obj = {"match_type": r["match_type"], "keywords": r["keywords"]}
                if r["rule_type"] == "include":
                    by_campaign[cid]["include"].append(rule_obj)
                else:
                    by_campaign[cid]["exclude"].append(rule_obj)
            rfc_rows = [
                {
                    "id": str(uuid4()),
                    "campaign_id": cid,
                    "name": "Migrated criteria",
                    "include_rules_json": data["include"] or None,
                    "exclude_rules_json": data["exclude"] or None,
                    "criteria_hash": _hash({"include": data["include"], "exclude": data["exclude"]}),
                    "is_active": True,
                    "created_at": data["created_at"],
                }
                for cid, data in by_campaign.items()
            ]
            if rfc_rows:
                bulk_insert(d, "role_fetch_criteria", rfc_rows)
            _step(progress, overall, "role_fetch_criteria ← title_match_rules", len(rules), len(rfc_rows))

            # --- email_fetch_batches ← contact_fetch_batches ---
            progress.update(overall, description="[cyan]email_fetch_batches ← contact_fetch_batches...")
            rows = s.execute(text(
                "SELECT id, campaign_id, requested_count, queued_count, state, created_at, finished_at "
                "FROM contact_fetch_batches"
            )).mappings().all()
            efb_rows = [
                {
                    "id": r["id"],
                    "campaign_id": r["campaign_id"],
                    "role_fetch_criteria_id": None,
                    "criteria_snapshot_json": None,
                    "criteria_hash": None,
                    "provider_order_json": ["apollo", "snov"],
                    "state": "succeeded" if r["state"] == "succeeded" else r["state"],
                    "selected_domain_count": r["requested_count"] or 0,
                    "queued_count": r["queued_count"] or 0,
                    "success_count": 0,
                    "failed_count": 0,
                    "created_at": r["created_at"],
                    "finished_at": r["finished_at"],
                }
                for r in rows
            ]
            if efb_rows:
                bulk_insert(d, "email_fetch_batches", efb_rows)
            _step(progress, overall, "email_fetch_batches ← contact_fetch_batches", len(rows), len(efb_rows))

            # --- verification_batches ← contact_verify_jobs ---
            progress.update(overall, description="[cyan]verification_batches ← contact_verify_jobs...")
            rows = s.execute(text(
                "SELECT id, pipeline_run_id, state, selected_count, verified_count, skipped_count, "
                "created_at, finished_at FROM contact_verify_jobs"
            )).mappings().all()
            pr_campaign: dict[str, str] = {}
            try:
                pr_rows = s.execute(text("SELECT id, campaign_id FROM pipeline_runs")).mappings().all()
                pr_campaign = {str(r["id"]): str(r["campaign_id"]) for r in pr_rows}
                console.log(f"  resolved {len(pr_campaign):,} pipeline_run → campaign mappings")
            except Exception as e:
                console.log(f"  [yellow]pipeline_runs not available: {e}[/yellow]")

            vb_rows, vb_skipped = [], 0
            for r in rows:
                campaign_id = pr_campaign.get(str(r["pipeline_run_id"])) if r["pipeline_run_id"] else None
                if not campaign_id:
                    vb_skipped += 1
                    continue
                vb_rows.append({
                    "id": r["id"],
                    "campaign_id": campaign_id,
                    "state": r["state"] or "succeeded",
                    "selected_count": r["selected_count"] or 0,
                    "queued_count": 0,
                    "verified_count": r["verified_count"] or 0,
                    "valid_count": 0,
                    "invalid_count": 0,
                    "skipped_count": r["skipped_count"] or 0,
                    "created_at": r["created_at"],
                    "finished_at": r["finished_at"],
                })
            if vb_rows:
                bulk_insert(d, "verification_batches", vb_rows)
            _step(progress, overall, "verification_batches ← contact_verify_jobs", len(rows), len(vb_rows), vb_skipped)

            # --- contacts ← contacts (merge Apollo+Snov by priority) ---
            progress.update(overall, description="[cyan]contacts ← contacts (fetching)...")
            old_contacts = s.execute(text("""
                SELECT c.id, c.company_id, c.source_provider, c.provider_person_id,
                       c.first_name, c.last_name, c.title, c.linkedin_url,
                       c.title_match, c.email,
                       c.provider_email_status, c.reveal_raw_json,
                       c.verification_status, c.zerobounce_raw,
                       c.created_at, c.updated_at
                FROM contacts c
                ORDER BY c.created_at ASC
            """)).mappings().all()
            console.log(f"  fetched {len(old_contacts):,} source contact rows, merging...")

            progress.update(overall, description="[cyan]contacts ← contacts (merging providers)...")
            merged: dict[str, dict] = {}
            skipped_contacts = 0

            for r in old_contacts:
                company_id = str(r["company_id"])
                campaign_id = domain_campaign.get(company_id)
                if not campaign_id:
                    skipped_contacts += 1
                    continue

                provider = r["source_provider"]
                email = (r["email"] or "").strip().lower() or None
                linkedin = (r["linkedin_url"] or "").strip() or None
                person_id = r["provider_person_id"]
                first = _normalize_name(r["first_name"] or "")
                last = _normalize_name(r["last_name"] or "")

                if email:
                    merge_key = f"email:{company_id}:{email}"
                elif linkedin:
                    merge_key = f"li:{company_id}:{linkedin}"
                elif person_id:
                    merge_key = f"pid:{company_id}:{provider}:{person_id}"
                else:
                    merge_key = f"name:{company_id}:{first}:{last}"

                if merge_key not in merged:
                    merged[merge_key] = {
                        "id": str(uuid4()),
                        "campaign_id": campaign_id,
                        "domain_id": r["company_id"],
                        "email_fetch_batch_id": None,
                        "criteria_hash": None,
                        "first_name": r["first_name"] or "",
                        "last_name": r["last_name"] or "",
                        "title": r["title"],
                        "linkedin_url": r["linkedin_url"],
                        "title_match": r["title_match"],
                        "apollo_person_id": None,
                        "snov_person_id": None,
                        "apollo_email": None,
                        "snov_email": None,
                        "provider_evidence_json": {},
                        "selected_email": None,
                        "selected_email_provider": None,
                        "verification_batch_id": None,
                        "verified_email_snapshot": None,
                        "verification_status": None,
                        "verification_sub_status": None,
                        "verification_raw_json": None,
                        "verification_applied": False,
                        "verified_at": None,
                        "created_at": r["created_at"],
                        "updated_at": r["updated_at"],
                    }

                row = merged[merge_key]
                if provider == "apollo":
                    row["apollo_person_id"] = person_id
                    row["apollo_email"] = r["email"]
                    row["provider_evidence_json"]["apollo"] = {
                        "person_id": person_id,
                        "email_status": r["provider_email_status"],
                    }
                elif provider == "snov":
                    row["snov_person_id"] = person_id
                    row["snov_email"] = r["email"]
                    row["provider_evidence_json"]["snov"] = {
                        "person_id": person_id,
                        "email_status": r["provider_email_status"],
                    }
                if r["email"]:
                    if provider == "apollo" or not row["selected_email"]:
                        row["selected_email"] = r["email"]
                        row["selected_email_provider"] = provider
                if r["verification_status"] and r["verification_status"] != "unverified":
                    row["verification_status"] = r["verification_status"]
                    row["verification_raw_json"] = r["zerobounce_raw"]
                    row["verification_applied"] = True
                    row["verified_email_snapshot"] = r["email"]

            contact_rows = list(merged.values())
            for row in contact_rows:
                if not row["provider_evidence_json"]:
                    row["provider_evidence_json"] = None

            merged_count = len(old_contacts) - len(contact_rows) - skipped_contacts
            console.log(
                f"  merged {merged_count:,} duplicate provider rows → "
                f"[green]{len(contact_rows):,} unique contacts[/green]"
            )
            progress.update(overall, description="[cyan]contacts ← contacts (inserting)...")
            if contact_rows:
                bulk_insert(d, "contacts", contact_rows)
            _step(progress, overall, "contacts", len(old_contacts), len(contact_rows), skipped_contacts)

            d.commit()

    console.rule("[bold green]Phase 2 complete")


# ---------------------------------------------------------------------------
# Phase 3: verify temp DB
# ---------------------------------------------------------------------------

def phase3_verify(source_url: str, temp_url: str) -> None:
    print("\n=== Phase 3: Verifying TEMP DB ===")
    src = make_engine(source_url)
    dst = make_engine(temp_url)

    with src.connect() as s, dst.connect() as d:
        src_counts = row_counts(s, OLD_TABLES)
        dst_counts = row_counts(d, NEW_TABLES)
        print_counts("Source DB (old tables):", src_counts)
        print_counts("Temp DB (new tables):", dst_counts)

        # FK integrity checks
        print("\n  FK integrity checks...")
        fk_checks = [
            ("contacts", "campaign_id", "campaigns", "id"),
            ("contacts", "domain_id", "uploaded_domains", "id"),
            ("uploaded_domains", "campaign_id", "campaigns", "id"),
            ("scrape_results", "domain_id", "uploaded_domains", "id"),
            ("classification_results", "domain_id", "uploaded_domains", "id"),
        ]
        all_ok = True
        for child_table, child_col, parent_table, parent_col in fk_checks:
            broken = d.execute(text(f"""
                SELECT COUNT(*) FROM {child_table} c
                WHERE c.{child_col} IS NOT NULL
                AND NOT EXISTS (SELECT 1 FROM {parent_table} p WHERE p.{parent_col} = c.{child_col})
            """)).scalar()
            status = "OK" if broken == 0 else f"BROKEN ({broken} orphans)"
            print(f"    {child_table}.{child_col} → {parent_table}: {status}")
            if broken:
                all_ok = False

        # Spot checks
        print("\n  Sample contacts:")
        sample = d.execute(text(
            "SELECT first_name, last_name, title, selected_email, verification_status "
            "FROM contacts WHERE selected_email IS NOT NULL LIMIT 5"
        )).mappings().all()
        for row in sample:
            print(f"    {row['first_name']} {row['last_name']} | {row['title']} | {row['selected_email']} | {row['verification_status']}")

        print("\n  Sample domains:")
        sample = d.execute(text(
            "SELECT domain, scrape_status, decision_status, fetch_status FROM uploaded_domains LIMIT 5"
        )).mappings().all()
        for row in sample:
            print(f"    {row['domain']} | scrape={row['scrape_status']} decision={row['decision_status']} fetch={row['fetch_status']}")

        if not all_ok:
            print("\n  WARNING: FK integrity issues found. Review before applying to prod.")


# ---------------------------------------------------------------------------
# Phase 4 + 5: apply to prod
# ---------------------------------------------------------------------------

def phase4_apply_prod(temp_url: str, prod_url: str) -> None:
    print("\n=== Phase 4: Applying to PROD DB ===")
    temp = make_engine(temp_url)
    prod = make_engine(prod_url)

    # Drop all old tables in prod
    print("  Dropping old tables in PROD...")
    old_drop_order = [
        "contact_provider_attempts", "contact_reveal_batches", "contact_verify_jobs",
        "contact_fetch_jobs", "contact_fetch_batches", "contact_fetch_runtime_controls",
        "contacts", "title_match_rules",
        "classification_results", "company_feedback", "analysis_jobs",
        "crawl_artifacts", "crawl_jobs", "scrapepage", "scrapejob",
        "scrape_run_items", "scrape_runs", "scrape_prompts",
        "prompts", "companies",
        "job_events", "pipeline_run_events", "pipeline_runs",
        "ai_usage_events",
        "uploads",
        "campaigns",
        "integration_secrets",
        "alembic_version",
    ]
    with prod.connect() as conn:
        conn.execute(text("SET session_replication_role = replica"))  # disable FK checks temporarily
        for table in old_drop_order:
            try:
                conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                print(f"    dropped {table}")
            except Exception as e:
                print(f"    skip {table}: {e}")
        conn.execute(text("SET session_replication_role = DEFAULT"))
        conn.commit()

    # Create new schema in prod
    print("  Creating new schema in PROD...")
    import os
    original = os.environ.get("PS_DATABASE_URL")
    os.environ["PS_DATABASE_URL"] = prod_url
    try:
        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")
    finally:
        if original is not None:
            os.environ["PS_DATABASE_URL"] = original
        else:
            os.environ.pop("PS_DATABASE_URL", None)

    # Bulk copy from temp to prod
    print("  Copying data from TEMP → PROD...")
    with temp.connect() as t, prod.connect() as p:
        for table in NEW_TABLES:
            rows = t.execute(text(f"SELECT * FROM {table}")).mappings().all()
            if rows:
                bulk_insert(p, table, [dict(r) for r in rows])
                print(f"    {table}: {len(rows):,} rows")
            else:
                print(f"    {table}: (empty)")
        p.commit()


def phase5_verify_prod(temp_url: str, prod_url: str) -> None:
    print("\n=== Phase 5: Verifying PROD DB ===")
    temp = make_engine(temp_url)
    prod = make_engine(prod_url)

    with temp.connect() as t, prod.connect() as p:
        temp_counts = row_counts(t, NEW_TABLES)
        prod_counts = row_counts(p, NEW_TABLES)
        all_match = True
        print(f"\n  {'Table':<40} {'TEMP':>10} {'PROD':>10} {'Match':>8}")
        print("  " + "-" * 72)
        for table in sorted(NEW_TABLES):
            tc = temp_counts.get(table, -1)
            pc = prod_counts.get(table, -1)
            match = "OK" if tc == pc else "MISMATCH"
            if tc != pc:
                all_match = False
            print(f"  {table:<40} {tc:>10,} {pc:>10,} {match:>8}")

        if all_match:
            print("\n  All row counts match. Migration successful.")
        else:
            print("\n  WARNING: Row count mismatches detected. Investigate before going live.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Schema migration script — simplified 14-table design.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            Modes:
              --setup-temp   Build new schema in TEMP DB and migrate data from SOURCE DB.
                             Safe: never touches PROD DB. Run this first, then test your app.

              --apply-prod   Replicate TEMP DB to PROD DB.
                             Destructive: drops all old tables in PROD. Run only when satisfied.
        """),
    )
    parser.add_argument("--setup-temp", action="store_true", help="Build temp DB and migrate data")
    parser.add_argument("--apply-prod", action="store_true", help="Replicate temp DB to prod")
    parser.add_argument("--source-db", help="Source (prod) DB URL — required for --setup-temp")
    parser.add_argument("--temp-db", required=True, help="Temp/staging DB URL")
    parser.add_argument("--prod-db", help="Production DB URL — required for --apply-prod")
    args = parser.parse_args()

    if not args.setup_temp and not args.apply_prod:
        parser.print_help()
        sys.exit(1)

    if args.setup_temp:
        if not args.source_db:
            print("ERROR: --source-db is required for --setup-temp")
            sys.exit(1)

        print("This will:")
        print(f"  1. Create the new 14-table schema in TEMP DB ({args.temp_db[:40]}...)")
        print(f"  2. Migrate and transform data from SOURCE DB ({args.source_db[:40]}...)")
        print("  3. Run verification checks")
        print("\nPROD DB will NOT be touched.")
        confirm("Proceed?")

        phase1_create_schema(args.temp_db)
        phase2_transform(args.source_db, args.temp_db)

        src_counts = {}
        with make_engine(args.source_db).connect() as conn:
            src_counts = row_counts(conn, OLD_TABLES)
        with make_engine(args.temp_db).connect() as conn:
            dst_counts = row_counts(conn, NEW_TABLES)

        print_counts("\nSource DB row counts:", src_counts)
        print_counts("Temp DB row counts:", dst_counts)
        confirm("Row counts look reasonable — run verification checks?")

        phase3_verify(args.source_db, args.temp_db)
        print("\n✓ Setup complete. Point your app at TEMP DB and test.")
        print("  When satisfied, run: --apply-prod --temp-db ... --prod-db ...")

    elif args.apply_prod:
        if not args.prod_db:
            print("ERROR: --prod-db is required for --apply-prod")
            sys.exit(1)

        print("\n" + "!" * 60)
        print("WARNING: This will DESTROY all data in PROD DB and replace it")
        print(f"with data from TEMP DB ({args.temp_db[:40]}...).")
        print("!" * 60)
        confirm("Are you absolutely sure you want to apply to PROD?")
        confirm("Last chance — this cannot be undone. Continue?")

        phase4_apply_prod(args.temp_db, args.prod_db)
        phase5_verify_prod(args.temp_db, args.prod_db)
        print("\n✓ Production migration complete.")


if __name__ == "__main__":
    main()
