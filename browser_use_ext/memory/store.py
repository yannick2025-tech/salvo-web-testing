"""JSON 记忆文件读写"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import List, Optional

from .models import ElementMemory, MemoryFile

logger = logging.getLogger(__name__)


class MemoryStore:
    """基于 JSON 文件的记忆存储"""

    def __init__(self, storage_path: str, max_memories: int = 1000):
        self.storage_path = Path(storage_path)
        self.max_memories = max_memories
        self._lock = threading.Lock()
        self._cache: Optional[MemoryFile] = None

        # 确保目录存在
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> MemoryFile:
        """从文件加载记忆"""
        if self._cache is not None:
            return self._cache

        if not self.storage_path.exists():
            self._cache = MemoryFile()
            return self._cache

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._cache = MemoryFile.model_validate(data)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"记忆文件读取失败，将重新创建: {e}")
            self._cache = MemoryFile()

        return self._cache

    def _save(self, memory_file: MemoryFile) -> None:
        """保存记忆到文件"""
        with self._lock:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                f.write(memory_file.model_dump_json(indent=2, ensure_ascii=False))
            self._cache = memory_file

    def _evict_if_needed(self, memory_file: MemoryFile) -> None:
        """超出 max_memories 时淘汰最旧的条目"""
        if len(memory_file.memories) > self.max_memories:
            memory_file.memories.sort(key=lambda m: m.last_used_at)
            memory_file.memories = memory_file.memories[-self.max_memories :]
            logger.info(f"淘汰记忆条目至 {self.max_memories} 条")

    def query_by_flat_key(self, flat_key: str) -> Optional[ElementMemory]:
        """按 flat key 查询记忆"""
        memory_file = self._load()
        for m in memory_file.memories:
            if m.key.mode == "flat" and m.key.flat_key == flat_key:
                return m
        return None

    def query_by_hierarchical_path(self, path: List[str]) -> Optional[ElementMemory]:
        """按 hierarchical path 查询记忆（逐层匹配）"""
        memory_file = self._load()
        best_match = None
        best_depth = -1

        for m in memory_file.memories:
            if m.key.mode != "hierarchical":
                continue
            mem_path = m.key.hierarchical_path
            # 逐层匹配：当前路径的每一层必须和记忆路径一致
            # 当前路径可以比记忆路径短（部分匹配）
            depth = 0
            for i, segment in enumerate(path):
                if i < len(mem_path) and mem_path[i] == segment:
                    depth += 1
                else:
                    break
            if depth > best_depth:
                best_depth = depth
                best_match = m

        # 至少匹配 1 层才返回
        return best_match if best_depth > 0 else None

    def query(self, flat_key: str, hierarchical_path: Optional[List[str]] = None, key_mode: str = "flat") -> Optional[ElementMemory]:
        """通用查询接口"""
        if key_mode == "hierarchical" and hierarchical_path:
            return self.query_by_hierarchical_path(hierarchical_path)
        return self.query_by_flat_key(flat_key)

    def find_by_key(self, key_string: str) -> Optional[ElementMemory]:
        """按 to_flat_string 归一化后的 KEY 字符串查找记忆（用于判定是否已存在）。"""
        memory_file = self._load()
        for m in memory_file.memories:
            if m.key.to_flat_string() == key_string:
                return m
        return None

    def note_reused(self, key_string: str) -> Optional[ElementMemory]:
        """记忆被复用成功：只计入使用次数与时间，不改变操作步骤。"""
        memory_file = self._load()
        for m in memory_file.memories:
            if m.key.to_flat_string() == key_string:
                m.touch()
                self._save(memory_file)
                logger.info(f"记忆复用成功，计入使用: {key_string} (成功次数: {m.success_count})")
                return m
        return None

    def save(self, memory: ElementMemory) -> None:
        """保存或更新一条记忆"""
        memory_file = self._load()

        # 查找是否已有同 key 的记忆
        existing_idx = None
        for i, m in enumerate(memory_file.memories):
            if m.key.to_flat_string() == memory.key.to_flat_string():
                existing_idx = i
                break

        if existing_idx is not None:
            # 更新已有记忆
            existing = memory_file.memories[existing_idx]
            existing.operation_steps = memory.operation_steps
            existing.element_signature = memory.element_signature
            existing.context = memory.context
            existing.touch()
            logger.info(f"更新记忆: {memory.key.to_flat_string()} (成功次数: {existing.success_count})")
        else:
            # 新增记忆
            memory_file.memories.append(memory)
            self._evict_if_needed(memory_file)
            logger.info(f"新增记忆: {memory.key.to_flat_string()}")

        self._save(memory_file)

    def get_all(self) -> List[ElementMemory]:
        """获取所有记忆"""
        return self._load().memories

    def clear(self) -> None:
        """清空所有记忆"""
        self._save(MemoryFile())

    def reload(self) -> None:
        """强制重新加载文件（清除缓存）"""
        self._cache = None


class ShardedMemoryStore:
    """按页面/模块拆分多 JSON 的分片记忆存储。

    目录结构：
        memory/
          index.json          # 索引：shard 名 -> 文件 + url_pattern
          login.json          # 各分片文件（MemoryFile 格式）
          charge-order.json
          ...
          elements.json       # default：未匹配 url_pattern 的记忆

    与 MemoryStore 暴露相同接口，可无缝替换给 auto_apply / learner / integration。
    """

    def __init__(self, memory_dir: str, index_file: str = "index.json", default_file: str = "elements.json"):
        self.dir = Path(memory_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.dir / index_file
        self.default_file = default_file
        self._lock = threading.Lock()
        self._shards_cache: Optional[list[dict]] = None

    # ------------------------------------------------------------------ #
    # 索引
    # ------------------------------------------------------------------ #
    def _load_index(self) -> list[dict]:
        """加载分片索引列表 [{name, file, url_pattern}]。"""
        if self._shards_cache is not None:
            return self._shards_cache
        if not self.index_path.exists():
            self._shards_cache = []
            return self._shards_cache
        try:
            with open(self.index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._shards_cache = list(data.get("shards", []))
        except Exception as e:
            logger.warning(f"分片索引读取失败: {e}")
            self._shards_cache = []
        return self._shards_cache

    def _write_index(self, shards: list[dict]) -> None:
        with self._lock:
            with open(self.index_path, "w", encoding="utf-8") as f:
                json.dump({"shards": shards}, f, ensure_ascii=False, indent=2)
            self._shards_cache = shards

    # ------------------------------------------------------------------ #
    # 文件读取
    # ------------------------------------------------------------------ #
    def _load_file(self, filename: str) -> "MemoryFile":
        p = self.dir / filename
        if not p.exists():
            return MemoryFile()
        try:
            with open(p, "r", encoding="utf-8") as f:
                return MemoryFile.model_validate(json.load(f))
        except Exception as e:
            logger.warning(f"记忆分片文件读取失败: {filename} -> {e}")
            return MemoryFile()

    def _save_file(self, filename: str, memory_file: "MemoryFile") -> None:
        with self._lock:
            with open(self.dir / filename, "w", encoding="utf-8") as f:
                f.write(memory_file.model_dump_json(indent=2, ensure_ascii=False))

    def _all_files(self) -> list[str]:
        """所有分片文件 + default 文件。"""
        files = [s.get("file") for s in self._load_index() if s.get("file")]
        if self.default_file not in files:
            files.append(self.default_file)
        return files

    # ------------------------------------------------------------------ #
    # 对外接口（与 MemoryStore 一致）
    # ------------------------------------------------------------------ #
    def get_all(self) -> List[ElementMemory]:
        memories: List[ElementMemory] = []
        for f in self._all_files():
            memories.extend(self._load_file(f).memories)
        return memories

    def find_by_key(self, key_string: str) -> Optional[ElementMemory]:
        for m in self.get_all():
            if m.key.to_flat_string() == key_string:
                return m
        return None

    def query_by_flat_key(self, flat_key: str) -> Optional[ElementMemory]:
        for m in self.get_all():
            if m.key.mode == "flat" and m.key.flat_key == flat_key:
                return m
        return None

    def query_by_hierarchical_path(self, path: List[str]) -> Optional[ElementMemory]:
        best_match = None
        best_depth = -1
        for m in self.get_all():
            if m.key.mode != "hierarchical":
                continue
            mem_path = m.key.hierarchical_path
            depth = 0
            for i, segment in enumerate(path):
                if i < len(mem_path) and mem_path[i] == segment:
                    depth += 1
                else:
                    break
            if depth > best_depth:
                best_depth = depth
                best_match = m
        return best_match if best_depth > 0 else None

    def query(self, flat_key: str, hierarchical_path: Optional[List[str]] = None, key_mode: str = "flat") -> Optional[ElementMemory]:
        if key_mode == "hierarchical" and hierarchical_path:
            return self.query_by_hierarchical_path(hierarchical_path)
        return self.query_by_flat_key(flat_key)

    def note_reused(self, key_string: str) -> Optional[ElementMemory]:
        for f in self._all_files():
            mf = self._load_file(f)
            changed = False
            for m in mf.memories:
                if m.key.to_flat_string() == key_string:
                    m.touch()
                    changed = True
            if changed:
                self._save_file(f, mf)
                return mf.memories[0] if mf.memories else None
        return None

    def _route_file(self, url_pattern: Optional[str]) -> str:
        """按 url_pattern 匹配分片；无匹配返回 default 文件。"""
        for s in self._load_index():
            pat = s.get("url_pattern")
            if pat and url_pattern and _url_match(url_pattern, pat):
                return s.get("file", self.default_file)
        return self.default_file

    def save(self, memory: ElementMemory) -> None:
        filename = self._route_file(memory.context.url_pattern if memory.context else None)
        mf = self._load_file(filename)
        # 同 key 更新
        for i, m in enumerate(mf.memories):
            if m.key.to_flat_string() == memory.key.to_flat_string():
                existing = mf.memories[i]
                existing.operation_steps = memory.operation_steps
                existing.element_signature = memory.element_signature
                existing.context = memory.context
                existing.touch()
                self._save_file(filename, mf)
                logger.info(f"[shard:{filename}] 更新记忆: {memory.key.to_flat_string()}")
                return
        mf.memories.append(memory)
        self._save_file(filename, mf)
        logger.info(f"[shard:{filename}] 新增记忆: {memory.key.to_flat_string()}")

    def clear(self) -> None:
        for f in self._all_files():
            self._save_file(f, MemoryFile())

    def add_shard(self, name: str, file: str, url_pattern: str) -> None:
        """注册一个分片。"""
        shards = self._load_index()
        shards = [s for s in shards if s.get("name") != name]
        shards.append({"name": name, "file": file, "url_pattern": url_pattern})
        self._write_index(shards)


def _url_match(url: str, pattern: str) -> bool:
    """glob 风格匹配（* 通配）。"""
    import fnmatch

    return fnmatch.fnmatch(url, pattern) or pattern.strip("*") in url
