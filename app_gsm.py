from __future__ import annotations

import datetime as dt
import gc
import io

import matplotlib.pyplot as plt
import streamlit as st

from meteo_lib import gsm_utils as gsm

# ==============================================================================
# ページ設定
# ==============================================================================
st.set_page_config(
    page_title="JMA GSM 地上気圧・上空気温（雪目安）作図",
    page_icon="❄️",
    layout="wide",
)

st.title("JMA GSM 地上気圧・上空気温（雪目安）天気図")
st.caption("京都大学生存圏研究所 (RISH) GSM GPV アーカイブより取得・作図")

# 描画領域プリセット
EXTENT_PRESETS: dict[str, tuple[float, float, float, float]] = {
    "標準（日本付近: 117°E–156°E, 18°N–61°N）": (117.0, 156.0, 18.0, 61.0),
    "広域（極東・シベリア高気圧含む: 105°E–165°E, 15°N–65°N）": (105.0, 165.0, 15.0, 65.0),
    "北日本〜日本海中心（125°E–152°E, 30°N–52°N）": (125.0, 152.0, 30.0, 52.0),
}

# ==============================================================================
# サイドバー UI
# ==============================================================================
with st.sidebar:
    st.header("作図パラメータ設定")

    # 1. 初期値の日付（デフォルトは前日の00UTC）
    default_date = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)
    init_date = st.date_input(
        "初期日 (UTC)",
        value=default_date,
        min_value=dt.date(2018, 1, 1),
        max_value=dt.datetime.now(dt.timezone.utc).date(),
    )

    # 2. 初期時刻 (UTC)
    init_hour = st.radio(
        "初期時刻 (UTC)",
        options=["00", "06", "12", "18"],
        index=0,
        horizontal=True,
    )

    # 3. 予報時間 (6時間刻み)
    # ※ 00/12UTCは最大132h(一部264h)、06/18UTCは最大84h(一部132h)
    max_ft = 132 if init_hour in ("00", "12") else 84
    fcst_hours = st.slider(
        "予報時間 FT (時間)",
        min_value=0,
        max_value=max_ft,
        value=24,
        step=6,
    )

    # 4. 季節カラーレンジ
    season_label = st.radio(
        "気温カラーレンジ設定",
        options=["冬季（寒気・雪解析向け）", "夏季（暖気解析向け）"],
        index=0,
    )
    season = "winter" if season_label.startswith("冬季") else "summer"

    # 5. 表示範囲
    extent_label = st.selectbox(
        "描画領域",
        options=list(EXTENT_PRESETS.keys()),
        index=0,
    )
    extent = EXTENT_PRESETS[extent_label]

    # 6. 解像度 (DPI)
    dpi = st.select_slider(
        "出力解像度 (DPI)",
        options=[120, 150, 200],
        value=150,
    )

    run_btn = st.button("天気図を作成", type="primary", use_container_width=True)


# ==============================================================================
# キャッシュ付き作図関数（PNGバイナリを返却してメモリを即時解放）
# ==============================================================================
@st.cache_data(ttl=3600, max_entries=16, show_spinner=False)
def render_gsm_png_bytes(
    dt_str: str,
    fcst_hours: int,
    season: str,
    extent: tuple[float, float, float, float],
    dpi: int,
) -> bytes:
    """GSM天気図を生成し、PNGのバイト列として返す（Figureは即時クローズ）。"""
    fig = gsm.plot_gsm_snow_chart(
        dt_str=dt_str,
        fcst_hours=fcst_hours,
        season=season,
        extent=extent,
        save_path=None,
        return_fig=True,
    )
    if fig is None:
        raise RuntimeError("天気図の生成に失敗しました。")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    gc.collect()
    buf.seek(0)
    return buf.getvalue()


# ==============================================================================
# メイン表示エリア
# ==============================================================================
dt_str = f"{init_date.strftime('%Y%m%d')}{init_hour}"
init_dt = dt.datetime.strptime(dt_str, "%Y%m%d%H")
valid_dt = init_dt + dt.timedelta(hours=fcst_hours)

if run_btn or "gsm_last_params" not in st.session_state:
    st.session_state["gsm_last_params"] = (dt_str, fcst_hours, season, extent, dpi)

req_dt_str, req_ft, req_season, req_extent, req_dpi = st.session_state["gsm_last_params"]
req_init_dt = dt.datetime.strptime(req_dt_str, "%Y%m%d%H")
req_valid_dt = req_init_dt + dt.timedelta(hours=req_ft)

try:
    with st.spinner(f"GSMデータを取得・作図中... ({req_init_dt.strftime('%Y/%m/%d %H')}UTC + {req_ft}h)"):
        png_bytes = render_gsm_png_bytes(
            dt_str=req_dt_str,
            fcst_hours=req_ft,
            season=req_season,
            extent=req_extent,
            dpi=req_dpi,
        )

    col_img, col_info = st.columns([3, 1])

    with col_img:
        st.image(
            png_bytes,
            caption=f"Initial: {req_init_dt.strftime('%Y/%m/%d %H')} UTC / Valid: {req_valid_dt.strftime('%Y/%m/%d %H')} UTC (FT+{req_ft}h)",
            use_container_width=True,
        )

    with col_info:
        st.subheader("出力情報")
        st.markdown(
            f"""
            - **初期時刻**: `{req_init_dt.strftime('%Y-%m-%d %H:00')} UTC`
            - **対象時刻**: `{req_valid_dt.strftime('%Y-%m-%d %H:00')} UTC`
            - **予報時間**: `FT+{req_ft}h`
            - **雪目安線 (500hPa)**: `-36°C` (紫) / `-30°C` (青)
            - **雪目安線 (850hPa)**: `-12°C` (紫) / `-6°C` (青)
            """
        )

        file_name = (
            f"gsm_ini{req_dt_str}_ft{req_ft:03d}_"
            f"valid{req_valid_dt.strftime('%Y%m%d%H')}.png"
        )
        st.download_button(
            label="PNG画像をダウンロード",
            data=png_bytes,
            file_name=file_name,
            mime="image/png",
            use_container_width=True,
        )

except Exception as e:
    st.error(f"データの取得または作図中にエラーが発生しました:\n{e}")
    st.info("※ 最新の初期時刻はRISHアーカイブへの反映まで数時間のタイムラグがあります。1〜2つ前の初期時刻をお試しください。")