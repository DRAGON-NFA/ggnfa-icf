# app.py
import os
import sys
import logging
from flask import Flask, request, jsonify
import requests
import json
import random
from datetime import datetime

# 从新的 database.py 和 nft_data.py 导入
from database import init_db, get_unassigned_nft, record_assignment, check_order_assigned
from nft_data import NFT_ITEMS # 假设 NFT_ITEMS 定义在 nft_data.py 中

app = Flask(__name__)

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 从环境变量加载 Shopify API 凭证
SHOPIFY_API_KEY = os.getenv('SHOPIFY_API_KEY')
SHOPIFY_API_PASSWORD = os.getenv('SHOPIFY_API_PASSWORD')
SHOPIFY_SHOP_NAME = os.getenv('SHOPIFY_SHOP_NAME')
SHOPIFY_API_VERSION = os.getenv('SHOPIFY_API_VERSION', '2024-04') # 默认使用最新稳定版本

if not all([SHOPIFY_API_KEY, SHOPIFY_API_PASSWORD, SHOPIFY_SHOP_NAME]):
    logging.error("ERROR: Missing required environment variables. Please check your Render configuration.")
    sys.exit(1)

# 构建 Shopify Admin API 基础 URL
SHOPIFY_ADMIN_API_BASE_URL = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_API_PASSWORD}@{SHOPIFY_SHOP_NAME}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}"

# 在应用启动时初始化数据库
with app.app_context(): # 确保在Flask应用上下文中执行
    init_db(NFT_ITEMS)

@app.route('/')
def home():
    """简单的健康检查路由"""
    logging.info("Received GET request to /")
    return jsonify({"message": "NFT Blind Box Webhook Service is running!"}), 200

@app.route('/webhooks/orders/paid', methods=['POST'])
def orders_paid_webhook():
    """处理Shopify订单支付Webhook"""
    logging.info("Received POST request to /webhooks/orders/paid (Shopify Order Paid Webhook).")

    try:
        data = request.json
        if not data:
            logging.warning("Received empty or non-JSON request body.")
            return jsonify({"message": "Invalid JSON"}), 400

        order_id = data.get('id')
        customer_email = data.get('email')
        order_number = data.get('order_number')

        if not order_id:
            logging.error("Order ID not found in webhook data.")
            return jsonify({"message": "Order ID missing"}), 400

        logging.info(f"Processing order ID: {order_id}, Order Number: {order_number}, Customer email: {customer_email}")

        # 检查订单是否已经分配过NFT，避免重复处理
        if check_order_assigned(str(order_id)):
            logging.info(f"Order ID {order_id} already has an NFT assigned. Skipping re-assignment.")
            return jsonify({"message": "Order already processed"}), 200 # 返回成功，不重试

        # --- NFT 分配逻辑 ---
        assigned_nft = get_unassigned_nft() # 从数据库获取并标记一个未分配NFT

        if assigned_nft:
            nft_id = assigned_nft['nft_id']
            nft_image_url = assigned_nft['image_url']
            nft_name = assigned_nft['name']

            logging.info(f"Assigned NFT: {nft_id} (Image: {nft_image_url}, Name: {nft_name}) to Order {order_id}.")

            # --- 更新 Shopify 订单的 note_attributes ---
            # 这是为了在用户订单详情页显示分配的NFT信息
            order_update_url = f"{SHOPIFY_ADMIN_API_BASE_URL}/orders/{order_id}.json"
            headers = {"Content-Type": "application/json"}
            payload = {
                "order": {
                    "id": order_id,
                    "note_attributes": [
                        {"name": "Assigned_NFT_ID", "value": nft_id},
                        {"name": "Assigned_NFT_Name", "value": nft_name},
                        {"name": "Assigned_NFT_Image", "value": nft_image_url},
                        # 您可以添加更多信息，例如分配时间等
                        {"name": "NFT_Assignment_Date", "value": datetime.utcnow().isoformat()}
                    ]
                }
            }

            try:
                shopify_response = requests.put(order_update_url, headers=headers, data=json.dumps(payload))
                shopify_response.raise_for_status() # 如果状态码不是2xx，则抛出HTTPError
                logging.info(f"Successfully updated Shopify Order {order_id} with NFT details.")
                # 记录分配历史
                record_assignment(nft_id, nft_image_url, nft_name, str(order_id), customer_email)
                return jsonify({"message": "NFT assigned and order updated successfully!"}), 200

            except requests.exceptions.RequestException as e:
                logging.error(f"Failed to update Shopify Order {order_id}. Error: {e}")
                logging.error(f"Shopify API Response: {shopify_response.text if shopify_response else 'N/A'}")
                return jsonify({"message": "Failed to update Shopify order"}), 500 # 500 表示服务器内部错误

        else:
            logging.error("No unassigned NFTs available for distribution.")
            # 可以在这里触发警报，例如发送邮件给管理员
            return jsonify({"message": "No NFTs available"}), 503 # 503 Service Unavailable

    except Exception as e:
        logging.error(f"Error processing webhook: {e}", exc_info=True)
        return jsonify({"message": "Internal Server Error"}), 500

@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def catch_all(path):
    """
    捕获所有未匹配的请求，用于调试。
    """
    logging.debug(f"Catch-all route triggered for path: /{path}")
    logging.debug(f"Caught {request.method} request to unrecognized path: /{path}")
    logging.debug(f"Headers: {dict(request.headers)}")
    if request.is_json:
        try:
            logging.debug(f"JSON Data (捕获): {json.dumps(request.json, indent=2)}")
        except Exception as e:
            logging.debug(f"Could not parse JSON data: {e}")
            logging.debug(f"Raw Data: {request.get_data(as_text=True)}")
    else:
        logging.debug(f"Raw Data (捕获): {request.get_data(as_text=True)}")
    return jsonify({"message": f"Path /{path} not found or not handled by specific webhook. Check logs for details."}), 404

if __name__ == '__main__':
    # 仅在本地开发时运行，Render 会使用 gunicorn 启动
    app.run(debug=True, host='0.0.0.0', port=os.getenv('PORT', 5000))
