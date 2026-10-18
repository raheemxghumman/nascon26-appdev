"""Real WHIP/WHEP packet probe using Chrome's explicit synthetic camera fixture."""
import json
import time
from pathlib import Path
import httpx
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

options = webdriver.ChromeOptions()
for flag in ('--headless', '--no-sandbox', '--disable-dev-shm-usage', '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', '--unsafely-treat-insecure-origin-as-secure=http://host.docker.internal:8080'):
    options.add_argument(flag)
driver = webdriver.Remote('http://localhost:4444', options=options)
result = {'source': 'Chrome synthetic camera and microphone; real WebRTC packets'}
try:
    account = httpx.post('http://localhost:8080/api/v1/auth/login',json={'email':'player@nascon.test','password':'Nascon@26'}).json()
    driver.get('http://host.docker.internal:8080/web/creator/player-alpha-1')
    driver.execute_script('sessionStorage.setItem("account",arguments[0]);', json.dumps(account))
    driver.refresh()
    driver.find_element(By.ID,'start-broadcast').click()
    WebDriverWait(driver,20).until(lambda d: 'You are live' in d.find_element(By.ID,'broadcast-status').text or 'could not' in d.find_element(By.ID,'broadcast-status').text)
    result['publisher_status'] = driver.find_element(By.ID,'broadcast-status').text
    result['peer_state'] = driver.execute_script('return peer.connectionState')
    WebDriverWait(driver,15).until(lambda d: d.execute_script('return peer.connectionState')=='connected')
    result['live_lookup'] = httpx.get('http://localhost:8080/api/v1/live/match-m1').json()
    driver.switch_to.new_window('tab')
    driver.get('http://host.docker.internal:8080/web/matches/match-m1/live')
    WebDriverWait(driver,10).until(lambda d: d.find_element(By.ID,'webrtc').is_displayed())
    driver.switch_to.frame(driver.find_element(By.ID,'webrtc'))
    WebDriverWait(driver,20).until(lambda d: d.execute_script('return !!document.querySelector("video") && document.querySelector("video").readyState>=2'))
    result['playback'] = driver.execute_script('const v=document.querySelector("video"); return {width:v.videoWidth,height:v.videoHeight,time:v.currentTime,readyState:v.readyState}')
    time.sleep(12)
    result['passed'] = True
except Exception as error:
    result['passed'] = False
    result['error'] = str(error)[:1000]
    try: result['page_status'] = driver.find_element(By.ID,'broadcast-status').text
    except Exception: pass
finally:
    driver.quit()
    Path('tests/reports/media-probe.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if not result['passed']:
    raise SystemExit(1)
