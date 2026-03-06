# #!/usr/bin/env python3
# """Focused scraper for one website: home, about, products, screenshots, OCR, markdown."""

# from __future__ import annotations

# import argparse
# import asyncio
# import json
# import logging
# from dataclasses import asdict, dataclass
# from datetime import datetime, timezone
# from pathlib import Path

# from playwright.async_api import async_playwright
# from scrapling import Selector

# from app.services.markdown_service import MarkdownService
# from app.services.ocr_service import OCRService
# from app.services.scrape_service import (
#     FetchResult,
#     discover_internal_links,
#     fetch_with_fallback,
#     resolve_domain,
# )
# from app.services.url_utils import canonical_internal_url, clean_text, domain_from_url, normalize_url


# ABOUT_HINTS = ("about", "company", "who-we-are", "our-story", "history")
# PRODUCT_HINTS = ("products", "product", "catalog", "linecard", "brands", "shop", "solutions")


# @dataclass
# class PageCapture:
#     page_kind: str
#     requested_url: str
#     final_url: str
#     canonical_url: str
#     fetch_mode: str
#     status_code: int
#     title: str
#     description: str
#     raw_text: str
#     screenshot_path: str
#     screenshot_ocr_text: str
#     screenshot_ocr_error: str
#     markdown_content: str
#     llm_used: bool
#     llm_error: str


# def parse_args() -> argparse.Namespace:
#     parser = argparse.ArgumentParser(description="Focused scrape for home/about/products.")
#     parser.add_argument("website_url", help="Website URL to scrape.")
#     parser.add_argument(
#         "--output-dir",
#         type=Path,
#         default=Path("data/scrape_previews"),
#         help="Base output directory.",
#     )
#     parser.add_argument(
#         "--markdown-model",
#         default="openai/gpt-5-nano",
#         help="OpenRouter/OpenAI model name used for markdown conversion.",
#     )
#     parser.add_argument(
#         "--no-ocr",
#         action="store_true",
#         help="Disable screenshot OCR.",
#     )
#     parser.add_argument(
#         "--no-screenshot",
#         action="store_true",
#         help="Disable screenshot capture.",
#     )
#     parser.add_argument(
#         "--js-fallback",
#         action="store_true",
#         help="Allow DynamicFetcher fallback on thin static pages.",
#     )
#     return parser.parse_args()


# def extract_selector_text(selector: Selector) -> tuple[str, str, str]:
#     title = clean_text(str(selector.css("title::text").get(default="")))[:300]
#     description = clean_text(str(selector.css("meta[name='description']::attr(content)").get(default="")))[:1000]
#     raw_text = clean_text(str(selector.get_all_text(separator=" ")))[:40000]
#     return title, description, raw_text


# def score_link(candidate_url: str, kind: str) -> int:
#     lowered = candidate_url.lower()
#     score = 0
#     if kind == "about":
#         if any(token in lowered for token in ABOUT_HINTS):
#             score += 10
#         if "/about" in lowered:
#             score += 6
#     if kind == "products":
#         if any(token in lowered for token in PRODUCT_HINTS):
#             score += 10
#         if "/products" in lowered or "/catalog" in lowered:
#             score += 6
#     if "/blog" in lowered or "/news" in lowered or "/press" in lowered:
#         score -= 8
#     if "/tag/" in lowered or "/category/" in lowered:
#         score -= 6
#     return score


# def select_best_links(home_url: str, selector: Selector, domain: str) -> dict[str, str]:
#     links = discover_internal_links(selector, home_url, domain)
#     picks = {"about": "", "products": ""}
#     for kind in ("about", "products"):
#         ranked = sorted(
#             ((score_link(link, kind), link) for link in links),
#             key=lambda item: (item[0], item[1]),
#             reverse=True,
#         )
#         for score, link in ranked:
#             if score <= 0:
#                 continue
#             picks[kind] = link
#             break
#     return picks


# async def capture_screenshot(url: str, output_path: Path) -> tuple[str, str]:
#     try:
#         async with async_playwright() as playwright:
#             browser = await playwright.chromium.launch(headless=True)
#             page = await browser.new_page(viewport={"width": 1440, "height": 2200})
#             await page.goto(url, wait_until="networkidle", timeout=30000)
#             await page.screenshot(path=str(output_path), full_page=True)
#             await browser.close()
#         return str(output_path), ""
#     except Exception as exc:  # noqa: BLE001
#         return "", str(exc)


# async def capture_page(
#     *,
#     page_kind: str,
#     requested_url: str,
#     domain: str,
#     output_dir: Path,
#     markdown_model: str,
#     enable_ocr: bool,
#     enable_screenshot: bool,
#     use_js_fallback: bool,
#     ocr_service: OCRService,
#     markdown_service: MarkdownService,
# ) -> PageCapture | None:
#     canonical = canonical_internal_url(requested_url, domain)
#     if not canonical:
#         return None

#     fetch: FetchResult = await fetch_with_fallback(canonical, use_js=use_js_fallback)
#     if fetch.selector is None:
#         return PageCapture(
#             page_kind=page_kind,
#             requested_url=requested_url,
#             final_url=canonical,
#             canonical_url=canonical,
#             fetch_mode=fetch.fetch_mode,
#             status_code=fetch.status_code,
#             title="",
#             description="",
#             raw_text="",
#             screenshot_path="",
#             screenshot_ocr_text="",
#             screenshot_ocr_error=fetch.error_message,
#             markdown_content="",
#             llm_used=False,
#             llm_error=fetch.error_code or "fetch_failed",
#         )

#     final_url = str(fetch.selector.url or canonical)
#     title, description, raw_text = extract_selector_text(fetch.selector)

#     screenshot_path = ""
#     screenshot_ocr_text = ""
#     screenshot_ocr_error = ""
#     if enable_screenshot:
#         screenshot_file = output_dir / f"{page_kind}.png"
#         screenshot_path, screenshot_error = await capture_screenshot(final_url, screenshot_file)
#         if screenshot_path and enable_ocr:
#             screenshot_ocr_text, screenshot_ocr_error = ocr_service.extract_text_from_file(screenshot_path)
#         elif screenshot_error:
#             screenshot_ocr_error = screenshot_error

#     markdown_input = raw_text
#     if screenshot_ocr_text:
#         markdown_input = f"{raw_text}\n\n[SCREENSHOT_OCR]\n{screenshot_ocr_text}"

#     markdown_content, llm_used, llm_error = markdown_service.to_markdown(
#         url=final_url,
#         title=title,
#         page_text=markdown_input,
#         ocr_text=screenshot_ocr_text,
#         model=markdown_model,
#     )

#     return PageCapture(
#         page_kind=page_kind,
#         requested_url=requested_url,
#         final_url=final_url,
#         canonical_url=canonical_internal_url(final_url, domain) or canonical,
#         fetch_mode=fetch.fetch_mode,
#         status_code=fetch.status_code,
#         title=title,
#         description=description,
#         raw_text=raw_text,
#         screenshot_path=screenshot_path,
#         screenshot_ocr_text=screenshot_ocr_text,
#         screenshot_ocr_error=screenshot_ocr_error,
#         markdown_content=markdown_content,
#         llm_used=llm_used,
#         llm_error=llm_error,
#     )


# async def run_scrape(args: argparse.Namespace) -> Path:
#     normalized_url = normalize_url(args.website_url)
#     if not normalized_url:
#         raise ValueError(f"Invalid website URL: {args.website_url}")
#     domain = domain_from_url(normalized_url)
#     if not await resolve_domain(domain):
#         raise RuntimeError(f"DNS not resolved for {domain}")

#     timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
#     output_dir = args.output_dir / f"{domain}_{timestamp}"
#     output_dir.mkdir(parents=True, exist_ok=True)

#     ocr_service = OCRService()
#     markdown_service = MarkdownService()

#     home_capture = await capture_page(
#         page_kind="home",
#         requested_url=normalized_url,
#         domain=domain,
#         output_dir=output_dir,
#         markdown_model=args.markdown_model,
#         enable_ocr=not args.no_ocr,
#         enable_screenshot=not args.no_screenshot,
#         use_js_fallback=args.js_fallback,
#         ocr_service=ocr_service,
#         markdown_service=markdown_service,
#     )
#     if home_capture is None:
#         raise RuntimeError("Could not capture homepage.")

#     captures: list[PageCapture] = [home_capture]

#     candidate_links: dict[str, str] = {"about": "", "products": ""}
#     home_fetch = await fetch_with_fallback(home_capture.final_url, use_js=args.js_fallback)
#     if home_fetch.selector is not None:
#         candidate_links = select_best_links(home_capture.final_url, home_fetch.selector, domain)

#     for kind in ("about", "products"):
#         target_url = candidate_links.get(kind, "")
#         if not target_url:
#             continue
#         capture = await capture_page(
#             page_kind=kind,
#             requested_url=target_url,
#             domain=domain,
#             output_dir=output_dir,
#             markdown_model=args.markdown_model,
#             enable_ocr=not args.no_ocr,
#             enable_screenshot=not args.no_screenshot,
#             use_js_fallback=args.js_fallback,
#             ocr_service=ocr_service,
#             markdown_service=markdown_service,
#         )
#         if capture is not None:
#             captures.append(capture)

#     summary = {
#         "website_url": args.website_url,
#         "normalized_url": normalized_url,
#         "domain": domain,
#         "captures": [asdict(capture) for capture in captures],
#     }

#     summary_path = output_dir / "summary.json"
#     summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=True), encoding="utf-8")

#     combined_md_lines = [f"# Focused scrape: {domain}", ""]
#     for capture in captures:
#         combined_md_lines.append(f"## {capture.page_kind}")
#         combined_md_lines.append(f"- url: {capture.final_url}")
#         combined_md_lines.append(f"- fetch_mode: {capture.fetch_mode}")
#         combined_md_lines.append(f"- status_code: {capture.status_code}")
#         combined_md_lines.append(f"- screenshot_path: {capture.screenshot_path or '-'}")
#         combined_md_lines.append("")
#         combined_md_lines.append(capture.markdown_content or "_No markdown content._")
#         combined_md_lines.append("")

#     combined_path = output_dir / "combined.md"
#     combined_path.write_text("\n".join(combined_md_lines), encoding="utf-8")
#     return output_dir


# def main() -> None:
#     logging.basicConfig(level=logging.INFO, format="%(message)s")
#     args = parse_args()
#     output_dir = asyncio.run(run_scrape(args))
#     print(output_dir)


# if __name__ == "__main__":
#     main()

# from scrapling.fetchers import DynamicFetcher

# page = DynamicFetcher.fetch("https://www.google.com/maps", headless=True)

# print(page)

from pathlib import Path
from playwright.async_api import async_playwright
import asyncio


async def take_screenshot(url: str, out_file: Path) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 2200})
        # await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)

        await page.screenshot(path=str(out_file), full_page=True)
        await browser.close()


asyncio.run(
    take_screenshot(
        "https://www.google.com/maps", Path("data/scrape_previews/home.png")
    )
)
