import os
import time
import requests
import re
import json
import zipfile
import csv
from bs4 import BeautifulSoup

CONJUGATION_PATH = 'conjugation.csv'

def get_or_cache(url):
    if not os.path.isdir(".cache/"):
        os.makedirs(".cache/")

    # convert url to a file-secure name
    fixed_url = re.sub(r'[^\w\-_\.]', '_', url)
    file = ".cache/" + fixed_url + ".html"

    try:
        with open(file, 'r', encoding="utf8") as f:
            return f.read()
    except FileNotFoundError:
        print("Requesting", url)

    # if file does not exist, get the content from the website
    content = requests.get(url).content.decode()

    with open(file, 'w', encoding="utf8") as f:
        f.write(content)

    return content


def scrape_grammar_points():
    soup = BeautifulSoup(get_or_cache(
        'https://bunpro.jp/grammar_points'), 'html.parser')

    all_points = {}

    for nlevel in soup.select("ul.search-container_results > li"):
        assert nlevel.h2
        level = nlevel.h2.text

        all_points[level] = []

        lesson_names = nlevel.select(".index-lesson-data > h4")
        lesson_points = nlevel.select(".index-lesson-data ~ ul")
        assert lesson_names
        assert lesson_points
        assert len(lesson_names) == len(lesson_points)

        for lesson_name, lesson_points in zip(lesson_names, lesson_points):
            all_points[level].append(lesson := {})

            assert lesson_name.span

            lesson["points"] = points = []
            lesson["brief"] = lesson_name.text.partition(":")[0].strip()
            if lesson_name.span.text.strip():
                lesson["full"] = lesson_name.text.strip()
            else:
                lesson["full"] = lesson["brief"]

            assert lesson["brief"]

            for point_raw in lesson_points.select("li"):
                points.append(point := {})
                assert point_raw.a
                assert point_raw.p

                point["id"] = str(point_raw["id"]).removeprefix(
                    "grammar-point-id-")
                point["href"] = "https://bunpro.jp" + str(point_raw.a["href"])
                point["eng"] = point_raw.a["title"]
                point["text"] = point_raw["data-grammar-point"]

                assert point["id"]
                assert point["href"]
                assert point["eng"]
                assert point["text"]

    return all_points


def grammar_points():
    file = ".cache/points.json"
    try:
        with open(file, 'r') as fp:
            return json.load(fp)
    except FileNotFoundError:
        print("Gathering Points JSON")

    points = scrape_grammar_points()

    with open(file, 'w') as fp:
        json.dump(points, fp, ensure_ascii=False)

    return points


def update_conjugation():
    points = [
        point
        for levels in grammar_points().values()
        for lessons in levels
        for point in lessons["points"]
    ]
    points_map = {point["id"]: point for point in points}
    assert len(points_map) == len(points), "Points sharing IDs"

    # found missing grammar points in the file
    try:
        with open(CONJUGATION_PATH, newline='') as csvfile:
            reader = csv.reader(csvfile)
            ids = [row[0] for row in reader]
            ids_set = set(ids)
            assert len(ids) == len(ids_set), "Duplicates IDs in csv"

            missing = set(points_map).difference(ids_set)
    except FileNotFoundError:
        missing = set(points_map)

    if not missing:
        return

    print("Missing Points:", missing)

    # append all missing rows
    with open(CONJUGATION_PATH, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows([id, points_map[id]["text"], "", ""]
                         for id in sorted(missing, key=int))


def dict_builder():
    points = grammar_points()
    with open(CONJUGATION_PATH, newline='') as csvfile:
        conjugations = {
            row[0]: tuple(row[1:])
            for row in csv.reader(csvfile)}

    index = {
        "title": "Bunpro Grammar",
        "revision": time.strftime("%Y-%m-%d"),
        # "revision": str(int(time.time())),
        "description": "Dictionary with grammar points from Bunpro",
        "author": "imsamuka (dict packer)",
        "url": "https://bunpro.jp",  # TODO: dictionary source on URL
        "format": 3,
        "sourceLanguage": "jp",
        "targetLanguage": "eng",
    }

    tags = [[
        "Bunpro" + level,
        "partOfSpeech",
        0,
        "JLPT level of the grammar point by Bunpro",
        0
    ] for level in points]

    terms = []

    for level, lesson, point in (
        (level, lesson, point)
        for level, lessons in points.items()
        for lesson in lessons
        for point in lesson["points"]
    ):
        term, reading, inflection = conjugations[point["id"]]
        terms.append([
            term,
            reading,
            None,
            inflection,
            0,
            [{
                "type": "structured-content",
                "content": [
                    point["eng"],
                    {"tag": "br"},
                    {
                        "tag": "a",
                        "href": point["href"],
                        "content": f'{level} {lesson["full"]} - {point["text"]}'
                    }
                ]
            }],
            0,
            "Bunpro" + level,
        ])

    if not os.path.isdir("build/"):
        os.makedirs("build/")

    with zipfile.ZipFile("build/{title}-{revision}.zip".format_map(index), mode="w") as myzip:
        with myzip.open("index.json", "w") as file:
            file.write(json.dumps(index, ensure_ascii=False).encode())
        with myzip.open("tag_bank_1.json", "w") as file:
            file.write(json.dumps(tags, ensure_ascii=False).encode())
        with myzip.open("term_bank_1.json", "w") as file:
            file.write(json.dumps(terms, ensure_ascii=False).encode())

    # json.dump(index, open("build/index.json", "w"))
    # json.dump(tags, open("build/tag_bank_1.json", "w"), ensure_ascii=False)
    # json.dump(terms, open("build/term_bank_1.json", "w"), ensure_ascii=False)


if __name__ == "__main__":
    update_conjugation()
    dict_builder()
