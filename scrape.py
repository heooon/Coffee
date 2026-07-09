import requests
from bs4 import BeautifulSoup
import re
import json
import urllib3
import datetime
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor

# Suppress SSL verification warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Threading Lock for thread-safe ScraperAPI key rotation
keyring_lock = threading.Lock()

# Read ScraperAPI keys from GitHub Actions secrets environment
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY")
SCRAPER_API_KEY_SECONDARY = os.environ.get("SCRAPER_API_KEY_SECONDARY")
SCRAPER_API_PREMIUM = os.environ.get("SCRAPER_API_PREMIUM", "false").lower() == "true"

# Register available keys into a list for dynamic rotation
SCRAPER_API_KEYS = []
if SCRAPER_API_KEY:
    SCRAPER_API_KEYS.append(SCRAPER_API_KEY)
if SCRAPER_API_KEY_SECONDARY:
    SCRAPER_API_KEYS.append(SCRAPER_API_KEY_SECONDARY)

# Track the index of the currently active ScraperAPI key
current_key_index = 0

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive"
}

def fetch_url(url, custom_headers=None):
    """Fetches HTML content, routing through a rotating keyring of ScraperAPI keys on GitHub Actions"""
    global SCRAPER_API_KEYS, current_key_index
    headers_to_use = custom_headers if custom_headers else HEADERS
    
    is_naver = "smartstore.naver.com" in url or "m.smartstore.naver.com" in url
    
    # Try ScraperAPI keyring rotation on GitHub Actions for Naver targets
    if is_naver and SCRAPER_API_KEYS:
        attempts_with_keys = len(SCRAPER_API_KEYS)
        for _ in range(attempts_with_keys):
            # Thread-safe read of the active key index and parameters
            with keyring_lock:
                if current_key_index >= len(SCRAPER_API_KEYS):
                    break
                active_key = SCRAPER_API_KEYS[current_key_index]
                key_num = current_key_index + 1
                
            print(f"[우회 - ScraperAPI] 네이버 수집 우회 터널을 작동합니다 (키 인덱스: {key_num}/{len(SCRAPER_API_KEYS)}) -> {url[:50]}...")
            
            try:
                payload = {
                    'api_key': active_key,
                    'url': url
                }
                if SCRAPER_API_PREMIUM:
                    payload['premium'] = 'true'
                    print("[우회 옵션] ScraperAPI 프리미엄 주거용 프록시(premium=true)를 활성화합니다.")
                    
                r = requests.get('https://api.scraperapi.com', params=payload, verify=False, timeout=50)
                
                # HTTP 403 means current key is exhausted or blocked
                if r.status_code == 403:
                    print(f"[우회 실패 - ScraperAPI] 현재 키(인덱스: {key_num})가 만료되거나 소진되었습니다 (HTTP 403).")
                    try:
                        print(f"[우회 실패 상세] 응답 내용: {r.text.strip()}")
                    except Exception:
                        pass
                    
                    # Thread-safe increment of index
                    with keyring_lock:
                        # Only increment if index hasn't been advanced by another parallel thread yet!
                        if current_key_index == key_num - 1:
                            print("[우회 로테이션] 다음 ScraperAPI 예비 키로 즉시 실시간 전환합니다.")
                            current_key_index += 1
                    continue
                    
                elif r.status_code != 200:
                    print(f"[우회 실패 - ScraperAPI] 응답 오류 - HTTP 상태 코드: {r.status_code}")
                    try:
                        print(f"[우회 실패 상세] 응답 내용: {r.text.strip()}")
                    except Exception:
                        pass
                    return r
                else:
                    return r
                    
            except Exception as e:
                print(f"[우회 오류 - ScraperAPI] 연결 오류: {e}")
                with keyring_lock:
                    if current_key_index == key_num - 1:
                        current_key_index += 1
                continue
    
    # Direct fetch (Default on local machine, or fallback on GitHub Actions when all keys are exhausted)
    return requests.get(url, headers=headers_to_use, verify=False, timeout=10)

def scrape_502_coffee():
    """Scrapes products from 502 Coffee (Cafe24 site)"""
    products = []
    try:
        r = fetch_url("https://502coffee.com/category/%EC%9B%90%EB%91%90/24/")
        if r.status_code != 200:
            return products
        
        soup = BeautifulSoup(r.text, "html.parser")
        items = soup.select(".prdList > li")
        
        for li in items:
            name_tag = li.select_one(".name a")
            name = ""
            if name_tag:
                spans = name_tag.find_all("span", recursive=False)
                if len(spans) > 1:
                    name = spans[-1].text.strip()
                elif len(spans) == 1:
                    name = spans[0].text.strip()
                else:
                    name = name_tag.text.strip()
            
            if not name:
                continue
            
            # Exclude drip bags
            if "드립백" in name:
                continue
            
            price = 0
            desc_div = li.select_one(".description")
            if desc_div and desc_div.has_attr("ec-data-price"):
                try:
                    price = int(desc_div["ec-data-price"])
                except ValueError:
                    price = 0
            
            if price == 0:
                price_span = li.select_one(".spec li")
                if price_span:
                    match = re.search(r"([\d,]+)\s*원", price_span.text)
                    if match:
                        price = int(match.group(1).replace(",", ""))
            
            img_tag = li.select_one(".thumbnail img")
            img_url = ""
            if img_tag:
                img_url = img_tag.get("src", "")
                if img_url.startswith("//"):
                    img_url = "https:" + img_url
            
            link_tag = li.select_one(".thumbnail a")
            product_url = ""
            if link_tag:
                product_url = link_tag.get("href", "")
                if product_url.startswith("/"):
                    product_url = "https://502coffee.com" + product_url
            
            soldout = False
            for img in li.find_all("img"):
                alt = img.get("alt", "")
                if "품절" in alt or "sold" in alt.lower():
                    soldout = True
                    break
            
            if "품절" in li.text or "SOLD OUT" in li.text:
                soldout = True
            
            products.append({
                "store": "502",
                "name": name,
                "price": price,
                "imageUrl": img_url,
                "productUrl": product_url,
                "soldOut": soldout
            })
    except Exception as e:
        print(f"Error scraping 502 Coffee: {e}")
    
    return products

def scrape_naver_smartstore(url, store_name):
    """Scrapes products from Naver Smartstore using the mobile category endpoint (with up to 4 retries)"""
    print(f"\n=> [{store_name}] 네이버 스마트스토어 수집 시작 (대상 URL: {url})")
    # Optimize retries to 4 to balance success rate and API credits
    for attempt in range(4):
        products = []
        try:
            custom_headers = HEADERS.copy()
            # Impersonate normal search portal referrer entry using ASCII-safe query to avoid encoding error
            custom_headers["Referer"] = "https://search.naver.com/search.naver?query=coffee"
            
            print(f"   [{store_name}] 시도 {attempt+1}/4: HTTP 요청을 보냅니다...")
            r = fetch_url(url, custom_headers)
            
            if r.status_code != 200:
                backoff_time = 3.0 + attempt * 2.5
                print(f"   [{store_name}] 시도 {attempt+1}/4 HTTP 오류 발생 (상태 코드: {r.status_code})")
                print(f"   -> [대기 조치] 과부하 및 추가 차단 방지를 위해 {backoff_time}초 동안 대기합니다...")
                time.sleep(backoff_time)
                continue
            
            soup = BeautifulSoup(r.text, "html.parser")
            script_tag = soup.find("script", string=re.compile(r"window\.__PRELOADED_STATE__\s*="))
            
            if not script_tag:
                backoff_time = 3.0 + attempt * 2.5
                print(f"   [{store_name}] 시도 {attempt+1}/4 방화벽 감지로 수집 실패 (로그인 챌린지 또는 보안 캡차 발생)")
                try:
                    title_tag = soup.find("title")
                    title_text = title_tag.text.strip() if title_tag else "제목 없음"
                    print(f"   -> [실패 페이지 분석] HTML 제목: {title_text}")
                except Exception:
                    pass
                print(f"   -> [대기 조치] 차단 우회를 위해 IP 변경 대기시간 {backoff_time}초 적용...")
                time.sleep(backoff_time)
                continue
            
            content = script_tag.string.strip()
            match = re.search(r"window\.__PRELOADED_STATE__\s*=\s*({.+?});?\s*$", content, re.DOTALL)
            if not match:
                match = re.search(r"window\.__PRELOADED_STATE__\s*=\s*({.+})", content)
            
            if not match:
                print(f"   [{store_name}] 시도 {attempt+1}/4 정규표현식 파싱 매칭 실패. 2초 대기 후 재시도...")
                time.sleep(2.0)
                continue
                
            json_str = match.group(1)
            json_str = json_str.replace(":undefined", ":null").replace(": undefined", ": null")
            
            data = json.loads(json_str)
            widget_contents = data.get("widgetContents", {})
            
            products_list = []
            for key in widget_contents:
                widget = widget_contents[key]
                if isinstance(widget, dict):
                    for subkey, subval in widget.items():
                        if isinstance(subval, dict) and "data" in subval and isinstance(subval["data"], list):
                            items_data = subval["data"]
                            if items_data and "name" in items_data[0]:
                                products_list = items_data
                                break
                    if products_list:
                        break
            
            if not products_list:
                def deep_search_products(d):
                    if isinstance(d, dict):
                        for k, v in d.items():
                            if k == "simpleProducts" and isinstance(v, list) and v and "name" in v[0]:
                                return v
                            if k == "products" and isinstance(v, list) and v and "name" in v[0]:
                                return v
                            if isinstance(v, (dict, list)):
                                res = deep_search_products(v)
                                if res:
                                    return res
                    elif isinstance(d, list):
                        for item in d:
                            res = deep_search_products(item)
                            if res:
                                return res
                    return None
                products_list = deep_search_products(data)
            
            if products_list:
                channel_name = "johnsrcoffee"
                if "deepdiveroasters" in url:
                    channel_name = "deepdiveroasters"
                elif "shinyangroaster" in url:
                    channel_name = "shinyangroaster"
                elif "identity_coffeelab" in url:
                    channel_name = "identity_coffeelab"
                
                # Deduplicate inside this store fetch using a local set
                seen_store_names = set()
                for p in products_list:
                    name = p.get("name") or p.get("productName")
                    if not name:
                        continue
                    
                    name = name.strip()
                    # Exclude drip bags
                    if "드립백" in name:
                        continue
                    
                    # Prevent local duplicates in the same store list response
                    if name in seen_store_names:
                        continue
                    seen_store_names.add(name)
                    
                    benefits = p.get("benefitsView") or {}
                    price = benefits.get("dispDiscountedSalePrice") or benefits.get("discountedSalePrice") or p.get("discountedSalePrice") or p.get("salePrice") or 0
                    img_url = p.get("representativeImageUrl") or p.get("imageUrl") or ""
                    if isinstance(img_url, str):
                        img_url = img_url.strip()
                    
                    product_id = p.get("id") or p.get("productNo")
                    if product_id:
                        product_id = str(product_id).strip()
                    product_url = f"https://smartstore.naver.com/{channel_name}/products/{product_id}" if product_id else ""
                    
                    status = p.get("productStatusType", "")
                    stock_qty = p.get("stockQuantity")
                    
                    soldout = (status == "OUTOFSTOCK" or stock_qty == 0)
                    
                    products.append({
                        "store": store_name,
                        "name": name,
                        "price": price,
                        "imageUrl": img_url,
                        "productUrl": product_url,
                        "soldOut": soldout
                    })
                
                # If we parsed products successfully, return them and break out of retries!
                if products:
                    print(f"   [성공] Naver [{store_name}] 수집 성공! (수집 개수: {len(products)})")
                    return products
            else:
                print(f"   [{store_name}] 시도 {attempt+1}/4 빈 상품 리스트 응답. 2초 대기 후 재시도...")
                time.sleep(2.0)
                
        except Exception as e:
            print(f"   [{store_name}] 에러 발생 (시도 {attempt+1}/4): {e}")
            time.sleep(2.0)
            
    print(f"   [최종 실패] Naver [{store_name}] 수집에 최종 실패했습니다.")
    return []

def main():
    print("Starting automated coffee scraper...")
    print(f"[진단] 환경변수 검사 -> ScraperAPI 활성 키 개수: {len(SCRAPER_API_KEYS)}개 감지됨")
    for i, key in enumerate(SCRAPER_API_KEYS):
        if key:
            masked = f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "너무 짧음"
            print(f"  -> [진단 키 {i+1}] 앞4자리...뒤4자리: {masked}")
    
    if SCRAPER_API_KEYS:
        print("[인증 성공] 우회 장치(ScraperAPI 로테이터)가 감지되었습니다. 깃허브 무인 자동화 모드로 실행합니다.")
    else:
        print("[로컬 직접 수집] 한국 가정용 다이렉트 수집 모드로 실행합니다. (네이버 429 차단 시 대기시간이 길어질 수 있습니다)")
        
    # Execute sequentially to avoid free tier concurrency limits (HTTP 499)
    print("\n--------------------------------------------------")
    print("Executing sequential scrapes to prevent ScraperAPI concurrency limit...")
    print("--------------------------------------------------")
    
    print("\n=> [502 Coffee] 수집 시작...")
    products_502 = scrape_502_coffee()
    print(f"   [502 Coffee] 수집 완료! (수집 개수: {len(products_502)})")
    
    # Pause between scrapes to lower rate limits
    delay = 2.5
    print(f"대기 중: 스토어간 요청 간격을 위해 {delay}초 동안 쉬어갑니다...")
    time.sleep(delay)
    
    products_johns = scrape_naver_smartstore(
        "https://m.smartstore.naver.com/johnsrcoffee/category/ALL?cp=1", 
        "존스몰"
    )
    
    print(f"대기 중: 스토어간 요청 간격을 위해 {delay}초 동안 쉬어갑니다...")
    time.sleep(delay)
    
    products_deepdive1 = scrape_naver_smartstore(
        "https://m.smartstore.naver.com/deepdiveroasters/category/811c59eb9bcc48fc9fbe6300ec14f760?cp=1", 
        "딥다이브"
    )
    
    print(f"대기 중: 스토어간 요청 간격을 위해 {delay}초 동안 쉬어갑니다...")
    time.sleep(delay)
    
    products_deepdive2 = scrape_naver_smartstore(
        "https://m.smartstore.naver.com/deepdiveroasters/category/87e68b8f863e41faa2300c93ac4312e7?cp=1", 
        "딥다이브"
    )

    print(f"대기 중: 스토어간 요청 간격을 위해 {delay}초 동안 쉬어갑니다...")
    time.sleep(delay)
    
    products_shin = scrape_naver_smartstore(
        "https://m.smartstore.naver.com/shinyangroaster/category/7132a8c411e0400b848b622df6fd377d?cp=1", 
        "신양"
    )
    
    print(f"대기 중: 스토어간 요청 간격을 위해 {delay}초 동안 쉬어갑니다...")
    time.sleep(delay)
    
    products_identity = scrape_naver_smartstore(
        "https://m.smartstore.naver.com/identity_coffeelab/category/ALL?cp=1", 
        "아이덴티티"
    )
        
    all_products = products_502 + products_johns + products_deepdive1 + products_deepdive2 + products_shin + products_identity
    
    # Highly robust deduplication
    seen_keys = set()
    unique_products = []
    for p in all_products:
        p_name = p.get("name", "").strip()
        p_store = p.get("store", "").strip()
        p_url = p.get("productUrl", "").strip()
        
        # Primary check: using (store, name) key to ensure complete logical uniqueness
        dedup_key = (p_store, p_name)
        
        if dedup_key not in seen_keys:
            # Also double check by URL if URL exists
            if p_url and p_url in [x.get("productUrl", "").strip() for x in unique_products if x.get("productUrl")]:
                continue
            seen_keys.add(dedup_key)
            unique_products.append(p)
            
    # Get current time in KST (UTC+9) for live execution timestamp
    kst_now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
    last_scraped_str = kst_now.strftime("%Y-%m-%d %H:%M") # "2026-06-19 17:35"

    output_data = {
        "success": True,
        "count": len(unique_products),
        "last_scraped": last_scraped_str,
        "products": unique_products
    }
    
    # Write directly to products.json
    with open("products.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=4)
        
    print(f"Scraped and saved {len(unique_products)} products to products.json successfully!")

if __name__ == "__main__":
    main()
