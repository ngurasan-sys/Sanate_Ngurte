from playwright.sync_api import sync_playwright

def run_cuj(page):
    # Log console messages
    page.on("console", lambda msg: print(f"Browser console [{msg.type}]: {msg.text}"))
    page.on("pageerror", lambda err: print(f"Browser pageerror: {err}"))

    page.goto("http://localhost:5173")
    page.wait_for_timeout(3000)

    # Let's see all buttons
    for button in page.locator("button").all():
         text = button.text_content()
         title = button.get_attribute("title")
         if text and "Straddle" in text:
             button.click()
             break
         if title and "Straddle" in title:
             button.click()
             break

    page.wait_for_timeout(2000)
    page.screenshot(path="verification.png")
    page.wait_for_timeout(1000)

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            record_video_dir="/home/jules/verification/videos",
            viewport={'width': 1280, 'height': 800}
        )
        page = context.new_page()
        try:
            run_cuj(page)
        except Exception as e:
            print(f"Error: {e}")
        finally:
            context.close()
            browser.close()
