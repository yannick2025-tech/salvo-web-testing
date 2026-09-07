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
    """按「平台 + URL path 第一段」拆分多 JSON 的分片记忆存储。

    目录结构（多平台模式）：
        <shard_dir>/
          <platform_alias>/          # 平台别名，由 host 精确映射（runner 注入）
            _common.json             # 公共记忆（登录页、无法解析 path 时）
            order.json               # /order/*   -> 订单管理
            station.json             # /station/* -> 电站管理
          elements.json              # 兼容旧单文件（无平台上下文时）

    路由键：
    - 平台目录：memory.context.host（或 store 注入的 platform_host/alias）精确映射。
    - 分片文件：URL path 第一段 -> <seg>.json；无法解析则 _common.json。

    与 MemoryStore 暴露相同接口，可无缝替换给 auto_apply / learner / integration。
    """

    COMMON_FILE = "_common.json"

    def __init__(
        self,
        memory_dir: str,
        platform_alias: str = "",
        platform_host: str = "",
        default_file: str = "elements.json",
    ):
        self.dir = Path(memory_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.default_file = default_file
        self._lock = threading.Lock()
        # 平台上下文（由 runner 注入）：platform_alias 决定子目录名；platform_host 用于写入路由。
        self.platform_alias = platform_alias
        self.platform_host = platform_host

    # ------------------------------------------------------------------ #
    # 路径解析
    # ------------------------------------------------------------------ #
    @staticmethod
    def resolve_shard(url_or_path: str) -> str:
        """把 URL、path 或 glob pattern 解析为分片文件名：第一段 -> <seg>.json。

        例：/station/site/list -> station.json；/Login 或 *Login* -> _common.json。
        容忍 url_pattern 的 glob 形态（去掉 * 后解析）。
        """
        from urllib.parse import urlparse

        if not url_or_path:
            return ShardedMemoryStore.COMMON_FILE
        raw = url_or_path.strip().strip("*").strip()
        try:
            parsed = urlparse(raw)
            path = parsed.path or raw
        except Exception:
            path = raw
        seg = (path or "").strip("/").split("/")[0]
        if not seg or seg.lower() in ("login", "logout"):
            return ShardedMemoryStore.COMMON_FILE
        # 仅允许字母数字/下划线/连字符，避免路径注入
        safe = "".join(c for c in seg if c.isalnum() or c in "_-")
        return f"{safe}.json" if safe else ShardedMemoryStore.COMMON_FILE

    def _platform_dir(self, host: Optional[str] = None) -> Optional[str]:
        """返回平台子目录名；无平台上下文返回 None（回退单文件）。"""
        # 优先用注入的平台别名（runner 已按 host 解析好）
        if self.platform_alias:
            return self.platform_alias
        # 否则尝试用传入 host 匹配 platform_host
        if host and self.platform_host and host == self.platform_host:
            return self.platform_alias or None
        return None

    def _resolve_path(self, host: Optional[str], url_pattern: Optional[str]) -> str:
        """返回相对 shard_dir 的文件路径（可能含平台子目录）。"""
        platform = self._platform_dir(host)
        shard = self.resolve_shard(url_pattern or "")
        if platform:
            return str(Path(platform) / shard)
        # 无平台上下文：回退单文件（兼容旧行为）
        return self.default_file

    # ------------------------------------------------------------------ #
    # 文件读取
    # ------------------------------------------------------------------ #
    def _load_file(self, rel_path: str) -> "MemoryFile":
        p = self.dir / rel_path
        if not p.exists():
            return MemoryFile()
        try:
            with open(p, "r", encoding="utf-8") as f:
                return MemoryFile.model_validate(json.load(f))
        except Exception as e:
            logger.warning(f"记忆分片文件读取失败: {rel_path} -> {e}")
            return MemoryFile()

    def _save_file(self, rel_path: str, memory_file: "MemoryFile") -> None:
        p = self.dir / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with open(p, "w", encoding="utf-8") as f:
                f.write(memory_file.model_dump_json(indent=2, ensure_ascii=False))

    def _all_files(self) -> list[str]:
        """所有分片文件（含平台子目录）+ default 文件。"""
        files: list[str] = []
        if self.platform_alias:
            base = self.dir / self.platform_alias
            if base.exists():
                files.extend(str(p.relative_to(self.dir)) for p in base.glob("*.json"))
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

    def _route_file(self, memory: ElementMemory) -> str:
        """按 memory.context 的 host + url_pattern 路由到分片文件。"""
        ctx = memory.context
        return self._resolve_path(ctx.host if ctx else None, ctx.url_pattern if ctx else None)

    def save(self, memory: ElementMemory) -> None:
        filename = self._route_file(memory)
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

    # 兼容旧接口（测试/遗留代码可能调用 add_shard）
    def add_shard(self, name: str, file: str, url_pattern: str) -> None:
        """兼容旧接口：不再使用 index.json，此方法保留为空操作以避免破坏调用方。"""
        logger.debug(f"add_shard 已弃用（忽略）: {name}")


def _url_match(url: str, pattern: str) -> bool:
    """glob 风格匹配（* 通配）。"""
    import fnmatch

    return fnmatch.fnmatch(url, pattern) or pattern.strip("*") in url
