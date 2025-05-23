# nft_data.py (更新，用于测试)

NFT_ITEMS = []

NUM_MAIN_SERIES = 200
NUM_SUB_SERIES_PER_MAIN = 30

# --- 用于测试的公共图片链接列表 ---
# 替换为一些您喜欢的公共可访问的图片URL
# 这里提供几个示例，您可以添加更多，或者使用图片占位符服务
TEST_IMAGE_URLS = [
    "https://images.unsplash.com/photo-1549497554-e0b49f5c2f5d?w=400&h=400&fit=crop&q=80", # 抽象艺术
    "https://images.unsplash.com/photo-1579783900882-c0d3ce7ddf44?w=400&h=400&fit=crop&q=80", # 几何图案
    "https://images.unsplash.com/photo-1620247667232-a5676e8a8e3d?w=400&h=400&fit=crop&q=80", # 渐变色
    "https://images.unsplash.com/photo-1524316827092-2a2651b142bc?w=400&h=400&fit=crop&q=80", # 纹理
    "https://images.unsplash.com/photo-1557683316-973673baf923?w=400&h=400&fit=crop&q=80", # 彩虹条纹
    "https://images.unsplash.com/photo-1510255959955-4d7a46f48821?w=400&h=400&fit=crop&q=80" # 抽象线条
]

# 用于循环选择图片的索引
current_image_index = 0

for i in range(1, NUM_MAIN_SERIES + 1):
    main_series_id_str = f"ICF{i:03d}" # 格式化为 ICF001, ICF002, ..., ICF200

    # 从 TEST_IMAGE_URLS 列表中循环选择图片
    # 每 200 个主系列，就会使用一次 TEST_IMAGE_URLS 列表中的所有图片
    # 这样可以确保每个主系列都有一张“专属”的测试图片，但这些图片会在多个主系列中重复出现
    main_image_url = TEST_IMAGE_URLS[current_image_index % len(TEST_IMAGE_URLS)]
    current_image_index += 1


    for j in range(1, NUM_SUB_SERIES_PER_MAIN + 1):
        sub_series_id_str = f"#{j:02d}" # 格式化为 #01, #02, ..., #30

        unique_nft_id = f"{main_series_id_str}-{sub_series_id_str}" # 例如：ICF001-#01

        nft_name = f"神秘之星 {main_series_id_str} {sub_series_id_str}" # 例如：神秘之星 ICF001 #01

        NFT_ITEMS.append({
            "nft_id": unique_nft_id,
            "image_url": main_image_url, # 所有子系列共享同一张图片
            "name": nft_name
        })

print(f"Generated {len(NFT_ITEMS)} unique NFT items.")
# 示例打印几个，验证生成是否正确
# for i in range(5):
#     print(NFT_ITEMS[i])
# # 打印同一个主系列的不同子系列，验证图片URL是否相同
# for i in range(0, 3): # ICF001 的前3个子系列
#     print(NFT_ITEMS[i])
# for i in range(29, 32): # ICF001 的最后几个子系列和 ICF002 的开头几个
#     print(NFT_ITEMS[i])