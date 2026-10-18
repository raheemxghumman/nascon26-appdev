"""Three real Grid sessions exercise the published guest DOM contract."""
import os
import time
import uuid
import httpx
import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

API = os.environ.get("BASE_URL", "http://localhost:8080")
WEB = os.environ.get("BROWSER_BASE_URL", "http://host.docker.internal:8080")
GRID = os.environ.get("SELENIUM_URL", "http://localhost:4444")


@pytest.fixture(params=["chrome", "firefox"])
def browser(request):
    options = webdriver.ChromeOptions() if request.param == "chrome" else webdriver.FirefoxOptions()
    options.add_argument("--headless" if request.param == "chrome" else "-headless")
    if request.param == "chrome":
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Remote(command_executor=GRID, options=options)
    driver.set_window_size(420, 900)
    yield driver
    driver.quit()


def selector(name):
    return (By.CSS_SELECTOR, f'[data-testid="{name}"]')


def open_live(browser):
    browser.get(WEB + "/q/m1-live")
    wait = WebDriverWait(browser, 3)
    wait.until(EC.visibility_of_element_located(selector("guest-video-player")))
    wait.until(lambda b: b.find_element(*selector("live-score-banner")).text != "—")
    return wait


def test_qr_resolution_zero_friction(browser):
    open_live(browser)
    assert browser.current_url.endswith("/web/matches/match-m1/live")
    assert not browser.find_element(*selector("progressive-auth-modal")).is_displayed()
    for name in ("live-score-banner", "pinned-merch-card", "chat-input-field", "chat-send-btn"):
        assert browser.find_element(*selector(name)).is_displayed()
    button = browser.find_element(*selector("chat-send-btn"))
    assert button.size["height"] >= 48 and button.size["width"] >= 48


def test_guest_block_opens_registration(browser):
    wait = open_live(browser)
    text = "guest-test-" + uuid.uuid4().hex
    browser.find_element(*selector("chat-input-field")).send_keys(text)
    browser.find_element(*selector("chat-send-btn")).click()
    wait.until(EC.visibility_of_element_located(selector("progressive-auth-modal")))
    assert text not in browser.find_element(*selector("chat-message-list")).text
    r = httpx.post(API + "/api/v1/chat", json={"text":text}, headers={"Authorization":"Bearer guest_anon_tok_7721"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "GUEST_WRITE_FORBIDDEN"


def test_cart_staging_and_live_score(browser):
    wait = open_live(browser)
    browser.find_element(*selector("add-to-guest-cart-btn")).click()
    assert browser.find_element(*selector("guest-cart-count")).text == "1"
    # Measure in the browser so WebDriver transport time is not counted as score-delivery latency.
    result = browser.execute_async_script("""
      const done=arguments[arguments.length-1], el=document.querySelector('[data-testid="live-score-banner"]');
      const previous=el.textContent, start=performance.now();
      const timer=setTimeout(()=>{observer.disconnect();done({error:'score update exceeded 500ms'});},500);
      const observer=new MutationObserver(()=>{if(el.textContent!==previous){clearTimeout(timer);observer.disconnect();done({elapsed:performance.now()-start});}});
      observer.observe(el,{childList:true,subtree:true,characterData:true});
      fetch('/audit/v1/events',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({event_id:arguments[0],match_id:'match-m1',type:'score',payload:{team_id:'club-alpha-1',event_type:'goal'}})})
        .then(r=>{if(r.status!==201){clearTimeout(timer);observer.disconnect();done({error:'score append failed: '+r.status});}});
    """, "selenium-"+uuid.uuid4().hex)
    assert "error" not in result, result
    assert result["elapsed"] < 500
