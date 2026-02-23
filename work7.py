import streamlit as st
import pandas as pd
import time
import json
import os
import io
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# Sitenin sekme adını ve genişliğini ayarlayalım
st.set_page_config(page_title="İddaa Analiz Pro", layout="wide")

VERI_DOSYASI = "takimlar.json"

# Veritabanını yükleme fonksiyonu
def veritabanini_yukle():
    VARSAYILAN_VERITABANI = {
        "Türkiye Süper Lig": {
            "Galatasaray": "https://arsiv.mackolik.com/Takim/1/Galatasaray",
            "Fenerbahçe": "https://arsiv.mackolik.com/Takim/2/Fenerbahce",
            "Beşiktaş": "https://arsiv.mackolik.com/Takim/3/Besiktas",
            "Trabzonspor": "https://arsiv.mackolik.com/Takim/4/Trabzonspor",
            "Başakşehir": "https://arsiv.mackolik.com/Takim/2855/Basaksehir"
            # Kodu çok uzatmamak adına varsayılan listeyi kısalttım, json dosyan zaten var!
        },
        "İngiltere Premier Lig": {"Arsenal": "", "Manchester City": ""},
        "İspanya La Liga": {"Barcelona": "", "Real Madrid": ""}
    }
    
    if not os.path.exists(VERI_DOSYASI):
        with open(VERI_DOSYASI, "w", encoding="utf-8") as f:
            json.dump(VARSAYILAN_VERITABANI, f, ensure_ascii=False, indent=4)
            
    with open(VERI_DOSYASI, "r", encoding="utf-8") as f:
        return json.load(f)

VERITABANI = veritabanini_yukle()

# Hafıza (Session State) ayarları (Site yenilendiğinde veriler silinmesin diye)
if 'df' not in st.session_state:
    st.session_state.df = pd.DataFrame()

def is_score(text):
    if "-" not in text: return False
    temiz = text.replace(" ", "").replace("(", "").replace(")", "").replace("\xa0", "")
    parts = temiz.split("-")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit(): return True
    return False

def sonuc_bul(skor_metni):
    try:
        skor = str(skor_metni).replace(" ", "").replace("(", "").replace(")", "").replace("\xa0", "")
        if '-' not in skor: return None
        ev, dep = map(int, skor.split('-'))
        if ev > dep: return 1
        elif ev < dep: return 2
        else: return 0
    except:
        return None

def verileri_cek(secilen_takim, url, secilen_sezon):
    driver = None
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        driver.get(url)
        time.sleep(2)
        
        baslangic_yili = secilen_sezon.split('-')[0]
        
        try:
            option_xpath = f"//option[contains(text(), '{baslangic_yili}')]"
            option_element = driver.find_element(By.XPATH, option_xpath)
            select_element = option_element.find_element(By.XPATH, "..")
            select = Select(select_element)
            select.select_by_visible_text(option_element.text)
            time.sleep(3) 
        except:
            return None, "Sezon seçilemedi. Bu takım o sezon ligde olmayabilir."

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        tablolar = soup.find_all('table')
        en_iyi_veriler = []

        for tablo in tablolar:
            gecici_veriler = []
            satirlar = tablo.find_all('tr')
            for satir in satirlar:
                hucreler = satir.find_all('td')
                dolu_hucreler = [h.text.strip().replace('\xa0', '').replace('\n', '') for h in hucreler if h.text.strip() != '']
                if len(dolu_hucreler) < 4: continue 
                
                ms_index = -1
                for i, metin in enumerate(dolu_hucreler):
                    if is_score(metin):
                        if i > 0 and i < len(dolu_hucreler) - 1:
                            ms_index = i
                            break
                
                if ms_index != -1:
                    ms = dolu_hucreler[ms_index]
                    ev = dolu_hucreler[ms_index - 1]
                    dep = dolu_hucreler[ms_index + 1]
                    iy = ""
                    for i in range(ms_index + 1, len(dolu_hucreler)):
                        if is_score(dolu_hucreler[i]):
                            iy = dolu_hucreler[i]
                            break
                    tarih = dolu_hucreler[0]
                    for i in range(ms_index):
                        if "." in dolu_hucreler[i] and any(c.isdigit() for c in dolu_hucreler[i]):
                            tarih = dolu_hucreler[i]
                            break
                    gecici_veriler.append([tarih, ev, ms, dep, iy])
            
            if len(gecici_veriler) > len(en_iyi_veriler):
                en_iyi_veriler = gecici_veriler

        if not en_iyi_veriler:
            return None, "Maç verileri sayfada bulunamadı."

        df = pd.DataFrame(en_iyi_veriler, columns=['Tarih', 'Ev Sahibi', 'MS Skoru', 'Deplasman', 'İY Skoru'])
        df['IY_Sonuc'] = df['İY Skoru'].apply(sonuc_bul)
        df['MS_Sonuc'] = df['MS Skoru'].apply(sonuc_bul)
        df = df.dropna(subset=['IY_Sonuc', 'MS_Sonuc'])
        
        harf_sozlugu = {1: '1', 2: '2', 0: 'X'}
        df['IY_Harf'] = df['IY_Sonuc'].map(harf_sozlugu)
        df['MS_Harf'] = df['MS_Sonuc'].map(harf_sozlugu)
        df['İY/MS Formatı'] = df['IY_Harf'] + "/" + df['MS_Harf']
        
        # Sadece göstereceğimiz sütunları seçelim
        df_son = df[['Tarih', 'Ev Sahibi', 'İY Skoru', 'MS Skoru', 'Deplasman', 'İY/MS Formatı']]
        return df_son, "Başarılı"
        
    except Exception as e:
        return None, f"Hata: {str(e)}"
    finally:
        if driver: driver.quit()

def excele_donustur(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Analiz')
    veriler = output.getvalue()
    return veriler

# --- WEB SİTESİ ARAYÜZÜ ---

st.title("⚽ Profesyonel İddaa/Maç Analiz Programı")
st.markdown("---")

# Yan Menü (Sidebar) Kontrolleri
st.sidebar.header("🔍 Arama Ayarları")

secilen_lig = st.sidebar.selectbox("Lig Seçin", list(VERITABANI.keys()))
takim_listesi = list(VERITABANI[secilen_lig].keys()) if secilen_lig in VERITABANI else []
secilen_takim = st.sidebar.selectbox("Takım Seçin", takim_listesi)

sezon_secenekleri = ["2025-2026", "2024-2025", "2023-2024", "2022-2023", "2021-2022", "2020-2021"]
secilen_sezon = st.sidebar.selectbox("Sezon Seçin", sezon_secenekleri, index=1)

url = VERITABANI.get(secilen_lig, {}).get(secilen_takim, "")

# Dinamik Link İsteme (Web mantığına uygun)
if secilen_takim and not url:
    st.sidebar.warning(f"⚠️ {secilen_takim} takımının linki eksik!")
    yeni_url = st.sidebar.text_input("Mackolik Arşiv Linkini Buraya Yapıştırın:")
    if st.sidebar.button("💾 Linki Kaydet"):
        if "arsiv.mackolik.com/Takim" in yeni_url:
            VERITABANI[secilen_lig][secilen_takim] = yeni_url.strip()
            with open(VERI_DOSYASI, "w", encoding="utf-8") as f:
                json.dump(VERITABANI, f, ensure_ascii=False, indent=4)
            st.sidebar.success("Link kaydedildi! Sayfa yenileniyor...")
            time.sleep(1)
            st.rerun() # Sayfayı yenile
        else:
            st.sidebar.error("Geçersiz link!")

st.sidebar.markdown("---")

# Veri İndirme Butonu
if st.sidebar.button("🚀 Verileri Çek", use_container_width=True):
    if url:
        with st.spinner(f'{secilen_sezon} sezonu verileri Mackolik\'ten çekiliyor. Lütfen bekleyin...'):
            df, mesaj = verileri_cek(secilen_takim, url, secilen_sezon)
            if df is not None:
                st.session_state.df = df
                st.success(f"✅ {secilen_takim} verileri başarıyla yüklendi!")
            else:
                st.error(f"❌ Hata: {mesaj}")
    else:
        st.sidebar.error("Önce takımın linkini kaydetmelisin!")

# --- ANA EKRAN (FİLTRE VE TABLO) ---
if not st.session_state.df.empty:
    df_gosterilecek = st.session_state.df.copy()
    
    col1, col2 = st.columns(2)
    with col1:
        filtre_secenekleri = ["Tümü", "1/X veya 2/X", "1/2 veya 2/1", "X/1", "X/X", "X/2", "1/1", "2/2"]
        secilen_filtre = st.selectbox("🎯 İY/MS Filtresi:", filtre_secenekleri)
    with col2:
        sirala_secenekleri = ["Eskiden Yeniye", "Yeniden Eskiye"]
        secilen_sirala = st.selectbox("📅 Sıralama:", sirala_secenekleri)

    # Filtreleme İşlemi
    if secilen_filtre == "1/2 veya 2/1":
        df_gosterilecek = df_gosterilecek[df_gosterilecek['İY/MS Formatı'].isin(['1/2', '2/1'])]
    elif secilen_filtre == "1/X veya 2/X":
        df_gosterilecek = df_gosterilecek[df_gosterilecek['İY/MS Formatı'].isin(['1/X', '2/X'])]
    elif secilen_filtre != "Tümü":
        df_gosterilecek = df_gosterilecek[df_gosterilecek['İY/MS Formatı'] == secilen_filtre]
        
    # Sıralama İşlemi
    df_gosterilecek['Gercek_Tarih'] = pd.to_datetime(df_gosterilecek['Tarih'], format='%d.%m.%Y', errors='coerce')
    if secilen_sirala == "Eskiden Yeniye":
        df_gosterilecek = df_gosterilecek.sort_values(by='Gercek_Tarih', ascending=True)
    else:
        df_gosterilecek = df_gosterilecek.sort_values(by='Gercek_Tarih', ascending=False)
    
    # Gereksiz tarih sütununu gizle
    df_gosterilecek = df_gosterilecek.drop(columns=['Gercek_Tarih'])

    # Tabloyu Web Sitesine Çiz
    st.dataframe(df_gosterilecek, use_container_width=True, hide_index=True)

    # Excel Olarak İndirme Butonu
    excel_verisi = excele_donustur(df_gosterilecek)
    st.download_button(
        label="📥 Ekranda Görünenleri Excel Olarak İndir",
        data=excel_verisi,
        file_name=f"{secilen_takim}_{secilen_sezon}_analiz.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary"
    )
else:
    st.info("👈 Analize başlamak için sol menüden takım seçip 'Verileri Çek' butonuna tıklayın.")