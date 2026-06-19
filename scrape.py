import requests
from bs4 import BeautifulSoup
import re
import json
import urllib3
import datetime
import os
import time
from concurrent.futures import ThreadPoolExecutor

# Suppress SSL verification warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Read ScraperAPI key from GitHub Actions secrets environment
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive"
}

def fetch_url(url, custom_headers=None):
    """Fetches HTML content, routing through ScraperAPI on GitHub Actions to bypass Naver blocking"""
    headers_to_use = custom_headers if custom_headers else HEADERS
    
    # If API Key is present in environment, route through ScraperAPI to bypass cloud IP blocks
    if SCRAPER_API_KEY and ("smartstore.naver.com" in url or "m.smartstore.naver.com" in url):
        print(f"[우회] 깃허브 서버에서 네이버 수집 우회 터널을 작동합니다 -> {url[:50]}...")
        try:
            # Use only free-tier compatible parameters (api_key and url) to prevent HTTP 500 errors!
            payload = {
                'api_key': SCRAPER_API_KEY,
                'url': url
            }
            # ScraperAPI automatically rotates high-quality proxies and handles header fingerprints
            r = requests.get('http://api.scraperapi.com', params=payload, verify=False, timeout=50)
            return r
        except Exception as e:
            print(f"[우회 실패] 프록시 연결 오류: {e}. 다이렉트 시도로 폴백합니다.")
    
    # Direct fetch (Default on local machine)
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
                "store": "502 Coffee",
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
    """Scrapes products from Naver Smartstore using the mobile category endpoint (with up to 3 retries)"""
    # Try up to 3 times to fetch and successfully parse the JSON payload
    for attempt in range(3):
        products = []
        try:
            custom_headers = HEADERS.copy()
            custom_headers["Referer"] = url
            
            r = fetch_url(url, custom_headers)
            if r.status_code != 200:
                print(f"[시도 {attempt+1}/3] Naver [{store_name}] HTTP 오류: {r.status_code}. 재시도합니다...")
                time.sleep(1.5)
                continue
            
            soup = BeautifulSoup(r.text, "html.parser")
            script_tag = soup.find("script", string=re.compile(r"window\.__PRELOADED_STATE__\s*="))
            
            if not script_tag:
                print(f"[시도 {attempt+1}/3] Naver [{store_name}] 방화벽 감지로 수집 실패 (스크립트 없음). IP 변경 및 재시도...")
                time.sleep(2)
                continue
            
            content = script_tag.string.strip()
            match = re.search(r"window\.__PRELOADED_STATE__\s*=\s*({.+?});?\s*$", content, re.DOTALL)
            if not match:
                match = re.search(r"window\.__PRELOADED_STATE__\s*=\s*({.+})", content)
            
            if not match:
                print(f"[시도 {attempt+1}/3] Naver [{store_name}] 정규표현식 매칭 실패. 재시도...")
                time.sleep(1.5)
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
                if "shinyangroaster" in url:
                    channel_name = "shinyangroaster"
                
                for p in products_list:
                    name = p.get("name") or p.get("productName")
                    if not name:
                        continue
                    
                    price = p.get("salePrice") or p.get("discountedSalePrice") or 0
                    img_url = p.get("representativeImageUrl") or p.get("imageUrl") or ""
                    
                    product_id = p.get("id") or p.get("productNo")
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
                    print(f"[성공] Naver [{store_name}] 수집 성공! (수집 개수: {len(products)})")
                    return products
            else:
                print(f"[시도 {attempt+1}/3] Naver [{store_name}] 빈 리스트 응답. 재시도...")
                time.sleep(2)
                
        except Exception as e:
            print(f"Error scraping {store_name} (Attempt {attempt+1}/3): {e}")
            time.sleep(2)
            
    print(f"[최종 실패] Naver [{store_name}] 수집에 최종 실패했습니다.")
    return []

def main():
    print("Starting automated coffee scraper...")
    if SCRAPER_API_KEY:
        print("[인증 성공] ScraperAPI 우회 키가 감지되었습니다. 깃허브 무인 자동화 모드로 실행합니다.")
    else:
        print("[로컬 직접 수집] 한국 가정용 다이렉트 수집 모드로 실행합니다.")
        
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_502 = executor.submit(scrape_502_coffee)
        future_johns = executor.submit(
            scrape_naver_smartstore, 
            "https://m.smartstore.naver.com/johnsrcoffee/category/ALL?cp=1", 
            "존스몰"
        )
        future_deepdive1 = executor.submit(
            scrape_naver_smartstore, 
            "https://m.smartstore.naver.com/deepdiveroasters/category/811c59eb9bcc48fc9fbe6300ec14f760?cp=1", 
            "딥다이브"
        )
        future_deepdive2 = executor.submit(
            scrape_naver_smartstore, 
            "https://m.smartstore.naver.com/deepdiveroasters/category/87e68b8f863e41faa2300c93ac4312e7?cp=1", 
            "딥다이브"
        )

        future_shin = executor.submit(
            scrape_naver_smartstore, 
            "https://m.smartstore.naver.com/shinyangroaster/category/7132a8c411e0400b848b622df6fd377d?cp=1", 
            "신양"
        )
        
        products_502 = future_502.result()
        products_johns = future_johns.result()
        products_deepdive1 = future_deepdive1.result()
        products_deepdive2 = future_deepdive2.result()
        products_shin = future_shin.result()
        
    all_products = products_502 + products_johns + products_deepdive1 + products_deepdive2 + products_shin
    
    # Deduplicate
    seen_urls = set()
    unique_products = []
    for p in all_products:
        p_url = p.get("productUrl")
        if p_url and p_url not in seen_urls:
            seen_urls.add(p_url)
            unique_products.append(p)
        elif not p_url:
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
