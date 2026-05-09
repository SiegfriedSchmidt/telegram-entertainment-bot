import asyncio
import aiohttp
from dataclasses import dataclass
from typing import Optional, Dict, List, Any, Tuple
from lib.logger import main_logger
from lib.storage import storage

REPO_OWNER = "SiegfriedSchmidt"
REPO_NAME = "telegram-entertainment-bot"
url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits"


@dataclass
class Commit:
    sha: str
    message: str


async def get_commits() -> List[Dict[str, Any]]:
    params = {
        "per_page": 10,
        "page": 1
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    commits = await response.json()
                    if commits:
                        return commits
                else:
                    main_logger.error(f"GitHub API error: {response.status}")
                    raise RuntimeError(f"GitHub API error: {response.status}")
        except aiohttp.ClientError as e:
            main_logger.error(f"Network error fetching commit: {e}")
            raise
        except Exception:
            raise
        return []


def get_commit_obj(commit: dict) -> Commit:
    commit_info = commit.get("commit", {})
    message = commit_info.get("message", "No message")
    return Commit(sha=commit["sha"], message=message)


def prepare_latest_commits(commits: List[Dict[str, Any]]) -> List[Commit]:
    prepared_commits: List[Commit] = []
    found = False
    for commit in reversed(commits):
        if found:
            prepared_commits.append(get_commit_obj(commit))
        elif commit.get("sha", "") == storage.latest_github_commit_sha:
            found = True

    if not found:
        return [get_commit_obj(commits[0])]

    return list(reversed(prepared_commits))


async def get_commits_message() -> Tuple[Optional[List[str]], str]:
    raw_commits = await get_commits()
    commits = prepare_latest_commits(raw_commits)
    if len(commits) == 0:
        return None, raw_commits[0].get("sha", "")

    lines = [f"<b>Latest Update</b> {len(commits)} new commits:"]
    for commit in commits:
        lines.append(f"- {commit.sha[:7]}: {commit.message}")

    return lines, commits[0].sha


async def main():
    print(await get_commits_message())


if __name__ == '__main__':
    asyncio.run(main())
