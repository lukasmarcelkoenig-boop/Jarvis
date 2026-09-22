"""Isolated public-page inspection. No reuse of personal browser sessions."""
from pathlib import Path
from .core.runway import public_https


def inspect_page(url,output):
    public_https(url)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser=p.chromium.launch()
        try:
            context=browser.new_context(accept_downloads=False,service_workers='block',viewport={'width':1280,'height':800})
            def gate(route):
                try:
                    if route.request.method not in ('GET','HEAD'):
                        route.abort();return
                    public_https(route.request.url)
                    route.continue_()
                except Exception:route.abort()
            context.route('**/*',gate)
            page=context.new_page()
            page.goto(url,wait_until='domcontentloaded',timeout=30000)
            page.screenshot(path=str(output),full_page=False)
            return {'title':page.title(),'url':page.url,'text':page.locator('body').inner_text(timeout=10000)[:12000]}
        finally:browser.close()
