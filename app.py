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
area = st.text_input("エリア", placeholder="例: 福岡市、博多駅、天神南駅")

keyword = st.selectbox("キーワード", options=KEYWORD_TEMPLATES)

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

    # --- クライアント診断 ---
    chart_data = [r for r in results if r["評価"] != "-"]
    if clinic_name and chart_data:
        match = find_clinic_rank(results, clinic_name)
        avg_reviews = sum(r["口コミ数"] for r in chart_data) / len(chart_data)
        avg_rating = sum(r["評価"] for r in chart_data) / len(chart_data)
        top3 = [r for r in chart_data if r["順位"] <= 3]
        top3_avg_reviews = sum(r["口コミ数"] for r in top3) / len(top3) if top3 else 0
        top3_avg_rating = sum(r["評価"] for r in top3) / len(top3) if top3 else 0

        st.divider()
        st.subheader("🩺 クライアント診断")

        if match:
            rank = match["順位"]
            rating = match["評価"] if match["評価"] != "-" else 0
            reviews = match["口コミ数"]

            # --- 現状サマリ ---
            st.markdown(f"**{match['医院名']}** の現状")
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("現在の順位", f"{rank}位", delta=f"トップ3まであと{max(rank - 3, 0)}つ" if rank > 3 else "トップ3圏内")
            review_gap = int(top3_avg_reviews - reviews)
            col_b.metric("口コミ数", f"{reviews}件", delta=f"トップ3平均まで{review_gap:+d}件" if review_gap != 0 else "トップ3平均と同等")
            rating_gap = top3_avg_rating - rating if rating else 0
            col_c.metric("評価", f"⭐ {rating}", delta=f"トップ3平均まで{rating_gap:+.1f}" if abs(rating_gap) > 0.05 else "トップ3平均と同等")

            # --- 改善アクション ---
            st.divider()
            st.markdown("**改善アクション**")

            actions = []

            # 口コミ数の診断
            if reviews < top3_avg_reviews:
                need = int(top3_avg_reviews - reviews)
                actions.append(
                    f"📝 **口コミを増やす（あと約{need}件）** — トップ3の平均は{top3_avg_reviews:.0f}件。"
                    f"来院後のフォローメールやQRコード掲示で口コミ獲得の仕組みを作りましょう。"
                )
            elif reviews >= top3_avg_reviews:
                actions.append(
                    f"✅ **口コミ数は十分**（{reviews}件 / トップ3平均{top3_avg_reviews:.0f}件）。"
                    f"口コミの「質」と返信対応が次の差別化ポイントです。"
                )

            # 評価の診断
            if rating and rating < 4.5:
                actions.append(
                    f"⭐ **評価を上げる（現在{rating}）** — "
                    f"低評価の口コミがあれば丁寧に返信し、満足度の高い患者に口コミをお願いしましょう。"
                )
            elif rating and rating >= 4.5:
                actions.append(
                    f"✅ **評価は高水準**（{rating}）。この評価を維持しつつ口コミ数を増やすのが理想です。"
                )

            # 順位の診断
            if rank > 3:
                above_me = [r for r in chart_data if r["順位"] < rank]
                weaker_above = [r for r in above_me if r["口コミ数"] < reviews]
                if weaker_above:
                    names = "、".join(r["医院名"] for r in weaker_above[:3])
                    actions.append(
                        f"🎯 **順位を逆転できる可能性あり** — "
                        f"{names} は口コミ数で下回っているのに上位です。"
                        f"Googleビジネスプロフィールの情報充実（カテゴリ・営業時間・写真）で逆転が狙えます。"
                    )
                else:
                    actions.append(
                        f"📋 **Googleビジネスプロフィールの最適化** — "
                        f"カテゴリ設定、営業時間、写真の充実、投稿の定期更新で関連性スコアを上げましょう。"
                    )

            for action in actions:
                st.markdown(action)

            # --- トップ3との比較表 ---
            if top3:
                st.divider()
                st.markdown("**トップ3との比較**")
                compare = top3 + [match] if rank > 3 else top3
                df_compare = pd.DataFrame(compare)
                def highlight_client(row):
                    if clinic_name.lower() in row["医院名"].lower():
                        return ["background-color: #fff3cd; font-weight: bold"] * len(row)
                    return [""] * len(row)
                st.dataframe(
                    df_compare.style.apply(highlight_client, axis=1),
                    use_container_width=True,
                    hide_index=True,
                )

        else:
            st.warning(
                f"「{clinic_name}」がトップ{len(results)}位以内に見つかりませんでした。\n\n"
                f"**まずはランクインすることが第一目標です。** "
                f"Googleビジネスプロフィールの登録・最適化から始めましょう。\n\n"
                f"- 上位{len(chart_data)}件の平均: 口コミ {avg_reviews:.0f}件 / 評価 {avg_rating:.1f}\n"
                f"- トップ3の平均: 口コミ {top3_avg_reviews:.0f}件 / 評価 {top3_avg_rating:.1f}"
            )
