import os
import time
import json
import requests
from bs4 import BeautifulSoup
from seleniumbase import Driver

# ==================== CONFIGURATION ====================
PORTAL_URL = "https://student.gcuf.edu.pk/login.php"

STUDENT_ID = os.getenv("GCUF_STUDENT_ID", "38405-9951669-5")
PORTAL_PASSWORD = os.getenv("GCUF_PASSWORD", "299792458Mf@")

DISCORD_WEBHOOK_URL = os.getenv(
    "DISCORD_WEBHOOK_URL",
    "https://discord.com/api/webhooks/1544064903827161101/57ZVULBM9B5W3jVJgUCvWinvXfnaF6J5zl3qi_HseUtYJ4ZjQtlLEHKdM0pnjEiF0uht"
)

NTFY_TOPIC = os.getenv("NTFY_TOPIC", "Result_is_out")
CHECK_INTERVAL = 900
CACHE_FILE = "seen_results.json"
# =======================================================


def load_cached_data():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_cached_data(data):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def send_discord_alert(title: str, message: str):
    if not DISCORD_WEBHOOK_URL:
        return
    payload = {
        "username": "GCUF Result Bot",
        "embeds": [
            {
                "title": f"🎓 {title}",
                "description": message,
                "color": 3447003
            }
        ]
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    except Exception as e:
        print(f"Discord error: {e}")


def send_ntfy_alert(title: str, message: str, priority: str = "urgent"):
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    clean_title = title.encode("ascii", "ignore").decode("ascii").strip()
    headers = {
        "Title": clean_title,
        "Priority": priority,
        "Tags": "mortar_board,books"
    }
    try:
        requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=10)
    except Exception as e:
        print(f"ntfy error: {e}")


def parse_active_results_table(page_source: str):
    soup = BeautifulSoup(page_source, "html.parser")
    subjects = {}
    semester_summary = ""

    active_pane = soup.find("div", class_=lambda c: c and "tab-pane" in c and "active" in c)
    target_container = active_pane if active_pane else soup

    tables = target_container.find_all("table")
    chosen_table = tables[0] if tables else None

    if not chosen_table:
        return subjects, semester_summary

    rows = chosen_table.find_all("tr")
    for row in rows:
        cols = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if not cols:
            continue

        if any("Semester Report" in c or "GPA:" in c for c in cols):
            semester_summary = " | ".join([c for c in cols if c])
            continue

        if cols[0].isdigit() and len(cols) >= 8:
            sr_no = cols[0]
            subject_title = cols[1]
            obtained_marks = cols[6] if len(cols) > 6 else "-"
            total_marks = cols[7] if len(cols) > 7 else "-"
            grade = cols[8] if len(cols) > 8 else "-"
            remarks = cols[-1] if len(cols) >= 12 else "N/A"

            subjects[subject_title] = {
                "sr": sr_no,
                "marks": f"{obtained_marks}/{total_marks}",
                "grade": grade,
                "remarks": remarks
            }

    return subjects, semester_summary


def open_academics_section(driver):
    js_nav = """
    let links = Array.from(document.querySelectorAll("aside a, .sidebar a, nav a, a"));
    let target = links.find(a => a.innerText.trim().toLowerCase().includes("academic"));
    if (target) {
        if (target.href && target.href !== "#" && !target.href.startsWith("javascript")) {
            window.location.href = target.href;
        } else {
            target.click();
        }
        return true;
    }
    return false;
    """
    driver.execute_script(js_nav)
    time.sleep(3)


def click_latest_semester_tab(driver):
    js_click_latest = """
    let tabElements = Array.from(document.querySelectorAll("ul.nav-tabs li a, ul.nav li a, .nav-tabs a, a"));
    let semesterTabs = tabElements.filter(el => {
        let t = el.innerText.toLowerCase();
        return t.includes("semester") || t.includes("summer") || t.includes("fall") || t.includes("spring");
    });

    if (semesterTabs.length > 0) {
        let latestTab = semesterTabs[semesterTabs.length - 1];
        let tabName = latestTab.innerText.trim();
        latestTab.click();
        if (window.jQuery) {
            window.jQuery(latestTab).tab('show');
        }
        return tabName;
    }
    return null;
    """
    detected_tab = driver.execute_script(js_click_latest)
    time.sleep(3)
    return detected_tab if detected_tab else "Latest Semester"


def check_gcuf_portal():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Checking portal for latest semester...")
    
    is_ci = os.getenv("GITHUB_ACTIONS") == "true"
    if is_ci:
        driver = Driver(headless2=True, uc=True, no_sandbox=True, disable_gpu=True)
    else:
        driver = Driver(headless=True, uc=True)
    
    try:
        driver.get(PORTAL_URL)
        driver.wait_for_element_visible("input[type='password']", timeout=25)
        time.sleep(1)

        # 1. Login
        driver.type("input[placeholder*='username'], input[type='text']", STUDENT_ID)
        time.sleep(0.5)
        driver.type("input[type='password']", PORTAL_PASSWORD)
        time.sleep(0.5)
        driver.click("button:contains('Login'), input[value*='Login'], .btn:contains('Login')")
        time.sleep(4)

        # 2. Open Academics
        open_academics_section(driver)
        time.sleep(3)

        # 3. Automatically click latest semester tab
        active_tab_name = click_latest_semester_tab(driver)
        print(f"Auto-selected latest tab: '{active_tab_name}'")
        time.sleep(3)

        # 4. Parse Results
        page_source = driver.page_source
        current_subjects, summary = parse_active_results_table(page_source)
        cached_data = load_cached_data()

        if not current_subjects:
            print(f"[{active_tab_name}] No graded subjects found for the latest semester yet.")
            return

        # 5. Check for updates
        new_updates = []
        for sub_name, details in current_subjects.items():
            if sub_name not in cached_data:
                new_updates.append(
                    f"**{sub_name}**\n• Grade: `{details['grade']}` | Marks: `{details['marks']}` | Status: `{details['remarks']}`"
                )
            elif (cached_data[sub_name].get("grade") != details["grade"] or 
                  cached_data[sub_name].get("marks") != details["marks"]):
                new_updates.append(
                    f"🔄 **[UPDATED]** {sub_name}\n• Grade: `{details['grade']}` | Marks: `{details['marks']}`"
                )

        # 6. Dispatch Notifications
        if new_updates:
            print(f"Found {len(new_updates)} update(s) for '{active_tab_name}'! Sending alert...")
            message_body = "\n\n".join(new_updates)
            if summary:
                message_body += f"\n\n📊 **Summary:** `{summary}`"

            send_discord_alert(f"GCUF Result Update: {active_tab_name}", message_body)
            send_ntfy_alert(
                title=f"GCUF Result: {active_tab_name}",
                message=message_body.replace("**", "").replace("`", ""),
                priority="urgent"
            )
            save_cached_data(current_subjects)
        else:
            print(f"[{active_tab_name}] All {len(current_subjects)} loaded subjects are already cached. No changes.")

    except Exception as err:
        print(f"Error checking portal: {err}")
    finally:
        driver.quit()


if __name__ == "__main__":
    print("GCUF Auto-Latest Semester Monitor active. Listening for updates...")
    if os.getenv("GITHUB_ACTIONS"):
        check_gcuf_portal()
    else:
        while True:
            check_gcuf_portal()
            print(f"Sleeping for {CHECK_INTERVAL // 60} minutes...\n")
            time.sleep(CHECK_INTERVAL)