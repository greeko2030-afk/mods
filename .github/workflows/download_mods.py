
import hashlib
import pathlib
import sys
import time
import requests
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG_FILE = ROOT / "Mods.yml"
OUTPUT_ROOT = ROOT / "mods"

API = "https://api.modrinth.com/v2"
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "SupersonicClient-ModUpdater/1.0"
})

def get_json(url, params=None):
    for attempt in range(3):
        try:
            response = SESSION.get(
                url, params=params, timeout=45
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))

def download_file(url, expected_sha1):
    for attempt in range(3):
        try:
            response = SESSION.get(url, timeout=180)
            response.raise_for_status()
            data = response.content

            actual = hashlib.sha1(data).hexdigest()
            if expected_sha1 and actual.lower() != expected_sha1.lower():
                raise ValueError("SHA-1 verification failed")

            return data
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))

def main():
    config = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))

    versions = config["minecraft_versions"]
    loader = config.get("loader", "fabric")
    release_type = config.get("release_type", "release")
    slugs = config["mods"]

    failures = []
    downloaded = 0

    for game_version in versions:
        destination = OUTPUT_ROOT / game_version
        destination.mkdir(parents=True, exist_ok=True)

        for slug in slugs:
            try:
                project = get_json(f"{API}/project/{slug}")
                project_id = project["id"]

                mod_versions = get_json(
                    f"{API}/project/{project_id}/version",
                    params={
                        "game_versions": f'["{game_version}"]',
                        "loaders": f'["{loader}"]',
                    },
                )

                candidates = [
                    item for item in mod_versions
                    if item.get("version_type") == release_type
                    and item.get("status") == "listed"
                ]

                if not candidates:
                    print(f"SKIP: {slug} / {game_version}")
                    continue

                selected = max(
                    candidates,
                    key=lambda item: item["date_published"]
                )

                jars = [
                    file for file in selected.get("files", [])
                    if file.get("filename", "").lower().endswith(".jar")
                ]

                if not jars:
                    print(f"NO JAR: {slug} / {game_version}")
                    continue

                primary = next(
                    (file for file in jars if file.get("primary")),
                    jars[0]
                )

                target = destination / primary["filename"]
                data = download_file(
                    primary["url"],
                    primary.get("hashes", {}).get("sha1")
                )

                target.write_bytes(data)
                downloaded += 1
                print(
                    f"OK: {game_version} | {slug} | "
                    f"{selected['version_number']}"
                )

            except Exception as error:
                failures.append(f"{game_version} / {slug}: {error}")
                print(f"ERROR: {game_version} / {slug}: {error}")

    print(f"\nFinished. Downloaded JAR files: {downloaded}")

    if failures:
        print("\nFailures:")
        for failure in failures:
            print(f"- {failure}")

        # Preserve successful downloads, but mark the run as failed.
        sys.exit(1)

if __name__ == "__main__":
    main()
