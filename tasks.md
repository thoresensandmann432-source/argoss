# Tasks

- [ ] P1 | owner: infra | ETA: 2026-04-05 — Развернуть локальный Llama.cpp и настроить маршрутизацию запросов через него как первичный оффлайн LLM.
- [ ] P1 | owner: platform | ETA: 2026-04-06 — Ввести Redis TTL=1h для DuckDuckGo web_learn + aiohttp пайплайн, убрать requests.
- [ ] P1 | owner: platform | ETA: 2026-04-07 — Сохранение результатов поиска в PostgreSQL с full-text search для повторных запросов без сети.
- [ ] P2 | owner: sre | ETA: 2026-04-06 — Добавить circuit breaker + авто‑fallback провайдера поиска; слать алерт в лог при 3 неудачах.
- [ ] P2 | owner: sre | ETA: 2026-04-07 — Настроить watchtower/self-healing контейнеры и GitOps (ArgoCD) синк конфигураций.
- [ ] P2 | owner: infra | ETA: 2026-04-08 — Перенести кэш/индексы в RAM‑диск; разделить Ollama на лёгкую (в RAM) и тяжёлую (на диске) модели.
- [ ] P3 | owner: app | ETA: 2026-04-05 — Изолировать генератор контента в Docker-контейнер с ограничением 512 MB.
- [ ] P3 | owner: app | ETA: 2026-04-04 — Использовать repr() для логирования объектов во всех модулях web_learn/duckduckgo.
- [ ] P2 | owner: platform | ETA: 2026-04-06 — Интегрировать Cloudflare Workers AI/AI Gateway для edge inference и проксирования без API-ключей; обвязать serverless роуты.