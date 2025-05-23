import os
import sys
import hmac
import hashlib
import base64
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import logging

# Load .env
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Flask app
app = Flask(__name__)

# Required env vars
REQUIRED_ENV_VARS = [
    "SHOPIFY_API_KEY", "SHOPIFY_API_PASSWORD", "SHOPIFY_SHOP_NAME", "SHOPIFY_WEBHOOK_SECRET"
]

if not all(os.environ.get(var) for var in REQUIRED_ENV_VARS):
    logging.error("Missing required environment variables.")
    sys.exit(1)

# Environment vars
SHOPIFY_API_KEY = os.environ["SHOPIFY_API_KEY"]
SHOPIFY_API_PASSWORD = os.environ["SHOPIFY_API_PASSWORD"]
SHOPIFY_SHOP_NAME = os.environ["SHOPIFY_SHOP_NAME"]
SHOPIFY_WEBHOOK_SECRET = os.environ["SHOPIFY_WEBHOOK_SECRET"]
SHOPIFY_API_VERSION = "2024-04"

# Shopify API Base URL
SHOPIFY_BASE_URL = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_API_PASSWORD}@{SHOPIFY_SHOP_NAME}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}"

# Global cache for default location ID
DEFAULT_LOCATION_ID = None


def verify_webhook(data, hmac_header):
    """Verify Shopify webhook HMAC"""
    digest = hmac.new(SHOPIFY_WEBHOOK_SECRET.encode("utf-8"), data, hashlib.sha256).digest()
    computed_hmac = base64.b64encode(digest).decode()
    return hmac.compare_digest(computed_hmac, hmac_header)


def get_default_location_id():
    """Fetch and cache default location ID."""
    global DEFAULT_LOCATION_ID
    if DEFAULT_LOCATION_ID:
        return DEFAULT_LOCATION_ID

    try:
        url = f"{SHOPIFY_BASE_URL}/locations.json"
        headers = {"Content-Type": "application/json"}
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        locations = res.json().get("locations", [])
        if locations:
            DEFAULT_LOCATION_ID = locations[0]["id"]
            return DEFAULT_LOCATION_ID
        logging.error("No locations found.")
        return None
    except Exception as e:
        logging.error(f"Error fetching locations: {e}")
        return None


def get_available_nft_products():
    """Fetch NFT variants with SKU prefix 'NFT_SKU_' and inventory > 0."""
    products_url = f"{SHOPIFY_BASE_URL}/products.json"
    headers = {"Content-Type": "application/json"}
    all_nft_products = []
    page_info = None

    while True:
        params = {"limit": 250}
        if page_info:
            params["page_info"] = page_info

        try:
            res = requests.get(products_url, headers=headers, params=params, timeout=10)
            res.raise_for_status()
            products = res.json().get("products", [])

            for product in products:
                for variant in product.get("variants", []):
                    if variant.get("sku", "").startswith("NFT_SKU_") and variant.get("inventory_quantity", 0) > 0:
                        all_nft_products.append({
                            "product_id": product["id"],
                            "product_title": product["title"],
                            "variant_id": variant["id"],
                            "variant_sku": variant["sku"],
                            "inventory_quantity": variant["inventory_quantity"],
                            "inventory_item_id": variant["inventory_item_id"]
                        })

            # Handle pagination
            link_header = res.headers.get("link")
            if link_header and 'rel="next"' in link_header:
                import re
                match = re.search(r'page_info=([^&>]+)', link_header)
                page_info = match.group(1) if match else None
            else:
                break
        except Exception as e:
            logging.error(f"Error fetching products: {e}")
            break

    logging.info(f"Found {len(all_nft_products)} available NFT products.")
    return all_nft_products


def update_shopify_inventory(inventory_item_id, new_quantity, location_id):
    """Update inventory quantity via Shopify API"""
    url = f"{SHOPIFY_BASE_URL}/inventory_levels/set.json"
    headers = {"Content-Type": "application/json"}
    payload = {
        "inventory_item_id": inventory_item_id,
        "location_id": location_id,
        "set_quantity": new_quantity
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        res.raise_for_status()
        logging.info(f"Inventory updated: {inventory_item_id} -> {new_quantity}")
        return True
    except Exception as e:
        logging.error(f"Failed to update inventory: {e}")
        return False


@app.route('/webhooks/orders/paid', methods=['POST'])
def order_paid_webhook():
    logging.info("Webhook triggered: /webhooks/orders/paid")

    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256")
    if not verify_webhook(request.data, hmac_header):
        logging.warning("Invalid webhook signature.")
        return jsonify({"message": "Unauthorized"}), 401

    data = request.get_json()
    if not data:
        return jsonify({"message": "Invalid payload"}), 400

    order_id = data.get("id")
    email = data.get("email")
    logging.info(f"Processing order: {order_id} for {email}")

    available_nfts = get_available_nft_products()
    if not available_nfts:
        return jsonify({"message": "No NFT products available"}), 200

    assigned_nft = available_nfts[0]
    new_quantity = assigned_nft["inventory_quantity"] - 1

    location_id = get_default_location_id()
    if not location_id:
        return jsonify({"message": "No location found"}), 500

    if not update_shopify_inventory(assigned_nft["inventory_item_id"], new_quantity, location_id):
        return jsonify({"message": "Failed to update inventory"}), 500

    # Simulated NFT minting
    logging.info(f"Simulate mint NFT for {email} with SKU {assigned_nft['variant_sku']}")

    return jsonify({
        "message": "NFT assigned",
        "assigned_nft_sku": assigned_nft["variant_sku"]
    }), 200


# Catch-all (only if DEBUG_MODE=true)
if os.getenv("DEBUG_MODE", "false").lower() == "true":
    @app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE'])
    @app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
    def catch_all(path):
        logging.debug(f"Caught request to: /{path}")
        return jsonify({
            "message": f"DEBUG: Caught path /{path}",
            "headers": dict(request.headers),
            "body": request.get_json(silent=True)
        }), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
