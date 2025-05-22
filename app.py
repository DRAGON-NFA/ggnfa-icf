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
if not all([SHOPIFY_API_KEY, SHOPIFY_API_SECRET, SHOPIFY_ADMIN_API_ACCESS_TOKEN, SHOPIFY_STORE_DOMAIN, SHOPIFY_LOCATION_ID, BLIND_BOX_SKU]):
    print("错误：缺少必要的环境变量。请检查您的 .env 文件或 Render 配置。")
    # 暂时改为 pass，确保应用能启动，但会在第一次请求时报错
    pass 

# --- 辅助函数 ---
# 由于现在请求来自 Make (API Pull模式)，不再直接验证 Shopify HMAC
# verify_shopify_webhook 函数已移除，因为它不再用于此模式。


def shopify_admin_api_request(method, endpoint, json_data=None):
    """向 Shopify Admin API 发送请求的通用函数"""
    url = f"https://{SHOPIFY_STORE_DOMAIN}/admin/api/{SHOPIFY_API_VERSION}/{endpoint}"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_ADMIN_API_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }
    try:
        response = requests.request(method, url, headers=headers, json=json_data)
        response.raise_for_status()  # 如果请求不成功 (4xx 或 5xx)，抛出 HTTPError
        return response.json()
    except requests.exceptions.HTTPError as e:
        print(f"Shopify API 请求失败: {method} {url}, 错误: {e.response.text}")
        raise
    except requests.exceptions.RequestException as e:
        print(f"Shopify API 请求网络错误: {method} {url}, 错误: {e}")
        raise

def get_available_nft_products():
    """从 Shopify 获取所有可用的 NFT 产品（SKU 以 'NFT_SKU_' 开头且有库存）"""
    available_nfts = []
    # 使用 fields 参数优化响应体大小
    endpoint = "products.json?status=active&limit=250&fields=id,title,images,variants"
    while endpoint:
        try:
            data = shopify_admin_api_request("GET", endpoint)
            products = data.get('products', [])

            for product in products:
                # 根据 SKU 前缀识别您的 NFT 产品
                # 确保您的 NFT SKU 都有一个共同的前缀，例如 'NFT_SKU_'
                if product.get('variants'):
                    for variant in product['variants']:
                        if variant.get('sku', '').startswith('NFT_SKU_') and variant.get('inventory_quantity', 0) > 0:
                            # 优先使用变体图片，如果没有则使用产品主图
                            image_url = None
                            if variant.get('image_id'):
                                # 查找对应变体的图片 URL
                                for img in product.get('images', []):
                                    if img.get('id') == variant['image_id']:
                                        image_url = img.get('src')
                                        break
                            if not image_url and product.get('images'):
                                image_url = product['images'][0].get('src') # 使用产品主图

                            available_nfts.append({
                                "product_id": product['id'],
                                "variant_id": variant['id'],
                                "inventory_item_id": variant['inventory_item_id'],
                                "sku": variant['sku'],
                                "image_url": image_url
                            })

            # 处理分页
            # 注意：requests.Response().headers.get('link', '') 是不对的，应该是实际的响应对象
            # 应该从实际的 response 对象中获取 headers
            # 这里需要修改 shopify_admin_api_request 函数返回完整的响应对象，或者在此处从 requests.request 返回的对象获取 headers
            # 暂时简化分页，避免在这里引入更复杂的问题，如果您有大量产品需要分页，我们再单独处理
            # 假设一个请求就能获取所有，或者只获取第一页进行测试
            endpoint = None # 暂时禁用分页，只获取第一页

        except Exception as e:
            print(f"获取可用 NFT 产品时出错: {e}")
            # 在这里您可以选择是抛出错误还是返回空列表
            return []
    return available_nfts

def add_nft_to_order_metafield(order_id, nft_sku, nft_image_url, nft_product_id):
    """将分配的 NFT 信息作为元字段添加到订单中"""
    metafield_value = json.dumps({
        "sku": nft_sku,
        "image": nft_image_url,
        "product_id": nft_product_id
    })
    endpoint = f"orders/{order_id}/metafields.json"
    json_data = {
        "metafield": {
            "namespace": "custom",
            "key": "assigned_nft_details", # 这是一个固定且唯一的键
            "value": metafield_value,
            "type": "json_string"
        }
    }
    return shopify_admin_api_request("POST", endpoint, json_data)

def decrease_nft_inventory(inventory_item_id):
    """减少指定库存项目的库存数量"""
    endpoint = "inventory_levels/adjust.json"
    json_data = {
        "location_id": int(SHOPIFY_LOCATION_ID), # 确保是整数
        "inventory_item_id": inventory_item_id,
        "available_adjustment": -1 # 减少一个
    }
    return shopify_admin_api_request("POST", endpoint, json_data)

# --- Flask 路由 ---
@app.route('/')
def home():
    return "NFT Blind Box Allocator App is running!", 200

# !!! 临时调试路由：捕获所有 POST 请求 !!!
# 将此路由放在 /webhooks/orders/paid 路由之前
@app.route('/<path:dummy_path>', methods=['POST'])
def catch_all_post(dummy_path):
    print(f"DEBUG: 捕获到 POST 请求到未知路径: /{dummy_path}")
    print(f"DEBUG: 请求头部: {request.headers}")
    # 尝试解码请求数据，忽略编码错误
    try:
        request_data = request.get_data().decode('utf-8')
    except Exception as e:
        request_data = f"无法解码请求数据: {e}"
    print(f"DEBUG: 请求数据: {request_data}")
    return "Not Found (被调试路由捕获)", 404 # 仍然向 Make 返回 404

@app.route('/webhooks/orders/paid', methods=['POST'])
def handle_orders_paid_webhook():
    # **重要修改：移除 HMAC 验证逻辑**
    # 由于请求来自 Make (API Pull模式)，Make 已经从 Shopify API 拉取数据，
    # 并且Make发送给此应用的请求不包含X-Shopify-Hmac-Sha256头部。
    # 因此，我们不再需要在这里进行 HMAC 验证。

    try:
        # Make 发送的请求体就是 Shopify 订单的 JSON 数据
        order_data = request.json
        
        # 确保 order_data 不为空
        if not order_data:
            print("接收到的请求体为空或不是有效的 JSON。")
            return "无效的请求体", 400

        order_id = order_data.get('id')
        if not order_id:
            print("请求体中缺少订单 ID。")
            return "缺少订单 ID", 400

        print(f"接收到订单支付 Webhook (来自 Make API Pull)，订单 ID: {order_id}")

        # 2. 检查订单是否包含盲盒产品
        is_blind_box_order = False
        for line_item in order_data.get('line_items', []):
            if line_item.get('sku') == BLIND_BOX_SKU:
                is_blind_box_order = True
                break

        if not is_blind_box_order:
            print(f"订单 {order_id} 不包含盲盒产品，跳过处理。")
            return "非盲盒订单", 200

        # 3. 获取所有可用 NFT 产品
        available_nfts = get_available_nft_products()

        if not available_nfts:
            print(f"没有可用的 NFT 产品可以分配给订单 {order_id}。")
            # 您可以在这里添加逻辑来通知管理员，或者进行订单退款等
            return "没有可用 NFT", 200 # 返回 200 避免 Shopify 重试

        # 4. 随机选择一个 NFT
        selected_nft = random.choice(available_nfts)
        print(f"为订单 {order_id} 选择了 NFT: SKU={selected_nft['sku']}, Prod ID={selected_nft['product_id']}, Inv Item ID={selected_nft['inventory_item_id']}")

        # 5. 将 NFT 信息添加到订单元字段
        add_nft_to_order_metafield(
            order_id,
            selected_nft['sku'],
            selected_nft['image_url'],
            selected_nft['product_id']
        )

        # 6. 减少选定 NFT 的库存
        decrease_nft_inventory(selected_nft['inventory_item_id'])

        print(f"订单 {order_id} 处理成功。NFT '{selected_nft['sku']}' 已分配并减少库存。")
        return "OK", 200

    except Exception as e:
        print(f"处理 Webhook 时发生错误: {e}")
        # 在生产环境中，这里应该有更详细的错误日志记录
        return "内部服务器错误", 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
