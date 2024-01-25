import streamlit as st
from PIL import Image
import pandas as pd
import sqlite3
import os
from streamlit_folium import folium_static
import folium
import requests
import urllib3
import urllib.parse

# Googlespreadsheetから情報を取得
import streamlit as st
from google.oauth2 import service_account
import gspread
import pandas as pd

scopes = [ 'https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'
]
credentials = service_account.Credentials.from_service_account_file( "tech0-step3_1_1-suumo-jsonkey.json", scopes=scopes
)
gc = gspread.authorize(credentials)

SP_SHEET_KEY = "1rRtCz79tHmcBlmRGqbQDgwxgA_P8822bFhcb-k6MxQs"  # スプレッドシートのキー
sh = gc.open_by_key(SP_SHEET_KEY)
SP_SHEET = "20240125" # シート名「シート1」を指定

worksheet = sh.worksheet(SP_SHEET)
data = worksheet.get_all_values() # シート内の全データを取得
df = pd.DataFrame(data[1:], columns=data[0]) # 取得したデータをデータフレームに変換

# 国土地理院のAPIを利用して緯度と経度を取得する関数
def get_coordinates(address):
    response = requests.get(f"https://msearch.gsi.go.jp/address-search/AddressSearch?q={urllib.parse.quote(address)}")
    if response.json():
        lon, lat = response.json()[0]["geometry"]["coordinates"]
        return [lat, lon]
    else:
        return [None, None]

def filter_data(df, rent_min, rent_max, layout, no_deposit, no_key_money):
    # rent_min と rent_max を整数型に変換
    rent_min = int(rent_min)
    rent_max = int(rent_max)
    # 家賃でフィルタリング
    df["家賃_正規化"] = df["家賃_正規化"].astype(int)
    df = df[df["家賃_正規化"].between(rent_min, rent_max)]
    # 間取りでフィルタリング
    df = df[df["間取り"].isin(layout)]
    # 敷金のフィルタリング
    if no_deposit:
        df = df[df["敷金_正規化"] == 0]
    # 礼金のフィルタリング
    if no_key_money:
        df = df[df["礼金_正規化"] == 0]
    return df

# 東京23区のリスト
wards_of_tokyo = ["足立区", "荒川区", "板橋区", "江戸川区", "大田区", "葛飾区", "北区", "江東区",
                    "品川区", "渋谷区", "新宿区", "杉並区", "墨田区", "世田谷区", "台東区", "中央区",
                    "千代田区", "豊島区", "中野区", "練馬区", "目黒区", "文京区", "港区"]

def main():
    st.set_page_config(
        page_title="TOKYO不動産検索",
        menu_items={
            'About': """
            # 不動産検索アプリ
            このアプリは物件情報から重複物件を省いて表示されます。必要最低限の情報のみ掲載するアプリです。
            """
        })
    st.title('TOKYO不動産検索')
    st.write('東京都23区の不動産を重複なく検索できます！')

    # サイドバーの設定
    st.sidebar.title("検索条件")

    # サイドバーで東京23区を選択
    selected_wards = st.sidebar.multiselect('希望のエリアを選択', wards_of_tokyo)

    # サイドバーで家賃を選択
    rent_range = st.sidebar.slider('家賃の範囲（円）', 0, 500000, (0, 150000), 10000)

    # サイドバーで敷金・礼金の有無の選択
    no_deposit = st.sidebar.checkbox('敷金なし')
    no_key_money = st.sidebar.checkbox('礼金なし')

    layout = st.sidebar.multiselect('間取り', df['間取り'].unique())

    # 検索ボタン
    if st.sidebar.button('検索') or 'filtered_df' not in st.session_state:
        # 選択された区に基づいてデータをフィルタリング
        if selected_wards:
            df_filtered_by_wards = df[df['エリア'].str.contains('|'.join(selected_wards))]
        else:
            df_filtered_by_wards = df

        # その他のフィルターを適用
        rent_min, rent_max = rent_range  # rent_range を展開
        filtered_df = filter_data(df_filtered_by_wards, rent_min, rent_max, layout, no_deposit, no_key_money)


        # フィルタリングされたデータフレームのインデックスに名前を設定
        filtered_df.index.name = '物件No.'

        # フィルタリングされたデータフレームをsession_stateに保存
        st.session_state['filtered_df'] = filtered_df

    if 'filtered_df' in st.session_state:
        # セッション状態からフィルタリングされたデータフレームを取得
        filtered_df = st.session_state['filtered_df']

        # フィルタリングされた物件数を表示
        filtered_count = len(filtered_df)
        st.write(f"条件に合った物件数: {filtered_count}")
        st.dataframe(filtered_df.reset_index()[['物件No.', '建物名', '間取り', '家賃', '敷金', '礼金', 'エリア', 'URL']], width=1500, height=500)

        # 住所のカラムにジオコーディングを適用
        filtered_df['Coordinates'] = filtered_df['エリア'].apply(get_coordinates)

        # フィルタリングされた物件の座標の平均を計算
        valid_coords = filtered_df['Coordinates'].dropna()
        if len(valid_coords) > 0:
            average_lat = valid_coords.apply(lambda x: x[0]).mean()
            average_lon = valid_coords.apply(lambda x: x[1]).mean()
            map_center = [average_lat, average_lon]
        else:
            # 有効な座標がない場合、デフォルトの中心座標を使用
            map_center = [35.6895, 139.6917]

        # 地図の初期化（平均座標を中心として）
        m = folium.Map(
            location=map_center,
            zoom_start=12
            )

        # 各座標にマーカーをプロットし、物件名をポップアップで表示
        for _, row in filtered_df.iterrows():
            coord = row['Coordinates']
            if coord[0] is not None and coord[1] is not None:

                folium.Circle(
                location=coord,
                radius=200,
                color='#028DA0',
                fill=True,
                fill_color='#028DA0'
                ).add_to(m)

                folium.Marker(
                    location=coord,
                    popup=row['物件名'],
                ).add_to(m)

        # Streamlitアプリに地図を表示
        folium_static(m)

if __name__ == '__main__':
    main()