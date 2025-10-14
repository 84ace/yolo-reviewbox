from playwright.sync_api import sync_playwright

import time

import time

def run(playwright):
    browser = playwright.chromium.launch()
    page = browser.new_page()
    time.sleep(10)  # Wait for server to start
    page.goto("http://localhost:8000")

    # Verify 'Unannotated' and 'Null' filters
    class_filter = page.locator("#classFilter")
    class_filter.select_option("__unannotated__")
    page.wait_for_timeout(500) # wait for images to load
    page.screenshot(path="jules-scratch/verification/01_unannotated_filter.png")

    class_filter.select_option("__null__")
    page.wait_for_timeout(500) # wait for images to load
    page.screenshot(path="jules-scratch/verification/02_null_filter.png")

    # Verify 'Add New Images' button
    with page.expect_file_chooser():
        page.locator("#btnImportImages").click()
    page.screenshot(path="jules-scratch/verification/03_add_new_images_modal.png")


    # Verify advanced export options
    page.locator("#btnExport").click()
    page.wait_for_timeout(500)
    page.screenshot(path="jules-scratch/verification/04_export_modal.png")

    browser.close()

with sync_playwright() as playwright:
    run(playwright)