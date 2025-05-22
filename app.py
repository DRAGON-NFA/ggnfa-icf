import os
import sys
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import logging

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# Verify environment variables
REQUIRED_ENV_VARS = ["SHOPIFY_API_KEY", "SHOPIFY_API_PASSWORD", "SHOPIFY_SHOP_NAME"]
if not all(os.environ.get(var) for var in REQUIRED_ENV_VARS):
    logging.error("ERROR: Missing required environment variables. Please check your .env file or Render configuration.")
    # Exit with an error code if critical environment variables are missing
    sys.exit(1)

SHOPIFY_API_KEY = os.environ.get("SHOPIFY_API_KEY")
SHOPIFY_API_PASSWORD = os.environ.get("SHOPIFY_API_PASSWORD")
SHOPIFY_SHOP_NAME = os.environ.get("SHOPIFY_SHOP_NAME")
SHOPIFY_API_VERSION = "2024-04" # You might want to update this to the latest stable version

# Base URL for Shopify Admin API
SHOPIFY_BASE_URL = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_API_PASSWORD}@{SHOPIFY_SHOP_NAME}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}"

# Helper function to get available NFT products from Shopify
def get_available_nft_products():
    """Fetches all available NFT products from Shopify (SKUs starting with 'NFT_SKU_' and in stock)."""
    products_url = f"{SHOPIFY_BASE_URL}/products.json"
    headers = {"Content-Type": "application/json"}
    all_nft_products = []
    page_info = None

    while True:
        params = {"limit": 250} # Max limit per request
        if page_info:
            params['page_info'] = page_info

        try:
            response = requests.get(products_url, headers=headers, params=params, timeout=10)
            response.raise_for_status() # Raise an exception for HTTP errors
            products_data = response.json().get('products', [])

            for product in products_data:
                for variant in product.get('variants', []):
                    # Check if SKU starts with 'NFT_SKU_' and is in stock
                    if variant.get('sku', '').startswith('NFT_SKU_') and variant.get('inventory_quantity', 0) > 0:
                        all_nft_products.append({
                            "product_id": product.get("id"),
                            "product_title": product.get("title"),
                            "variant_id": variant.get("id"),
                            "variant_sku": variant.get("sku"),
                            "inventory_quantity": variant.get("inventory_quantity")
                        })

            # Check for next page
            link_header = response.headers.get('link')
            if link_header:
                next_page_match = next((l for l in link_header.split(',') if 'rel="next"' in l), None)
                if next_page_match:
                    # Extract page_info from the 'next' link
                    import re
                    match = re.search(r'page_info=([^&>]+)', next_page_match)
                    if match:
                        page_info = match.group(1)
                    else:
                        page_info = None # No page_info found, stop pagination
                else:
                    page_info = None # No next page link
            else:
                page_info = None # No link header

            if not page_info:
                break # No more pages

        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching products from Shopify: {e}")
            break # Exit loop on error
        except Exception as e:
            logging.error(f"An unexpected error occurred during product fetch: {e}")
            break

    logging.info(f"Found {len(all_nft_products)} available NFT products.")
    return all_nft_products

# Helper function to update Shopify product inventory
def update_shopify_inventory(product_id, inventory_item_id, new_quantity, location_id):
    """Updates the inventory quantity of a Shopify product variant."""
    inventory_url = f"{SHOPIFY_BASE_URL}/inventory_levels/set.json"
    headers = {"Content-Type": "application/json"}
    payload = {
        "inventory_item_id": inventory_item_id,
        "location_id": location_id,
        "set_quantity": new_quantity
    }
    try:
        response = requests.post(inventory_url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        logging.info(f"Successfully updated inventory for item {inventory_item_id} to {new_quantity}.")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Error updating inventory for item {inventory_item_id}: {e}")
        return False
    except Exception as e:
        logging.error(f"An unexpected error occurred during inventory update: {e}")
        return False

# Function to get default location ID (assuming the shop has at least one location)
def get_default_location_id():
    """Fetches the default (first) inventory location ID for the Shopify shop."""
    locations_url = f"{SHOPIFY_BASE_URL}/locations.json"
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.get(locations_url, headers=headers, timeout=10)
        response.raise_for_status()
        locations = response.json().get('locations', [])
        if locations:
            logging.info(f"Successfully fetched default location ID: {locations[0]['id']}")
            return locations[0]['id']
        else:
            logging.error("No inventory locations found for this shop.")
            return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching inventory locations: {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred during location fetch: {e}")
        return None


# Webhook endpoint for Shopify order payment
@app.route('/webhooks/orders/paid', methods=['POST'])
def order_paid_webhook():
    logging.info("Received order paid webhook (from Make API Pull).")
    data = request.json

    if not data:
        logging.warning("Received empty webhook data.")
        return jsonify({"message": "No data received"}), 400

    order_id = data.get('id')
    email = data.get('email')
    logging.info(f"Processing order ID: {order_id}, Customer email: {email}")

    # Get available NFT products from Shopify
    available_nfts = get_available_nft_products()
    logging.info(f"Available NFTs found: {available_nfts}")

    if not available_nfts:
        logging.warning("No available NFT products found to assign.")
        return jsonify({"message": "No NFT products available for assignment"}), 200

    # For simplicity, assign the first available NFT product
    assigned_nft = available_nfts[0]
    nft_product_id = assigned_nft['product_id']
    nft_variant_id = assigned_nft['variant_id']
    nft_sku = assigned_nft['variant_sku']
    nft_inventory_item_id = assigned_nft['inventory_item_id']
    nft_current_quantity = assigned_nft['inventory_quantity']

    logging.info(f"Assigning NFT: SKU={nft_sku}, Product ID={nft_product_id}, Variant ID={nft_variant_id}")

    # Get the default location ID for inventory update
    default_location_id = get_default_location_id()
    if not default_location_id:
        logging.error("Failed to get default location ID, cannot update inventory.")
        return jsonify({"message": "Failed to update inventory, no location found"}), 500

    # Decrement the stock of the assigned NFT in Shopify
    new_quantity = nft_current_quantity - 1
    if update_shopify_inventory(nft_product_id, nft_inventory_item_id, new_quantity, default_location_id):
        logging.info(f"Successfully decremented stock for {nft_sku} to {new_quantity}.")
    else:
        logging.error(f"Failed to decrement stock for {nft_sku}.")
        # Even if inventory update fails, we might still proceed to send NFT
        # depending on business logic, but for now, we'll return an error.
        return jsonify({"message": "Failed to update NFT inventory"}), 500

    # Here you would integrate with your NFT minting/transfer logic
    # For example:
    # mint_nft_for_customer(email, nft_sku)
    logging.info(f"Simulating NFT mint/transfer for customer {email} with SKU {nft_sku}")
    # In a real scenario, you'd call an external API or blockchain interaction here.

    return jsonify({"message": "Webhook processed successfully", "assigned_nft_sku": nft_sku}), 200

# Catch-all route for debugging unexpected requests
@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def catch_all(path):
    logging.debug(f"DEBUG: Catch-all route triggered for path: /{path}")
    logging.debug(f"DEBUG: Method: {request.method}")
    logging.debug(f"DEBUG: Headers: {request.headers}")
    if request.is_json:
        logging.debug(f"DEBUG: JSON Data (catch-all): {request.json}")
    else:
        logging.debug(f"DEBUG: Form Data (catch-all): {request.form}")
    logging.debug(f"DEBUG: Raw Data (catch-all): {request.data}")
    logging.debug(f"DEBUG: Expected webhook route repr(): {'/webhooks/orders/paid'}")

    # If the exact webhook path was hit, but not by the specific route, log that.
    if path == 'webhooks/orders/paid':
        logging.debug(f"DEBUG: Caught POST request to unrecognized path: /{path}")
        logging.debug(f"DEBUG: Headers: {request.headers}")
        if request.is_json:
            logging.debug(f"DEBUG: JSON Data (捕获): {request.json}")
        else:
            logging.debug(f"DEBUG: Form Data (捕获): {request.form}")


    return jsonify({"message": f"Hello from catch-all route! Path: /{path}"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)