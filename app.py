from __future__ import annotations

import datetime as dt
import gc
import io

import matplotlib.pyplot as plt
import streamlit as st

from meteo_lib import gsm_utils as gsm
from meteo_lib import msm_utils as msm

# ==============================================================================
# ページ設定
# ==============================================================================
st.set_page_config(
    page_title="JMA GSM / MSM 地上気圧・上空気温（雪目安）天気図",
    page_icon="❄️",
    layout="wide",
)

st.title("JMA GSM / MSM 地上気圧・上空気温（雪目安）天気図")
st.caption("京都大学生存圏研究所 (RISH) GPV アーカイブより取得・作図")

# ==============================================================================
# モデル別プリセット定義
# ==============================================================================
GSM_EXTENTS: dict[str, tuple[float, float, float, float]] = {
    "標準（日本付近: 117°E–156°E, 18°N–61°N）": (117.0, 156.0, 18.0, 61.0),
    "広域（極東・シベリア高気圧含む: 105°E–165°E, 15°N–65°N）": (105.0, 165.0, 15.0, 65.0),
    "北日本〜日本海中心（125°E–152°E, 30°N–52°N）": (125.0, 152.0, 30.0, 52.0),
}

MSM_EXTENTS: dict[str, tuple[float, float, float, float]] = {
    "日本全体（MSM標準: 122°E–148°E, 24°N–46.5°N）": (122.0, 148.0, 24.0, 46.5),
    "北日本〜日本海・JPCZ解析（127°E–146°E, 33°N–46°N）": (127.0, 146.0, 33.0, 46.0),
    "東北・北海道（135°E–146.5°E, 36°N–46°N）": (135.0, 146.5, 36.0, 46.0),
    "本州中部〜関東甲信・北陸（133°E–143°E, 32.5°N–40.5°N）": (133.0, 143.0, 32.5, 40.5),
    "西日本〜東シナ海（124°E–137°E, 29°N–38°N）": (124.0, 137.0, 29.0, 38.0),
}

# ==============================================================================
# サイドバー UI
# ==============================================================================
with st.sidebar:
    st.header("作図パラメータ設定")

    # 1. モデル選択
    model_choice = st.radio(
        "数値予報モデル",
        options=["GSM (全球 0.5° / 総観場)", "MSM (メソ 5km / 局地場)"],
        index=0,
    )
    model_type = "GSM" if model_choice.startswith("GSM") else "MSM"

    # 2. 初期日 (UTC)
    default_date = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)
    init_date = st.date_input(
        "初期日 (UTC)",
        value=default_date,
        min_value=dt.date(2018, 1, 1),
        max_value=dt.datetime.now(dt.timezone.utc).date(),
    )

    # 3. 初期時刻 (UTC) & 予報時間 (FT) のモデル別設定
    if model_type == "GSM":
        init_hour = st.radio(
            "初期時刻 (UTC)",
            options=["00", "06", "12", "18"],
            index=0,
            horizontal=True,
        )
        max_ft = 132 if init_hour in ("00", "12") else 84
        fcst_hours = st.slider(
            "予報時間 FT (時間)",
            min_value=0,
            max_value=max_ft,
            value=24,
            step=6,
        )
        extent_dict = GSM_EXTENTS
    else:
        init_hour = st.selectbox(
            "初期時刻 (UTC)",
            options=["00", "03", "06", "09", "12", "15", "18", "21"],
            index=0,
        )
        fcst_hours = st.slider(
            "予報時間 FT (時間)",
            min_value=0,
            max_value=78,
            value=24,
            step=3,
        )
        extent_dict = MSM_EXTENTS

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
        options=list(extent_dict.keys()),
        index=0,
    )
    extent = extent_dict[extent_label]

    # 6. 解像度 (DPI)
    dpi = st.select_slider(
        "出力解像度 (DPI)",
        options=[120, 150, 200],
        value=150,
    )

    run_btn = st.button("天気図を作成", type="primary", use_container_width=True)


# ==============================================================================
# キャッシュ付き作図関数（GSM / MSM 共通ラッパー）
# ==============================================================================
@st.cache_data(ttl=3600, max_entries=24, show_spinner=False)
def render_chart_png_bytes(
    model_type: str,
    dt_str: str,
    fcst_hours: int,
    season: str,
    extent: tuple[float, float, float, float],
    dpi: int,
) -> bytes:
    """指定モデル（GSM/MSM）の天気図を生成し、PNGのバイト列として返す。"""
    if model_type == "GSM":
        fig = gsm.plot_gsm_snow_chart(
            dt_str=dt_str,
            fcst_hours=fcst_hours,
            season=season,
            extent=extent,
            save_path=None,
            return_fig=True,
        )
    else:
        fig = msm.plot_msm_snow_chart(
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

if run_btn or "gpv_last_params" not in st.session_state:
    st.session_state["gpv_last_params"] = (model_type, dt_str, fcst_hours, season, extent, dpi)

req_model, req_dt_str, req_ft, req_season, req_extent, req_dpi = st.session_state["gpv_last_params"]
req_init_dt = dt.datetime.strptime(req_dt_str, "%Y%m%d%H")
req_valid_dt = req_init_dt + dt.timedelta(hours=req_ft)

try:
    with st.spinner(
        f"{req_model} データを取得・作図中... ({req_init_dt.strftime('%Y/%m/%d %H')}UTC + {req_ft}h)"
    ):
        png_bytes = render_chart_png_bytes(
            model_type=req_model,
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
            caption=(
                f"[{req_model}] Initial: {req_init_dt.strftime('%Y/%m/%d %H')} UTC / "
                f"Valid: {req_valid_dt.strftime('%Y/%m/%d %H')} UTC (FT+{req_ft}h)"
            ),
            use_container_width=True,
        )

    with col_info:
        st.subheader("出力情報")
        isobar_step = "4 hPa（太線 20 hPa）" if req_model == "GSM" else "2 hPa（太線 10 hPa）"
        proj_name = "ポーラーステレオ図法" if req_model == "GSM" else "ランベルト正角円錐図法"

        st.markdown(
            f"""
            - **使用モデル**: `{req_model}`
            - **投影図法**: {proj_name}
            - **初期時刻**: `{req_init_dt.strftime('%Y-%m-%d %H:00')} UTC`
            - **対象時刻**: `{req_valid_dt.strftime('%Y-%m-%d %H:00')} UTC`
            - **予報時間**: `FT+{req_ft}h`
            - **等圧線間隔**: {isobar_step}
            - **雪目安 (500hPa)**: `-36°C` (紫) / `-30°C` (青)
            - **雪目安 (850hPa)**: `-12°C` (紫) / `-6°C` (青)
            """
        )

        file_name = (
            f"{req_model.lower()}_ini{req_dt_str}_ft{req_ft:03d}_"
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
    st.info(
        "※ 最新の初期時刻はRISHアーカイブへの反映まで数時間のタイムラグがあります。"
        "また、MSMの長い予報時間（FT+40h以降）は00UTC・12UTC初期値のみ提供されている場合があります。"
    )