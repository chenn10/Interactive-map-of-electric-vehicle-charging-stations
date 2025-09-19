import requests
import pandas as pd
import dash
from dash import Dash, dcc, html
from dash.dependencies import Input, Output
import plotly.express as px
from cachetools import TTLCache
import time
import logging

# 設置緩存
cache = TTLCache(maxsize=100, ttl=600)
logging.basicConfig(level=logging.INFO)

# TDX API 資訊
app_id = '111b01501-f2489520-a640-4d14'
app_key = 'e3817bcd-2eef-49d7-a6c7-8155f487bd08'
auth_url = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"

# 每個城市的對應 API URL
city_urls = {
    "台北市": "https://tdx.transportdata.tw/api/basic/v1/EV/ChargingPoint/City/Taipei?$top=30&$format=JSON",
    "新北市": "https://tdx.transportdata.tw/api/basic/v1/EV/ChargingPoint/City/NewTaipei?$top=30&$format=JSON",
    "桃園市": "https://tdx.transportdata.tw/api/basic/v1/EV/ChargingPoint/City/Taoyuan?$top=30&$format=JSON",
    "台中市": "https://tdx.transportdata.tw/api/basic/v1/EV/ChargingPoint/City/Taichung?$top=30&$format=JSON",
    "台南市": "https://tdx.transportdata.tw/api/basic/v1/EV/ChargingPoint/City/Tainan?$top=30&$format=JSON",
    "高雄市": "https://tdx.transportdata.tw/api/basic/v1/EV/ChargingPoint/City/Kaohsiung?$top=30&$format=JSON"
}

# 縣市座標資料
city_locations = pd.DataFrame({
    "城市": list(city_urls.keys()),
    "lat": [25.0330, 25.0169, 24.9937, 24.1477, 22.9999, 22.6273],
    "lon": [121.5654, 121.4628, 121.2969, 120.6736, 120.2270, 120.3014]
})

# 獲取認證令牌
def get_access_token():
    try:
        if "access_token" in cache:
            return cache["access_token"]

        response = requests.post(auth_url, data={
            'grant_type': 'client_credentials',
            'client_id': app_id,
            'client_secret': app_key
        })
        response.raise_for_status()
        token = response.json().get('access_token')
        cache["access_token"] = token
        return token
    except Exception as e:
        logging.error(f"Error fetching access token: {e}")
        return None

# 獲取特定城市的充電站數據，加入重試機制
def fetch_city_data(city):
    try:
        url = city_urls.get(city)
        if not url:
            logging.error(f"{city} 無對應的 API URL")
            return []

        if city in cache:
            return cache[city]

        for attempt in range(3):  # 最多重試3次
            token = get_access_token()
            if not token:
                logging.error("無法獲取 Access Token")
                return []

            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json().get('ChargingPoints', [])
                if not data:
                    logging.warning(f"API 返回 {city} 的數據為空")
                cache[city] = data
                return data
            else:
                logging.warning(f"Fetching data for {city} failed. Attempt {attempt + 1}/3")
                time.sleep(2)  # 等待2秒後重試

        logging.error(f"Failed to fetch data for {city} after 3 attempts")
        return []
    except Exception as e:
        logging.error(f"Error fetching data for {city}: {e}")
        return []

# 初始化 Dash 應用
app = Dash(__name__)

# 頁面佈局
app.layout = html.Div([
    html.H1("台灣電動車充電站地圖", style={'textAlign': 'center', 'color': 'white', 'backgroundColor': 'black'}),
    html.Div([
        dcc.Graph(id='map', style={'height': '600px', 'backgroundColor': 'black'}),  # 地圖
        # 彈窗容器
        html.Div([
            html.Div([
                html.Button('×', id='close-modal', n_clicks=0, 
                           style={'position': 'absolute', 'top': '10px', 'right': '15px', 
                                  'background': 'none', 'border': 'none', 'fontSize': '24px', 
                                  'color': 'white', 'cursor': 'pointer', 'zIndex': '1001'}),
                html.Div(id='modal-content', style={'padding': '0'})
            ], style={
                'position': 'relative',
                'backgroundColor': 'black',
                'borderRadius': '10px',
                'boxShadow': '0 4px 20px rgba(0,0,0,0.5)',
                'maxWidth': '800px',
                'maxHeight': '600px',
                'margin': 'auto',
                'overflow': 'auto'
            })
        ], id='modal', style={
            'display': 'none',
            'position': 'fixed',
            'top': '0',
            'left': '0',
            'width': '100%',
            'height': '100%',
            'backgroundColor': 'rgba(0,0,0,0.8)',
            'zIndex': '1000',
            'alignItems': 'center',
            'justifyContent': 'center',
            'transition': 'opacity 0.3s ease'
        })
    ], style={'position': 'relative'}),
    html.Div(id='info', style={'padding': '20px', 'backgroundColor': 'black', 'color': 'white'})  # 顯示點選的充電站資訊
], style={'backgroundColor': 'black', 'minHeight': '100vh'})

# 定義地圖初始狀態
@app.callback(
    Output('map', 'figure'),
    Input('map', 'clickData')
)
def update_map(click_data):
    fig = px.scatter_mapbox(
        city_locations,
        lat="lat", lon="lon", hover_name="城市",
        zoom=7, height=600, center={"lat": 23.7, "lon": 121},  # 固定中心在台灣
        size=[20]*len(city_locations)  # 擴大點擊範圍
    )
    fig.update_layout(mapbox_style="open-street-map")  # 使用免費地圖樣式
    fig.update_layout(margin={"r": 0, "t": 0, "l": 0, "b": 0})
    return fig

# 彈窗顯示圓餅圖
@app.callback(
    [Output('modal', 'style'),
     Output('modal-content', 'children')],
    [Input('map', 'clickData'),
     Input('close-modal', 'n_clicks')]
)
def toggle_modal(click_data, close_clicks):
    ctx = dash.callback_context
    
    if not ctx.triggered:
        return {'display': 'none'}, None
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # 如果點擊關閉按鈕，隱藏彈窗
    if trigger_id == 'close-modal':
        return {
            'display': 'none',
            'position': 'fixed',
            'top': '0',
            'left': '0',
            'width': '100%',
            'height': '100%',
            'backgroundColor': 'rgba(0,0,0,0.8)',
            'zIndex': '1000',
            'alignItems': 'center',
            'justifyContent': 'center',
            'transition': 'opacity 0.3s ease'
        }, None
    
    # 如果點擊地圖上的城市，顯示彈窗
    elif trigger_id == 'map' and click_data:
        try:
            selected_city = click_data['points'][0]['hovertext']
            charging_data = fetch_city_data(selected_city)
            
            if not charging_data:
                modal_content = html.Div([
                    html.H3(f"{selected_city}", style={'color': 'white', 'textAlign': 'center'}),
                    html.P("無充電站數據", style={'color': 'white', 'textAlign': 'center', 'fontSize': '18px'})
                ])
            else:
                df = pd.DataFrame(charging_data)
                if 'StationID' not in df.columns or 'ChargingRate' not in df.columns:
                    modal_content = html.Div([
                        html.H3(f"{selected_city}", style={'color': 'white', 'textAlign': 'center'}),
                        html.P("充電站數據無法解析", style={'color': 'white', 'textAlign': 'center', 'fontSize': '18px'})
                    ])
                else:
                    # 固定圖例字數
                    df['ChargingRate'] = df['ChargingRate'].str.slice(0, 15) + '...'
                    
                    # 創建圓餅圖
                    pie_chart = dcc.Graph(figure=px.pie(
                        df,
                        names="ChargingRate",
                        title=f"{selected_city} 充電站計費方式分布",
                        color_discrete_sequence=px.colors.qualitative.Set1
                    ).update_layout(
                        plot_bgcolor='black',
                        paper_bgcolor='black',
                        font_color='white',
                        title_font_color='white',
                        height=500,
                        transition_duration=500  # 添加過渡動畫
                    ))
                    
                    modal_content = pie_chart
            
            return {
                'display': 'flex',
                'position': 'fixed',
                'top': '0',
                'left': '0',
                'width': '100%',
                'height': '100%',
                'backgroundColor': 'rgba(0,0,0,0.8)',
                'zIndex': '1000',
                'alignItems': 'center',
                'justifyContent': 'center',
                'transition': 'opacity 0.3s ease'
            }, modal_content
            
        except Exception as e:
            logging.error(f"Error processing data for {click_data}: {e}")
            return {'display': 'none'}, None
    
    return {'display': 'none'}, None

# 點擊地圖更新底部資訊
@app.callback(
    Output('info', 'children'),
    Input('map', 'clickData')
)
def display_city_info(click_data):
    if click_data:
        try:
            selected_city = click_data['points'][0]['hovertext']  # 點選的城市名稱
            charging_data = fetch_city_data(selected_city)
            if not charging_data:
                return html.P(f"{selected_city} 無充電站數據", style={'color': 'white'})

            # 生成數據表格
            df = pd.DataFrame(charging_data)
            if 'StationID' not in df.columns or 'ChargingRate' not in df.columns:
                return html.P(f"{selected_city} 的充電站數據無法解析", style={'color': 'white'})

            # 顯示基本統計資訊
            total_stations = len(df)
            unique_rates = df['ChargingRate'].nunique()
            
            return html.Div([
                html.H3(f"{selected_city} 充電站統計", style={'color': 'white'}),
                html.P(f"總充電站數量: {total_stations}", style={'color': 'white', 'fontSize': '16px'}),
                html.P(f"不同計費方式: {unique_rates} 種", style={'color': 'white', 'fontSize': '16px'}),
                html.P("點擊上方地圖查看詳細分布圖表", style={'color': 'lightgray', 'fontSize': '14px', 'fontStyle': 'italic'})
            ])
        except Exception as e:
            logging.error(f"Error processing data for {click_data}: {e}")
            return html.P("發生錯誤，無法顯示數據", style={'color': 'white'})
    return html.P("請點選地圖上的城市查看充電站資訊", style={'color': 'white', 'textAlign': 'center', 'fontSize': '18px'})

if __name__ == '__main__':
    app.run(debug=True)
