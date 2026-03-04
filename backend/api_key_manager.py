"""
Multi-API Key Manager with per-model quota tracking, automatic rotation,
daily resets, and persistent usage state.

Usage:
    from api_key_manager import get_api_key_manager

    manager = get_api_key_manager()
    key = manager.get_current_key(model="gemini-3-flash-preview")
    manager.increment_usage(model="gemini-3-flash-preview")
"""

import os
import json
import threading
from datetime import date, datetime
from typing import Optional, Dict, List

# ─── Configuration ───
DAILY_QUOTA_LIMIT = 20  # Calls per key per model per day
USAGE_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_key_usage.json")


class APIKeyManager:
    """Thread-safe singleton manager for a specific API service's keys."""

    def __init__(self, service_name: str, multi_key_env: str, single_key_env: str):
        self._service_name = service_name
        self._multi_key_env = multi_key_env
        self._single_key_env = single_key_env
        self._lock = threading.Lock()
        self._current_index = 0
        self._last_reset_date = str(date.today())
        self._keys: List[Dict] = []

        self._load_keys()
        self._load_log()

    # ─── Key Loading ───

    def _load_keys(self):
        """Load API keys from environment variables."""
        keys_str = os.environ.get(self._multi_key_env, "")
        if keys_str:
            raw_keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        else:
            single = os.environ.get(self._single_key_env, "")
            raw_keys = [single] if single else []

        if not raw_keys:
            print(f"   [!] {self._service_name} Key Manager: No API keys found in "
                  f"{self._multi_key_env} or {self._single_key_env}")
            return

        for key in raw_keys:
            self._keys.append({
                "key": key,
                "key_suffix": f"...{key[-4:]}" if len(key) >= 4 else key,
                "model_usage": {},
                "exhausted_models": set(),
                "last_exhausted": None,
                "quota_used": 0,
                "exhausted": False,
            })

        source = self._multi_key_env if keys_str else self._single_key_env
        print(f"   [+] {self._service_name} Key Manager loaded {len(self._keys)} key(s) "
              f"from {source} (per-model tracking)")

    # ─── Core Methods ───

    def get_current_key(self, model: str = None) -> Optional[str]:
        """Return the currently available API key, skipping exhausted ones for this model."""
        with self._lock:
            if not self._keys:
                return None

            self._reset_daily_quotas_if_needed()

            # Try each key starting from current index
            for i in range(len(self._keys)):
                idx = (self._current_index + i) % len(self._keys)
                key_data = self._keys[idx]

                # Skip if exhausted for this model
                if model and model in key_data["exhausted_models"]:
                    continue

                # Skip if over quota for this model
                if model:
                    usage = key_data["model_usage"].get(model, 0)
                    if usage >= DAILY_QUOTA_LIMIT:
                        continue

                self._current_index = idx
                return key_data["key"]

            # All keys exhausted for this model
            return None

    def increment_usage(self, key: str = None, model: str = None) -> Optional[str]:
        """
        Increment usage counter for a key-model combination.
        Returns a new key string if auto-rotation occurred, else None.
        """
        with self._lock:
            if not self._keys:
                return None

            # Find the target key
            target = self._find_key_data(key)
            if not target:
                return None

            # Increment model usage
            if model:
                current = target["model_usage"].get(model, 0)
                target["model_usage"][model] = current + 1

            # Increment aggregate
            target["quota_used"] = target.get("quota_used", 0) + 1

            new_key = None

            # Check if quota exhausted for this model
            if model and target["model_usage"].get(model, 0) >= DAILY_QUOTA_LIMIT:
                target["exhausted_models"].add(model)
                target["last_exhausted"] = datetime.now().isoformat()
                print(f"   [!] {self._service_name} key {target['key_suffix']} reached "
                      f"{DAILY_QUOTA_LIMIT} calls for {model} - rotating")

                # Auto-rotate to next available key
                new_key = self._rotate_to_next(model)

            # Check global exhaustion
            if all(model in k["exhausted_models"] for k in self._keys if model):
                for k in self._keys:
                    k["exhausted"] = True

            self._save_log()
            return new_key

    def mark_exhausted(self, key: str = None, model: str = None) -> bool:
        """
        Mark a key as exhausted for a model (e.g. on 429 error).
        Returns True if there are backup keys available.
        """
        with self._lock:
            if not self._keys:
                return False

            target = self._find_key_data(key)
            if not target:
                return False

            if model:
                target["exhausted_models"].add(model)
            target["last_exhausted"] = datetime.now().isoformat()

            print(f"   [!] {self._service_name} key {target['key_suffix']} "
                  f"marked exhausted for {model or 'all models'}")

            # Auto-rotate
            self._rotate_to_next(model)
            self._save_log()

            # Check if any keys still available
            for k in self._keys:
                if model and model not in k["exhausted_models"]:
                    usage = k["model_usage"].get(model, 0)
                    if usage < DAILY_QUOTA_LIMIT:
                        return True
            return False

    def get_next_available_key(self, model: str = None) -> Optional[str]:
        """Manually rotate to the next available key."""
        with self._lock:
            return self._rotate_to_next(model)

    def get_key_count(self) -> int:
        """Return total number of configured keys."""
        return len(self._keys)

    def get_status(self, model: str = None) -> Dict:
        """Return full status snapshot for monitoring/API endpoint."""
        with self._lock:
            self._reset_daily_quotas_if_needed()

            keys_info = []
            available = 0
            exhausted_count = 0
            total_requests = 0

            for i, k in enumerate(self._keys):
                model_usage = k["model_usage"].get(model, 0) if model else sum(k["model_usage"].values())
                is_exhausted = (model in k["exhausted_models"]) if model else k.get("exhausted", False)
                is_over_quota = (model_usage >= DAILY_QUOTA_LIMIT) if model else False

                if is_exhausted or is_over_quota:
                    exhausted_count += 1
                else:
                    available += 1

                total_requests += k.get("quota_used", 0)

                keys_info.append({
                    "index": i,
                    "suffix": k["key_suffix"],
                    "key_suffix": k["key_suffix"],
                    "model_usage": dict(k["model_usage"]),
                    "exhausted_models": list(k["exhausted_models"]),
                    "used": model_usage,
                    "exhausted": is_exhausted or is_over_quota,
                    "last_exhausted": k.get("last_exhausted"),
                    "quota_used": k.get("quota_used", 0),
                })

            current_key_suffix = None
            if self._keys:
                current_key_suffix = self._keys[self._current_index]["key_suffix"]

            return {
                "service": self._service_name,
                "model": model,
                "total_keys": len(self._keys),
                "available_keys": available,
                "exhausted_keys": exhausted_count,
                "current_key": current_key_suffix,
                "current_index": self._current_index,
                "total_requests_today": total_requests,
                "quota_limit_per_key": DAILY_QUOTA_LIMIT,
                "last_reset_date": self._last_reset_date,
                "keys": keys_info,
            }

    # ─── Internal Helpers ───

    def _find_key_data(self, key: str = None) -> Optional[Dict]:
        """Find key data dict by key string, or return current key's data."""
        if key:
            for k in self._keys:
                if k["key"] == key:
                    return k
            return None
        if self._keys:
            return self._keys[self._current_index]
        return None

    def _rotate_to_next(self, model: str = None) -> Optional[str]:
        """Rotate to next available key (must be called under lock)."""
        if not self._keys:
            return None

        for i in range(1, len(self._keys) + 1):
            idx = (self._current_index + i) % len(self._keys)
            k = self._keys[idx]

            if model and model in k["exhausted_models"]:
                continue
            if model:
                usage = k["model_usage"].get(model, 0)
                if usage >= DAILY_QUOTA_LIMIT:
                    continue

            self._current_index = idx
            print(f"   [>] {self._service_name}: Rotated to key {k['key_suffix']} for {model or 'general'}")
            return k["key"]

        return None

    def _reset_daily_quotas_if_needed(self):
        """Reset all quotas if it's a new day (must be called under lock)."""
        today = str(date.today())
        if self._last_reset_date != today:
            old_date = self._last_reset_date
            self._last_reset_date = today
            for k in self._keys:
                k["model_usage"] = {}
                k["exhausted_models"] = set()
                k["exhausted"] = False
                k["quota_used"] = 0
            self._current_index = 0
            print(f"   [i] New day detected ({old_date} → {today}), "
                  f"resetting quotas for all {self._service_name} keys/models")
            self._save_log()

    # ─── Persistence ───

    def _save_log(self):
        """Save current state to JSON file."""
        try:
            data = {
                "service": self._service_name,
                "last_reset_date": self._last_reset_date,
                "current_index": self._current_index,
                "total_requests_today": sum(k.get("quota_used", 0) for k in self._keys),
                "quota_limit_per_key": DAILY_QUOTA_LIMIT,
                "keys": [],
            }
            for i, k in enumerate(self._keys):
                data["keys"].append({
                    "index": i,
                    "key_suffix": k["key_suffix"],
                    "model_usage": dict(k["model_usage"]),
                    "exhausted_models": list(k["exhausted_models"]),
                    "last_exhausted": k.get("last_exhausted"),
                    "quota_used": k.get("quota_used", 0),
                    "exhausted": k.get("exhausted", False),
                })

            with open(USAGE_LOG_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"   [!] Failed to save API key usage log: {e}")

    def _load_log(self):
        """Load persisted state from JSON file (if same day)."""
        if not os.path.exists(USAGE_LOG_FILE):
            return

        try:
            with open(USAGE_LOG_FILE, "r") as f:
                data = json.load(f)

            # Only restore if same day and same service
            if data.get("last_reset_date") != str(date.today()):
                print(f"   [i] {self._service_name}: Saved state is from {data.get('last_reset_date')}, "
                      f"quotas will reset on next request")
                return

            if data.get("service") != self._service_name:
                return

            saved_keys = data.get("keys", [])
            if len(saved_keys) != len(self._keys):
                print(f"   [i] {self._service_name}: Key count changed "
                      f"({len(saved_keys)} → {len(self._keys)}), starting fresh")
                return

            # Restore state by matching key suffix
            restored = 0
            for i, saved in enumerate(saved_keys):
                if i < len(self._keys) and saved.get("key_suffix") == self._keys[i]["key_suffix"]:
                    self._keys[i]["model_usage"] = saved.get("model_usage", {})
                    self._keys[i]["exhausted_models"] = set(saved.get("exhausted_models", []))
                    self._keys[i]["last_exhausted"] = saved.get("last_exhausted")
                    self._keys[i]["quota_used"] = saved.get("quota_used", 0)
                    self._keys[i]["exhausted"] = saved.get("exhausted", False)
                    restored += 1

            self._current_index = data.get("current_index", 0) % len(self._keys)
            self._last_reset_date = data.get("last_reset_date", str(date.today()))

            exhausted_count = sum(1 for k in self._keys if k["exhausted_models"])
            available_count = len(self._keys) - exhausted_count
            print(f"   [i] {self._service_name}: Loaded state from log "
                  f"({exhausted_count} exhausted, {available_count} available)")

        except Exception as e:
            print(f"   [!] Failed to load API key usage log: {e}")


# ─── Global Singletons ───

_google_manager: Optional[APIKeyManager] = None
_lock = threading.Lock()


def get_api_key_manager() -> APIKeyManager:
    """Get or create the Google API key manager (lazy singleton)."""
    global _google_manager
    if _google_manager is None:
        with _lock:
            if _google_manager is None:
                _google_manager = APIKeyManager(
                    service_name="Google",
                    multi_key_env="GOOGLE_API_KEYS",
                    single_key_env="GOOGLE_API_KEY",
                )
    return _google_manager
