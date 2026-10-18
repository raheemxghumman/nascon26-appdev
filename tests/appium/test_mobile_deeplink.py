"""Real Android deep-link and cross-surface chat tests; requires the release APK installed."""
import os
import time
import uuid
import httpx
import pytest
from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
from selenium import webdriver as browser_webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By

API = os.environ.get("BASE_URL", "http://localhost:8080")
PACKAGE = "com.nascon26.leaguedesk"


@pytest.fixture
def phone():
    options = UiAutomator2Options().load_capabilities({"platformName":"Android", "appium:automationName":"UiAutomator2",
        "appium:appPackage":PACKAGE,"appium:appActivity":".MainActivity","appium:noReset":True,
        **({"appium:udid":os.environ["ANDROID_UDID"]} if os.environ.get("ANDROID_UDID") else {})})
    driver = webdriver.Remote(os.environ.get("APPIUM_URL","http://localhost:4723"),options=options)
    yield driver
    driver.quit()


@pytest.mark.parametrize("url,title",[("nascon://entity/match-m1","Match live"),("nascon://stream/cs-session-101","Co-stream live")])
def test_deep_link_foreground_without_login(phone,url,title):
    started=time.monotonic()
    phone.execute_script("mobile:deepLink",{"url":url,"package":PACKAGE})
    WebDriverWait(phone,2,poll_frequency=.05).until(lambda d:d.find_element(AppiumBy.ANDROID_UIAUTOMATOR,f'new UiSelector().text("{title}")').is_displayed())
    assert phone.current_package==PACKAGE
    assert time.monotonic()-started<2


def test_native_join_and_browser_chat_delivery(phone):
    r=httpx.post(API+"/audit/v1/costream/session",json={"session_id":"cs-session-101","host_player_id":"player-alpha-1",
        "participants":["player-alpha-1","player-alpha-2"],"layout":"grid_2"})
    assert r.status_code in (200,201)
    phone.execute_script("mobile:deepLink",{"url":"nascon://stream/cs-session-101","package":PACKAGE})
    WebDriverWait(phone,5).until(lambda d:d.find_element(AppiumBy.ACCESSIBILITY_ID,"Join co-stream")).click()
    options=browser_webdriver.ChromeOptions();options.add_argument("--headless");options.add_argument("--no-sandbox")
    browser=browser_webdriver.Remote(os.environ.get("SELENIUM_URL","http://localhost:4444"),options=options)
    try:
        browser.get(os.environ.get("BROWSER_BASE_URL","http://host.docker.internal:8080")+"/web/costream/cs-session-101")
        WebDriverWait(browser,5).until(lambda b:b.find_element(By.CSS_SELECTOR,'[data-testid="chat-message-list"]'))
        token=httpx.post(API+"/api/v1/auth/login",json={"email":"player@nascon.test","password":"Nascon@26"}).json()["token"]
        text="Cross surface "+uuid.uuid4().hex[:8]
        started=time.monotonic()
        r=httpx.post(API+"/api/v1/chat",headers={"Authorization":"Bearer "+token},json={"chat_room_id":"chat-cs-session-101","text":text})
        assert r.status_code==200
        WebDriverWait(browser,3,poll_frequency=.05).until(lambda b:text in b.find_element(By.CSS_SELECTOR,'[data-testid="chat-message-list"]').text)
        WebDriverWait(phone,3,poll_frequency=.05).until(lambda d:d.find_element(AppiumBy.ANDROID_UIAUTOMATOR,f'new UiSelector().text("{text}")').is_displayed())
        assert time.monotonic()-started<3
    finally:
        browser.quit()
