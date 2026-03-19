import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup
import requests
from datetime import datetime, date
import time
import re
from urllib.parse import quote
import dateparser
import io
from playwright.sync_api import sync_playwright

st.set_page_config(page_title="📰 Crawler Tin tức", layout="wide")

st.title("📰 Crawler Tin tức VnExpress & CafeF (Playwright - ổn định trên Cloud)")
st.markdown("**Giống hệt notebook gốc của bạn, chỉ thay Selenium bằng Playwright**")

keywords_str = st.text_input(
    "Nhập từ khóa (cách nhau dấu phẩy):",
    value="vic, vhm, vre, vin group, phạm nhật vượng"
)
target_date = st.date_input(
    "Ngày giới hạn (lọc bài SAU ngày này):",
    value=date(2026, 3, 15)
)

def crawl_vnexpress(page, keyword):
    data = []
    base_url = f"https://timkiem.vnexpress.net/?search_q={quote(keyword)}"
    st.write(f"Đang crawl VnExpress: **{keyword}**")
    
    for page_num in range(1, 3):
        url = base_url if page_num == 1 else f"{base_url}&page={page_num}"
        page.goto(url, wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(4000)
        
        articles = page.locator("h3.title-news a").all()
        st.write(f"  VnExpress - Trang {page_num}: Tìm thấy {len(articles)} bài")
        
        for a in articles:
            try:
                title = a.text_content().strip()
                if keyword.lower() not in title.lower(): continue
                link = a.get_attribute("href")
                if link and "vnexpress.net" in link:
                    data.append({'Keyword': keyword, 'Tiêu đề': title, 'Link': link})
            except:
                continue
    return data

def crawl_cafef(page, keyword):
    data = []
    base_url = f"https://cafef.vn/tim-kiem.chn?keywords={quote(keyword)}"
    st.write(f"Đang crawl CafeF: **{keyword}**")
    
    for page_num in range(1, 3):
        url = base_url if page_num == 1 else f"https://cafef.vn/tim-kiem/trang-{page_num}.chn?keywords={quote(keyword)}"
        page.goto(url, wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(4000)
        
        html = page.content()
        soup = BeautifulSoup(html, 'html.parser')
        articles = soup.find_all('a', href=lambda h: h and '.chn' in h and 'tim-kiem' not in h)
        st.write(f"  CafeF - Trang {page_num}: Tìm thấy {len(articles)} bài")
        
        for article in articles:
            title = article.text.strip()
            if keyword.lower() not in title.lower(): continue
            link = article.get("href")
            data.append({'Keyword': keyword, 'Tiêu đề': title, 'Link': "https://cafef.vn" + link})
    return data

if st.button("🚀 BẮT ĐẦU CRAWL (Playwright - giống notebook gốc)", type="primary", use_container_width=True):
    keywords = [kw.strip() for kw in keywords_str.split(',') if kw.strip()]
    
    with st.spinner("Đang khởi động Playwright + crawl (3-6 phút)..."):
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            )
            page = browser.new_page()
            page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            
            all_data = []
            for kw in keywords:
                all_data.extend(crawl_vnexpress(page, kw))
                all_data.extend(crawl_cafef(page, kw))
                time.sleep(1)
            
            browser.close()

    # Phần lọc ngày GIỐNG NGUYÊN BẢN notebook của bạn
    df = pd.DataFrame(all_data)
    df_clean = df.drop_duplicates(subset=['Tiêu đề'])
    df_new = df_clean.copy()

    st.write(f"🔍 Đang lọc bài SAU ngày: {target_date}")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    keep_indices = []
    article_dates = []
    progress_bar = st.progress(0)

    for i, (idx, row) in enumerate(df_new.iterrows()):
        url = str(row.get('Link', '')).strip()
        if not url: 
            progress_bar.progress((i+1)/len(df_new))
            continue
        try:
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # (toàn bộ phần parse ngày giữ nguyên 100% như notebook cũ của bạn)
            date_text = None
            meta = soup.find('meta', attrs={'property': 'article:published_time'}) or \
                   soup.find('meta', attrs={'name': ['article:published_time', 'pubdate', 'publishdate']})
            if meta and meta.get('content'):
                date_text = meta['content']
            
            if not date_text:
                time_tag = soup.find('time')
                if time_tag and time_tag.get('datetime'):
                    date_text = time_tag['datetime']
            
            if not date_text:
                if "vnexpress.net" in url:
                    tag = soup.find('span', class_='date') or soup.find('time')
                else:
                    tag = soup.find('span', class_='pdate') or soup.find('span', class_='time')
                if tag:
                    date_text = tag.get_text(strip=True)
            
            if not date_text:
                progress_bar.progress((i+1)/len(df_new))
                continue

            parsed_date = None
            iso_match = re.search(r'(\d{4}-\d{2}-\d{2})', date_text)
            if iso_match:
                try:
                    parsed_date = datetime.strptime(iso_match.group(1), "%Y-%m-%d").date()
                except:
                    pass
            
            if not parsed_date:
                dmy_match = re.search(r'(\d{1,2})[./-](\d{1,2})[./-](\d{4})', date_text)
                if dmy_match:
                    d, m, y = dmy_match.groups()
                    try:
                        parsed_date = datetime.strptime(f"{d}/{m}/{y}", "%d/%m/%Y").date()
                    except:
                        pass
            
            if not parsed_date:
                parsed = dateparser.parse(date_text, languages=['vi'], settings={'DATE_ORDER': 'DMY'})
                if parsed:
                    parsed_date = parsed.date()
            
            if parsed_date and parsed_date > target_date:
                keep_indices.append(idx)
                article_dates.append(parsed_date.strftime("%d/%m/%Y"))
        except:
            pass
        progress_bar.progress((i+1)/len(df_new))

    df_filtered = df_new.loc[keep_indices].copy().reset_index(drop=True)
    df_filtered['Ngay_ra_tin'] = article_dates

    st.success(f"✅ HOÀN TẤT! Còn lại **{len(df_filtered)} bài** sau ngày {target_date}")

    st.dataframe(df_filtered[['Keyword', 'Tiêu đề', 'Ngay_ra_tin']].head(10))

    df_filtered['Nguồn'] = df_filtered['Link'].apply(lambda x: f'=HYPERLINK("{x}", "Xem bài báo")')
    df_final = df_filtered[['Keyword', 'Tiêu đề', 'Ngay_ra_tin', 'Nguồn']]

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_final.to_excel(writer, index=False)
    st.download_button(
        label="📥 TẢI FILE EXCEL (có hyperlink)",
        data=output.getvalue(),
        file_name=f"{keywords[0]}_DDMMYYYY_{target_date}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
