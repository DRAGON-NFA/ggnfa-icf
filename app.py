import os
import json
import random
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# 加载环境变量（仅用于本地开发和测试）
load_dotenv()

app = Flask(__name__)

# --- 配置信息 ---
SHOPIFY_API_KEY = os.getenv('SHOPIFY_API_KEY')
SHOPIFY_API_SECRET = os.getenv('SHOPIFY_API_SECRET')
SHOPIFY_ADMIN_API_ACCESS_TOKEN = os.getenv('SHOPIFY_ADMIN_API_ACCESS_TOKEN')
SHOPIFY_STORE_DOMAIN = os.getenv('SHOPIFY_STORE_DOMAIN')
SHOPIFY_LOCATION_ID = os.getenv('SHOPIFY_LOCATION_ID')
BLIND_BOX_SKU = os.getenv('BLIND_BOX_SKU', 'BLINDBOX') # 默认值，但建议在环境变量中明确设置
SHOPIFY_API_VERSION = '2024-04' # 使用最新的稳定 API 版本

# 确保所有必要的环境变量都已加载
if not all([SHOPIFY_API_KEY, SHOPIFY_API_SECRET, SHOPIFY_ADMIN_API_ACCESS_TOKEN, SHOPIFY_STORE_DOMAIN, SHOPIFY_LOCATION_ID, BLIND_BOX_SKU])
    print 错误 缺少必要的环境变量。请检查您的 .env 文件或 Render 配置.
    # 暂时改为 pass，确保应用能启动，但会在第一次请求时报错
    pass

# !!! 调试语句：打印盲盒 Webhook 路由的 repr() 表示 !!!
# 这会帮助我们发现潜在的不可见字符
print(fDEBUG 预期盲盒 Webhook 路由的 repr() {repr('webhooksorderspaid')})


# --- 辅助函数 ---
def shopify_admin_api_request(method, endpoint, json_data=None)
    向 Shopify Admin API 发送请求的通用函数
    url = fhttps{SHOPIFY_STORE_DOMAIN}adminapi{SHOPIFY_API_VERSION}{endpoint}
    headers = {
        X-Shopify-Access-Token SHOPIFY_ADMIN_API_ACCESS_TOKEN,
        Content-Type applicationjson
    }
    try
        response = requests.request(method, url, headers=headers, json=json_data)
        response.raise_for_status()  # 如果请求不成功 (4xx 或 5xx)，抛出 HTTPError
        return response.json()
    except requests.exceptions.HTTPError as e
        print(fShopify API 请求失败 {method} {url}, 错误 {e.response.text})
        raise
    except requests.exceptions.RequestException as e
        print(fShopify API 请求网络错误 {method} {url}, 错误 {e})
        raise

def get_available_nft_products()
    从 Shopify 获取所有可用的 NFT 产品SKU 以 'NFT_SKU_' 开头且有库存
    available_nfts = []
    endpoint = products.jsonstatus=active&limit=250&fields=id,title,images,variants
    while endpoint
        try
            data = shopify_admin_api_request(GET, endpoint)
            products = data.get('products', [])

            for product in products
                if product.get('variants')
                    for variant in product['variants']
                        if variant.get('sku', '').startswith('NFT_SKU_') and variant.get('inventory_quantity', 0)  0
                            image_url = None
                            if variant.get('image_id')
                                for img in product.get('images', [])
                                    if img.get('id') == variant['image_id']
                                        image_url = img.get('src')
                                        break
                            if not image_url and product.get('images')
                                image_url = product['images'][0].get('src')

                            available_nfts.append({
                                product_id product['id'],
                                variant_id variant['id'],
                                inventory_item_id variant['inventory_item_id'],
                                sku variant['sku'],
                                image_url image_url
                            })

            endpoint = None # 暂时禁用分页，只获取第一页

        except Exception as e
            print(f获取可用 NFT 产品时出错 {e})
            return []
    return available_nfts

def add_nft_to_order_metafield(order_id, nft_sku, nft_image_url, nft_product_id)
    将分配的 NFT 信息作为元字段添加到订单中
    metafield_value = json.dumps({
        sku nft_sku,
        image nft_image_url,
        product_id nft_product_id
    })
    endpoint = forders{order_id}metafields.json
    json_data = {
        metafield {
            namespace custom,
            key assigned_nft_details,
            value metafield_value,
            type json_string
        }
    }
    return shopify_admin_api_request(POST, endpoint, json_data)

def decrease_nft_inventory(inventory_item_id)
    减少指定库存项目的库存数量
    endpoint = inventory_levelsadjust.json
    json_data = {
        location_id int(SHOPIFY_LOCATION_ID),
        inventory_item_id inventory_item_id,
        available_adjustment -1
    }
    return shopify_admin_api_request(POST, endpoint, json_data)

# --- Flask 路由 ---
@app.route('')
def home()
    return NFT Blind Box Allocator App is running!, 200

# !!! 临时调试路由：捕获所有 POST 请求 !!!
# 确保此路由在 webhooksorderspaid 路由之前定义，这样如果精确匹配失败，它能捕获到请求。
@app.route('pathdummy_path', methods=['POST'])
def catch_all_post(dummy_path)
    print(fDEBUG 捕获到 POST 请求到未知路径 {dummy_path})
    print(fDEBUG 请求头部 {request.headers})
    try
        request_data = request.json
        print(fDEBUG JSON Data (捕获) {request_data})
    except Exception as e
        request_data = request.get_data().decode('utf-8', errors='ignore')
        print(fDEBUG Raw Data (捕获) {request_data})
    return Not Found (被调试路由捕获), 404 # 仍然向 Make 返回 404

@app.route('webhooksorderspaid', methods=['POST'])
def handle_orders_paid_webhook()
    try
        order_data = request.json

        if not order_data
            print(接收到的请求体为空或不是有效的 JSON。)
            return 无效的请求体, 400

        order_id = order_data.get('id')
        if not order_id
            print(请求体中缺少订单 ID。)
            return 缺少订单 ID, 400

        print(f接收到订单支付 Webhook (来自 Make API Pull)，订单 ID {order_id})

        is_blind_box_order = False
        for line_item in order_data.get('line_items', [])
            if line_item.get('sku') == BLIND_BOX_SKU
                is_blind_box_order = True
                break

        if not is_blind_box_order
            print(f订单 {order_id} 不包含盲盒产品，跳过处理。)
            return 非盲盒订单, 200

        available_nfts = get_available_nft_products()

        if not available_nfts
            print(f没有可用的 NFT 产品可以分配给订单 {order_id}。)
            return 没有可用 NFT, 200

        selected_nft = random.choice(available_nfts)
        print(f为订单 {order_id} 选择了 NFT SKU={selected_nft['sku']}, Prod ID={selected_nft['product_id']}, Inv Item ID={selected_nft['inventory_item_id']})

        add_nft_to_order_metafield(
            order_id,
            selected_nft['sku'],
            selected_nft['image_url'],
            selected_nft['product_id']
        )

        decrease_nft_inventory(selected_nft['inventory_item_id'])

        print(f订单 {order_id} 处理成功。NFT '{selected_nft['sku']}' 已分配并减少库存。)
        return OK, 200

    except Exception as e
        print(f处理 Webhook 时发生错误 {e})
        return 内部服务器错误, 500

if __name__ == '__main__'
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)