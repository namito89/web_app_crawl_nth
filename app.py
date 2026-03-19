import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import requests
from datetime import datetime, date
import time
import re
from urllib.parse import quote
import dateparser
import io

st.set_page_config(page_title="📰 Crawler Tin tức", layout="wide")

st.title("📰 Crawler Tin tức VnExpress & CafeF (Dùng đúng code gốc của bạn)")
st.markdown("**Giống hệt notebook cũ – chỉ thay giao diện web**")

keywords_str = st.text_input(
    "Nhập từ khóa (cách nhau dấu phẩy):",
    value="vic, vhm, vre, vin group, phạm nhật vượng"
)
target_date = st.date_input(
    "Ngày giới hạn (lọc bài SAU ngày này):",
    value=date(2026, 3, 15)
)

def crawl_vnexpress(driver, keyword):
    data = []
    base_url = f"https://timkiem.vnexpress.net/?search_q={quote(keyword)}"
    st.write(f"Đang crawl VnExpress: **{keyword}**")
    
    for page in range(1, 3):
        url = base_url if page == 1 else f"{base_url}&page={page}"
        driver.get(url)
        time.sleep(4)
        articles = driver.find_elements(By.CSS_SELECTOR, "h3.title-news")
        st.write(f"  VnExpress - Trang {page}: Tìm thấy {len(articles)} bài")
        
        for article in articles:
            try:
                a_tag = article.find_element(By.TAG_NAME, "a")
                title = a_tag.text.strip()
                if keyword.lower() not in title.lower(): continue
                link = a_tag.get_attribute("href")
                if link and "vnexpress.net" in link:
                    data.append({'Keyword': keyword, 'Tiêu đề': title, 'Link': link})
            except:
                continue
    return data

def crawl_cafef(driver, keyword):
    data = []
    base_url = f"https://cafef.vn/tim-kiem.chn?keywords={quote(keyword)}"
    st.write(f"Đang crawl CafeF: **{keyword}**")
    
    for page in range(1, 3):
        url = base_url if page == 1 else f"https://cafef.vn/tim-kiem/trang-{page}.chn?keywords={quote(keyword)}"
        driver.get(url)
        time.sleep(4)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        articles = soup.find_all('a', href=lambda h: h and '.chn' in h and 'tim-kiem' not in h)
        st.write(f"  CafeF - Trang {page}: Tìm thấy {len(articles)} bài")
        
        for article in articles:
            title = article.text.strip()
            if keyword.lower() not in title.lower(): continue
            link = article.get("href")
            data.append({'Keyword': keyword, 'Tiêu đề': title, 'Link': "https://cafef.vn" + link})
    return data

if st.button("🚀 BẮT ĐẦU CRAWL (giống notebook gốc)", type="primary", use_container_width=True):
    keywords = [kw.strip() for kw in keywords_str.split(',') if kw.strip()]
    
    with st.spinner("Đang khởi động Chrome headless + crawl (5-10 phút)..."):
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        
        all_data = []
        for kw in keywords:
            all_data.extend(crawl_vnexpress(driver, kw))
            all_data.extend(crawl_cafef(driver, kw))
        
        driver.quit()

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
        # (phần lọc ngày giữ nguyên 100% code cũ của bạn – mình không thay đổi)
        url = str(row.get('Link', '')).strip()
        if not url: 
            progress_bar.progress((i+1)/len(df_new))
            continue
        try:
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
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
