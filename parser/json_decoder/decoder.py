import json


def parse_categories(data):
    level1_list = []
    level2_list = []
    level3_list = []

    for level1 in data.get("data", {}).get("items", []):
        title1 = level1.get("title")
        url1 = level1.get("url")

        level1_list.append({
            "title": title1,
            "url": url1
        })

        for column in level1.get("columns", []):
            for level2 in column.get("items", []):
                title2 = level2.get("title")
                url2 = level2.get("url")

                level2_list.append({
                    "parent": title1,
                    "title": title2,
                    "url": url2
                })

                for level3 in level2.get("childs", []):
                    title3 = level3.get("title")
                    url3 = level3.get("url")

                    level3_list.append({
                        "parent": title2,
                        "title": title3,
                        "url": url3
                    })

    return level1_list, level2_list, level3_list


def main():
    with open("categories.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    level1, level2, level3 = parse_categories(data)

    print("\n=== УРОВЕНЬ 1 ===")
    for c in level1:
        print(c)

    print("\n=== УРОВЕНЬ 2 ===")
    for c in level2:
        print(c)

    print("\n=== УРОВЕНЬ 3 ===")
    for c in level3:
        print(c)


if __name__ == "__main__":
    main()