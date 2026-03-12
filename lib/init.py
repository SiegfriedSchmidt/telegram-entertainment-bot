import os
from pathlib import Path

bot_version = '0.2.1v beta'

secret_folder_path = Path(os.environ.get("SECRET_FOLDER_PATH", "./.secret"))
data_folder_path = Path(os.environ.get("DATA_FOLDER_PATH", "./data"))
assets_folder_path = Path(os.environ.get("ASSETS_FOLDER_PATH", "./assets"))

if not os.path.exists(secret_folder_path):
    secret_folder_path = '../' / secret_folder_path
if not os.path.exists(secret_folder_path):
    secret_folder_path = '../' / secret_folder_path
if not os.path.exists(data_folder_path):
    data_folder_path = '../' / data_folder_path
if not os.path.exists(assets_folder_path):
    assets_folder_path = '../' / assets_folder_path

keys_folder_path = secret_folder_path / ".ssh_keys"
settings_file_path = secret_folder_path / "settings.json"

persistent_file_path = data_folder_path / "persistent_data.json"
database_file_path = data_folder_path / "database.sqlite"
videos_folder_path = data_folder_path / "videos"
galton_videos_folder_path = data_folder_path / "galton"
blackjack_videos_folder_path = data_folder_path / "blackjack"

fonts_folder_path = assets_folder_path / "fonts"
galton_assets_folder_path = assets_folder_path / "galton"
blackjack_assets_folder_path = assets_folder_path / "blackjack"
