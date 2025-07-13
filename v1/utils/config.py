# utils/config.py

import os
import yaml
import json

class ConfigError(Exception):
    pass

def load_config(profile: str, path: str = None) -> dict:
    if path:
        cfg_path = path
    else:
        yaml_path = os.path.join(os.getcwd(), "config.yaml")
        json_path = os.path.join(os.getcwd(), "config.json")
        if os.path.isfile(yaml_path):
            cfg_path = yaml_path
        elif os.path.isfile(json_path):
            cfg_path = json_path
        else:
            raise ConfigError("Не найден config.yaml/json")

    with open(cfg_path, encoding="utf-8") as f:
        full = yaml.safe_load(f) if cfg_path.endswith((".yaml", ".yml")) else json.load(f)

    profiles = full.get("profiles", {})
    if profile not in profiles:
        raise ConfigError(f"Профиль '{profile}' не найден")
    cfg = profiles[profile].copy()

    required = [
        "graphql_url", "collection_address", "count",
        "connect_timeout", "read_timeout", "threads", "log_level",
        "enable_proxy"
    ]
    missing = [k for k in required if k not in cfg]
    if missing:
        raise ConfigError(f"В профиле '{profile}' не заданы: {missing}")

    try:
        cfg["connect_timeout"] = float(cfg["connect_timeout"])
        cfg["read_timeout"]    = float(cfg["read_timeout"])
        cfg["tg_connect_timeout"] = float(cfg.get("tg_connect_timeout", cfg["connect_timeout"]))
        cfg["tg_read_timeout"]    = float(cfg.get("tg_read_timeout", cfg["read_timeout"]))
        cfg["threads"]         = int(cfg["threads"])
        cfg["cycle_interval"]  = int(cfg.get("cycle_interval", 60))
        cfg["max_cycles"]      = int(cfg.get("max_cycles", 0))
        cfg["stats_interval"]  = int(cfg.get("stats_interval", 300))
        cfg["request_delay_min"] = float(cfg.get("request_delay_min", 1.0))
        cfg["request_delay_max"] = float(cfg.get("request_delay_max", 3.0))
        cfg["retry_total"]       = int(cfg.get("retry_total", 3))
        cfg["retry_backoff_factor"] = float(cfg.get("retry_backoff_factor", 1))
    except (TypeError, ValueError) as e:
        raise ConfigError(f"Неверный формат параметров: {e}")

    if cfg["enable_proxy"]:
        for k in ("proxy_username", "proxy_password", "proxy_host", "proxy_port"):
            if k not in cfg:
                raise ConfigError(f"Не задан '{k}' для proxy")
        cfg["proxy_port"] = int(cfg["proxy_port"])

    # по умолчанию пустые значения
    cfg.setdefault("sha256_hash", None)
    cfg.setdefault("x_gg_client", None)
    cfg.setdefault("user_agents", ["Mozilla/5.0"])
    cfg.setdefault("detail_user_agent", cfg["user_agents"][0])

    return cfg
