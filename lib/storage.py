import json
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Optional, List, Dict, Any, Set, get_origin, Literal
from datetime import datetime
from lib.init import persistent_file_path

FFMPEG_CRF = Literal[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30,
31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44,
45, 46, 47, 48, 49, 50, 51]
FFMPEG_PRESET = Literal['fast', 'veryfast', 'medium', 'slow', 'veryslow']


@dataclass
class PersistentData:
    notifications_enabled: bool = True
    fee_percentage: int = 0.1
    mine_block_interval_seconds: int = 86400
    mine_block_reward: int = 2000
    mine_block_user_timeout: int = 300
    mine_block_user_attempts: int = 16
    galton_max_concurrent_per_user: int = 2
    ffmpeg_use: bool = False
    ffmpeg_crf: FFMPEG_CRF = 23
    ffmpeg_preset: FFMPEG_PRESET = 'veryfast'
    latest_github_commit_sha: str = ''
    optimize: bool = True
    video_max_size: int = 40 * 2 ** 20
    # admin_ids: List[int] = field(default_factory=list)


class Storage(PersistentData):
    def __init__(self, filename: str):
        self.__filename = filename
        super().__init__()

        self.__field_types = {f.name: get_origin(f.type) for f in fields(PersistentData)}
        self.__auto_save_enabled = True
        self._load()

    def _load(self):
        if not Path(self.__filename).exists():
            return

        with open(self.__filename, 'r') as f:
            data = json.load(f)

        for key, value in data.items():
            if not hasattr(self, key):
                continue

            expected_type = self.__field_types.get(key)
            if expected_type is set and isinstance(value, list):
                setattr(self, key, set(value))
            elif expected_type is datetime and isinstance(value, str):
                setattr(self, key, datetime.fromisoformat(value))
            else:
                setattr(self, key, value)

    def save(self):
        data = {k: v for k, v in self.__dict__.items() if not k.startswith('_')}

        for key, value in list(data.items()):
            if isinstance(value, set):
                data[key] = list(value)
            elif isinstance(value, datetime):
                data[key] = value.isoformat()

        with open(self.__filename, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    @property
    def filename(self):
        return self.__filename

    def __setattr__(self, name, value):
        super().__setattr__(name, value)

        if not name.startswith('_') and hasattr(self, '_Storage__auto_save_enabled') and self.__auto_save_enabled:
            self.save()

    def batch_update(self):
        class BatchContext:
            def __init__(self, batch_storage):
                self.storage = batch_storage

            def __enter__(self):
                self.storage.__auto_save_enabled = False
                return self.storage

            def __exit__(self, *args):
                self.storage.__auto_save_enabled = True
                self.storage.save()

        return BatchContext(self)


storage = Storage(persistent_file_path)

if __name__ == '__main__':
    storage.startup_docker_checks = False
    # storage.user_count += 1
    # storage.last_user = "Alice"
    # storage.admin_ids.append(123456)
    # storage.enabled_chats.add(-1001234567890)

    # with storage.batch_update():
    #     storage.premium_users.add(987654)
    #     storage.blocked_keywords.add("spam")
    #     storage.total_messages += 5
    #     storage.last_active = datetime.now()

    # print(f"Total messages: {storage.total_messages}")
    print(f"File: {storage.filename}")
