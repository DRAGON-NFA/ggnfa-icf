import os
import json
import random
import hmac
import hashlib
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
    exit(1)

# --- 辅助函数 ---

def verify_shopify_webhook(data, hmac_header):
    """验证 Shopify Webhook 请求的 HMAC 签名"""
    if not hmac_header:
        print("Webhook 验证失败：缺少 X-Shopify-Hmac-Sha256 头部。")
        return False

    calculated_hmac = hmac.new(
        SHOPIFY_API_SECRET.encode('utf-8'),
        data,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calculated_hmac, hmac_header):
        print(f"Webhook 验证失败：HMAC 不匹配。计算的: {calculated_hmac}, 接收到的: {hmac_header}")
        return False
    return True

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
            link_header = requests.utils.parse_header_links(requests.Response().headers.get('link', ''))
            next_page_link = None
            for link in link_header:
                if link.get('rel') == 'next':
                    # 从完整的 URL 提取相对路径或新的 endpoint
                    # Shopify 分页链接通常是完整的 URL，这里需要提取出 'admin/api/...' 部分
                    next_page_link = link['url'].split(f"admin/api/{SHOPIFY_API_VERSION}/")[1]
                    break
            endpoint = next_page_link
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

@app.route('/webhooks/orders/paid', methods=['POST'])
def handle_orders_paid_webhook():
    # 1. 验证 Webhook 签名
    request_data = request.get_data()
    hmac_header = request.headers.get('X-Shopify-Hmac-Sha256')

    if not verify_shopify_webhook(request_data, hmac_header):
        return "Webhook 验证失败", 401

    try:
        order_data = request.json
        order_id = order_data.get('id')
        print(f"接收到订单支付 Webhook，订单 ID: {order_id}")

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
        return "内部服务器错误", 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)