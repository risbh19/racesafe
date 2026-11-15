"""Verify the keyboard and live-update flows and record an isolated RaceSafe demo."""

import os
import re
import subprocess
from contextlib import closing
from pathlib import Path

from imageio_ffmpeg import get_ffmpeg_exe
from playwright.sync_api import Locator, Page, expect, sync_playwright

ORIGIN = os.environ.get("WALKTHROUGH_ORIGIN", "http://127.0.0.1:8000")
OUTPUT = Path(os.environ.get("WALKTHROUGH_OUTPUT", "walkthrough"))
TEAM = "Walkthrough team"
RANKING_SKILL = "hardware sketching"


def focus(page: Page, target: Locator) -> None:
    expect(target).to_be_visible()
    for _ in range(140):
        if target.evaluate("(element) => element === document.activeElement"):
            return
        page.keyboard.press("Tab")
    raise AssertionError(f"Keyboard could not reach {target}")


def activate(page: Page, target: Locator) -> None:
    expect(target).to_be_enabled()
    focus(page, target)
    page.keyboard.press("Enter")


def enter(page: Page, field: str, value: str) -> None:
    focus(page, page.get_by_label(field, exact=True))
    page.keyboard.press("Control+a")
    page.keyboard.press("Backspace")
    if value:
        page.keyboard.type(value)
    expect(page.get_by_label(field, exact=True)).to_have_value(value)


def register(page: Page, role: str, skill: str | None = None) -> None:
    page.goto(ORIGIN, wait_until="domcontentloaded")
    activate(page, page.get_by_role("button", name="Create a RaceSafe account"))
    enter(page, "Display name", f"Demo {role}")
    enter(page, "Email", f"walkthrough-{role.lower()}@example.test")
    enter(page, "Password", "Walkthrough-demo-2026")
    if skill:
        enter(page, "Skills (separate with commas)", skill)
    activate(page, page.get_by_role("button", name="Create account", exact=True))
    expect(page.get_by_text("Live updates on")).to_be_visible()


def sign_in_as_leader(page: Page) -> None:
    page.goto(ORIGIN, wait_until="domcontentloaded")
    enter(page, "Email", "walkthrough-leader@example.test")
    enter(page, "Password", "Walkthrough-demo-2026")
    activate(page, page.get_by_role("button", name="Sign in", exact=True))
    expect(page.get_by_text("Live updates on")).to_be_visible()
    activate(page, page.get_by_role("button", name="My team", exact=True))


def caption(page: Page, message: str) -> None:
    page.evaluate(
        """(message) => {
            let caption = document.getElementById('walkthrough-caption')
            if (!caption) {
                caption = document.createElement('div')
                caption.id = 'walkthrough-caption'
                caption.setAttribute('aria-hidden', 'true')
                caption.style.cssText = 'position:fixed;bottom:10px;left:10px;right:10px;z-index:1000;'
                    + 'background:#162b25;color:white;padding:9px 12px;border-radius:6px;'
                    + 'font:600 14px/1.3 system-ui;pointer-events:none;'
                document.body.append(caption)
            }
            caption.textContent = message
        }""",
        message,
    )


def fits_viewport(page: Page) -> None:
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def verify_stale_filter(page: Page) -> None:
    delayed = re.compile(r"/api/hackathons/1/board\?limit=40$")
    held = []
    def hold(route):
        held.append(route)

    page.route(delayed, hold, times=1)
    with page.expect_request(delayed):
        activate(page, page.get_by_role("button", name="Load more"))
    enter(page, "Filter by skill", "python")
    activate(page, page.get_by_role("button", name="Apply", exact=True))
    cards = page.get_by_role("region", name="Open teams").get_by_role("article")
    expect(cards).to_have_count(20)
    expect(cards.first.get_by_text("python", exact=True)).to_be_visible()

    # Completing the earlier request must not replace the filtered results.
    assert len(held) == 1
    held[0].fulfill(status=200, json={"teams": [], "next_before": None})
    expect(cards).to_have_count(20)
    expect(cards.first.get_by_text("python", exact=True)).to_be_visible()
    enter(page, "Filter by skill", "")
    activate(page, page.get_by_role("button", name="Apply", exact=True))
    expect(cards.first.get_by_role("heading", name=re.compile("^Benchmark team "))).to_be_visible()


def verify_approval_rollback(leader: Page) -> None:
    accept_path = re.compile(r"/api/join-requests/\d+/accept$")
    held = []

    def hold(route):
        held.append(route)

    leader.route(accept_path, hold, times=1)
    accept = leader.get_by_role("button", name="Accept Demo Applicant")
    with leader.expect_request(accept_path):
        activate(leader, accept)
    expect(accept).to_have_count(0)
    assert len(held) == 1
    held[0].fulfill(status=409, json={"detail": "Approval conflicted. Try again."})
    expect(leader.get_by_role("alert")).to_contain_text("Approval conflicted")
    expect(accept).to_be_visible()


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        desktop = {"width": 900, "height": 800}
        phone = {"width": 390, "height": 800}
        leader_context = browser.new_context(
            viewport=desktop, record_video_dir=OUTPUT / "raw", record_video_size=desktop,
        )
        applicant_context = browser.new_context(
            viewport=phone, is_mobile=True, has_touch=True,
            record_video_dir=OUTPUT / "raw", record_video_size=phone,
        )
        leader = leader_context.new_page()
        applicant = applicant_context.new_page()
        expect.set_options(timeout=12000)
        try:
            register(leader, "Leader")
            register(applicant, "Applicant")
            caption(leader, "Leader · desktop · keyboard only")
            caption(applicant, "Applicant · 390 px phone · keyboard only")
            fits_viewport(applicant)
            verify_stale_filter(applicant)
            activate(applicant, applicant.get_by_role("button", name="Load more"))
            cards = applicant.get_by_role("region", name="Open teams").get_by_role("article")
            expect(cards).to_have_count(40)
            last_retained = cards.nth(38).get_by_role("heading").inner_text()

            caption(leader, "1 · Create an open team")
            caption(applicant, "1 · The board stays open in this session")
            activate(leader, leader.locator("summary").filter(has_text=re.compile("^Create a team$")))
            enter(leader, "Team name", TEAM)
            enter(leader, "Description", "Looking for Python and design teammates.")
            enter(leader, "Skills you need (separate with commas)", RANKING_SKILL)
            activate(leader, leader.get_by_role("button", name="Create team", exact=True))
            expect(leader.get_by_role("heading", name=TEAM)).to_be_visible()
            expect(leader.get_by_text("Draft", exact=True)).to_be_visible()
            expect(cards.first.get_by_role("heading", name=TEAM)).to_be_visible()
            expect(cards).to_have_count(40)
            expect(cards.last.get_by_role("heading", name=last_retained, exact=True)).to_be_visible()

            caption(applicant, "2 · Live update arrived and all 40 cards stayed loaded")
            applicant.wait_for_timeout(1500)
            activate(applicant, applicant.get_by_role("button", name=f"View {TEAM}"))
            fits_viewport(applicant)
            enter(applicant, "Message to the team leader", "I can help with the prototype.")
            activate(applicant, applicant.get_by_role("button", name="Request to join"))
            expect(applicant.get_by_text("Your request is pending.")).to_be_visible()
            activate(applicant, applicant.locator("summary").filter(has_text=re.compile("^My join requests$")))
            expect(applicant.get_by_role("button", name=f"Cancel request to {TEAM}")).to_be_visible()

            caption(leader, "3 · A simulated conflict restores the optimistically removed request")
            expect(leader.get_by_role("button", name="Accept Demo Applicant")).to_be_visible()
            verify_approval_rollback(leader)
            leader.wait_for_timeout(2000)
            caption(leader, "4 · Successful approval turns the draft into a formed team")
            activate(leader, leader.get_by_role("button", name="Accept Demo Applicant"))
            expect(applicant.get_by_text("2/4 seats", exact=True)).to_be_visible()
            expect(applicant.get_by_text("Formed", exact=True)).to_be_visible()
            expect(applicant.get_by_role("button", name="Leave team")).to_be_visible()
            caption(applicant, "3 · Approval and seat count update without reloading")
            fits_viewport(applicant)
            applicant.wait_for_timeout(1500)

            caption(leader, "5 · A rotated invite disappears live from the previous tab")
            activate(leader, leader.get_by_role("button", name="Generate invite code"))
            expect(leader.locator(".invite")).to_contain_text("Expires")
            with closing(browser.new_context()) as second_context:
                second_leader = second_context.new_page()
                sign_in_as_leader(second_leader)
                activate(second_leader, second_leader.get_by_role("button", name="Generate invite code"))
                expect(second_leader.locator(".invite")).to_contain_text("Expires")
                expect(leader.locator(".invite")).to_have_count(0)

            caption(leader, "6 · Suggestions update when a match arrives, and the team audit records approval")
            activate(leader, leader.get_by_role("button", name="Rank available teammates"))
            expect(leader.get_by_text("Skills score measures coverage", exact=False)).to_be_visible()
            with closing(browser.new_context()) as candidate_context:
                candidate = candidate_context.new_page()
                register(candidate, "Matching", RANKING_SKILL)
                expect(leader.get_by_text("Demo Matching", exact=True)).to_be_visible()
            activate(leader, leader.locator("summary").filter(has_text=re.compile("^Team activity$")))
            expect(leader.get_by_text("request.accepted by Demo Leader")).to_be_visible()
            caption(applicant, "Verified · two independent sessions, mobile layout and keyboard")
            leader.wait_for_timeout(2200)
        finally:
            leader_context.close()
            applicant_context.close()
            leader.video.save_as(OUTPUT / "leader.webm")
            applicant.video.save_as(OUTPUT / "applicant.webm")
            browser.close()

    subprocess.run([
        get_ffmpeg_exe(), "-hide_banner", "-loglevel", "warning", "-y",
        "-i", str(OUTPUT / "leader.webm"), "-i", str(OUTPUT / "applicant.webm"),
        "-filter_complex", "[0:v][1:v]hstack=inputs=2:shortest=1",
        "-t", "299", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(OUTPUT / "racesafe-walkthrough.mp4"),
    ], check=True)
    print("Keyboard-only desktop and mobile flows, optimistic rollback, live invite rotation, and live ranking passed.")


if __name__ == "__main__":
    main()
