import asyncio
import json
from playwright.async_api import async_playwright
import re
import time

from core.mongo import init_database
from mongo_db.models import OzonProductRaw
from mongo_db.save_products import save_ozon_raw_products
from parser.ozon.ozon_cat_links import links
from parser.ozon.ozon_session import OzonParser

MAX_PRODUCTS = 10000



def timer(func):
    async def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        end = time.perf_counter()

        print(f"{func.__name__} выполнена за {end - start:.3f} сек")
        return result

    return wrapper

def normalize_price(p):

    if not p:
        return None

    return int(
        p.replace("₽", "")
         .replace(" ", "")
         .replace(" ", "")
    )


def get_review_points(item):

    tile = item.get("tileImage", {})

    badges = [
        tile.get("leftBottomBadgeV2"),
        tile.get("secondLeftBottomBadgeV2")
    ]

    for badge in badges:

        if not badge:
            continue

        text = badge.get("text", "")

        if "балл" in text:

            m = re.search(r"\d+", text)

            if m:
                return int(m.group())

    return None

def extract_products(data):

    import json

    products = []

    for value in data.get("widgetStates", {}).values():

        try:
            widget = json.loads(value)
        except:
            continue

        items = widget.get("items")

        if not items:
            continue

        for item in items:

            if not item.get("tileImage"):
                continue

            sku = item.get("id")

            if not isinstance(sku, str):
                continue

            products.append(item)

    return products



def parse_product(item, category):

    sku = item.get("id")

    title = None
    original_price = None
    price = None
    discount = None
    rating = None
    reviews = None
    brand = None
    stock = None
    images = []
    review_points = get_review_points(item)

    for block in item.get("mainState", []):

        t = block.get("type")

        # название
        if t == "textAtom":
            title = block["textAtom"]["text"]

        # цены
        if t == "priceV2":

            prices = block["priceV2"].get("price", [])

            for p in prices:

                style = p.get("textStyle")
                value = p.get("text")

                if style == "PRICE":
                    price = normalize_price(value)


                elif style == "ORIGINAL_PRICE":
                    original_price = normalize_price(value)

            discount = block["priceV2"].get("discount")

        # labelList может содержать много разных вещей

        if t == "labelList":

            items = block["labelList"].get("items", [])

            for i in items:

                text = i.get("title", "")

                if not text:
                    continue

                text = text.strip().lower()

                # ---------- баллы за отзыв ----------
                if "балл" in text:

                    m = re.search(r"\d+", text)
                    if m:
                        review_point = int(m.group())

                # ---------- отзывы ----------
                elif "отзыв" in text:

                    reviews = int(
                        re.sub(r"\D", "", text)
                    )

                # ---------- рейтинг ----------
                elif re.match(r"^\d\.\d$", text):

                    rating = float(text)

                # ---------- остаток ----------
                elif "осталось" in text:

                    stock = int(
                        re.sub(r"\D", "", text)
                    )

                # ---------- бренд ----------
                elif "<b>" in text:

                    brand = (
                        text.replace("<b>", "")
                        .replace("</b>", "")
                        .strip()
                    )

    # картинка
    try:

        for img in item["tileImage"]["items"]:

            if "image" in img:
                link = img["image"].get("link")

                if link:
                    images.append(link)

    except:
        pass

    # ссылка
    url = None
    if item.get("action"):
        url = "https://www.ozon.ru" + item["action"]["link"]

    return {
        "sku": sku,
        "title": title,
        "original_price": original_price,
        "price": price,
        "discount": discount,
        "rating": rating,
        "reviews": reviews,
        "brand": brand,
        "stock": stock,
        "images": images,
        "url": url,
        "category": category,
        "review_points": review_points,
    }

async def collect_products(parser, url, category):

    products_map = {}

    page = 1
    batch = 20

    while True:

        tasks = []

        for p in range(page, page + batch):
            tasks.append(parser.fetch_page(p, url))


        responses = await asyncio.gather(*tasks, return_exceptions=True)

        new_products = 0

        for data in responses:

            if not data or isinstance(data, Exception):
                continue

            items = extract_products(data)

            if not items:
                continue

            for item in items:

                product = parse_product(item, category)

                if not product:
                    continue

                sku = product["sku"]

                if sku not in products_map:
                    products_map[sku] = product
                    new_products += 1

        print("products:", len(products_map))

        # если новых товаров нет — значит конец категории
        if new_products == 0:
            print("no more products")
            break

        page += batch

        if len(products_map) >= 5000:
            break

    return list(products_map.values())


async def collect_products_with_points(parser, url, category, parent_category):

    products_map = {}
    min_products = 200
    page = 1
    batch = 20

    while len(products_map) < min_products:

        tasks = []

        for p in range(page, page + batch):
            tasks.append(parser.fetch_page(p, url))

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        new_products = 0

        for data in responses:

            if not data or isinstance(data, Exception):
                continue

            items = extract_products(data)

            if not items:
                continue

            for item in items:

                product = parse_product(item, category)

                if not product:
                    continue

                # 🔴 ФИЛЬТР ТОВАРОВ С БАЛЛАМИ
                if not product.get("review_points"):
                    continue
                product["parent_category"] = parent_category
                sku = product["sku"]

                if sku not in products_map:
                    products_map[sku] = product
                    new_products += 1

        print("products with points:", len(products_map))

        page += batch

        # если новых нет — конец
        if new_products == 0:
            print("no more products with points")
            break

    products = list(products_map.values())
    print("save start", len(products))
    await save_ozon_raw_products(products)
    return list(products_map.values())

sem = asyncio.Semaphore(1)

# async def parse_category(parser, category):
#
#     async with sem:
#
#         title = category["title"]
#         url = category["url"]
#
#         products = []
#
#         for page in range(1, 4):
#
#             try:
#
#                 data = await parser.fetch_page(page, url)
#
#                 items = extract_products(data) or []
#
#                 if not items:
#                     break
#
#                 for item in items:
#
#                     product = parse_product(item, title)
#
#                     if product:
#                         products.append(product)
#
#             except Exception as e:
#                 print("ERROR:", title, e)
#
#         print(title, len(products))
#         print(products[:2])
#         return products

async def parse_category(parser, category):

    async with sem:

        parent_category = category["parent_category"]
        title = category["title"]
        url = category["url"]

        products = []

        for page in range(1, 4):

            try:

                data = await parser.fetch_page(page, url)

                items = extract_products(data) or []

                if not items:
                    break

                for item in items:

                    product = parse_product(item, title)

                    if product and product.get("price"):
                        product["parent_category"] = parent_category
                        products.append(product)

            except Exception as e:
                print("ERROR:", title, e)

        await save_ozon_raw_products(products)

        print(title, len(products))
        return products

async def parse_category_with_points(parser, category):

    async with sem:

        title = category["title"]
        url = category["url"]

        products_map = {}

        for page in range(1, 4):

            try:

                data = await parser.fetch_page(page, url)

                items = extract_products(data) or []

                if not items:
                    break

                for item in items:

                    product = parse_product(item, title)

                    if not product:
                        continue

                    # фильтр баллов
                    if not product.get("review_points"):
                        continue

                    sku = product["sku"]
                    products_map[sku] = product

            except Exception as e:
                print("ERROR:", title, e)

        print(title, "points:", len(products_map))

        return list(products_map.values())


@timer
async def parse_with_points():
    await init_database()

    all_products = {}

    for group in links:

        for category in group:

            title = category["title"]
            url = category["url"]
            parent_category = category["parent_category"]

            parser = OzonParser()

            try:

                await parser.start()

                url += "?has_points_from_reviews=t"

                products = await collect_products_with_points(
                    parser,
                    url,
                    title,
                    parent_category
                )

                for p in products:
                    all_products[p["sku"]] = p

                print(title, "saved:", len(products))

            except Exception as e:
                print("ERROR:", title, e)

            finally:
                await parser.close()

    print("TOTAL WITH POINTS:", len(all_products))

    with open("../ozon_points_products.json", "w", encoding="utf-8") as f:
        json.dump(list(all_products.values()), f, ensure_ascii=False, indent=2)

@timer
async def parse_all_goods():
    await init_database()
    parser = OzonParser()
    await parser.start()

    tasks = []

    for group in links:
        for category in group:
            tasks.append(
                parse_category(parser, category)
            )

    results = await asyncio.gather(*tasks)

    products = []

    for r in results:
        products.extend(r)

    print("TOTAL:", len(products))

    with open("../ozon_products.json", "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

    await parser.close()

if __name__ == "__main__":
    asyncio.run(parse_with_points())