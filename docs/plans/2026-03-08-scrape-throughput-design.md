# Scrape Throughput Tuning Design

## Goal
Increase scrape throughput without changing product behavior. Playwright remains mandatory for screenshots. HTML and markdown generation behavior stays intact.

## Decisions
- Add `PS_WORKER_CONCURRENCY` so one worker service can fan out into multiple worker processes.
- Keep artifact cleanup on only one worker process to avoid duplicate cleanup work.
- Replace hardcoded scrape timeouts and retries with settings so deployment can tune behavior without code changes.
- Lower the default static, dynamic, and screenshot waits to fail faster on blocked or slow sites.

## Default Tuning
- Worker concurrency: `1`
- Static fetch timeout: `12s`
- Static retries: `1`
- Dynamic fetch timeout: `15000ms`
- Dynamic retries: `1`
- Screenshot timeout: `25000ms`
- Screenshot settle wait: `800ms`

## Expected Outcome
- More jobs processed in parallel.
- Faster abandonment of blocked and slow sites.
- No change to the requirement that screenshots and OCR are still produced through Playwright.
