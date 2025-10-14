from playwright.sync_api import sync_playwright
import zipfile
import os

def create_dummy_zip():
    with zipfile.ZipFile("dummy_images.zip", "w") as z:
        z.writestr("test1.jpg", b"")
        z.writestr("test2.jpg", b"")

def run(playwright):
    create_dummy_zip()
    browser = playwright.chromium.launch()
    page = browser.new_page()
    page.goto("http://localhost:8000")

    # Import images
    with page.expect_file_chooser() as fc_info:
        page.locator("#btnImportImages").click()
    file_chooser = fc_info.value
    file_chooser.set_files("dummy_images.zip")
    page.wait_for_timeout(1000)

    # Go to review page
    page.locator("a[href='/review']").click()
    page.wait_for_timeout(1000)

    # Verify filter is present
    page.screenshot(path="jules-scratch/verification/06_review_page_filter.png")

    # Verify 'n' shortcut
    page.once("dialog", lambda dialog: dialog.accept())
    page.keyboard.press("n")
    page.wait_for_timeout(1000)
    page.screenshot(path="jules-scratch/verification/07_review_page_null_shortcut.png")

    # Verify click to skip
    page.locator("#currCanvas").click()
    page.wait_for_timeout(1000)
    page.screenshot(path="jules-scratch/verification/08_review_page_click_skip.png")


    browser.close()
    os.remove("dummy_images.zip")

with sync_playwright() as playwright:
    run(playwright)