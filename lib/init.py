import os
from pathlib import Path

bot_version = '1.0v alpha'

secret_folder_path = Path(os.environ.get("SECRET_FOLDER_PATH", "./.secret"))
data_folder_path = Path(os.environ.get("DATA_FOLDER_PATH", "./data"))
assets_folder_path = Path(os.environ.get("ASSETS_FOLDER_PATH", "./assets"))
migrations_folder_path = Path(os.environ.get("MIGRATIONS_FOLDER_PATH", "./migrations"))

for _ in range(2):
    if not os.path.exists(secret_folder_path):
        secret_folder_path = '../' / secret_folder_path
    if not os.path.exists(data_folder_path):
        data_folder_path = '../' / data_folder_path
    if not os.path.exists(assets_folder_path):
        assets_folder_path = '../' / assets_folder_path
    if not os.path.exists(migrations_folder_path):
        migrations_folder_path = '../' / migrations_folder_path

blackjack_assets_folder_path = assets_folder_path / "blackjack"
roulette_assets_folder_path = assets_folder_path / "roulette"

settings_file_path = secret_folder_path / "settings.json"

persistent_file_path = data_folder_path / "persistent_data.json"
database_file_path = data_folder_path / "database.sqlite"
cookies_file_path = data_folder_path / "cookies.txt"

videos_folder_path = data_folder_path / "videos"
videos_folder_path.mkdir(exist_ok=True)

galton_backgrounds_folder_path = data_folder_path / "galton_backgrounds"
galton_backgrounds_folder_path.mkdir(exist_ok=True)

tmp_folder_path = data_folder_path / "tmp"
tmp_folder_path.mkdir(exist_ok=True)
