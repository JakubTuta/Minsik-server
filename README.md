# Minsik Server

The backend for [Minsik](https://minsik.jtuta.cloud) — a book discovery and tracking app.

[Live App](https://minsik.jtuta.cloud) · [Web Repo](https://github.com/JakubTuta/Minsik-web) · [API Docs](https://minsik.api.jtuta.cloud/docs) · License: MIT

---

A set of microservices behind a single REST gateway. The web frontend lives in [Minsik-web](https://github.com/JakubTuta/Minsik-web).

## Getting Started

```bash
git clone https://github.com/JakubTuta/Minsik-server
cd Minsik-server
cp .env.example .env
docker compose up -d --build
```

The API will be available at `http://localhost:8040`. See `.env.example` for all configuration options — every variable is commented.

## API Documentation

Interactive Swagger UI with all endpoints and schemas:
**[minsik.api.jtuta.cloud/docs](https://minsik.api.jtuta.cloud/docs)**

---

## What's inside

- **Full-text search** across books, authors, and series with type filters
- **9-dimension ratings** — overall stars plus Pacing, Emotional Impact, Intellectual Depth, Writing Quality, Rereadability, Readability, Plot Complexity, and Humor
- **Bookshelves** with four statuses (Want to Read, Reading, Read, Abandoned), favourites, and comments with optional spoiler flag
- **Continuous data ingestion** from Open Library and Google Books, with automatic description enrichment
- **JWT authentication** with short-lived access tokens and rotating refresh tokens
- **Recommendations** — generic and personalized book and author suggestions

---

## Configuration

The full reference is in `.env.example`. Below is what matters most.

### Required for production

| Variable               | Notes                                                                 |
| ---------------------- | --------------------------------------------------------------------- |
| `DB_PASSWORD`          | Replace the default with a strong password                            |
| `REDIS_PASSWORD`       | Replace the default with a strong password                            |
| `JWT_SECRET_KEY`       | Generate with `openssl rand -hex 32`                                  |
| `GOOGLE_BOOKS_API_KEY` | Obtain from [Google Cloud Console](https://console.cloud.google.com/) |
| `ENV`                  | Set to `production`                                                   |
| `DEBUG`                | Set to `false`                                                        |
| `LOG_LEVEL`            | Set to `ERROR`                                                        |

### Notable optional settings

- **Cache TTLs** — how long book, author, and search results are cached (`CACHE_*_TTL`)
- **Rate limiting** — requests per minute for regular and admin endpoints (`RATE_LIMIT_*`)
- **Continuous ingestion** — toggle and configure polling intervals for Open Library and Google Books (`CONTINUOUS_*`)
- **Data cleanup** — minimum quality score thresholds for automatic pruning (`CLEANUP_*`)
- **Search reindex** — cron schedule for Elasticsearch index rebuilds (`ES_REINDEX_CRON`)

---

## Architecture

The gateway is the only publicly exposed service. All internal services communicate over gRPC.

| Service                  | Role                                                  |
| ------------------------ | ----------------------------------------------------- |
| `gateway-service`        | Public REST API, routes requests to internal services |
| `auth-service`           | Registration, login, JWT issuance and validation      |
| `books-service`          | Book, author, and series catalog; search              |
| `user-data-service`      | Bookshelves, ratings, favourites, comments            |
| `ingestion-service`      | Data import from Open Library and Google Books        |
| `recommendation-service` | Generic and personalized book/author recommendations  |
| `rq-worker`              | Background job worker for the ingestion queue         |

Infrastructure: PostgreSQL 15, Redis 7, Elasticsearch 8.

## Tech Stack

|                        |                            |
| ---------------------- | -------------------------- |
| Gateway                | FastAPI + uvicorn          |
| Internal communication | gRPC + Protocol Buffers    |
| Database               | PostgreSQL 15              |
| Search                 | Elasticsearch 8            |
| Cache / Background     | Redis 7 + RQ + APScheduler |
| Auth                   | JWT (HS256)                |
| Migrations             | Alembic                    |

---

## License

Distributed under the MIT License. Copyright © 2025 Jakub Tutka.
