import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# ========== ページ設定 ==========
st.set_page_config(
    page_title="MEO順位チェッカー",
    page_icon="📍",
    layout="centered",
)

def geocode_city(city_name, api_key):
    """市名から緯度経度を取得（SerpAPI の Google Maps 経由）"""
    params = {
        "engine": "google_maps",
        "q": city_name,
        "hl": "ja",
        "api_key": api_key,
    }
    resp = requests.get("https://serpapi.com/search.json", params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if "local_map" in data:
        lm = data["local_map"]
        lat = lm.get("gps_coordinates", {}).get("latitude")
        lng = lm.get("gps_coordinates", {}).get("longitude")
        if lat and lng:
            return (lat, lng)
    pr = data.get("place_results", {})
    gps_coords = pr.get("gps_coordinates", {})
    if gps_coords.get("latitude") and gps_coords.get("longitude"):
        return (gps_coords["latitude"], gps_coords["longitude"])
    return None

# ========== キーワードテンプレ ==========
KEYWORD_TEMPLATES = [
    "歯医者",
    "歯科",
    "インプラント",
    "矯正歯科",
    "ホワイトニング",
    "小児歯科",
    "歯医者 おすすめ",
    "歯医者 口コミ",
    "審美歯科",
    "入れ歯",
]


def search_google_maps(keyword, lat, lng, api_key, zoom=13):
    """Google Maps で検索"""
    params = {
        "engine": "google_maps",
        "q": keyword,
        "ll": f"@{lat},{lng},{zoom}z",
        "hl": "ja",
        "api_key": api_key,
    }
    resp = requests.get("https://serpapi.com/search.json", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def extract_results(data):
    """結果を抽出"""
    results = []
    for i, place in enumerate(data.get("local_results", []), start=1):
        results.append({
            "順位": i,
            "医院名": place.get("title", "不明"),
            "評価": place.get("rating", "-"),
            "口コミ数": place.get("reviews", 0),
            "住所": place.get("address", ""),
        })
    return results


def find_clinic_rank(results, clinic_name):
    """医院名で検索（部分一致）"""
    clinic_lower = clinic_name.lower()
    for r in results:
        if clinic_lower in r["医院名"].lower():
            return r
    return None


# ========== UI ==========
st.title("📍 MEO順位チェッカー")
st.caption("Google Mapsでの検索順位をリアルタイムで確認")

# API キー（Streamlit Cloud の secrets から取得）
api_key = st.secrets.get("SERPAPI_KEY", "")
if not api_key:
    api_key = st.text_input("SerpAPI Key", type="password")
    if not api_key:
        st.stop()

# --- 入力フォーム ---
area = st.text_input("エリア（市区町村名）", placeholder="例: 福岡市、宮崎市、横浜市")

col1, col2 = st.columns([3, 1])
with col1:
    keyword_custom = st.text_input(
        "キーワード",
        placeholder="例: インプラント",
    )
with col2:
    keyword_template = st.selectbox("よく使う", options=["--"] + KEYWORD_TEMPLATES)

# 手入力を優先、空欄ならテンプレを使う
if keyword_custom:
    keyword = keyword_custom
elif keyword_template != "--":
    keyword = keyword_template
else:
    keyword = ""

search_keyword = f"{area} {keyword}" if keyword else ""

clinic_name = st.text_input("医院名（任意・部分一致で検索）", placeholder="例: さくら歯科")

# --- 検索ボタン ---
if st.button("🔍 検索する", type="primary", use_container_width=True):
    if not search_keyword.strip():
        st.warning("キーワードを入力してください")
        st.stop()

    # 座標を取得
    with st.spinner(f"「{area}」の位置情報を取得中..."):
        coords = geocode_city(area, api_key)
        if coords is None:
            st.error(f"「{area}」の位置情報が取得できませんでした。正しい市区町村名か確認してください。")
            st.stop()
        lat, lng = coords

    with st.spinner("Google Maps を検索中..."):
        try:
            data = search_google_maps(search_keyword, lat, lng, api_key)
            results = extract_results(data)
        except requests.exceptions.HTTPError as e:
            st.error(f"APIエラー: {e}")
            st.stop()
        except Exception as e:
            st.error(f"エラー: {e}")
            st.stop()

    if not results:
        st.warning("結果が見つかりませんでした")
        st.stop()

    # --- 医院名検索結果 ---
    if clinic_name:
        match = find_clinic_rank(results, clinic_name)
        if match:
            st.success(f"**{match['医院名']}** は **{match['順位']}位** / {len(results)}件中")
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("順位", f"{match['順位']}位")
            mc2.metric("評価", f"⭐ {match['評価']}")
            mc3.metric("口コミ", f"{match['口コミ数']}件")
        else:
            st.warning(f"「{clinic_name}」はトップ{len(results)}位以内に見つかりませんでした")

    # --- 順位一覧 ---
    st.divider()
    st.subheader(f"🗺️ {search_keyword}")
    st.caption(f"{datetime.now().strftime('%Y-%m-%d %H:%M')} 時点")

    df = pd.DataFrame(results)

    # 医院名ハイライト
    if clinic_name:
        def highlight_row(row):
            if clinic_name.lower() in row["医院名"].lower():
                return ["background-color: #fff3cd; font-weight: bold"] * len(row)
            return [""] * len(row)
        styled = df.style.apply(highlight_row, axis=1)
        st.dataframe(styled, use_container_width=True, hide_index=True)
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

    # --- 分析コメント ---
    if results:
        avg_rating = sum(r["評価"] for r in results if r["評価"] != "-") / max(
            sum(1 for r in results if r["評価"] != "-"), 1
        )
        avg_reviews = sum(r["口コミ数"] for r in results) / len(results)
        st.divider()
        st.caption(
            f"上位{len(results)}件の平均: 評価 {avg_rating:.1f} / 口コミ {avg_reviews:.0f}件"
        )
